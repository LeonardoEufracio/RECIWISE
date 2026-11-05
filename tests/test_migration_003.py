import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url

from concurrency_support import ISOLATED_ONLY
from isolated_postgres import ROOT, bootstrap, connection
from postgres_support import snapshot

pytestmark = ISOLATED_ONLY
UP = (ROOT / "migrations/003_sprint1_concurrencia.sql").read_text(encoding="utf-8")
DOWN = (ROOT / "migrations/rollback/003_sprint1_concurrencia.sql").read_text(encoding="utf-8")


@contextmanager
def legacy_database(monkeypatch):
    # Parent URL has already passed the random marker/localhost checks.
    control = connection()
    token = uuid.uuid4().hex
    database = "reciwise_test_" + token
    control.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    control.close()
    url = make_url(os.environ["RECIWISE_TEST_DATABASE_URL"]).set(database=database).render_as_string(hide_password=False)
    with monkeypatch.context() as config:
        config.setenv("RECIWISE_ISOLATED_TOKEN", token)
        profiles = bootstrap(url, migrated=False, roles=False)
        conn = connection(url)
        try:
            yield conn, profiles
        finally:
            conn.execute("ROLLBACK")
            conn.close()
    # Database remains inside our owned disposable container, removed by runner.


def legacy_graph(conn, profiles):
    ids = {name: uuid.uuid4() for name in ("report", "vehicle", "vehicle2", "site")}
    conn.execute("""INSERT INTO public.reports(id,citizen_id,description,latitude,longitude,observed_at)
        VALUES (%s,%s,'Legacy ficticio',-12,-77,now())""", (ids["report"], profiles["citizen"]))
    for name in ("vehicle", "vehicle2"):
        conn.execute("INSERT INTO public.vehicles(id,label,vehicle_type) VALUES (%s,%s,'otro')", (ids[name], str(ids[name])))
    conn.execute("""INSERT INTO public.service_sites(id,name,site_type,latitude,longitude)
        VALUES (%s,'Sitio ficticio','ambos',-12,-77)""", (ids["site"],))
    return ids


@pytest.mark.parametrize("conflict", ["vehicle", "driver", "photos"])
def test_migration_aborts_without_repairing_conflicts(monkeypatch, conflict):
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
        with pytest.raises(psycopg.errors.RaiseException, match="003 blocked"):
            conn.execute(UP)
        conn.execute("ROLLBACK")
        assert snapshot(conn) == before
        assert conn.execute("SELECT to_regclass('public.photo_upload_operations')").fetchone()[0] is None
        assert conn.execute("""SELECT count(*) FROM information_schema.columns
            WHERE table_schema='public' AND table_name='report_photos' AND column_name='slot'"""
        ).fetchone()[0] == 0


def test_backfill_and_reversal_preserve_existing_rows(monkeypatch):
    with legacy_database(monkeypatch) as (conn, profiles):
        ids = legacy_graph(conn, profiles)
        for value in (3, 1, 2):
            conn.execute("""INSERT INTO public.report_photos(id,report_id,storage_path,content_type,size_bytes,created_at)
                VALUES (%s,%s,%s,'image/jpeg',1,'2026-01-01T00:00:00Z')""", (uuid.UUID(int=value), ids["report"], f"legacy/{value}"))
        before = snapshot(conn)
        conn.execute(UP)
        assert conn.execute("SELECT slot FROM public.report_photos ORDER BY id").fetchall() == [(1,), (2,), (3,)]
        conn.execute(DOWN)
        assert snapshot(conn) == before
        assert conn.execute("SELECT relrowsecurity FROM pg_class WHERE oid='public.photo_upload_operations_archive_003'::regclass").fetchone() == (True,)
        # Keeping the extension/archive must not prevent a later UP migration.
        conn.execute(UP)
        assert conn.execute("SELECT count(*) FROM public.report_photos").fetchone()[0] == 3


def test_reversal_refuses_unresolved_work_and_preserves_completed_journal(monkeypatch):
    with legacy_database(monkeypatch) as (conn, profiles):
        ids = legacy_graph(conn, profiles)
        conn.execute(UP)
        operation = uuid.uuid4()
        path = f"reports/{profiles['citizen']}/{ids['report']}/{operation}.jpg"
        conn.execute("""INSERT INTO public.photo_upload_operations(id,actor_id,report_id,bucket,storage_path,extension)
            VALUES (%s,%s,%s,'reciwise-reportes',%s,'jpg')""", (operation, profiles["citizen"], ids["report"], path))
        with pytest.raises(psycopg.errors.RaiseException, match="unresolved"):
            conn.execute(DOWN)
        conn.execute("ROLLBACK")
        assert conn.execute("SELECT state FROM public.photo_upload_operations WHERE id=%s", (operation,)).fetchone() == ("pending",)
        conn.execute("UPDATE public.photo_upload_operations SET state='rejected' WHERE id=%s", (operation,))
        conn.execute(DOWN)
        assert conn.execute("SELECT id FROM public.photo_upload_operations_archive_003").fetchone() == (operation,)
