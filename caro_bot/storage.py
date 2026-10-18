"""Stockage SQLite de CARO : la mémoire de conversation et les rappels."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class Storage:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                due_utc TEXT NOT NULL,
                message TEXT NOT NULL,
                sent INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                t TEXT NOT NULL,
                symbol TEXT NOT NULL,
                r REAL,
                pnl_pct REAL,
                score REAL
            );
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                posted_at TEXT NOT NULL
            );
            """
        )
        self.db.commit()

    # ---------- Mémoire ----------

    def add_turn(self, chat_id, role, text):
        self.db.execute(
            "INSERT INTO history (chat_id, role, text, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, role, text, datetime.now(timezone.utc).isoformat()),
        )
        self.db.commit()

    def recent_history(self, chat_id, limit=20):
        """Les derniers échanges, au format messages de l'API, en commençant par un message de l'utilisateur."""
        rows = self.db.execute(
            "SELECT role, text FROM history WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        messages = [{"role": r["role"], "content": r["text"]} for r in reversed(rows)]
        while messages and messages[0]["role"] != "user":
            messages.pop(0)
        return messages

    def clear_history(self, chat_id):
        self.db.execute("DELETE FROM history WHERE chat_id = ?", (chat_id,))
        self.db.commit()

    # ---------- Rappels ----------

    def add_reminder(self, chat_id, due_utc, message):
        cur = self.db.execute(
            "INSERT INTO reminders (chat_id, due_utc, message) VALUES (?, ?, ?)",
            (chat_id, due_utc.isoformat(), message),
        )
        self.db.commit()
        return cur.lastrowid

    def pending_reminders(self, chat_id=None):
        sql = "SELECT id, chat_id, due_utc, message FROM reminders WHERE sent = 0"
        args = ()
        if chat_id is not None:
            sql += " AND chat_id = ?"
            args = (chat_id,)
        rows = self.db.execute(sql + " ORDER BY due_utc", args).fetchall()
        return [
            {
                "id": r["id"],
                "chat_id": r["chat_id"],
                "due_utc": datetime.fromisoformat(r["due_utc"]),
                "message": r["message"],
            }
            for r in rows
        ]

    def mark_sent(self, reminder_id):
        self.db.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))
        self.db.commit()

    # ---------- Valeurs simples (état de l'interrupteur, bots arrêtés) ----------

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set(self, key, value):
        self.db.execute(
            "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
        self.db.commit()

    # ---------- Publications ----------

    def add_post(self, text):
        self.db.execute(
            "INSERT INTO posts (text, posted_at) VALUES (?, ?)", (text, datetime.now(timezone.utc).isoformat())
        )
        self.db.commit()

    def recent_posts(self, limit=7):
        rows = self.db.execute("SELECT text FROM posts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [r["text"] for r in rows]

    # ---------- Trades (pour les Diagnostics de l'application) ----------

    def replace_trades(self, trades):
        self.db.execute("DELETE FROM trades")
        self.db.executemany(
            "INSERT INTO trades (t, symbol, r, pnl_pct, score) VALUES (?, ?, ?, ?, ?)",
            [(x["t"], x["symbol"], x.get("r"), x.get("pnl_pct"), x.get("score")) for x in trades],
        )
        self.db.commit()

    def list_trades(self):
        rows = self.db.execute("SELECT t, symbol, r, pnl_pct, score FROM trades ORDER BY t").fetchall()
        return [{k: r[k] for k in ("t", "symbol", "r", "pnl_pct", "score") if r[k] is not None} for r in rows]

    def delete_reminder(self, chat_id, reminder_id):
        cur = self.db.execute(
            "DELETE FROM reminders WHERE id = ? AND chat_id = ? AND sent = 0",
            (reminder_id, chat_id),
        )
        self.db.commit()
        return cur.rowcount > 0
