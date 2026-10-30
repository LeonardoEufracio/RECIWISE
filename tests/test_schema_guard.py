"""Real schema-gate acceptance tests; never substitute SQLite for PostgreSQL."""
import os
import socket
import threading
import traceback
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine, event
from sqlalchemy.exc import DBAPIError

from app import main
from app.schema_guard import SchemaCheckError, capture_catalog, verify_schema
from concurrency_support import ISOLATED_ONLY
from postgres_support import snapshot
from test_migration_003 import UP, legacy_database
from test_photo_restart import api_worker


@pytest.fixture
def guarded_database(monkeypatch):
    with legacy_database(monkeypatch) as (conn, profiles):
        conn.execute(UP)
        url = URL.create("postgresql+psycopg", username="postgres", host=conn.info.host,
                         port=conn.info.port, database=conn.info.dbname)
        engine = create_engine(url, connect_args={"connect_timeout": 2})
        monkeypatch.setattr(main, "get_engine", lambda: engine)
        try:
            yield conn, engine, profiles, url
        finally:
            engine.dispose()


@ISOLATED_ONLY
def test_complete_schema_starts_and_reports_readiness(guarded_database, monkeypatch):
    _, engine, _, _ = guarded_database
    checked_on_threads = []
    original = main.verify_schema
    def verify(target):
        checked_on_threads.append(threading.get_ident())
        return original(target)
    monkeypatch.setattr(main, "verify_schema", verify)
    caller = threading.get_ident()
    with TestClient(main.app) as client:
        assert client.get("/health").json() == {"status": "ok", "version": "0.1.0"}
        assert client.get("/ready").json() == {"status": "ready", "schema": "003"}
        assert client.get("/me").status_code == 401  # Business reached auth instead of a schema 503.
    assert checked_on_threads and caller not in checked_on_threads
    assert main.app.state.schema_compatible is False


@ISOLATED_ONLY
def test_001_without_003_is_rejected_without_migration(monkeypatch):
    with legacy_database(monkeypatch) as (conn, _):
        engine = create_engine(URL.create("postgresql+psycopg", username="postgres", host=conn.info.host,
                                          port=conn.info.port, database=conn.info.dbname))
        monkeypatch.setattr(main, "get_engine", lambda: engine)
        try:
            before = snapshot(conn)
            with pytest.raises(SchemaCheckError) as exc:
                with TestClient(main.app):
                    pytest.fail("The old schema cannot complete startup")
            assert exc.value.code == "schema_incompatible"
            assert snapshot(conn) == before
            assert conn.execute("SELECT to_regclass('public.photo_upload_operations')").fetchone() == (None,)
        finally:
            engine.dispose()


