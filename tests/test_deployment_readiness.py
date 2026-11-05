"""Read-only diagnostics and regression for refused legacy-schema startup."""
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app
from app import main
from app.schema_guard import SchemaCheckError
from app.security import Actor, get_current_actor
from concurrency_support import ISOLATED_ONLY, pg_case
from isolated_postgres import connection
from postgres_support import snapshot
from scripts import d2_preflight
from test_migration_003 import legacy_database, legacy_graph


@ISOLATED_ONLY
def test_preflight_keeps_all_existing_rows_and_reports_readonly(pg_case):
    _, _, ids, _ = pg_case
    conn = connection()
    try:
        before = snapshot(conn)
        journal_before = conn.execute("SELECT count(*) FROM public.photo_upload_operations").fetchone()
        report = d2_preflight.collect(conn)
        assert report["transaction_read_only"] == "on"
        assert report["transaction_isolation"] == "repeatable read"
        assert snapshot(conn) == before
        assert conn.execute("SELECT count(*) FROM public.photo_upload_operations").fetchone() == journal_before
        assert conn.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        # The local bootstrap has no real Storage catalog: never translate missing evidence to zero.
        assert report["sections"]["storage_metadata"]["unavailable"] is True
        assert "storage_metadata" in report["query_errors"]
        serialized = json.dumps(report, default=str)
        assert str(ids["citizen"]) not in serialized
        assert "Reporte aislado de concurrencia" not in serialized
    finally:
        conn.close()


@ISOLATED_ONLY
@pytest.mark.parametrize("statement", [
    "UPDATE public.vehicles SET available=available WHERE false",
    "DELETE FROM public.photo_upload_operations WHERE false",
    "CREATE TABLE public.audit_must_not_exist(id integer)",
    "SELECT id FROM public.reports FOR UPDATE",
])
def test_preflight_transaction_rejects_writes_and_row_locks(statement):
    conn = connection()
    try:
        with d2_preflight.readonly(conn):
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction) as exc:
                conn.execute(statement)
            assert exc.value.sqlstate == "25006"
        assert conn.execute("SELECT to_regclass('public.audit_must_not_exist')").fetchone() == (None,)
    finally:
        conn.close()


@ISOLATED_ONLY
@pytest.mark.parametrize("conflict", ["vehicle", "driver", "photos"])
def test_preflight_detects_conflicts_without_repairing_them(monkeypatch, conflict):
    with legacy_database(monkeypatch) as (conn, profiles):
        ids = legacy_graph(conn, profiles)
        if conflict == "photos":
            for _ in range(4):
                conn.execute("""INSERT INTO public.report_photos(report_id,storage_path,content_type,size_bytes)
                    VALUES (%s,%s,'image/jpeg',1)""", (ids["report"], str(uuid.uuid4())))
        else:
            start = datetime(2030, 1, 1, tzinfo=timezone.utc)
            for index in range(2):
                vehicle = ids["vehicle2"] if index and conflict == "driver" else ids["vehicle"]
                driver = profiles["driver2"] if index and conflict == "vehicle" else profiles["driver"]
                conn.execute("""INSERT INTO public.shifts(vehicle_id,driver_id,departure_site_id,
                    disposal_site_id,starts_at,ends_at,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (vehicle, driver, ids["site"], ids["site"], start, start+timedelta(hours=1), profiles["manager"]))
        before = snapshot(conn)
        report = d2_preflight.collect(conn)
        counts = report["sections"]["conflicts"][0]
        assert counts[{"vehicle": "vehicle_overlap_pairs", "driver": "driver_overlap_pairs",
                       "photos": "reports_over_three_photos"}[conflict]] == 1
        assert report["sections"]["journal"] == {"not_present": True}
        assert snapshot(conn) == before


@ISOLATED_ONLY
def test_backend_refuses_legacy_schema_at_startup(monkeypatch):
    # Regression for the prior NO-GO finding; the old schema must never serve business traffic.
    with legacy_database(monkeypatch) as (conn, profiles):
        ids = legacy_graph(conn, profiles)
        conn.execute("UPDATE public.vehicles SET available=true")
        engine = create_engine(URL.create("postgresql+psycopg", username="postgres", host=conn.info.host,
                                         port=conn.info.port, database=conn.info.dbname))
        monkeypatch.setattr(main, "get_engine", lambda: engine)
        def database():
            with Session(engine) as db:
                yield db
        saved = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_actor] = lambda: Actor(uuid.UUID(profiles["manager"]), "encargado_municipal")
        try:
            with pytest.raises(SchemaCheckError):
                with TestClient(app):
                    pytest.fail("Legacy schema must not complete startup")
            # Deliberately do not enter lifespan, as with an ASGI server configured to skip it.
            client = TestClient(app, raise_server_exceptions=False)
            try:
                assert client.get("/health").status_code == 200
                assert client.get("/ready").status_code == 503
                assert client.get(f"/reports/{ids['report']}/photos").status_code == 503
                assert client.post("/municipal/shifts", json={}).status_code == 503
                assert conn.execute("SELECT count(*) FROM public.shifts").fetchone() == (0,)
            finally:
                client.close()
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(saved)
            engine.dispose()


def test_audit_output_cannot_overwrite_env(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["d2_preflight.py", "--from-project-env", "--output", ".env"])
    monkeypatch.setattr(d2_preflight, "dotenv_values", lambda *args: pytest.fail("Must refuse before reading credentials"))
    with pytest.raises(SystemExit) as exc:
        d2_preflight.main()
    assert exc.value.code == 2


def test_audit_rejects_sqlite_without_fallback(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["d2_preflight.py"])
    monkeypatch.setenv("RECIWISE_AUDIT_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    assert d2_preflight.main() == 2
    assert json.loads(capsys.readouterr().out)["error_type"] == "ValueError"
