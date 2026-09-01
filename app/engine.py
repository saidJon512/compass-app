"""Test dvigateli: sessiya boshqaruvi + staircase qarori.

Daraja mantig'i bu yerda EMAS — u faqat `staircase.py` da. Bu modul
sessiyani olib boradi: savol beradi, javobni baholaydi, blok tugaganda
staircase qarorini qo'llaydi.
"""

from __future__ import annotations

import logging
import uuid

from app import ai, questions, store
from app.staircase import (
    BLOCK_SIZE,
    LEVEL_NAMES,
    LEVEL_SHORT,
    LEVELS,
    MAX_QUESTIONS,
    BlockResult,
    decide_next,
    level_index,
)

log = logging.getLogger(__name__)


class EngineError(Exception):
    """Sessiya holati bilan bog'liq xato (topilmadi, tugagan, desinxron)."""


# --------------------------------------------------------------------------
# Ichki yordamchilar
# --------------------------------------------------------------------------

def _new_block(state: dict, level: str) -> None:
    block = questions.pick_block(level, set(state["used_ids"]), BLOCK_SIZE)
    state["current_level"] = level
    state["current_block"] = [q["id"] for q in block]
    state["cursor"] = 0
    state["block_correct"] = 0
    state["block_skills"] = {}
    state["used_ids"].extend(q["id"] for q in block)


def _current_question(state: dict) -> dict | None:
    if state["cursor"] >= len(state["current_block"]):
        return None
    return questions.get_question(state["current_block"][state["cursor"]])


def _serve(state: dict) -> dict:
    """Joriy savolni ko'rsatiladigan ko'rinishda qaytaradi.

    Variantlar tartibi state ga yoziladi — ilova qayta ochilganda savol
    aynan o'sha ko'rinishda tiklanishi uchun.
    """
    view = questions.public_view(_current_question(state))
    state["shown_options"] = view.get("options", [])
    return view


def _progress(state: dict) -> dict:
    """Ilova yuqorisidagi daraja va progress uchun ma'lumot."""
    level = state["current_level"]
    return {
        "asked": state["asked"],
        "max_questions": MAX_QUESTIONS,
        "level": level,
        "level_name": LEVEL_NAMES[level],
        "level_short": LEVEL_SHORT[level],
        "level_index": level_index(level),
        "level_total": len(LEVELS),
        "in_block": state["cursor"] + 1,
        "block_size": len(state["current_block"]),
        "blocks_done": len(state["blocks"]),
    }


def _blocks(state: dict) -> list[BlockResult]:
    return [BlockResult.from_dict(b) for b in state["blocks"]]


def _block_summary(blocks: list[BlockResult]) -> list[dict]:
    return [
        {
            "level": b.level,
            "level_name": LEVEL_NAMES[b.level],
            "level_short": LEVEL_SHORT[b.level],
            "correct": b.correct,
            "total": b.total,
            "percent": round(b.ratio * 100),
        }
        for b in blocks
    ]


# --------------------------------------------------------------------------
# Sessiyani boshlash / tiklash
# --------------------------------------------------------------------------

def start_session(user: dict) -> dict:
    """Yangi test boshlaydi. Test HAR DOIM A1 dan boshlanadi.

    Foydalanuvchining tugallanmagan eski sessiyalari yopiladi — bir vaqtda
    faqat bitta faol test bo'ladi.
    """
    store.abandon_unfinished(int(user["id"]))

    state = {
        "blocks": [],
        "current_level": "A1",
        "current_block": [],
        "cursor": 0,
        "block_correct": 0,
        "block_skills": {},
        "used_ids": [],
        "asked": 0,
        "shown_options": [],
        "finished": False,
    }
    _new_block(state, "A1")

    sid = uuid.uuid4().hex
    question = _serve(state)
    store.create_session(sid, user, state)

    return {
        "session_id": sid,
        "name": (user.get("first_name") or "").strip(),
        "question": question,
        "progress": _progress(state),
    }


def peek(session_id: str) -> dict | None:
    """Sessiyaning joriy savolini qayta ko'rsatadi.

    Variantlar tartibi saqlanadi — ilova yopilib qayta ochilganda savol
    joyidan siljib ketmasligi uchun.
    """
    session = store.load_session(session_id)
    if session is None or session["finished_at"]:
        return None

    state = session["state"]
    if _current_question(state) is None:
        return None

    view = questions.public_view(_current_question(state))
    saved = state.get("shown_options") or []
    if view.get("options") and sorted(saved) == sorted(view["options"]):
        view["options"] = saved

    return {
        "session_id": session_id,
        "name": session["name"] or "",
        "question": view,
        "progress": _progress(state),
    }


