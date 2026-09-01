"""Savollar bankini yuklash va blok uchun savol tanlash."""

from __future__ import annotations

import json
import random

from app import config
from app.staircase import LEVELS

_BANK: dict[str, list[dict]] = {}


def load_bank() -> dict[str, list[dict]]:
    """questions.json ni o'qiydi va tekshiradi. Bir marta yuklanadi."""
    global _BANK
    if _BANK:
        return _BANK

    with open(config.QUESTIONS_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    bank: dict[str, list[dict]] = {}
    seen_ids: set[str] = set()

    for level in LEVELS:
        items = raw.get(level, [])
        clean: list[dict] = []
        for q in items:
            qid = q["id"]
            if qid in seen_ids:
                raise ValueError(f"Takrorlangan savol id: {qid}")
            seen_ids.add(qid)

            if q.get("type") == "free_text":
                # AI kaliti yo'q bo'lsa, ochiq javobli savollarni bera olmaymiz -
                # ularni baholaydigan narsa yo'q.
                if not config.AI_ENABLED:
                    continue
            else:
                if q["correct"] not in q["options"]:
                    raise ValueError(f"{qid}: 'correct' variantlar ichida yo'q")
                if len(set(q["options"])) != len(q["options"]):
                    raise ValueError(f"{qid}: takrorlangan variantlar bor")
            clean.append(q)

        if len(clean) < 5:
            raise ValueError(f"{level} darajasida 5 tadan kam savol bor ({len(clean)})")
        bank[level] = clean

    _BANK = bank
    return _BANK


def pick_block(level: str, used_ids: set[str], size: int = 5) -> list[dict]:
    """Berilgan darajadan `size` ta savol tanlaydi.

    - avval ishlatilmagan savollardan oladi (takror chiqmasligi uchun);
    - ko'nikmalarni aralashtiradi (grammar / vocabulary / reading);
    - blokda ko'pi bilan 1 ta free_text bo'ladi (uzoq cho'zilmasligi uchun).
    """
    pool = [q for q in load_bank()[level] if q["id"] not in used_ids]
    if len(pool) < size:
        # Bank tugab qolsa - shu darajaning hamma savolidan qaytadan tanlaymiz.
        pool = list(load_bank()[level])

    free_text = [q for q in pool if q.get("type") == "free_text"]
    mcq = [q for q in pool if q.get("type") != "free_text"]

    random.shuffle(free_text)
    chosen: list[dict] = free_text[:1] if free_text else []

    # Ko'nikmalar bo'yicha guruhlab, navbat bilan olamiz -> muvozanatli blok
    by_skill: dict[str, list[dict]] = {}
    for q in mcq:
        by_skill.setdefault(q["skill"], []).append(q)
    for lst in by_skill.values():
        random.shuffle(lst)

    skills = sorted(by_skill, key=lambda s: -len(by_skill[s]))
    while len(chosen) < size:
        added = False
        for s in skills:
            if len(chosen) >= size:
                break
            if by_skill[s]:
                chosen.append(by_skill[s].pop())
                added = True
        if not added:
            break

    random.shuffle(chosen)
    return chosen[:size]


def public_view(q: dict) -> dict:
    """Frontendga yuboriladigan ko'rinish - to'g'ri javob HECH QACHON yuborilmaydi."""
    view = {
        "id": q["id"],
        "type": q.get("type", "mcq"),
        "skill": q["skill"],
        # O'zbekcha topshiriq matni
        "question": q["question"],
    }
    if q.get("passage"):
        view["passage"] = q["passage"]
    if q.get("sentence"):
        # Tekshiriladigan inglizcha jumla (grammatika/lug'at savollarida)
        view["sentence"] = q["sentence"]
    if q.get("type") == "free_text":
        view["min_words"] = q.get("min_words", 20)
    else:
        opts = list(q["options"])
        random.shuffle(opts)
        view["options"] = opts
    return view


def get_question(qid: str) -> dict | None:
    for items in load_bank().values():
        for q in items:
            if q["id"] == qid:
                return q
    return None
