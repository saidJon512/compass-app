"""Natijani Telegram chatga yuborish.

Nega bu kerak: Mini App ichida ko'rsatilgan natija ilova yopilgach yo'qoladi.
Chatga yuborilgan xabar esa foydalanuvchida qoladi va adminga ham boradi.
"""

from __future__ import annotations

import logging

import httpx

from app import config

log = logging.getLogger(__name__)


async def send_message(chat_id: int, text: str) -> None:
    if not config.BOT_TOKEN or not chat_id:
        return
    url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"chat_id": chat_id, "text": text})
            if resp.status_code != 200:
                log.warning("sendMessage %s: %s", resp.status_code, resp.text[:200])
    except httpx.HTTPError as e:
        log.warning("Botga xabar yuborilmadi (chat_id=%s): %s", chat_id, e)


def admin_report(result: dict) -> str:
    who = result.get("name") or "Noma'lum"
    if result.get("username"):
        who += f" (@{result['username']})"
    detail = ", ".join(
        f"{b['level_short']}: {b['correct']}/{b['total']}" for b in result["blocks"]
    )
    return (
        f"📊 Yangi natija\n{who}\nID: {result['tg_user_id']}\n"
        f"Daraja: {result['level_name']}\n"
        f"Bloklar: {detail}\nSabab: {result['reason']}"
    )


async def send_result(result: dict) -> None:
    """Natijani foydalanuvchiga, kerak bo'lsa adminga yuboradi."""
    text = f"🎯 Test natijasi: {result['level_name']}\n\n{result['summary']}"
    await send_message(result["tg_user_id"], text)

    if config.ADMIN_CHAT_ID and config.ADMIN_CHAT_ID != result["tg_user_id"]:
        await send_message(config.ADMIN_CHAT_ID, admin_report(result))
