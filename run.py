"""Ilovani bitta buyruq bilan ishga tushiradi.

    python run.py

Nima bo'ladi:
  1. web server ko'tariladi (Mini App fayllari + API);
  2. kerak bo'lsa HTTPS tunnel ochiladi va manzil topiladi;
  3. bot shu manzil bilan ishga tushadi va chap tarafdagi doimiy
     "Open" tugmasini o'rnatadi.

To'xtatish: Ctrl+C
"""

from __future__ import annotations

import asyncio
import logging

import uvicorn
from telegram import Update

from app import config, tunnel
from app.bot import build_application, configure_bot_ui

logging.basicConfig(
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Application").setLevel(logging.WARNING)
log = logging.getLogger("run")

BANNER = """
╭──────────────────────────────────────────────────────────╮
│  {name}
│  Mini App:  {url}
│  Lokal:     http://127.0.0.1:{port}
╰──────────────────────────────────────────────────────────╯
"""


async def main() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit(".env faylida BOT_TOKEN yo'q.")

    # --- 1) Web server ---
    server = uvicorn.Server(
        uvicorn.Config(
            "app.api:app",
            host=config.HOST,
            port=config.PORT,
            log_level="warning",
            access_log=False,
        )
    )
    server_task = asyncio.create_task(server.serve())

    # Server ko'tarilishini kutamiz — tunnel bo'sh portga ulanmasin.
    while not server.started and not server_task.done():
        await asyncio.sleep(0.1)
    if server_task.done():
        await server_task  # xatoni ko'rsatish uchun
        return

    # --- 2) HTTPS manzil ---
    tunnel_proc = None
    if config.WEBAPP_URL:
        log.info("WEBAPP_URL .env dan olindi: %s", config.WEBAPP_URL)
    else:
        try:
            tunnel_proc, url = await tunnel.open_tunnel(config.PORT)
            if url:
                config.WEBAPP_URL = url
                log.info("Tunnel ochildi: %s", url)
        except tunnel.TunnelError as e:
            log.error("Tunnel ochilmadi: %s", e)
            log.error("Bot baribir ishlaydi, lekin ilova tugmasi ko'rinmaydi.")

    print(
        BANNER.format(
            name=config.APP_NAME,
            url=config.WEBAPP_URL or "sozlanmagan (.env → WEBAPP_URL)",
            port=config.PORT,
        )
    )

    # --- 3) Bot ---
    application = build_application()
    async with application:
        # Menyu tugmasini shu yerdan o'rnatamiz: post_init ni python-telegram-bot
        # faqat run_polling() ichida chaqiradi, biz esa siklni qo'lda boshqaramiz.
        await configure_bot_ui(application.bot)
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        log.info("Tayyor. Telegram'da botga /start yozing.")
        try:
            await server_task
        finally:
            await application.updater.stop()
            await application.stop()
            if tunnel_proc and tunnel_proc.returncode is None:
                tunnel_proc.terminate()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("To'xtatildi.")