def resume(user: dict) -> dict | None:
    """Foydalanuvchining tugallanmagan testini topib, joriy savolini qaytaradi.

    Ilova har ochilganda shu chaqiriladi: test yarmida uzilib qolgan bo'lsa,
    foydalanuvchi aynan qolgan joyidan davom etadi.
    """
    sid = store.find_active_session(int(user["id"]))
    if sid is None:
        return None
    return peek(sid)


def last_result(tg_user_id: int) -> dict | None:
    """Oxirgi tugallangan test natijasi (natija ekranini tiklash uchun)."""
    session = store.last_finished_session(int(tg_user_id))
    if session is None:
        return None

    level = session["final_level"]
    blocks = [BlockResult.from_dict(b) for b in session["state"].get("blocks", [])]
    return {
        "done": True,
        "level": level,
        "level_name": LEVEL_NAMES[level],
        "summary": session["summary"] or "",
        "name": session["name"] or "",
        "total_questions": sum(b.total for b in blocks),
        "blocks": _block_summary(blocks),
        "finished_at": session["finished_at"],
    }


# --------------------------------------------------------------------------
# Javob qabul qilish
# --------------------------------------------------------------------------

async def submit_answer(session_id: str, question_id: str, answer: str) -> dict:
    """Javobni qabul qiladi, blok tugasa staircase qarorini qo'llaydi.

    Qaytaradi:
      {"done": False, "question": {...}, "progress": {...},
       "level_change": None | {"from": "A1", "to": "A2", "direction": "up"}}
      {"done": True, "level": "A2", "summary": "...", "blocks": [...], ...}
    """
    session = store.load_session(session_id)
    if session is None:
        raise EngineError("Sessiya topilmadi")
    if session["finished_at"]:
        raise EngineError("Bu test allaqachon tugagan")

    state = session["state"]
    q = _current_question(state)
    if q is None:
        raise EngineError("Savol navbati buzilgan")
    if q["id"] != question_id:
        # Ilova eski savolni qayta yubordi (masalan, ikki marta bosildi).
        raise EngineError("Savol mos kelmadi")

    # --- Baholash ---
    if q.get("type") == "free_text":
        is_correct = await ai.grade_free_text(q, answer)
    else:
        is_correct = answer.strip() == q["correct"]

    acc = state["block_skills"].setdefault(q["skill"], [0, 0])
    acc[0] += int(is_correct)
    acc[1] += 1
    state["block_correct"] += int(is_correct)
    state["cursor"] += 1
    state["asked"] += 1

    # --- Blok davom etmoqda: keyingi savol ---
    if state["cursor"] < len(state["current_block"]):
        question = _serve(state)
        store.save_state(session_id, state)
        return {
            "done": False,
            "level_change": None,
            "question": question,
            "progress": _progress(state),
        }

    # --- Blok tugadi: staircase qarori ---
    state["blocks"].append(
        BlockResult(
            level=state["current_level"],
            correct=state["block_correct"],
            total=len(state["current_block"]),
            by_skill=dict(state["block_skills"]),
        ).to_dict()
    )

    decision = decide_next(_blocks(state))

    if decision.action == "continue":
        previous = state["current_level"]
        _new_block(state, decision.level)
        question = _serve(state)
        store.save_state(session_id, state)

        change = None
        if decision.level != previous:
            change = {
                "from": previous,
                "from_name": LEVEL_NAMES[previous],
                "to": decision.level,
                "to_name": LEVEL_NAMES[decision.level],
                "direction": (
                    "up" if level_index(decision.level) > level_index(previous) else "down"
                ),
            }

        return {
            "done": False,
            "level_change": change,
            "question": question,
            "progress": _progress(state),
        }

    # --- Test tugadi ---
    state["finished"] = True
    final_level = decision.level
    blocks = _blocks(state)
    name = session["name"] or ""

    summary = await ai.write_summary(name, final_level, blocks)
    store.finish_session(session_id, state, final_level, summary)

    return {
        "done": True,
        "level": final_level,
        "level_name": LEVEL_NAMES[final_level],
        "summary": summary,
        "reason": decision.reason,
        "total_questions": state["asked"],
        "tg_user_id": session["tg_user_id"],
        "name": name,
        "username": session["username"],
        "blocks": _block_summary(blocks),
    }
