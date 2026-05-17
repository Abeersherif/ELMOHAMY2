"""
Runtime store — persistent chat history + audit log.
Lives in mohamy_runtime.db (separate from law_database.db).
"""
import json
import logging
import os
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mohamy.runtime")

BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DB_PATH = os.getenv("RUNTIME_DB_PATH", str(BASE_DIR / "mohamy_runtime.db"))

CHAT_RETENTION_DAYS = int(os.getenv("CHAT_RETENTION_DAYS", "90"))
AUDIT_RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "30"))

# PII patterns redacted from audit logs (Egyptian context)
_PII_PATTERNS = [
    (re.compile(r"\b\d{14}\b"), "[NATIONAL_ID]"),
    (re.compile(r"(?<!\d)(?:\+?20|0020)?0?1[0125]\d{8}\b"), "[PHONE]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[CARD]"),
]


def redact_pii(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    redacted = text
    for pattern, placeholder in _PII_PATTERNS:
        redacted = pattern.sub(placeholder, redacted)
    return redacted


_lock = threading.RLock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(RUNTIME_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_schema() -> None:
    with _lock, _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                user_msg    TEXT,
                bot_msg     TEXT,
                articles    TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_chat_session
                ON chat_sessions(session_id, id);

            CREATE TABLE IF NOT EXISTS audit_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
                session_id      TEXT,
                event_type      TEXT NOT NULL,
                query           TEXT,
                answer_text     TEXT,
                intent          TEXT,
                target_tables   TEXT,
                retrieved_count INTEGER,
                retrieved_refs  TEXT,
                filtered_count  INTEGER,
                filtered_refs   TEXT,
                source          TEXT,
                latency_ms      INTEGER,
                error           TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_audit_session
                ON audit_log(session_id, id);
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON audit_log(timestamp);

            CREATE TABLE IF NOT EXISTS consents (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                kind        TEXT NOT NULL,
                accepted    INTEGER NOT NULL,
                ip          TEXT,
                user_agent  TEXT,
                accepted_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_consents_session
                ON consents(session_id);

            CREATE TABLE IF NOT EXISTS reports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                reason      TEXT,
                message_ref TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_reports_session
                ON reports(session_id);
            """
        )
        # Migrations for existing DBs (add columns idempotently)
        audit_cols = {r[1] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()}
        for col_name in ("answer_text", "rulings_refs"):
            if col_name not in audit_cols:
                try:
                    conn.execute(f"ALTER TABLE audit_log ADD COLUMN {col_name} TEXT")
                    logger.info(f"📒 Migrated audit_log: added {col_name} column")
                except sqlite3.OperationalError as e:
                    logger.warning(f"audit_log migration ({col_name}) skipped: {e}")

        # Privacy isolation — owner_id per browser. Chats from before this
        # migration have no owner, so we wipe them (per product decision) and
        # orphan old audit/reports rows so they become invisible to all owners.
        chat_cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_sessions)").fetchall()}
        if "owner_id" not in chat_cols:
            wiped = conn.execute("DELETE FROM chat_sessions").rowcount
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN owner_id TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_owner ON chat_sessions(owner_id, session_id, id)")
            logger.info(f"🔒 Privacy migration: wiped {wiped} pre-owner chat rows, added owner_id")

        if "owner_id" not in audit_cols:
            conn.execute("ALTER TABLE audit_log ADD COLUMN owner_id TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_owner ON audit_log(owner_id, id)")
            logger.info("🔒 Privacy migration: added owner_id to audit_log (old rows orphaned)")

        reports_cols = {r[1] for r in conn.execute("PRAGMA table_info(reports)").fetchall()}
        if "owner_id" not in reports_cols:
            conn.execute("ALTER TABLE reports ADD COLUMN owner_id TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_owner ON reports(owner_id, id)")
            logger.info("🔒 Privacy migration: added owner_id to reports (old rows orphaned)")

        consents_cols = {r[1] for r in conn.execute("PRAGMA table_info(consents)").fetchall()}
        if "owner_id" not in consents_cols:
            conn.execute("ALTER TABLE consents ADD COLUMN owner_id TEXT")
            logger.info("🔒 Privacy migration: added owner_id to consents")

    logger.info(f"📒 Runtime store ready at {RUNTIME_DB_PATH}")


# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------
def append_turn(
    session_id: str,
    owner_id: str,
    user_msg: str,
    bot_msg: str,
    articles: Optional[List[Dict[str, Any]]] = None,
) -> None:
    if not session_id or not owner_id:
        logger.warning("append_turn called with empty session_id/owner_id — skipping")
        return
    try:
        with _lock, _connect() as conn:
            cur = conn.execute(
                "INSERT INTO chat_sessions (session_id, owner_id, user_msg, bot_msg, articles) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, owner_id, user_msg, bot_msg,
                 json.dumps(articles, ensure_ascii=False) if articles else None),
            )
            logger.info(
                f"💾 chat_sessions saved: session={session_id[:8]}… id={cur.lastrowid}"
            )
    except Exception as e:
        logger.error(f"❌ append_turn failed: {e}", exc_info=True)


def delete_last_turns(session_id: str, owner_id: str, count: int) -> int:
    """Delete the most recent N turns for a session owned by owner_id."""
    if not session_id or not owner_id or count < 1:
        return 0
    with _lock, _connect() as conn:
        cur = conn.execute(
            "DELETE FROM chat_sessions WHERE id IN "
            "(SELECT id FROM chat_sessions "
            " WHERE session_id = ? AND owner_id = ? "
            " ORDER BY id DESC LIMIT ?)",
            (session_id, owner_id, count),
        )
        logger.info(
            f"🗑️ chat_sessions trimmed: session={session_id[:8]}… removed={cur.rowcount}"
        )
        return cur.rowcount


def fetch_history(session_id: str, owner_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    if not session_id or not owner_id:
        return []
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT id, user_msg, bot_msg, articles, created_at "
            "FROM chat_sessions WHERE session_id = ? AND owner_id = ? "
            "ORDER BY id ASC LIMIT ?",
            (session_id, owner_id, limit),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "user": r["user_msg"],
            "bot": r["bot_msg"],
            "articles": json.loads(r["articles"]) if r["articles"] else [],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def list_sessions(owner_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Chat sessions belonging to one owner — sidebar list."""
    if not owner_id:
        return []
    with _lock, _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                session_id,
                (SELECT user_msg FROM chat_sessions cs2
                 WHERE cs2.session_id = cs.session_id AND cs2.owner_id = ?
                 ORDER BY id ASC LIMIT 1)               AS title,
                MAX(created_at)                         AS last_at,
                COUNT(*)                                AS turns
            FROM chat_sessions cs
            WHERE cs.owner_id = ?
            GROUP BY session_id
            ORDER BY MAX(id) DESC
            LIMIT ?
            """,
            (owner_id, owner_id, limit),
        ).fetchall()
    return [
        {
            "session_id": r["session_id"],
            "title": (r["title"] or "محادثة").strip()[:80],
            "last_at": r["last_at"],
            "turns": r["turns"],
        }
        for r in rows
    ]


def record_consent(
    session_id: str,
    owner_id: str,
    kind: str,
    accepted: bool,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    if not session_id or not owner_id or not kind:
        return
    try:
        with _lock, _connect() as conn:
            conn.execute(
                "INSERT INTO consents (session_id, owner_id, kind, accepted, ip, user_agent) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, owner_id, kind, 1 if accepted else 0, ip, user_agent),
            )
    except Exception as e:
        logger.error(f"❌ record_consent failed: {e}")


def record_report(
    session_id: str,
    owner_id: str,
    reason: Optional[str] = None,
    message_ref: Optional[str] = None,
) -> None:
    if not session_id or not owner_id:
        return
    try:
        with _lock, _connect() as conn:
            conn.execute(
                "INSERT INTO reports (session_id, owner_id, reason, message_ref) "
                "VALUES (?, ?, ?, ?)",
                (session_id, owner_id, redact_pii(reason), message_ref),
            )
    except Exception as e:
        logger.error(f"❌ record_report failed: {e}")


def cleanup_expired(
    chat_days: int = CHAT_RETENTION_DAYS,
    audit_days: int = AUDIT_RETENTION_DAYS,
) -> Dict[str, int]:
    """Delete chat turns older than chat_days and audit rows older than audit_days.
    Pass 0 to disable that retention. Returns counts of deleted rows."""
    deleted = {"chat": 0, "audit": 0}
    with _lock, _connect() as conn:
        if chat_days > 0:
            cur = conn.execute(
                "DELETE FROM chat_sessions WHERE created_at < datetime('now', ?)",
                (f"-{chat_days} days",),
            )
            deleted["chat"] = cur.rowcount
        if audit_days > 0:
            cur = conn.execute(
                "DELETE FROM audit_log WHERE timestamp < datetime('now', ?)",
                (f"-{audit_days} days",),
            )
            deleted["audit"] = cur.rowcount
    if deleted["chat"] or deleted["audit"]:
        logger.info(
            f"🧹 Retention cleanup: removed {deleted['chat']} chat turns "
            f"(>{chat_days}d) + {deleted['audit']} audit rows (>{audit_days}d)"
        )
    return deleted


def delete_session(session_id: str, owner_id: str) -> int:
    if not session_id or not owner_id:
        return 0
    with _lock, _connect() as conn:
        cur = conn.execute(
            "DELETE FROM chat_sessions WHERE session_id = ? AND owner_id = ?",
            (session_id, owner_id),
        )
        return cur.rowcount


def recent_turns_for_reformulation(
    session_id: str, owner_id: str, limit: int = 3
) -> List[Dict[str, str]]:
    """Last N turns shaped for the router's reformulate_query (user/bot keys)."""
    if not session_id or not owner_id:
        return []
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT user_msg, bot_msg FROM chat_sessions "
            "WHERE session_id = ? AND owner_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, owner_id, limit),
        ).fetchall()
    return list(reversed([{"user": r["user_msg"] or "", "bot": r["bot_msg"] or ""} for r in rows]))


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
def _refs(articles: List[Dict[str, Any]]) -> str:
    return json.dumps(
        [
            {
                "table": a.get("table"),
                "id": a.get("id"),
                "law_name": a.get("law_name"),
                "main_category": a.get("main_category"),
                "number": a.get("number"),
                "titel": (a.get("titel") or "")[:120],
                "is_cancelled": bool(a.get("is_cancelled")),
                "cancellation_signal": a.get("cancellation_signal") or "",
            }
            for a in articles
        ],
        ensure_ascii=False,
    )


def fetch_reports(
    owner_id: str,
    session_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    if not owner_id:
        return []
    with _lock, _connect() as conn:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM reports WHERE owner_id = ? AND session_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (owner_id, session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reports WHERE owner_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (owner_id, limit),
            ).fetchall()
    return [dict(r) for r in rows]


def log_audit(
    event_type: str,
    session_id: Optional[str] = None,
    owner_id: Optional[str] = None,
    query: Optional[str] = None,
    answer_text: Optional[str] = None,
    intent: Optional[str] = None,
    target_tables: Optional[List[str]] = None,
    retrieved: Optional[List[Dict[str, Any]]] = None,
    filtered: Optional[List[Dict[str, Any]]] = None,
    rulings: Optional[List[Dict[str, Any]]] = None,
    source: Optional[str] = None,
    latency_ms: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    try:
        rulings_json = None
        if rulings:
            rulings_json = json.dumps(
                [
                    {
                        "id": r.get("id"),
                        "titel": r.get("titel"),
                        "date": r.get("date"),
                        "linked": bool(r.get("linked")),
                    }
                    for r in rulings
                ],
                ensure_ascii=False,
            )
        with _lock, _connect() as conn:
            conn.execute(
                "INSERT INTO audit_log "
                "(timestamp, session_id, owner_id, event_type, query, answer_text, intent, target_tables, "
                " retrieved_count, retrieved_refs, filtered_count, filtered_refs, "
                " rulings_refs, source, latency_ms, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    session_id,
                    owner_id,
                    event_type,
                    redact_pii(query),
                    redact_pii(answer_text),
                    intent,
                    json.dumps(target_tables, ensure_ascii=False) if target_tables else None,
                    len(retrieved) if retrieved is not None else None,
                    _refs(retrieved) if retrieved else None,
                    len(filtered) if filtered is not None else None,
                    _refs(filtered) if filtered else None,
                    rulings_json,
                    source,
                    latency_ms,
                    error,
                ),
            )
    except Exception as e:
        logger.error(f"❌ Audit write failed: {e}")


def fetch_audit(
    owner_id: str,
    session_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    if not owner_id:
        return []
    with _lock, _connect() as conn:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE owner_id = ? AND session_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (owner_id, session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE owner_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (owner_id, limit),
            ).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        for json_field in ("target_tables", "retrieved_refs", "filtered_refs"):
            if d.get(json_field):
                try:
                    d[json_field] = json.loads(d[json_field])
                except Exception:
                    pass
        out.append(d)
    return out
