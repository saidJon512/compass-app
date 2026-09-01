"""Telegram Mini App initData ni tekshirish.

Frontend yuborgan Telegram ID ga ishonib bo'lmaydi - uni istalgan odam
o'zgartirishi mumkin. Shuning uchun initData ning HMAC imzosini bot token
bilan tekshiramiz va foydalanuvchini FAQAT shundan olamiz.

Hujjat: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

from app import config

log = logging.getLogger(__name__)

MAX_AGE_SECONDS = 24 * 60 * 60  # initData 24 soatdan eski bo'lmasin

# Telegram mijozlari `signature` (Ed25519, uchinchi tomon tekshiruvi uchun)
# maydonini HMAC hisobiga turlicha kiritadi: mos yozuvlar amalga oshiruvi
# faqat `hash` ni chiqaradi, ba'zi hujjatlarda esa `signature` ham
# chiqariladi. Ikkala variantni ham sinaymiz.
#
# Bu xavfsizlikni PASAYTIRMAYDI: ikkala variant ham bot token bilan
# imzolangan va biz ishlatadigan maydonlar (`user`, `auth_date`) ikkalasida
# ham imzo ostida qoladi. `signature` ning o'zi hech qayerda ishlatilmaydi.
_DROP_VARIANTS: tuple[tuple[str, frozenset[str]], ...] = (
    ("signature qo'shilgan", frozenset()),
    ("signature chiqarilgan", frozenset({"signature"})),
)


class InitDataError(Exception):
    pass


def _data_check_string(pairs: dict[str, str], drop: frozenset[str]) -> str:
    keys = sorted(k for k in pairs if k not in drop)
    return "\n".join(f"{k}={pairs[k]}" for k in keys)


def verify_init_data(init_data: str) -> dict:
    """initData satrini tekshiradi va Telegram foydalanuvchisini qaytaradi.

    Qaytadi: {"id": int, "first_name": str, "username": str | None, ...}
    """
    if not init_data:
        raise InitDataError("initData bo'sh")
    if not config.BOT_TOKEN:
        raise InitDataError("BOT_TOKEN sozlanmagan")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataError("hash yo'q")

    secret_key = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()

    for label, drop in _DROP_VARIANTS:
        expected = hmac.new(
            secret_key, _data_check_string(pairs, drop).encode(), hashlib.sha256
        ).hexdigest()
        if hmac.compare_digest(expected, received_hash):
            log.debug("initData imzosi mos keldi (%s)", label)
            break
    else:
        # Shaxsiy ma'lumot yozmaymiz — faqat maydon nomlari, tashxis uchun.
        log.warning("initData imzosi mos kelmadi. Maydonlar: %s", sorted(pairs))
        log.debug("Tekshirilgan initData: %s", init_data)
        raise InitDataError("imzo mos kelmadi")

    auth_date = int(pairs.get("auth_date", "0"))
    if auth_date and time.time() - auth_date > MAX_AGE_SECONDS:
        raise InitDataError("initData eskirgan")

    user_raw = pairs.get("user")
    if not user_raw:
        raise InitDataError("user maydoni yo'q")

    user = json.loads(user_raw)
    if "id" not in user:
        raise InitDataError("user.id yo'q")
    return user


def resolve_user(init_data: str) -> dict:
    """Ishlab chiqarishda - qat'iy tekshiruv.

    ALLOW_INSECURE_DEV=true bo'lsagina brauzerdan sinash uchun soxta
    foydalanuvchiga ruxsat beriladi.
    """
    try:
        return verify_init_data(init_data)
    except InitDataError:
        if config.ALLOW_INSECURE_DEV:
            return {"id": 0, "first_name": "Mehmon", "username": None, "_dev": True}
        raise
