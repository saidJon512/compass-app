"""CEFR daraja zinapoyasi (staircase) algoritmi.

Bu modul BUTUNLAY deterministik: hech qanday AI chaqiruvi yo'q.
Daraja qarori faqat shu yerdagi if/else mantiqqa bog'liq, shuning uchun
"A1 dan keyin faqat A2" qoidasi hech qachon buzilmaydi.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal

# --- Zinapoya: tartib qat'iy, sakrash mumkin emas ---
LEVELS: list[str] = ["A1", "A2", "B1", "B2", "C1", "C2"]

# A1/A2/... — faqat ICHKI kalitlar (savollar banki va bazada ishlatiladi).
# Foydalanuvchiga hech qachon ko'rsatilmaydi; ekranda faqat quyidagi nomlar
# turadi.
LEVEL_NAMES: dict[str, str] = {
    "A1": "Beginner",
    "A2": "Elementary",
    "B1": "Pre-Intermediate",
    "B2": "Intermediate",
    "C1": "Upper-Intermediate",
    "C2": "Advanced",
}

# Zinapoya va ro'yxatlar uchun qisqartma — to'liq nom sig'maydigan joylarda.
LEVEL_SHORT: dict[str, str] = {
    "A1": "Beg",
    "A2": "Elem",
    "B1": "Pre-Int",
    "B2": "Int",
    "C1": "Upp-Int",
    "C2": "Adv",
}

BLOCK_SIZE = 5          # har blokda nechta savol
MAX_QUESTIONS = 30      # xavfsizlik chegarasi (vaqt cheklovi)
UP_THRESHOLD = 0.80     # >= 80% -> bir pog'ona yuqoriga
DOWN_THRESHOLD = 0.40   # <  40% -> bir pog'ona pastga
# 40-79% oralig'i -> aynan shu daraja, test tugaydi


def level_index(level: str) -> int:
    return LEVELS.index(level)


def step_up(level: str) -> str | None:
    """Bittagina yuqoriga. C2 dan yuqorisi yo'q -> None."""
    i = level_index(level)
    return LEVELS[i + 1] if i + 1 < len(LEVELS) else None


def step_down(level: str) -> str | None:
    """Bittagina pastga. A1 dan pasti yo'q -> None."""
    i = level_index(level)
    return LEVELS[i - 1] if i - 1 >= 0 else None


@dataclass
class BlockResult:
    """Bitta blok (5 savol) natijasi."""
    level: str
    correct: int
    total: int
    # ko'nikma kesimida: {"grammar": [to'g'ri, jami], ...}
    by_skill: dict[str, list[int]]

    @property
    def ratio(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "BlockResult":
        return BlockResult(
            level=d["level"],
            correct=d["correct"],
            total=d["total"],
            by_skill={k: list(v) for k, v in d.get("by_skill", {}).items()},
        )


StopReason = Literal[
    "precise",           # 40-79% -> aniq daraja topildi
    "ceiling",           # C2 da ham 80%+ -> eng yuqori chegara
    "floor",             # A1 da ham 40% dan past -> eng past chegara
    "confirmed_ceiling", # yuqoridagi daraja allaqachon yiqilgan edi
    "max_questions",     # 30 savol chegarasi
]


@dataclass
class Decision:
    action: Literal["continue", "finish"]
    level: str                      # continue -> qaysi darajadan so'rash; finish -> yakuniy daraja
    reason: StopReason | None = None


def _failed_levels(blocks: list[BlockResult]) -> set[str]:
    """Foydalanuvchi <40% olgan darajalar."""
    return {b.level for b in blocks if b.ratio < DOWN_THRESHOLD}


def _best_passed_level(blocks: list[BlockResult]) -> str:
    """>=40% olingan eng yuqori daraja. Hech biri bo'lmasa A1."""
    passed = [b.level for b in blocks if b.ratio >= DOWN_THRESHOLD]
    if not passed:
        return "A1"
    return max(passed, key=level_index)


def decide_next(blocks: list[BlockResult]) -> Decision:
    """Bloklar tarixiga qarab keyingi qadamni aniqlaydi.

    Qaytaradi:
      Decision(action="continue", level=X) -> X darajasidan yana 5 savol ber
      Decision(action="finish",  level=Y)  -> test tugadi, yakuniy daraja Y
    """
    # Test boshlanishi: har doim A1 dan.
    if not blocks:
        return Decision(action="continue", level="A1")

    last = blocks[-1]
    asked = sum(b.total for b in blocks)
    ratio = last.ratio

    # --- 1) >= 80%: bir pog'ona yuqoriga ---
    if ratio >= UP_THRESHOLD:
        nxt = step_up(last.level)

        # (b) C2 da ham 80%+ -> eng yuqori chegara
        if nxt is None:
            return Decision("finish", "C2", "ceiling")

        # Guard: bu darajada allaqachon yiqilgan bo'lsa, qayta ko'tarilmaymiz.
        # Aks holda A2 -> B1 -> A2 -> B1 tebranishi 30 savolgacha cho'ziladi.
        # Pastda o'tib, yuqorida yiqilish = aniq shift chegarasi topilgani.
        if nxt in _failed_levels(blocks):
            return Decision("finish", last.level, "confirmed_ceiling")

        # (d) savollar chegarasi
        if asked >= MAX_QUESTIONS:
            return Decision("finish", _best_passed_level(blocks), "max_questions")

        return Decision("continue", nxt)

    # --- 2) 40-79%: aynan shu daraja, test to'xtaydi ---
    if ratio >= DOWN_THRESHOLD:
        return Decision("finish", last.level, "precise")

    # --- 3) < 40%: bir pog'ona pastga ---
    prev = step_down(last.level)

    # (c) A1 da ham past ball -> eng past chegara
    if prev is None:
        return Decision("finish", "A1", "floor")

    # (d) savollar chegarasi
    if asked >= MAX_QUESTIONS:
        return Decision("finish", _best_passed_level(blocks), "max_questions")

    # Pastki darajada tasdiqlash uchun yana bir blok
    return Decision("continue", prev)


def strongest_skill(blocks: list[BlockResult]) -> tuple[str, float] | None:
    """Eng yuqori foizli ko'nikma (grammar / vocabulary / reading).

    Kamida 2 ta savol berilgan ko'nikmalar orasidan tanlanadi, aks holda
    bitta tasodifiy to'g'ri javob "kuchli tomon" bo'lib ko'rinib qoladi.
    """
    totals: dict[str, list[int]] = {}
    for b in blocks:
        for skill, (c, t) in b.by_skill.items():
            acc = totals.setdefault(skill, [0, 0])
            acc[0] += c
            acc[1] += t

    eligible = {s: v for s, v in totals.items() if v[1] >= 2}
    if not eligible:
        return None

    skill, (c, t) = max(eligible.items(), key=lambda kv: kv[1][0] / kv[1][1])
    return skill, c / t
