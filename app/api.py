"""Mini App backend: API + ilova fayllari.

Butun test mantig'i serverda turadi. Ilova (frontend) faqat ko'rsatadi —
to'g'ri javoblarni u hech qachon ko'rmaydi.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import config, engine, notify, questions, store
from app.tg_auth import InitDataError, resolve_user

log = logging.getLogger(__name__)


# Webhook rejimida bot shu jarayonning ichida yashaydi (alohida poller yo'q).
_tg_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _tg_app

    store.init_db()
    bank = questions.load_bank()
    log.info(
        "Savollar banki: %s ta savol. Baza: %s. AI: %s",
        sum(len(v) for v in bank.values()),
        store.backend_name(),
        "yoqilgan" if config.AI_ENABLED else "o'chiq (shablon xulosa)",
    )
    if config.ALLOW_INSECURE_DEV:
        log.warning("ALLOW_INSECURE_DEV=true — initData tekshirilmaydi. Faqat sinash uchun!")

    if config.USE_WEBHOOK and config.BOT_TOKEN:
        # Kech import: lokal (polling) rejimda bot moduli umuman kerak emas.
        from app.bot import build_application, configure_bot_ui

        _tg_app = build_application()
        await _tg_app.initialize()
        await _tg_app.start()
        await configure_bot_ui(_tg_app.bot)

        if config.WEBAPP_URL:
            await _tg_app.bot.set_webhook(
                url=f"{config.WEBAPP_URL}/tg/webhook",
                secret_token=config.WEBHOOK_SECRET,
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True,
            )
            log.info("Webhook o'rnatildi: %s/tg/webhook", config.WEBAPP_URL)
        else:
            log.error("USE_WEBHOOK=true, lekin WEBAPP_URL bo'sh — bot xabar ololmaydi")

    yield

    if _tg_app is not None:
        await _tg_app.stop()
        await _tg_app.shutdown()


app = FastAPI(title=config.APP_NAME, lifespan=lifespan)


# --------------------------------------------------------------------------
# So'rov modellari
# --------------------------------------------------------------------------

class InitIn(BaseModel):
    init_data: str = Field(default="", max_length=8000)


class AnswerIn(BaseModel):
    init_data: str = Field(default="", max_length=8000)
    session_id: str = Field(max_length=64)
    question_id: str = Field(max_length=64)
    answer: str = Field(default="", max_length=4000)


def _user(init_data: str) -> dict:
    try:
        return resolve_user(init_data)
    except InitDataError as e:
        raise HTTPException(status_code=401, detail=f"Telegram tekshiruvi o'tmadi: {e}")


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------

@app.post("/api/bootstrap")
async def bootstrap(payload: InitIn):
    """Ilova ochilganda birinchi chaqiriladigan endpoint.

    Foydalanuvchini aniqlaydi va uchta holatdan birini qaytaradi:
      active      — yarim qolgan test bor, o'sha savoldan davom etadi;
      last_result — oldin test topshirgan, natijasi ko'rsatiladi;
      ikkalasi ham bo'lmasa — ilova boshlash ekranini ko'rsatadi.
    """
    user = _user(payload.init_data)
    return {
        "name": (user.get("first_name") or "").strip(),
        "active": engine.resume(user),
        "last_result": engine.last_result(int(user["id"])),
        "is_admin": int(user["id"]) in config.ADMIN_IDS,
        "dev_mode": bool(user.get("_dev")),
    }


@app.post("/api/start")
async def start(payload: InitIn):
    """Yangi test boshlaydi (eski tugallanmagani bekor qilinadi)."""
    return engine.start_session(_user(payload.init_data))


@app.post("/api/answer")
async def answer(payload: AnswerIn):
    user = _user(payload.init_data)

    session = store.load_session(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Sessiya topilmadi")
    # Sessiya egasini tekshiramiz: birov boshqasining session_id sini
    # topib qo'ysa ham, uning testini davom ettira olmasin.
    if session["tg_user_id"] != int(user["id"]):
        raise HTTPException(status_code=403, detail="Bu sessiya sizga tegishli emas")

    try:
        result = await engine.submit_answer(
            payload.session_id, payload.question_id, payload.answer
        )
    except engine.EngineError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if result["done"]:
        # DIQQAT: Telegram.WebApp.sendData() inline yoki menyu tugmasidan
        # ochilgan Mini App'da ISHLAMAYDI — natijani server o'zi yuboradi.
        await notify.send_result(result)

    return result


@app.post("/api/admin/results")
async def admin_results(payload: InitIn):
    """Admin paneli: oxirgi natijalar va umumiy statistika."""
    user = _user(payload.init_data)
    if int(user["id"]) not in config.ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Bu bo'lim faqat administrator uchun")

    from app.staircase import LEVEL_NAMES

    return {
        "totals": store.totals(),
        "by_level": {
            LEVEL_NAMES.get(k, k): v for k, v in store.level_stats().items()
        },
        "results": [
            {
                "name": r["name"] or "Noma'lum",
                "username": r["username"],
                "level_name": LEVEL_NAMES.get(r["final_level"], r["final_level"]),
                "finished_at": r["finished_at"],
            }
            for r in store.recent_results(100)
        ],
    }


@app.post("/tg/webhook")
async def tg_webhook(request: Request):
    """Telegram yangiliklarni shu manzilga yuboradi (webhook rejimi).

    Maxfiy sarlavha tekshiriladi — aks holda istalgan odam botga soxta
    yangilik yuborishi mumkin bo'lardi.
    """
    if _tg_app is None:
        raise HTTPException(status_code=503, detail="Bot webhook rejimida ishlamayapti")
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != config.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Maxfiy sarlavha mos kelmadi")

    from telegram import Update

    update = Update.de_json(await request.json(), _tg_app.bot)
    await _tg_app.process_update(update)
    return {"ok": True}


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "ai": config.AI_ENABLED,
        "db": store.backend_name(),
        "webhook": config.USE_WEBHOOK,
        "dev_mode": config.ALLOW_INSECURE_DEV,
        "webapp_url": config.WEBAPP_URL,
    }


# --------------------------------------------------------------------------
# Ilova fayllari
# --------------------------------------------------------------------------

app.mount("/assets", StaticFiles(directory=config.WEBAPP_DIR), name="assets")


@app.middleware("http")
async def no_cache(request: Request, call_next):
    """Ilova fayllari keshlanmasin.

    Telegram webview HTML/JS ni qattiq keshlaydi — yangilanish chiqarilganda
    foydalanuvchida eski versiya ochilib qolmasligi uchun keshni o'chiramiz.
    """
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/assets"):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    return response


@app.get("/")
async def index():
    return FileResponse(config.WEBAPP_DIR / "index.html")