MUTATIONS = [
    ("missing-vehicle-exclusion", "ALTER TABLE public.shifts DROP CONSTRAINT shifts_vehicle_no_overlap"),
    ("wrong-driver-resource", """ALTER TABLE public.shifts DROP CONSTRAINT shifts_driver_no_overlap;
        ALTER TABLE public.shifts ADD CONSTRAINT shifts_driver_no_overlap EXCLUDE USING gist
        (vehicle_id WITH =,tstzrange(starts_at,ends_at,'[)') WITH &&) WHERE(status='programado')"""),
    ("wrong-range-boundary", """ALTER TABLE public.shifts DROP CONSTRAINT shifts_vehicle_no_overlap;
        ALTER TABLE public.shifts ADD CONSTRAINT shifts_vehicle_no_overlap EXCLUDE USING gist
        (vehicle_id WITH =,tstzrange(starts_at,ends_at,'[]') WITH &&) WHERE(status='programado')"""),
    ("wrong-reservation-predicate", """ALTER TABLE public.shifts DROP CONSTRAINT shifts_driver_no_overlap;
        ALTER TABLE public.shifts ADD CONSTRAINT shifts_driver_no_overlap EXCLUDE USING gist
        (driver_id WITH =,tstzrange(starts_at,ends_at,'[)') WITH &&) WHERE(status='cancelado')"""),
    ("nullable-slot", "ALTER TABLE public.report_photos ALTER COLUMN slot DROP NOT NULL"),
    ("wrong-slot-type", "ALTER TABLE public.report_photos ALTER COLUMN slot TYPE integer"),
    ("ineffective-slot-check", """ALTER TABLE public.report_photos DROP CONSTRAINT report_photos_slot_valid;
        ALTER TABLE public.report_photos ADD CONSTRAINT report_photos_slot_valid CHECK (true)"""),
    ("unvalidated-check", """ALTER TABLE public.report_photos DROP CONSTRAINT report_photos_slot_valid;
        ALTER TABLE public.report_photos ADD CONSTRAINT report_photos_slot_valid CHECK(slot BETWEEN 1 AND 3) NOT VALID"""),
    ("wrong-slot-unique", """ALTER TABLE public.report_photos DROP CONSTRAINT report_photos_report_slot_key;
        ALTER TABLE public.report_photos ADD CONSTRAINT report_photos_report_slot_key UNIQUE(report_id,slot,id)"""),
    ("missing-journal", "DROP TABLE public.photo_upload_operations"),
    ("missing-retry-column", "ALTER TABLE public.photo_upload_operations DROP COLUMN next_attempt_at"),
    ("ineffective-owned-path", """ALTER TABLE public.photo_upload_operations DROP CONSTRAINT photo_operation_owned_path;
        ALTER TABLE public.photo_upload_operations ADD CONSTRAINT photo_operation_owned_path CHECK(true)"""),
    ("wrong-journal-fk", """ALTER TABLE public.photo_upload_operations DROP CONSTRAINT photo_upload_operations_report_id_fkey;
        ALTER TABLE public.photo_upload_operations ADD CONSTRAINT photo_upload_operations_report_id_fkey
          FOREIGN KEY(report_id) REFERENCES public.reports(id) ON DELETE CASCADE"""),
    ("wrong-retry-index", """DROP INDEX public.photo_operations_due_idx;
        CREATE INDEX photo_operations_due_idx ON public.photo_upload_operations(next_attempt_at,id) WHERE state='complete'"""),
    ("journal-rls-disabled", "ALTER TABLE public.photo_upload_operations DISABLE ROW LEVEL SECURITY"),
    ("journal-access-granted", "GRANT SELECT ON public.photo_upload_operations TO anon"),
    ("journal-fk-enforcement-disabled", "ALTER TABLE public.photo_upload_operations DISABLE TRIGGER ALL"),
]


@ISOLATED_ONLY
@pytest.mark.parametrize("name,mutation", MUTATIONS, ids=[item[0] for item in MUTATIONS])
def test_partial_or_incompatible_003_refuses_startup(guarded_database, name, mutation):
    conn, engine, _, _ = guarded_database
    conn.execute(mutation)  # Deliberate drift in our disposable database only.
    before = snapshot(conn)
    with pytest.raises(SchemaCheckError) as exc:
        with TestClient(main.app):
            pytest.fail("Incompatible database must not serve traffic")
    assert exc.value.code == "schema_incompatible"
    assert snapshot(conn) == before
    assert main.app.state.schema_guard_started is False


