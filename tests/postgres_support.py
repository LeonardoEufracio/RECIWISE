"""Opt-in PostgreSQL helpers. Never create schemas, commit, or load project secrets.

During migration 003 review, only the disposable localhost runner is allowed.
Default pytest skips when no test URL is provided; SQLite is forbidden here.
"""
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

from psycopg import sql

TABLES = (
    "profiles", "reports", "report_photos", "vehicles", "service_sites", "shifts",
    "events", "event_reports", "grouping_decisions",
)


def connect():
    from isolated_postgres import connection
    return connection()


@contextmanager
def transaction(conn, *, readonly=False):
    # Poolers may ignore startup options: enforce and verify inside each TX.
    conn.execute("BEGIN READ ONLY" if readonly else "BEGIN")
    try:
        conn.execute("SET LOCAL statement_timeout = '12s'")
        conn.execute("SET LOCAL lock_timeout = '2s'")
        if readonly:
            assert conn.execute("SHOW transaction_read_only").fetchone()[0] == "on"
        assert conn.execute("SHOW session_replication_role").fetchone()[0] == "origin"
        yield conn
    finally:
        # Never use a connection context manager: it commits on successful exit.
        conn.execute("ROLLBACK")


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, default=str,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def snapshot(conn):
    """Hash every field of every S1 row, without writing private content to disk."""
    result = {}
    for table in TABLES:
        rows = conn.execute(sql.SQL(
            "SELECT row_to_json(t) FROM public.{} t"
        ).format(sql.Identifier(table))).fetchall()
        hashes = sorted(digest(row[0]) for row in rows)
        result[table] = {"count": len(hashes), "sha256": digest(hashes)}
    return result


def evidence(name, data):
    target = os.getenv("RECIWISE_TEST_EVIDENCE_DIR")
    if target:
        directory = Path(target)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
