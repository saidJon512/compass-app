"""Mini App ning to'liq oqimini uchidan-uchiga tekshiradi.

Haqiqiy HTTP so'rovlar orqali: initData imzosi, sessiya, javob berish,
staircase qarori, natija. Telegram ham, Claude ham chaqirilmaydi.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# DIQQAT: config .env ni import paytida o'qiydi, shuning uchun sozlamalarni
# undan OLDIN qo'yamiz. load_dotenv mavjud env o'zgaruvchini bosmaydi.
_TMP_DB = Path(tempfile.mkdtemp(prefix="compass-test-")) / "test.db"
os.environ["DB_PATH"] = str(_TMP_DB)
os.environ["ALLOW_INSECURE_DEV"] = "false"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["TUNNEL"] = "none"

from fastapi.testclient import TestClient  # noqa: E402

from app import config, notify  # noqa: E402
from app.api import app  # noqa: E402
from app.staircase import LEVELS  # noqa: E402

# config.DB_PATH BASE_DIR ga nisbatan qo'shiladi — mutlaq yo'lni qaytaramiz.
config.DB_PATH = _TMP_DB

# Test haqiqiy Telegram xabarini YUBORMASLIGI kerak — aks holda har ishga
# tushirishda admin chatga soxta natijalar tushadi.
_sent: list[tuple[int, str]] = []


async def _fake_send(chat_id: int, text: str) -> None:
    _sent.append((chat_id, text))


notify.send_message = _fake_send

BANK = json.loads((config.QUESTIONS_PATH).read_text(encoding="utf-8"))
ANSWERS = {q["id"]: q.get("correct") for level in BANK.values() for q in level}

_failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  OK   {name}")
    else:
        print(f"  XATO {name} — {detail}")
        _failures.append(name)


# --------------------------------------------------------------------------
# Haqiqiy initData yasaymiz (Telegram qanday imzolasa, shunday)
# --------------------------------------------------------------------------

def make_init_data(user_id: int, first_name: str = "Test", signature: str | None = None) -> str:
    """Telegram imzolagandek initData yasaydi.

    signature=None        — `signature` maydoni umuman yo'q (eski mijozlar);
    signature="hashed"    — bor va HMAC hisobiga KIRADI;
    signature="unhashed"  — bor, lekin HMAC hisobidan CHIQARILADI.

    Haqiqiy Telegram mijozlari shu uch ko'rinishning birini yuboradi —
    uchalasi ham qabul qilinishi kerak.
    """
    user = json.dumps(
        {"id": user_id, "first_name": first_name, "username": f"u{user_id}"},
        separators=(",", ":"),
    )
    pairs = {"auth_date": "2000000000", "query_id": "AAA", "user": user}
    if signature:
        pairs["signature"] = "FaKeEd25519SiGnAtUrE_-x"

    hashed = {k: v for k, v in pairs.items() if not (signature == "unhashed" and k == "signature")}
    check_string = "\n".join(f"{k}={hashed[k]}" for k in sorted(hashed))

    secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


# --------------------------------------------------------------------------

def check_bank() -> None:
    """Savollar bankining shakli: topshiriq o'zbekcha, variantlar inglizcha."""
    all_q = [q for level in BANK.values() for q in level]

    check("bankda 132 ta savol bor", len(all_q) == 132, str(len(all_q)))
    check("id lar takrorlanmaydi", len({q["id"] for q in all_q}) == len(all_q))

    # Bo'sh joy belgisi FAQAT inglizcha jumlada bo'lishi kerak — o'zbekcha
    # topshiriqda "___" turgan bo'lsa, demak jumla ko'chirilmay qolgan.
    stray = [q["id"] for q in all_q if "___" in q["question"]]
    check("«___» o'zbekcha topshiriqda yo'q", not stray, ", ".join(stray[:5]))

    # Har bir mcq savoli javob berish uchun yetarli kontekstga ega bo'lsin:
    # yo inglizcha jumla, yo matn, yoki savolning o'zi to'liq tushunarli.
    mcq = [q for q in all_q if q.get("type", "mcq") == "mcq"]
    bad = [q["id"] for q in mcq if q["correct"] not in q["options"]]
    check("to'g'ri javob variantlar ichida", not bad, ", ".join(bad[:5]))

    dup = [q["id"] for q in mcq if len(set(q["options"])) != len(q["options"])]
    check("variantlar takrorlanmaydi", not dup, ", ".join(dup[:5]))

    # Bo'sh joyli jumla bor bo'lsa, unda "___" ham bo'lishi kerak.
    broken = [
        q["id"] for q in mcq
        if q.get("sentence") and "___" not in q["sentence"] and "…" not in q["sentence"]
    ]
    check("jumlalarda bo'sh joy belgisi bor", not broken, ", ".join(broken[:5]))


