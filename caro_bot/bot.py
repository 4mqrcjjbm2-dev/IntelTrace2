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
import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update  # noqa: E402
from telegram.constants import ChatAction  # noqa: E402
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters  # noqa: E402

from backup import OllamaBackup, reply_with_backup  # noqa: E402
from brain import Brain  # noqa: E402
from killswitch import Freqtrade, KillSwitch  # noqa: E402
from promo import draft_post, parse_hhmm  # noqa: E402
from storage import Storage  # noqa: E402
from threecommas import ThreeCommas, format_bots, format_deals  # noqa: E402
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
TELEGRAM_ON = os.getenv("CARO_DISABLE_TELEGRAM") != "1"  # 1 = tests locaux, sans Telegram
TOKEN = env("TELEGRAM_BOT_TOKEN", required=TELEGRAM_ON)
env("ANTHROPIC_API_KEY", required=True)
OWNER_ID = int(env("TELEGRAM_OWNER_ID", "0") or 0)
TZ = ZoneInfo(env("CARO_TZ", "America/Toronto"))
store = Storage(env("CARO_DB", str(HERE / "caro.db")))
_3c_key, _3c_secret = env("THREECOMMAS_API_KEY"), env("THREECOMMAS_API_SECRET")
threecommas = ThreeCommas(_3c_key, _3c_secret) if _3c_key and _3c_secret else None
_ollama_key = env("OLLAMA_API_KEY")
backup = OllamaBackup(_ollama_key, env("OLLAMA_MODEL", "gpt-oss:120b")) if _ollama_key else None

# Interrupteur d'urgence : une clé 3Commas SÉPARÉE, avec la permission d'écriture sur les bots, et/ou Freqtrade.
_k_key, _k_secret = env("THREECOMMAS_KILL_API_KEY"), env("THREECOMMAS_KILL_API_SECRET")
_ft_url = env("FREQTRADE_URL")
killswitch = KillSwitch(
    store,
    threecommas=ThreeCommas(_k_key, _k_secret) if _k_key and _k_secret else None,
    freqtrade=Freqtrade(_ft_url, env("FREQTRADE_USER", ""), env("FREQTRADE_PASSWORD", "")) if _ft_url else None,
)

