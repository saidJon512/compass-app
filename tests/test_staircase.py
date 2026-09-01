"""Staircase algoritmi testlari - eng muhim talab: BITTADAN ORTIQ SAKRAMASLIK."""

import sys
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.staircase import (  # noqa: E402
    BLOCK_SIZE,
    LEVELS,
    MAX_QUESTIONS,
    BlockResult,
    decide_next,
    level_index,
)


def block(level: str, correct: int) -> BlockResult:
    return BlockResult(level=level, correct=correct, total=BLOCK_SIZE, by_skill={})


def run(scores: list[int], levels_out: list[str] | None = None):
    """`scores` - har blokdagi to'g'ri javoblar soni. Yakuniy qarorni qaytaradi."""
    blocks: list[BlockResult] = []
    d = decide_next(blocks)
    path = [d.level]
    for s in scores:
        if d.action == "finish":
            break
        blocks.append(block(d.level, s))
        d = decide_next(blocks)
        path.append(d.level)
    if levels_out is not None:
        levels_out[:] = path
    return d, blocks


def test_starts_at_a1():
    assert decide_next([]).level == "A1"
    assert decide_next([]).action == "continue"


def test_never_jumps_more_than_one_level():
    """ASOSIY TALAB: har qanday ketma-ketlikda daraja bittadan ortiq o'zgarmaydi."""
    for scores in product(range(BLOCK_SIZE + 1), repeat=5):
        path: list[str] = []
        run(list(scores), path)
        for a, b in zip(path, path[1:]):
            assert abs(level_index(a) - level_index(b)) <= 1, (
                f"{scores}: {a} -> {b} sakrash!"
            )


def test_up_one_level_on_80_percent():
    d, _ = run([4])
    assert (d.action, d.level) == ("continue", "A2")
    d, _ = run([5])
    assert (d.action, d.level) == ("continue", "A2")


def test_stops_on_middle_score():
    for s in (2, 3):
        d, _ = run([s])
        assert d.action == "finish"
        assert d.level == "A1"
        assert d.reason == "precise"


def test_a1_floor():
    for s in (0, 1):
        d, _ = run([s])
        assert (d.action, d.level, d.reason) == ("finish", "A1", "floor")


def test_c2_ceiling():
    # A1..C1 da 5/5, keyin C2 da 5/5 -> C2 da to'xtaydi
    d, _ = run([5, 5, 5, 5, 5, 5])
    assert (d.action, d.level, d.reason) == ("finish", "C2", "ceiling")


def test_step_down_gives_confirmation_block():
    # A1: 5/5 -> A2; A2: 0/5 -> A1 ga qaytadi va yana blok beriladi
    path: list[str] = []
    d, _ = run([5, 0], path)
    assert path == ["A1", "A2", "A1"]
    assert d.action == "continue"


def test_no_reascend_into_failed_level():
    # A1:5/5 -> A2; A2:1/5 -> A1; A1:5/5 -> A2 allaqachon yiqilgan, to'xtaydi
    d, _ = run([5, 1, 5])
    assert d.action == "finish"
    assert d.level == "A1"
    assert d.reason == "confirmed_ceiling"


def test_never_exceeds_max_questions():
    for scores in product(range(BLOCK_SIZE + 1), repeat=8):
        blocks: list[BlockResult] = []
        d = decide_next(blocks)
        for s in scores:
            if d.action == "finish":
                break
            blocks.append(block(d.level, s))
            d = decide_next(blocks)
        assert sum(b.total for b in blocks) <= MAX_QUESTIONS, scores
        # 8 ta blok berilgan bo'lsa, algoritm albatta to'xtagan bo'lishi kerak
        assert d.action == "finish", scores


def test_final_level_always_valid():
    for scores in product(range(BLOCK_SIZE + 1), repeat=6):
        d, _ = run(list(scores))
        assert d.level in LEVELS


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  OK   {name}")
            except AssertionError as e:
                failed += 1
                print(f"  FAIL {name}: {e}")
    print("\nHammasi o'tdi." if not failed else f"\n{failed} ta test yiqildi.")
    sys.exit(1 if failed else 0)