@ISOLATED_ONLY
def test_guard_reads_only_and_always_rolls_back(guarded_database):
    conn, engine, _, _ = guarded_database
    before = snapshot(conn)
    catalog = capture_catalog(engine)
    statements, commits, rollbacks = [], [], []
    def statement(connection, cursor, sql, parameters, context, many):
        statements.append(sql)
    def committed(connection):
        commits.append(True)
    def rolled_back(connection):
        rollbacks.append(True)
    event.listen(engine, "before_cursor_execute", statement)
    event.listen(engine, "commit", committed)
    event.listen(engine, "rollback", rolled_back)
    try:
        verify_schema(engine)
    finally:
        event.remove(engine, "before_cursor_execute", statement)
        event.remove(engine, "commit", committed)
        event.remove(engine, "rollback", rolled_back)
    assert commits == [] and rollbacks == [True]
    assert statements[0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    assert all(sql.lstrip().split()[0] in {"SET", "SHOW", "SELECT"} for sql in statements)
    assert capture_catalog(engine) == catalog and snapshot(conn) == before


@ISOLATED_ONLY
def test_server_enforces_readonly_during_verification(guarded_database):
    conn, engine, _, _ = guarded_database
    failures = []
    def inject_write(connection, cursor, statement, parameters, context, many):
        if statement == "SHOW transaction_read_only":
            try:
                connection.exec_driver_sql("UPDATE public.vehicles SET available=available WHERE false")
            except DBAPIError as exc:
                failures.append(exc.orig.sqlstate)
                raise
    event.listen(engine, "after_cursor_execute", inject_write)
    try:
        with pytest.raises(SchemaCheckError):
            verify_schema(engine)
    finally:
        event.remove(engine, "after_cursor_execute", inject_write)
    assert failures == ["25006"]


@ISOLATED_ONLY
def test_btree_gist_in_extensions_schema_remains_compatible(guarded_database):
    conn, engine, _, _ = guarded_database
    conn.execute("CREATE SCHEMA extensions; ALTER EXTENSION btree_gist SET SCHEMA extensions")
    verify_schema(engine)


@ISOLATED_ONLY
def test_runtime_readiness_detects_drift_and_blocks_business(guarded_database):
    conn, _, _, _ = guarded_database
    with TestClient(main.app) as client:
        assert client.get("/ready").status_code == 200
        conn.execute("ALTER TABLE public.shifts DROP CONSTRAINT shifts_driver_no_overlap")
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        assert client.get("/me").status_code == 503
        assert client.post("/reports", json={}).status_code == 503


def test_skipping_lifespan_cannot_enable_business(monkeypatch):
    monkeypatch.setattr(main, "get_engine", lambda: pytest.fail("A probe must not bypass startup"))
    client = TestClient(main.app)
    try:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        for path in ("/me", "/reports/mine", "/municipal/reports"):
            assert client.get(path).status_code == 503
        unavailable = client.get("/me", headers={"Origin": "http://localhost:5173"})
        assert unavailable.status_code == 503
        assert unavailable.headers["access-control-allow-origin"] == "http://localhost:5173"
    finally:
        client.close()


def test_postgres_connection_failure_is_controlled_and_redacted(monkeypatch, caplog):
    # Reserve but do not listen on the port: no real database or secrets involved.
    with socket.socket() as socket_guard:
        socket_guard.bind(("127.0.0.1", 0))
        url = URL.create("postgresql+psycopg", username="private_test_user", password="fictitious_secret",
                         host="127.0.0.1", port=socket_guard.getsockname()[1], database="private_test_db")
        engine = create_engine(url, connect_args={"connect_timeout": 1})
        monkeypatch.setattr(main, "get_engine", lambda: engine)
        try:
            with pytest.raises(SchemaCheckError) as exc:
                with TestClient(main.app):
                    pytest.fail("Offline PostgreSQL cannot start")
            rendered = "".join(traceback.format_exception(exc.type, exc.value, exc.tb)) + caplog.text
            assert exc.value.code == "database_unavailable"
            assert all(value not in rendered for value in ("private_test_user", "fictitious_secret", "private_test_db"))
        finally:
            engine.dispose()


def test_non_postgres_production_engine_has_no_fallback(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    monkeypatch.setattr(main, "get_engine", lambda: engine)
    try:
        with pytest.raises(SchemaCheckError) as exc:
            with TestClient(main.app):
                pytest.fail("The deployed app cannot skip verification for SQLite")
        assert exc.value.code == "schema_incompatible"
    finally:
        engine.dispose()


@ISOLATED_ONLY
def test_process_restart_rechecks_correct_schema_and_keeps_records(guarded_database):
    _, _, profiles, url = guarded_database
    env = dict(os.environ, DATABASE_URL=url.render_as_string(hide_password=False),
        RECIWISE_TEST_DATABASE_URL=url.render_as_string(hide_password=False),
        RECIWISE_WORKER_CITIZEN=profiles["citizen"], RECIWISE_WORKER_MANAGER=profiles["manager"])
    headers = {"x-reciwise-test-actor": profiles["citizen"]}
    with api_worker(env) as (client, process):
        first_pid = process.pid
        assert client.get("/ready").json() == {"status": "ready", "schema": "003"}
        response = client.post("/reports", headers=headers, json={"description": "Reporte aislado de reinicio",
            "latitude": -12, "longitude": -77, "observed_at": datetime.now(timezone.utc).isoformat()})
        assert response.status_code == 201
        report = response.json()
    with api_worker(env) as (client, process):
        assert process.pid != first_pid
        assert client.get("/ready").status_code == 200
        assert client.get(f"/reports/{report['id']}", headers=headers).json() == report