# Publication quotidienne d'ECHO sur la chaîne Telegram du projet
PROMO_CHANNEL = env("PROMO_CHANNEL")  # ex. @macrypto_charlevoix ou -100123456789
PROMO_BRIEF_FILE = env("PROMO_BRIEF_FILE", str(HERE / "promo_brief.md"))
PROMO_TIME = env("PROMO_TIME", "09:00")


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
        "/3c : tes trades 3Commas ouverts (/3c bots pour tes bots)\n"
        "/stop : interrupteur d'urgence, arrête tous les bots\n"
        "/reprendre : redémarre les bots arrêtés par /stop\n"
        "/etat : état de l'interrupteur et de la publication du jour\n"
        "/post : ECHO prépare la publication du jour maintenant\n"
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
async def trois_c(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not threecommas:
        await update.message.reply_text("3Commas n'est pas branché. Ajoute THREECOMMAS_API_KEY et THREECOMMAS_API_SECRET au .env.")
        return
    try:
        if context.args and context.args[0].lower() == "bots":
            text = format_bots(await threecommas.bots())
        else:
            text = format_deals(await threecommas.active_deals())
    except PermissionError as e:
        text = str(e)
    except Exception as e:
        log.warning("3Commas : %s", e)
        text = "3Commas répond pas pour l'instant. Réessaie dans une minute."
    await send_long(update, text)


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
        text = await reply_with_backup(brain, backup, update.effective_chat.id, update.message.text)
    except httpx.HTTPError as e:
        log.error("Secours Ollama en erreur : %s", e)
        text = "Claude et mon cerveau de secours sont indisponibles. Réessaie dans quelques minutes."
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


# ---------- Interrupteur d'urgence ----------

def confirm_kb(action):
    if action == "reprendre":
        return InlineKeyboardMarkup([[InlineKeyboardButton("Oui, redémarrer", callback_data="kill:resume"), InlineKeyboardButton("Annuler", callback_data="kill:cancel")]])
    return InlineKeyboardMarkup([[InlineKeyboardButton("Oui, tout arrêter", callback_data="kill:stop"), InlineKeyboardButton("Annuler", callback_data="kill:cancel")]])


async def ask_kill(bot, chat_id, action):
    if not killswitch.configured:
        await bot.send_message(chat_id, "L'interrupteur n'est pas branché : ajoute THREECOMMAS_KILL_API_KEY/SECRET ou FREQTRADE_URL (voir le README).")
        return
    text = ("Confirmer le REDÉMARRAGE des bots arrêtés par l'interrupteur?" if action == "reprendre"
            else "Confirmer l'ARRÊT de tous tes bots? 3Commas n'ouvrira plus de trades et Freqtrade s'arrête. Les trades déjà ouverts restent ouverts.")
    await bot.send_message(chat_id, text, reply_markup=confirm_kb(action))


@owner_only
async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ask_kill(context.bot, update.effective_chat.id, "arreter")


@owner_only
async def resume_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ask_kill(context.bot, update.effective_chat.id, "reprendre")


@owner_only
async def etat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = [
        "Interrupteur : " + ("ACTIVÉ, bots arrêtés" if killswitch.active else "désactivé") + ("" if killswitch.configured else " (pas branché)"),
        "Publication du jour : " + (f"chaque jour à {PROMO_TIME} vers {PROMO_CHANNEL}" if PROMO_CHANNEL else "pas configurée (PROMO_CHANNEL)"),
    ]
    await update.message.reply_text("\n".join(lines))


# ---------- Publication quotidienne (ECHO) ----------

def promo_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Publier", callback_data="promo:ok"), InlineKeyboardButton("Refaire", callback_data="promo:redo"), InlineKeyboardButton("Annuler", callback_data="promo:no")]])


async def make_draft(app, chat_id):
    brief = (env("PROMO_BRIEF") or "").strip()
    if not brief:
        try:
            brief = Path(PROMO_BRIEF_FILE).read_text(encoding="utf-8").strip()
        except OSError:
            await app.bot.send_message(chat_id, f"Je trouve pas la fiche du projet ({PROMO_BRIEF_FILE}). Copie promo_brief.example.md en promo_brief.md et remplis-la.")
            return
    brain: Brain = app.bot_data["brain"]
    try:
        text = await draft_post(brain.client, brain.model, brief, store.recent_posts(), datetime.now(TZ).strftime("%Y-%m-%d"))
    except Exception as e:
        log.error("Brouillon ECHO : %s", e)
        await app.bot.send_message(chat_id, f"ECHO n'a pas pu écrire la publication ({e}).")
        return
    app.bot_data["promo_draft"] = text
    await app.bot.send_message(chat_id, "Brouillon d'ECHO pour " + str(PROMO_CHANNEL) + " :\n\n" + text, reply_markup=promo_kb())


async def promo_job(context: ContextTypes.DEFAULT_TYPE):
    if OWNER_ID and PROMO_CHANNEL:
        await make_draft(context.application, OWNER_ID)


@owner_only
async def post_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not PROMO_CHANNEL:
        await update.message.reply_text("Ajoute PROMO_CHANNEL au .env (ex. @tachaine) et fais de CARO un admin de la chaîne.")
        return
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    await make_draft(context.application, update.effective_chat.id)


# ---------- Boutons ----------

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.from_user or q.from_user.id != OWNER_ID:
        if q:
            await q.answer()
        return
    await q.answer()
    data = q.data or ""
    if data == "kill:stop":
        await q.edit_message_text("Arrêt en cours…")
        await q.edit_message_text("Interrupteur d'urgence ACTIVÉ.\n" + "\n".join(await killswitch.stop()))
    elif data == "kill:resume":
        await q.edit_message_text("Redémarrage en cours…")
        await q.edit_message_text("Interrupteur désactivé.\n" + "\n".join(await killswitch.resume()))
    elif data == "kill:cancel":
        await q.edit_message_text("Annulé. Rien n'a changé.")
    elif data == "promo:ok":
        text = context.application.bot_data.pop("promo_draft", None)
        if not text:
            await q.edit_message_text("Ce brouillon n'est plus disponible. Tape /post pour en refaire un.")
            return
        try:
            await context.bot.send_message(PROMO_CHANNEL, text)
            store.add_post(text)
            await q.edit_message_text("Publié sur " + str(PROMO_CHANNEL) + " :\n\n" + text)
        except Exception as e:
            context.application.bot_data["promo_draft"] = text
            await q.edit_message_text(f"Publication impossible ({e}). CARO est-il admin de la chaîne?\n\n" + text, reply_markup=promo_kb())
    elif data == "promo:redo":
        await q.edit_message_text("ECHO réécrit…")
        await make_draft(context.application, q.message.chat_id)
    elif data == "promo:no":
        context.application.bot_data.pop("promo_draft", None)
        await q.edit_message_text("Publication annulée pour aujourd'hui.")


# ---------- Démarrage ----------

async def post_init(app: Application):
    pending = store.pending_reminders()
    for r in pending:
        schedule(app, r)
    if PROMO_CHANNEL:
        app.job_queue.run_daily(promo_job, time=parse_hhmm(PROMO_TIME, TZ), name="promo")
    log.info("CARO prêt. %d rappel(s) rechargé(s). Secours Ollama : %s. Interrupteur : %s. Publication : %s.", len(pending),
             "oui" if backup else "non", "branché" if killswitch.configured else "non", PROMO_TIME if PROMO_CHANNEL else "non")
    if not OWNER_ID:
        log.warning("TELEGRAM_OWNER_ID est vide : envoie /start au bot pour connaître ton identifiant.")


def build_application():
    """Construit l'application Telegram (sans la lancer). Utilisé par main.py et par main() ci-dessous."""
    app = Application.builder().token(TOKEN).post_init(post_init).build()

    def on_reminder(chat_id, due_utc, message):
        rid = store.add_reminder(chat_id, due_utc, message)
        schedule(app, {"id": rid, "chat_id": chat_id, "due_utc": due_utc, "message": message})
        return rid

    app.bot_data["brain"] = make_brain(
        on_reminder=on_reminder,
        on_kill_request=(lambda chat_id, action: ask_kill(app.bot, chat_id, action)) if killswitch.configured else None,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("prix", prix))
    app.add_handler(CommandHandler("oublie", oublie))
    app.add_handler(CommandHandler("rappels", rappels))
    app.add_handler(CommandHandler("annule", annule))
    app.add_handler(CommandHandler("3c", trois_c))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("reprendre", resume_cmd))
    app.add_handler(CommandHandler("etat", etat))
    app.add_handler(CommandHandler("post", post_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    return app


def make_brain(on_reminder=None, on_kill_request=None):
    return Brain(
        client=anthropic.AsyncAnthropic(),
        store=store,
        tz=TZ,
        model=env("CARO_MODEL", "claude-opus-5-5"),
        effort=env("CARO_EFFORT", "low"),
        on_reminder=on_reminder,
        threecommas=threecommas,
        on_kill_request=on_kill_request,
    )


def main():
    """Bot Telegram seul (sans l'application web). Pour tout lancer : python main.py"""
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
