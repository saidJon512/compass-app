"""Claude API integratsiyasi.

AI ikkita ishni qiladi, XOLOS:
  1. free_text javoblarni ikkilik (to'g'ri/noto'g'ri) baholash;
  2. kod aniqlagan yakuniy daraja haqida tabiiy tilda xulosa yozish.

Daraja qarorini AI HECH QACHON qabul qilmaydi — u staircase.py da.
Kalit bo'lmasa yoki API xato bersa, tizim shablon matnga qaytadi.
"""

from __future__ import annotations

import json
import logging

import anthropic

from app import config
from app.staircase import LEVEL_NAMES, LEVELS, BlockResult, strongest_skill

log = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None

SKILL_UZ = {
    "grammar": "grammatika",
    "vocabulary": "so'z boyligi",
    "reading": "o'qib tushunish",
    "writing": "yozish",
}


def client() -> anthropic.AsyncAnthropic | None:
    global _client
    if not config.AI_ENABLED:
        return None
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


# --------------------------------------------------------------------------
# 1) Ochiq javobli savolni baholash
# --------------------------------------------------------------------------

GRADER_SYSTEM = """Sen — ingliz tili daraja aniqlash tizimidagi baholovchi
yordamchisan. Senga bitta daraja, shu darajaga mo'ljallangan yozma topshiriq
va o'quvchining javobi beriladi.

Topshiriq o'zbek tilida beriladi, lekin o'quvchi javobni INGLIZ TILIDA
yozishi kerak. Agar javob o'zbek tilida yozilgan bo'lsa — "noto'g'ri".

Quyidagi mezonlar bo'yicha baho ber:
- Grammatik to'g'rilik (asosiy zamon va gap tuzilishi shu darajaga mos keladimi)
- So'z boyligi (shu darajaga mos so'zlar ishlatilganmi)
- Uzunlik va tushunarlilik (topshiriq talabiga javob beradimi)

Kichik imlo va tinish belgisi xatolari javobni noto'g'ri qilmaydi — agar fikr
tushunarli bo'lsa va daraja talabiga umuman javob bersa, "to'g'ri" deb hisobla.
Javob mavzuga aloqasiz, juda qisqa yoki shu daraja talabidan sezilarli past
bo'lsa — "noto'g'ri".

FAQAT quyidagi JSON formatida javob ber, boshqa hech narsa yozma:
{"verdict": "correct"}  yoki  {"verdict": "incorrect"}

Oraliq baho berma — bu algoritm faqat ikkilik natijaga tayanadi."""


async def grade_free_text(question: dict, answer: str) -> bool:
    """Ochiq javobni baholaydi. Xato bo'lsa — foydalanuvchi foydasiga (True)."""
    c = client()
    if c is None:
        return False

    user_msg = (
        f"Daraja: {LEVEL_NAMES[question['level']]}\n"
        f"Topshiriq: {question['question']}\n"
        f"Kutilgan minimal uzunlik: {question.get('min_words', 20)} so'z\n\n"
        f"O'quvchining javobi:\n\"\"\"\n{answer.strip()[:2000]}\n\"\"\""
    )

    try:
        resp = await c.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=1000,
            system=GRADER_SYSTEM,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": user_msg}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        verdict = json.loads(text[text.find("{") : text.rfind("}") + 1])["verdict"]
        return verdict == "correct"
    except (anthropic.APIError, ValueError, KeyError, json.JSONDecodeError) as e:
        log.warning("free_text baholashda xato (%s) — javob to'g'ri deb qabul qilindi", e)
        # Bizning xatoyimiz o'quvchiga zarar keltirmasin.
        return True


# --------------------------------------------------------------------------
# 2) Yakuniy xulosa
# --------------------------------------------------------------------------

