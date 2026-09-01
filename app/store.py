"""Sessiya va natijalarni saqlash.

Ikkita omborni qo'llab-quvvatlaydi:

  SQLite   — `DATABASE_URL` bo'sh bo'lsa. Lokal ishlash uchun qulay.
  Postgres — `DATABASE_URL` berilgan bo'lsa (masalan Neon).

Nega ikkitasi: bepul hostinglarda (Render) disk VAQTINCHALIK — server qayta
ishga tushsa SQLite fayli o'chib ketadi va butun test tarixi yo'qoladi.
Postgres esa serverdan tashqarida turadi, shuning uchun ma'lumot saqlanadi.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from app import config

_PG = bool(config.DATABASE_URL)

if _PG:  # pragma: no cover - faqat serverda ishlaydi
    import psycopg
    from psycopg.rows import dict_row

_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS sessions (
    id           TEXT PRIMARY KEY,
    tg_user_id   INTEGER NOT NULL,
    name         TEXT,
    username     TEXT,
    state        TEXT NOT NULL,
    final_level  TEXT,
    summary      TEXT,
    created_at   TEXT NOT NULL,
    finished_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(tg_user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_done ON sessions(finished_at);
"""

_SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS sessions (
    id           TEXT PRIMARY KEY,
    tg_user_id   BIGINT NOT NULL,
    name         TEXT,
    username     TEXT,
    state        TEXT NOT NULL,
    final_level  TEXT,
    summary      TEXT,
    created_at   TEXT NOT NULL,
    finished_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(tg_user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_done ON sessions(finished_at);
"""


# --------------------------------------------------------------------------
# Ulanish qatlami
# --------------------------------------------------------------------------

def _connect():
    if _PG:  # pragma: no cover
        return psycopg.connect(config.DATABASE_URL, row_factory=dict_row)
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _sql(query: str) -> str:
    """SQL bir joyda `?` bilan yoziladi; Postgres uchun `%s` ga o'giriladi."""
    return query.replace("?", "%s") if _PG else query


@contextmanager
def _conn():
    """Ulanishni ochadi va HAR DOIM yopadi.

    sqlite3 da `with connect(...)` faqat tranzaksiyani yakunlaydi, ulanishni
    yopmaydi — shuning uchun yopishni o'zimiz qilamiz, aks holda ulanishlar
    to'planib qoladi.
    """
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _run(query: str, params: tuple = (), *, fetch: str | None = None) -> Any:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(_sql(query), params)
        if fetch == "one":
            row = cur.fetchone()
            return dict(row) if row else None
        if fetch == "all":
            return [dict(r) for r in cur.fetchall()]
        return None


def init_db() -> None:
    with _conn() as conn:
        if _PG:  # pragma: no cover
            with conn.cursor() as cur:
                cur.execute(_SCHEMA_PG)
        else:
            conn.executescript(_SCHEMA_SQLITE)


def backend_name() -> str:
    return "Postgres" if _PG else "SQLite"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Sessiyalar
# --------------------------------------------------------------------------

def create_session(sid: str, user: dict, state: dict) -> None:
    _run(
        "INSERT INTO sessions (id, tg_user_id, name, username, state, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            sid,
            int(user["id"]),
            (user.get("first_name") or "").strip() or None,
            user.get("username"),
            json.dumps(state, ensure_ascii=False),
            _now(),
        ),
    )


def load_session(sid: str) -> dict | None:
    row = _run("SELECT * FROM sessions WHERE id = ?", (sid,), fetch="one")
    if row is None:
        return None
    return {
        "id": row["id"],
        "tg_user_id": row["tg_user_id"],
        "name": row["name"],
        "username": row["username"],
        "state": json.loads(row["state"]),
        "final_level": row["final_level"],
        "summary": row["summary"],
        "finished_at": row["finished_at"],
    }


def save_state(sid: str, state: dict) -> None:
    _run(
        "UPDATE sessions SET state = ? WHERE id = ?",
        (json.dumps(state, ensure_ascii=False), sid),
    )


def finish_session(sid: str, state: dict, final_level: str, summary: str) -> None:
    _run(
        "UPDATE sessions SET state = ?, final_level = ?, summary = ?,"
        " finished_at = ? WHERE id = ?",
        (json.dumps(state, ensure_ascii=False), final_level, summary, _now(), sid),
    )


def find_active_session(tg_user_id: int) -> str | None:
    """Foydalanuvchining tugallanmagan oxirgi sessiyasi."""
    row = _run(
        "SELECT id FROM sessions WHERE tg_user_id = ? AND finished_at IS NULL"
        " ORDER BY created_at DESC LIMIT 1",
        (tg_user_id,),
        fetch="one",
    )
    return row["id"] if row else None


def abandon_unfinished(tg_user_id: int) -> None:
    """Yangi test boshlanganda eskilarini yopib qo'yadi."""
    _run(
        "UPDATE sessions SET finished_at = ?, final_level = 'abandoned'"
        " WHERE tg_user_id = ? AND finished_at IS NULL",
        (_now(), tg_user_id),
    )


def last_finished_session(tg_user_id: int) -> dict | None:
    """Oxirgi HAQIQATDAN tugallangan test ('abandoned' hisobga olinmaydi)."""
    row = _run(
        "SELECT id FROM sessions WHERE tg_user_id = ? AND finished_at IS NOT NULL"
        " AND final_level IS NOT NULL AND final_level != 'abandoned'"
        " ORDER BY finished_at DESC LIMIT 1",
        (tg_user_id,),
        fetch="one",
    )
    return load_session(row["id"]) if row else None


# --------------------------------------------------------------------------
# Admin paneli uchun
# --------------------------------------------------------------------------

def recent_results(limit: int = 100) -> list[dict]:
    return _run(
        "SELECT id, tg_user_id, name, username, final_level, finished_at"
        " FROM sessions WHERE finished_at IS NOT NULL"
        " AND final_level IS NOT NULL AND final_level != 'abandoned'"
        " ORDER BY finished_at DESC LIMIT ?",
        (limit,),
        fetch="all",
    )


def level_stats() -> dict[str, int]:
    """Daraja kesimida nechta o'quvchi tugatgan."""
    rows = _run(
        "SELECT final_level AS level, COUNT(*) AS n FROM sessions"
        " WHERE finished_at IS NOT NULL AND final_level IS NOT NULL"
        " AND final_level != 'abandoned' GROUP BY final_level",
        fetch="all",
    )
    return {r["level"]: int(r["n"]) for r in rows}


def totals() -> dict[str, int]:
    row = _run(
        "SELECT COUNT(*) AS total,"
        " SUM(CASE WHEN finished_at IS NOT NULL AND final_level != 'abandoned'"
        "          THEN 1 ELSE 0 END) AS finished"
        " FROM sessions",
        fetch="one",
    ) or {}
    return {
        "total": int(row.get("total") or 0),
        "finished": int(row.get("finished") or 0),
    }
