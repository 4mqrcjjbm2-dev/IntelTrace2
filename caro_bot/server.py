"""Serveur web de Black Box : sert l'application et son API, dans le même programme que le bot Telegram."""

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from aiohttp import web

from threecommas import format_bots

log = logging.getLogger("caro.web")
WEB = Path(__file__).resolve().parent / "web"
SESSION_DAYS = 30
SYMBOLS = {"BTCUSD", "ETHUSD", "SOLUSD"}
TIMEFRAMES = {"15m", "1hr", "6hr", "1day"}
GEMINI_CANDLES = "https://api.gemini.com/v2/candles/{sym}/{tf}"


@dataclass
class Ctx:
    store: object
    killswitch: object
    password: str
    secret: bytes
    brain: object = None
    threecommas: object = None  # client en lecture
    reply: object = None  # async (brain, chat_id, text) -> str ; par défaut brain.reply
    notify: object = None  # async (text) -> None ; avis dans Telegram
    app_chat_id: int = 1
    status: dict = field(default_factory=dict)
    http: object = None  # client httpx injecté pour les tests
    attempts: dict = field(default_factory=dict)
    cache: dict = field(default_factory=dict)


# ---------- Session ----------

def make_token(secret, now=None):
    exp = int((now or time.time()) + SESSION_DAYS * 86400)
    sig = hmac.new(secret, str(exp).encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def valid_token(secret, token, now=None):
    try:
        exp, sig = token.split(".", 1)
        good = hmac.new(secret, exp.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, good) and int(exp) > (now or time.time())
    except (AttributeError, ValueError):
        return False


def logged_in(request):
    return valid_token(request.app["ctx"].secret, request.cookies.get("bb_session", ""))


def err(status, message):
    return web.json_response({"erreur": message}, status=status)


PUBLIC = {"/api/sante", "/api/etat", "/api/login"}


@web.middleware
async def guard(request, handler):
    path = request.path
    if path.startswith("/api/"):
        if request.method == "POST" and request.headers.get("X-Requested-With") != "blackbox":
            return err(403, "Requête refusée.")
        if path not in PUBLIC and not logged_in(request):
            return err(401, "Connecte-toi d'abord.")
    resp = await handler(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["X-Frame-Options"] = "DENY"
    if path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------- Routes publiques ----------

async def sante(request):
    return web.json_response({"ok": True})


async def etat(request):
    ctx = request.app["ctx"]
    data = {"serveur": True, "connecte": logged_in(request)}
    if data["connecte"]:
        data.update({
            "kill_actif": ctx.killswitch.active,
            "interrupteur_branche": ctx.killswitch.configured,
            "threecommas": bool(ctx.threecommas),
            "caro": bool(ctx.brain),
        })
        data.update(ctx.status)
    return web.json_response(data)


async def login(request):
    ctx = request.app["ctx"]
    ip = request.headers.get("X-Forwarded-For", request.remote or "?").split(",")[0].strip()
    now = time.time()
    tries = [t for t in ctx.attempts.get(ip, []) if now - t < 600]
    if len(tries) >= 10:
        return err(429, "Trop d'essais. Attends 10 minutes.")
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        body = {}
    if not ctx.password or not hmac.compare_digest(str(body.get("motdepasse", "")).encode(), ctx.password.encode()):
        tries.append(now)
        ctx.attempts[ip] = tries
        return err(401, "Mot de passe incorrect.")
    ctx.attempts.pop(ip, None)
    resp = web.json_response({"ok": True})
    secure = request.secure or request.headers.get("X-Forwarded-Proto") == "https"
    resp.set_cookie("bb_session", make_token(ctx.secret), max_age=SESSION_DAYS * 86400, httponly=True, secure=secure, samesite="Strict", path="/")
    return resp


async def logout(request):
    resp = web.json_response({"ok": True})
    resp.del_cookie("bb_session", path="/")
    return resp


# ---------- Interrupteur d'urgence ----------

async def _kill_action(request, stop):
    ctx = request.app["ctx"]
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        body = {}
    if body.get("confirme") is not True:
        return err(400, "Confirmation requise.")
    if not ctx.killswitch.configured:
        return err(400, "L'interrupteur n'est pas branché : ajoute la clé 3Commas d'écriture ou Freqtrade dans Railway.")
    lines = await (ctx.killswitch.stop() if stop else ctx.killswitch.resume())
    title = "Interrupteur d'urgence ACTIVÉ depuis l'application." if stop else "Interrupteur désactivé depuis l'application."
    if ctx.notify:
        try:
            await ctx.notify(title + "\n" + "\n".join(lines))
        except Exception as e:
            log.warning("Avis Telegram impossible : %s", e)
    return web.json_response({"kill_actif": ctx.killswitch.active, "lignes": lines})


async def kill(request):
    return await _kill_action(request, True)


async def resume(request):
    return await _kill_action(request, False)


# ---------- Bots, bougies, trades ----------

async def bots(request):
    ctx = request.app["ctx"]
    if not ctx.threecommas:
        return web.json_response({"bots": [], "raison": "3Commas n'est pas branché (clé en lecture dans Railway)."})
    try:
        raw = await ctx.threecommas.bots()
        deals = await ctx.threecommas.active_deals()
    except Exception as e:
        log.warning("3Commas : %s", e)
        return err(502, "3Commas ne répond pas pour l'instant.")
    out = [{
        "id": b.get("id"), "nom": b.get("name", "?"), "actif": bool(b.get("is_enabled")),
        "paires": b.get("pairs") or [], "trades_ouverts": b.get("active_deals_count", 0),
        "profit_usd": b.get("finished_deals_profit_usd"),
    } for b in raw]
    trades = [{
        "paire": d.get("pair"), "bot": d.get("bot_name"), "pct": d.get("actual_profit_percentage"), "usd": d.get("actual_usd_profit"),
    } for d in deals]
    return web.json_response({"bots": out, "trades": trades, "resume": format_bots(raw)})


async def bougies(request):
    ctx = request.app["ctx"]
    sym = request.query.get("symbole", "SOLUSD").upper()
    tf = request.query.get("intervalle", "1hr")
    if sym not in SYMBOLS or tf not in TIMEFRAMES:
        return err(400, "Symbole ou intervalle inconnu.")
    key = (sym, tf)
    hit = ctx.cache.get(key)
    if hit and time.time() - hit[0] < 30:
        return web.json_response(hit[1])
    own = ctx.http is None
    client = ctx.http or httpx.AsyncClient(timeout=15)
    try:
        r = await client.get(GEMINI_CANDLES.format(sym=sym.lower(), tf=tf))
        r.raise_for_status()
        rows = r.json()
    except Exception as e:
        log.warning("Gemini : %s", e)
        return err(502, "Gemini ne répond pas pour l'instant.")
    finally:
        if own:
            await client.aclose()
    data = {"symbole": sym, "intervalle": tf, "bougies": rows[:600] if isinstance(rows, list) else []}
    ctx.cache[key] = (time.time(), data)
    return web.json_response(data)


def clean_trades(items):
    if not isinstance(items, list) or len(items) > 5000:
        raise ValueError("Liste de trades invalide (5000 au maximum).")
    out = []
    for i, x in enumerate(items):
        if not isinstance(x, dict) or not x.get("t"):
            raise ValueError(f"Trade {i + 1} : date manquante.")
        t = {"t": str(x["t"])[:40], "symbol": str(x.get("symbol", "?")).upper()[:10]}
        for k in ("r", "pnl_pct", "score"):
            if isinstance(x.get(k), (int, float)):
                t[k] = float(x[k])
        if "r" not in t and "pnl_pct" not in t:
            raise ValueError(f"Trade {i + 1} : il manque r ou pnl_pct.")
        out.append(t)
    return out


async def trades_get(request):
    return web.json_response({"trades": request.app["ctx"].store.list_trades()})


async def trades_post(request):
    try:
        body = await request.json()
        items = clean_trades(body.get("trades"))
    except (json.JSONDecodeError, ValueError, AttributeError) as e:
        return err(400, str(e) or "JSON invalide.")
    request.app["ctx"].store.replace_trades(items)
    return web.json_response({"ok": True, "nombre": len(items)})


# ---------- CARO ----------

async def caro(request):
    ctx = request.app["ctx"]
    if not ctx.brain:
        return err(503, "CARO n'est pas prêt.")
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        body = {}
    text = str(body.get("texte", "")).strip()[:1000]
    if not text:
        return err(400, "Message vide.")
    try:
        if ctx.reply:
            answer = await ctx.reply(ctx.brain, ctx.app_chat_id, text)
        else:
            answer = await ctx.brain.reply(ctx.app_chat_id, text)
    except Exception as e:
        log.error("CARO : %s", e)
        return err(502, "CARO n'a pas pu répondre. Vérifie la clé Anthropic dans Railway.")
    return web.json_response({"reponse": answer})


# ---------- Fichiers de l'application ----------

async def index(request):
    return web.FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})


def make_web_app(ctx):
    app = web.Application(middlewares=[guard], client_max_size=2 * 1024 * 1024)
    app["ctx"] = ctx
    app.router.add_get("/", index)
    app.router.add_get("/api/sante", sante)
    app.router.add_get("/api/etat", etat)
    app.router.add_post("/api/login", login)
    app.router.add_post("/api/logout", logout)
    app.router.add_post("/api/kill", kill)
    app.router.add_post("/api/reprendre", resume)
    app.router.add_get("/api/bots", bots)
    app.router.add_get("/api/bougies", bougies)
    app.router.add_get("/api/trades", trades_get)
    app.router.add_post("/api/trades", trades_post)
    app.router.add_post("/api/caro", caro)
    for name, ctype in (("manifest.webmanifest", "application/manifest+json"), ("icon-180.png", "image/png"), ("icon-512.png", "image/png")):
        app.router.add_get("/" + name, static_file(WEB / name, ctype))
    return app


def static_file(path, ctype):
    async def handler(request):
        return web.FileResponse(path, headers={"Content-Type": ctype})
    return handler