SUMMARY_SYSTEM = """Sen — til markazining rasmiy daraja aniqlash tizimidagi
yordamchi sun'iy intellektsan. Senga backend kod tomonidan ANIQLANGAN yakuniy
daraja va o'quvchining har bir blokdagi natijalari beriladi. Sening vazifang
bu ma'lumotni tabiiy, tushunarli va rag'batlantiruvchi tilda yozib berishdir.
O'zbek tilida yoz.

## QAT'IY QOIDA
Sen HECH QACHON daraja haqida o'zingcha qaror chiqarmaysan. Senga qaysi daraja
berilgan bo'lsa (masalan "final_level": "Elementary"), aynan o'sha darajani
natija sifatida e'lon qilasan — hech qachon kod bergan darajani
o'zgartirmaysan, "balki Pre-Intermediate ham bo'lishi mumkin" kabi gumon
bildirmaysan.

## DARAJA NOMI
Darajani FAQAT nomi bilan yoz: Beginner, Elementary, Pre-Intermediate,
Intermediate, Upper-Intermediate, Advanced. A1, A2, B1, B2, C1, C2 kabi
kodlarni HECH QACHON yozma — o'quvchi ularni umuman ko'rmaydi.

## YAKUNIY NATIJA MATNI TUZILISHI
1. Tabriklash va daraja e'loni
   (masalan: "Tabriklaymiz! Sizning ingliz tilidagi darajangiz — Elementary")
2. Bu daraja nimani anglatishini 1-2 gapda tushuntir
3. Kuchli tomon — qaysi ko'nikmada eng yuqori foiz bo'lgani (agar berilgan bo'lsa)
4. Keyingi qadam: qaysi darajadagi kursga yozilish tavsiya etiladi
5. Rag'batlantiruvchi yakuniy gap

## OHANG
- Hech qachon "past daraja", "zaif" kabi kamsituvchi so'z ishlatma
- Har bir daraja — o'sish bosqichi, natija emas, deb yoz
- O'quvchi ismi berilgan bo'lsa, ismi bilan murojaat qil
- Umumiy uzunlik: 120-180 so'z. Markdown sarlavha ishlatma, oddiy matn yoz."""


def _next_course_level(level: str) -> str:
    i = LEVELS.index(level)
    return LEVELS[i + 1] if i + 1 < len(LEVELS) else LEVELS[i]


def _fallback_summary(name: str, level: str, blocks: list[BlockResult]) -> str:
    """AI ishlamasa ishlatiladigan shablon matn."""
    total_c = sum(b.correct for b in blocks)
    total_q = sum(b.total for b in blocks)
    parts = [
        f"Tabriklaymiz{', ' + name if name else ''}! "
        f"Sizning ingliz tilidagi darajangiz — {LEVEL_NAMES[level]}.",
        f"Siz jami {total_q} ta savoldan {total_c} tasiga to'g'ri javob berdingiz.",
    ]

    best = strongest_skill(blocks)
    if best:
        skill, pct = best
        parts.append(
            f"Eng kuchli tomoningiz — {SKILL_UZ.get(skill, skill)} "
            f"({round(pct * 100)}%)."
        )

    nxt = _next_course_level(level)
    if nxt != level:
        parts.append(
            f"Keyingi qadam sifatida {LEVEL_NAMES[nxt]} darajasidagi "
            f"kursga yozilishingizni tavsiya qilamiz."
        )
    else:
        parts.append(
            "Siz eng yuqori bosqichdasiz — bilimingizni amaliyotda "
            "mustahkamlashda davom eting."
        )

    parts.append("Har bir daraja — bu o'sish bosqichi. Omad tilaymiz!")
    return " ".join(parts)


async def write_summary(name: str, level: str, blocks: list[BlockResult]) -> str:
    """Yakuniy xulosa matnini qaytaradi (AI yoki shablon)."""
    c = client()
    if c is None:
        return _fallback_summary(name, level, blocks)

    best = strongest_skill(blocks)
    # AI ga faqat NOMLAR beriladi — kodlarni ko'rmasa, javobiga ham yozmaydi.
    payload = {
        "student_name": name or None,
        "final_level": LEVEL_NAMES[level],
        "recommended_course_level": LEVEL_NAMES[_next_course_level(level)],
        "blocks": [
            {
                "level": LEVEL_NAMES[b.level],
                "correct": b.correct,
                "total": b.total,
                "percent": round(b.ratio * 100),
            }
            for b in blocks
        ],
        "strongest_skill": (
            {"skill": SKILL_UZ.get(best[0], best[0]), "percent": round(best[1] * 100)}
            if best
            else None
        ),
    }

    try:
        resp = await c.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2000,
            system=SUMMARY_SYSTEM,
            output_config={"effort": "low"},
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False, indent=2),
                }
            ],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        # Xavfsizlik to'ri: AI kod bergan darajani o'zgartirib yuborgan bo'lsa,
        # shablonga qaytamiz.
        if not text or LEVEL_NAMES[level] not in text:
            log.warning(
                "AI xulosasida «%s» darajasi yo'q — shablon ishlatildi", LEVEL_NAMES[level]
            )
            return _fallback_summary(name, level, blocks)
        return text
    except anthropic.APIError as e:
        log.warning("Xulosa yozishda API xatosi: %s", e)
        return _fallback_summary(name, level, blocks)