def run() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit(".env da BOT_TOKEN yo'q — testni ishga tushirib bo'lmaydi.")

    check_bank()

    with TestClient(app) as client:
        init = make_init_data(1001)

        # --- Imzo tekshiruvi ---
        r = client.post("/api/bootstrap", json={"init_data": ""})
        check("bo'sh initData rad etiladi", r.status_code == 401, f"status={r.status_code}")

        bad = init[:-1] + ("0" if init[-1] != "0" else "1")
        r = client.post("/api/bootstrap", json={"init_data": bad})
        check("buzilgan imzo rad etiladi", r.status_code == 401, f"status={r.status_code}")

        r = client.post("/api/bootstrap", json={"init_data": init})
        check("to'g'ri imzo qabul qilinadi", r.status_code == 200, r.text[:120])

        # Haqiqiy mijozlar `signature` maydonini yuboradi — u HMAC hisobiga
        # kirsa ham, kirmasa ham ilova ochilishi kerak.
        for mode in ("hashed", "unhashed"):
            r = client.post(
                "/api/bootstrap",
                json={"init_data": make_init_data(1001, signature=mode)},
            )
            check(f"signature ({mode}) qabul qilinadi", r.status_code == 200, r.text[:120])

        # Imzosi buzilgan bo'lsa, `signature` bor bo'lsa ham o'tmasligi kerak.
        sig_bad = make_init_data(1001, signature="hashed")
        sig_bad = sig_bad[:-1] + ("0" if sig_bad[-1] != "0" else "1")
        r = client.post("/api/bootstrap", json={"init_data": sig_bad})
        check("signature bo'lsa ham soxta imzo rad etiladi", r.status_code == 401,
              f"status={r.status_code}")

        boot = client.post("/api/bootstrap", json={"init_data": init}).json()
        check("yangi foydalanuvchida faol test yo'q", boot["active"] is None)
        check("yangi foydalanuvchida natija yo'q", boot["last_result"] is None)

        # --- Testni boshlash ---
        data = client.post("/api/start", json={"init_data": init}).json()
        sid = data["session_id"]
        check("test A1 dan boshlanadi", data["progress"]["level"] == "A1", data["progress"]["level"])
        check(
            "to'g'ri javob frontendga yuborilmaydi",
            "correct" not in data["question"],
            str(data["question"].keys()),
        )

        # --- Boshqa foydalanuvchi bu sessiyani davom ettira olmaydi ---
        r = client.post(
            "/api/answer",
            json={
                "init_data": make_init_data(2002),
                "session_id": sid,
                "question_id": data["question"]["id"],
                "answer": "x",
            },
        )
        check("begona foydalanuvchi rad etiladi", r.status_code == 403, f"status={r.status_code}")

        # --- Hammasiga to'g'ri javob: A1 dan C2 gacha ko'tarilishi kerak ---
        question = data["question"]
        seen_levels = ["A1"]
        result = None

        for _ in range(40):
            r = client.post(
                "/api/answer",
                json={
                    "init_data": init,
                    "session_id": sid,
                    "question_id": question["id"],
                    "answer": ANSWERS[question["id"]],
                },
            )
            check_ok = r.status_code == 200
            if not check_ok:
                check("javob qabul qilindi", False, r.text[:160])
                return
            body = r.json()
            if body["done"]:
                result = body
                break
            lvl = body["progress"]["level"]
            if lvl != seen_levels[-1]:
                seen_levels.append(lvl)
            question = body["question"]

        check("test tugadi", result is not None)
        if result is None:
            return

        check(
            "daraja bittadan sakradi va C2 gacha chiqdi",
            seen_levels == LEVELS,
            str(seen_levels),
        )
        check("yakuniy daraja C2", result["level"] == "C2", result["level"])
        check("to'xtash sababi 'ceiling'", result["reason"] == "ceiling", str(result["reason"]))
        check("xulosa matni bor", bool(result["summary"]))
        check(
            "xulosada daraja NOMI yozilgan",
            "Advanced" in result["summary"],
            result["summary"][:80],
        )
        check(
            "xulosada CEFR kodi YO'Q",
            not any(code in result["summary"] for code in ("A1", "A2", "B1", "B2", "C1", "C2")),
            result["summary"][:120],
        )
        check("6 ta blok o'tildi", len(result["blocks"]) == 6, str(len(result["blocks"])))

        # --- Tugagan sessiyaga qayta javob berib bo'lmaydi ---
        r = client.post(
            "/api/answer",
            json={
                "init_data": init,
                "session_id": sid,
                "question_id": question["id"],
                "answer": "x",
            },
        )
        check("tugagan test yopiq", r.status_code == 409, f"status={r.status_code}")

        # --- Natija saqlandi ---
        boot = client.post("/api/bootstrap", json={"init_data": init}).json()
        check("oxirgi natija tiklanadi", boot["last_result"] is not None)
        check(
            "tiklangan natija C2",
            boot["last_result"] and boot["last_result"]["level"] == "C2",
        )
        check("tugaganidan keyin faol test yo'q", boot["active"] is None)

        # --- Admin paneli ---
        r = client.post("/api/admin/results", json={"init_data": init})
        check("oddiy foydalanuvchi admin panelini ko'ra olmaydi",
              r.status_code == 403, f"status={r.status_code}")

        boot = client.post("/api/bootstrap", json={"init_data": init}).json()
        check("oddiy foydalanuvchida is_admin=false", boot["is_admin"] is False)

        config.ADMIN_IDS.add(1001)
        try:
            r = client.post("/api/admin/results", json={"init_data": init})
            check("admin panelni ocha oladi", r.status_code == 200, r.text[:120])
            if r.status_code == 200:
                panel = r.json()
                check("panelda tugallangan test bor", panel["totals"]["finished"] >= 1,
                      str(panel["totals"]))
                check("panelda daraja NOMI ko'rsatiladi",
                      "Advanced" in panel["by_level"], str(list(panel["by_level"])))
                check("ro'yxatda natija bor", len(panel["results"]) >= 1)
            boot = client.post("/api/bootstrap", json={"init_data": init}).json()
            check("adminda is_admin=true", boot["is_admin"] is True)
        finally:
            config.ADMIN_IDS.discard(1001)

        # --- Yarim qolgan test tiklanadi ---
        u3 = make_init_data(3003)
        d3 = client.post("/api/start", json={"init_data": u3}).json()
        client.post(
            "/api/answer",
            json={
                "init_data": u3,
                "session_id": d3["session_id"],
                "question_id": d3["question"]["id"],
                "answer": ANSWERS[d3["question"]["id"]],
            },
        )
        b3 = client.post("/api/bootstrap", json={"init_data": u3}).json()
        check("yarim qolgan test topiladi", b3["active"] is not None)
        check(
            "davomi 2-savoldan",
            b3["active"] and b3["active"]["progress"]["in_block"] == 2,
            str(b3["active"] and b3["active"]["progress"]["in_block"]),
        )

        # --- Hammasiga noto'g'ri javob: A1 da to'xtashi kerak ---
        u4 = make_init_data(4004)
        d4 = client.post("/api/start", json={"init_data": u4}).json()
        q4 = d4["question"]
        res4 = None
        for _ in range(40):
            body = client.post(
                "/api/answer",
                json={
                    "init_data": u4,
                    "session_id": d4["session_id"],
                    "question_id": q4["id"],
                    "answer": "__butunlay_noto'g'ri__",
                },
            ).json()
            if body["done"]:
                res4 = body
                break
            q4 = body["question"]

        check("past ballda test tugadi", res4 is not None)
        if res4:
            check("yakuniy daraja A1", res4["level"] == "A1", res4["level"])
            check("sabab 'floor'", res4["reason"] == "floor", str(res4["reason"]))
            check("5 ta savolda to'xtadi", res4["total_questions"] == 5, str(res4["total_questions"]))


if __name__ == "__main__":
    run()
    print()
    if _failures:
        print(f"{len(_failures)} ta test o'tmadi: {', '.join(_failures)}")
        sys.exit(1)
    print("Hammasi o'tdi.")
