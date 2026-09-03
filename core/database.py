import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import settings
from core.schemas import DecisionRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    eventid      TEXT    NOT NULL,
    hostname     TEXT    NOT NULL,
    problem_name TEXT    NOT NULL,
    severity     INTEGER NOT NULL,
    action       TEXT    NOT NULL,
    family       TEXT    NOT NULL,
    reasoning    TEXT    NOT NULL,
    confidence   REAL    NOT NULL,
    message      TEXT    NOT NULL,
    dry_run      INTEGER NOT NULL,
    steps_used   INTEGER NOT NULL,
    duration_ms  INTEGER NOT NULL,
    llm_model    TEXT    NOT NULL,
    created_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eventid    ON decisions(eventid);
CREATE INDEX IF NOT EXISTS idx_created_at ON decisions(created_at);
"""


@contextmanager
def get_connection():
    conn = sqlite3.connect(settings.db_file, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)


def save_decision(record: DecisionRecord) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO decisions (
                eventid, hostname, problem_name, severity, action, family,
                reasoning, confidence, message, dry_run, steps_used,
                duration_ms, llm_model, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.eventid,
                record.hostname,
                record.problem_name,
                record.severity,
                record.action,
                record.family,
                record.reasoning,
                record.confidence,
                record.message,
                int(record.dry_run),
                record.steps_used,
                record.duration_ms,
                record.llm_model,
                record.created_at or datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return cur.lastrowid


def already_processed(eventid: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM decisions WHERE eventid = ? LIMIT 1", (eventid,)
        ).fetchone()
        return row is not None


def get_recent_decisions(limit: int = 50) -> list[DecisionRecord]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [DecisionRecord(**dict(r)) for r in rows]


def get_decision(decision_id: int) -> DecisionRecord | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM decisions WHERE id = ?", (decision_id,)
        ).fetchone()
        return DecisionRecord(**dict(row)) if row else None


def get_stats() -> dict:
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM decisions"
        ).fetchone()["n"]
        acked = conn.execute(
            "SELECT COUNT(*) AS n FROM decisions WHERE action = 'ACKNOWLEDGE'"
        ).fetchone()["n"]
        escalated = conn.execute(
            "SELECT COUNT(*) AS n FROM decisions WHERE action = 'ESCALATE'"
        ).fetchone()["n"]
        avg_ms = conn.execute(
            "SELECT COALESCE(AVG(duration_ms), 0) AS v FROM decisions"
        ).fetchone()["v"]
        avg_conf = conn.execute(
            "SELECT COALESCE(AVG(confidence), 0) AS v FROM decisions"
        ).fetchone()["v"]
        return {
            "total": total,
            "acknowledged": acked,
            "escalated": escalated,
            "ack_rate": round(100 * acked / total, 1) if total else 0.0,
            "avg_duration_s": round(avg_ms / 1000, 1),
            "avg_confidence": round(avg_conf, 2),
        }
