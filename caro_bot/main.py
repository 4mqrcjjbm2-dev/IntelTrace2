"""Black Box : lance ensemble le bot Telegram CARO et l'application web.

Lancer :  python main.py   (Railway le fait tout seul)
"""

import asyncio
import hashlib
import logging
import os
import signal

from aiohttp import web
from telegram import Update

import bot as caro
from backup import reply_with_backup
from server import Ctx, make_web_app

log = logging.getLogger("caro.main")


async def run():
    tg = None
    if caro.TELEGRAM_ON:
        tg = caro.build_application()
        await tg.initialize()
        await caro.post_init(tg)
        await tg.start()
        await tg.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        brain = tg.bot_data["brain"]
    else:
        log.warning("Telegram désactivé (CARO_DISABLE_TELEGRAM=1) : application web seulement.")
        brain = caro.make_brain()

    async def notify(text):
        if tg and caro.OWNER_ID:
            await tg.bot.send_message(caro.OWNER_ID, text)

    password = caro.env("APP_PASSWORD", "")
    if not password:
        log.warning("APP_PASSWORD est vide : personne ne pourra se connecter à l'application.")
    secret = (caro.env("APP_SECRET") or "").encode() or hashlib.sha256(("blackbox:" + password + ":" + (caro.TOKEN or "")).encode()).digest()
    ctx = Ctx(
        store=caro.store,
        killswitch=caro.killswitch,
        password=password,
        secret=secret,
        brain=brain,
        threecommas=caro.threecommas,
        reply=lambda b, chat_id, text: reply_with_backup(b, caro.backup, chat_id, text),
        notify=notify,
        app_chat_id=caro.OWNER_ID or 1,  # même mémoire que Telegram, et les rappels arrivent dans Telegram
        status={"telegram": bool(tg), "promo": bool(caro.PROMO_CHANNEL), "secours": bool(caro.backup)},
    )
    runner = web.AppRunner(make_web_app(ctx))
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("Application Black Box en ligne sur le port %d.", port)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    await stop.wait()

    await runner.cleanup()
    if tg:
        await tg.updater.stop()
        await tg.stop()
        await tg.shutdown()


if __name__ == "__main__":
    asyncio.run(run())
