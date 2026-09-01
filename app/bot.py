"""Telegram bot — ilovaga kirish nuqtasi.

Bu botda test o'tmaydi. Uning vazifasi ikkita:
  1. /start bosilganda ilovani ochadigan tugma berish;
  2. yozish maydonining chap tarafida DOIMIY "Open" tugmasini o'rnatish.

Test butunlay Mini App ichida o'tadi.
"""

from __future__ import annotations

import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonCommands,
    MenuButtonWebApp,
    Update,
    WebAppInfo,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes

from app import config, engine

log = logging.getLogger(__name__)


def _open_keyboard() -> InlineKeyboardMarkup | None:
    """Ilovani ochadigan inline tugma. WEBAPP_URL bo'lmasa — tugma yo'q."""
    if not config.WEBAPP_URL:
        return None
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                text="🎯 Darajangizni aniqlang",
                web_app=WebAppInfo(url=config.WEBAPP_URL),
            )
        ]]
    )


WELCOME = (
    "Assalomu alaykum{name}!\n\n"
    "Bu — ingliz tili darajangizni aniqlaydigan ilova. Test Beginner "
    "darajadan boshlanadi va javoblaringizga qarab moslashib boradi: har 5 savoldan "
    "keyin daraja bir pog'ona ko'tariladi yoki pasayadi.\n\n"
    "Odatda 10–20 ta savol yetarli. Ilovani ochish uchun quyidagi tugmani "
    "yoki pastdagi «{menu}» tugmasini bosing."
)

NO_URL = (
    "⚠️ Ilova manzili hali sozlanmagan.\n\n"
    ".env faylida WEBAPP_URL ni to'ldiring yoki TUNNEL=cloudflared bilan "
    "run.py ni ishga tushiring — u manzilni o'zi topadi."
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = _open_keyboard()
    if keyboard is None:
        await update.message.reply_text(NO_URL)
        return

    first = (update.effective_user.first_name or "").strip()
    await update.message.reply_text(
        WELCOME.format(
            name=f", {first}" if first else "",
            menu=config.MENU_BUTTON_TEXT,
        ),
        reply_markup=keyboard,
    )


async def cmd_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Oxirgi natijani chatga qayta chiqaradi."""
    result = engine.last_result(update.effective_user.id)
    if result is None:
        await update.message.reply_text(
            "Sizda hali tugallangan test yo'q. /start bosib ilovani oching.",
            reply_markup=_open_keyboard(),
        )
        return

    detail = "\n".join(
        f"  {b['level_name']} — {b['correct']}/{b['total']} ({b['percent']}%)"
        for b in result["blocks"]
    )
    await update.message.reply_text(
        f"🎯 <b>{result['level_name']}</b>\n\n"
        f"{result['summary']}\n\n"
        f"<b>Bloklar bo'yicha:</b>\n{detail}",
        parse_mode=ParseMode.HTML,
    )


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Telegram ID ni ko'rsatadi — admin ro'yxatini to'ldirish uchun kerak."""
    uid = update.effective_user.id
    is_admin = uid in config.ADMIN_IDS
    await update.message.reply_text(
        f"Sizning Telegram ID: {uid}\n\n"
        + (
            "✅ Siz administratorsiz — ilovada «Natijalar» bo'limi ko'rinadi."
            if is_admin
            else "Administrator qilish uchun shu raqamni ADMIN_IDS ga qo'shing."
        )
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📘 Yordam\n\n"
        "/start — ilovani ochish\n"
        "/natija — oxirgi test natijangiz\n"
        "/help — shu xabar\n\n"
        "Test yarmida ilovani yopib qo'ysangiz ham holat saqlanadi — "
        "qayta ochsangiz, o'sha savoldan davom etadi.",
        reply_markup=_open_keyboard(),
    )


async def configure_bot_ui(bot) -> None:
    """Buyruqlar ro'yxati va chap tarafdagi doimiy menyu tugmasini o'rnatadi.

    chat_id berilmagani uchun bu BARCHA foydalanuvchilar uchun standart
    tugma bo'ladi — /start bosmagan odam ham ilovani ocha oladi.

    DIQQAT: buni `Application.post_init` ga bog'lab bo'lmaydi — python-telegram-bot
    post_init ni FAQAT `run_polling()` / `run_webhook()` ichida chaqiradi.
    run.py hayot siklini qo'lda boshqargani uchun bu funksiya u yerdan
    to'g'ridan-to'g'ri chaqiriladi.
    """
    await bot.set_my_commands(
        [
            ("start", "Ilovani ochish"),
            ("natija", "Oxirgi natijangiz"),
            ("id", "Telegram ID ingiz"),
            ("help", "Yordam"),
        ]
    )

    if not config.WEBAPP_URL:
        # Manzil yo'q — eski WebApp tugmasi qolib ketmasin, buyruqlarga qaytaramiz.
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        log.warning("WEBAPP_URL bo'sh — menyu tugmasi o'rnatilmadi")
        return

    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text=config.MENU_BUTTON_TEXT,
                web_app=WebAppInfo(url=config.WEBAPP_URL),
            )
        )
        log.info(
            "Menyu tugmasi o'rnatildi: «%s» → %s",
            config.MENU_BUTTON_TEXT,
            config.WEBAPP_URL,
        )
    except TelegramError as e:
        # Telegram HTTPS bo'lmagan yoki noto'g'ri manzilni rad etadi.
        log.error("Menyu tugmasini o'rnatib bo'lmadi: %s", e)


def build_application() -> Application:
    if not config.BOT_TOKEN:
        raise SystemExit(".env faylida BOT_TOKEN yo'q.")

    application = Application.builder().token(config.BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("natija", cmd_result))
    application.add_handler(CommandHandler("id", cmd_id))
    application.add_handler(CommandHandler("help", cmd_help))
    return application
