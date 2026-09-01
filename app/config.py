"""Sozlamalar — hammasi .env dan o'qiladi."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# --- Telegram ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Mini App manzili. Bo'sh bo'lsa va TUNNEL yoqilgan bo'lsa — run.py uni
# tunnel ochilgandan keyin avtomatik to'ldiradi.
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip().rstrip("/")

# Render o'z manzilini shu o'zgaruvchida beradi — qo'lda yozish shart emas.
if not WEBAPP_URL:
    WEBAPP_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")

MENU_BUTTON_TEXT = os.getenv("MENU_BUTTON_TEXT", "Open").strip()
APP_NAME = os.getenv("APP_NAME", "COMPASS Daraja Testi").strip()

_admin = os.getenv("ADMIN_CHAT_ID", "").strip()
ADMIN_CHAT_ID: int | None = int(_admin) if _admin.lstrip("-").isdigit() else None


def _ids(raw: str) -> set[int]:
    return {int(p) for p in raw.replace(" ", "").split(",") if p.lstrip("-").isdigit()}


# Admin panelini ko'ra oladigan Telegram ID lar.
# ADMIN_CHAT_ID ham avtomatik shu ro'yxatga qo'shiladi.
ADMIN_IDS: set[int] = _ids(os.getenv("ADMIN_IDS", ""))
if ADMIN_CHAT_ID:
    ADMIN_IDS.add(ADMIN_CHAT_ID)

# --- Claude API (ixtiyoriy) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5").strip()
AI_ENABLED = bool(ANTHROPIC_API_KEY)

# --- Server ---
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Botni qanday ishlatish:
#   false (lokal) — polling: bot Telegramdan yangiliklarni o'zi so'rab turadi;
#                   buning uchun jarayon TO'XTAMASDAN ishlashi kerak.
#   true (server) — webhook: Telegram yangilikni serverga o'zi yuboradi.
#                   Uxlab qolgan bepul server ham shu so'rov bilan uyg'onadi.
USE_WEBHOOK = _bool("USE_WEBHOOK", False)

# Webhook manzilini faqat Telegram bilishi kerak. Bo'sh bo'lsa — tokendan
# barqaror maxfiy satr hosil qilamiz (har ishga tushirishda bir xil chiqadi).
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
if not WEBHOOK_SECRET and BOT_TOKEN:
    import hashlib

    WEBHOOK_SECRET = hashlib.sha256(f"webhook:{BOT_TOKEN}".encode()).hexdigest()[:48]

# Postgres ulanish satri (masalan Neon). Bo'sh bo'lsa — SQLite ishlatiladi.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# Telegram Mini App FAQAT HTTPS orqali ochiladi. Lokal mashinada HTTPS yo'q,
# shuning uchun tunnel kerak: "cloudflared" (hisob kerak emas) yoki "ngrok".
# "none" = tunnel ochilmaydi, WEBAPP_URL ni o'zingiz yozasiz.
TUNNEL = os.getenv("TUNNEL", "cloudflared").strip().lower()

# DIQQAT: faqat lokal sinash uchun. Yoqilsa initData imzosi tekshirilmaydi —
# istalgan odam o'zini boshqa foydalanuvchi deb ko'rsatishi mumkin.
ALLOW_INSECURE_DEV = _bool("ALLOW_INSECURE_DEV", False)

# --- Yo'llar ---
DB_PATH = BASE_DIR / os.getenv("DB_PATH", "data/sessions.db")
QUESTIONS_PATH = BASE_DIR / "data" / "questions.json"
WEBAPP_DIR = BASE_DIR / "webapp"
TOOLS_DIR = BASE_DIR / ".tools"
