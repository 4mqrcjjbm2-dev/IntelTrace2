"""CARO sur Telegram.

Lancer :  python bot.py   (depuis le dossier caro_bot, avec un fichier .env rempli)
"""

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import anthropic  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from telegram import Update  # noqa: E402
from telegram.constants import ChatAction  # noqa: E402
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters  # noqa: E402

from brain import Brain  # noqa: E402
from storage import Storage  # noqa: E402
from tools import fetch_prices, format_price  # noqa: E402

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s : %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # sinon le token Telegram apparaît dans les URL des journaux
log = logging.getLogger("caro")

TELEGRAM_LIMIT = 4000


def env(name, default=None, required=False):
    value = os.getenv(name, default)
    if required and not value:
        sys.exit(f"Il manque {name} dans le fichier .env (voir .env.example).")
    return value


load_dotenv(HERE / ".env")
TOKEN = env("TELEGRAM_BOT_TOKEN", required=True)
env("ANTHROPIC_API_KEY", required=True)
OWNER_ID = int(env("TELEGRAM_OWNER_ID", "0") or 0)
TZ = ZoneInfo(env("CARO_TZ", "America/Toronto"))
store = Storage(env("CARO_DB", str(HERE / "caro.db")))


# ---------- Accès ----------

def owner_only(handler):
    """Seul le propriétaire parle à CARO. Les autres comptes sont ignorés."""

    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not OWNER_ID or not user or user.id != OWNER_ID:
            if user:
                log.info("Message ignoré du compte %s", user.id)
            return
        return await handler(update, context)

    return wrapped


async def send_long(update: Update, text):
    for i in range(0, len(text), TELEGRAM_LIMIT):
        await update.effective_message.reply_text(text[i : i + TELEGRAM_LIMIT])


# ---------- Rappels ----------

def fmt_local(dt_utc):
    return dt_utc.astimezone(TZ).strftime("%Y-%m-%d à %H:%M")


async def fire_reminder(context: ContextTypes.DEFAULT_TYPE):
    r = context.job.data
    await context.bot.send_message(r["chat_id"], f"⏰ Rappel : {r['message']}")
    store.mark_sent(r["id"])


def schedule(app, reminder):
    # Un rappel manqué pendant que le bot était éteint part tout de suite.
    when = max(reminder["due_utc"], datetime.now(timezone.utc) + timedelta(seconds=2))
    app.job_queue.run_once(fire_reminder, when=when, data=reminder, name=f"rappel-{reminder['id']}")


# ---------- Commandes ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not OWNER_ID:
        await update.message.reply_text(
            f"Salut! Ton identifiant Telegram est {user.id}.\n"
            f"Mets TELEGRAM_OWNER_ID={user.id} dans le fichier .env, puis redémarre le bot."
        )
        return
    if user.id != OWNER_ID:
        return
    await update.message.reply_text(
        "CARO en ligne. Parle-moi normalement.\n\n"
        "/prix btc eth : prix crypto\n"
        "/rappels : tes rappels à venir\n"
        "/annule 3 : supprime le rappel no 3\n"
        "/oublie : efface ma mémoire de notre conversation"
    )


@owner_only
async def prix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbols = context.args or ["btc", "eth"]
    try:
        prices = await fetch_prices(symbols)
    except Exception as e:
        log.warning("CoinGecko : %s", e)
        await update.message.reply_text("CoinGecko répond pas pour l'instant. Réessaie dans une minute.")
        return
    if not prices:
        await update.message.reply_text("Je trouve pas ces cryptos. Essaie un symbole comme btc, eth ou sol.")
        return
    lines = [format_price(s, p) for s, p in prices.items()]
    lines.append(f"Source : CoinGecko, {datetime.now(TZ):%H:%M}")
    await update.message.reply_text("\n".join(lines))


@owner_only
async def oublie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    store.clear_history(update.effective_chat.id)
    await update.message.reply_text("C'est oublié. On repart à zéro.")


@owner_only
async def rappels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = store.pending_reminders(update.effective_chat.id)
    if not items:
        await update.message.reply_text("Aucun rappel à venir.")
        return
    lines = [f"{r['id']}. {fmt_local(r['due_utc'])} : {r['message']}" for r in items]
    await update.message.reply_text("Tes rappels :\n" + "\n".join(lines))


@owner_only
async def annule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Écris /annule suivi du numéro. Tape /rappels pour voir les numéros.")
        return
    rid = int(context.args[0])
    if store.delete_reminder(update.effective_chat.id, rid):
        for job in context.job_queue.get_jobs_by_name(f"rappel-{rid}"):
            job.schedule_removal()
        await update.message.reply_text(f"Rappel {rid} annulé.")
    else:
        await update.message.reply_text(f"Je trouve pas de rappel no {rid} à venir.")


@owner_only
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    brain: Brain = context.application.bot_data["brain"]
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    try:
        text = await brain.reply(update.effective_chat.id, update.message.text)
    except anthropic.AuthenticationError:
        text = "Ma clé API Anthropic est refusée. Vérifie ANTHROPIC_API_KEY dans le .env."
    except anthropic.RateLimitError:
        text = "Trop de demandes en même temps. Réessaie dans une minute."
    except anthropic.APIConnectionError:
        text = "Je rejoins pas les serveurs de Claude. Réessaie dans un instant."
    except anthropic.APIStatusError as e:
        log.error("Erreur API %s : %s", e.status_code, e.message)
        text = f"Erreur de l'API Claude ({e.status_code}). Les détails sont dans le journal du bot."
    await send_long(update, text)


# ---------- Démarrage ----------

async def post_init(app: Application):
    pending = store.pending_reminders()
    for r in pending:
        schedule(app, r)
    log.info("CARO prêt. %d rappel(s) rechargé(s).", len(pending))
    if not OWNER_ID:
        log.warning("TELEGRAM_OWNER_ID est vide : envoie /start au bot pour connaître ton identifiant.")


def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()

    def on_reminder(chat_id, due_utc, message):
        rid = store.add_reminder(chat_id, due_utc, message)
        schedule(app, {"id": rid, "chat_id": chat_id, "due_utc": due_utc, "message": message})
        return rid

    app.bot_data["brain"] = Brain(
        client=anthropic.AsyncAnthropic(),
        store=store,
        tz=TZ,
        model=env("CARO_MODEL", "claude-opus-5-5"),
        effort=env("CARO_EFFORT", "low"),
        on_reminder=on_reminder,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("prix", prix))
    app.add_handler(CommandHandler("oublie", oublie))
    app.add_handler(CommandHandler("rappels", rappels))
    app.add_handler(CommandHandler("annule", annule))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
