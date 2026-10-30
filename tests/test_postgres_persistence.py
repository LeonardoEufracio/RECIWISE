"""Read existing pilot records before/after restarting our own FastAPI process."""
import hashlib
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from postgres_support import TABLES, connect, digest, evidence, snapshot, transaction

pytestmark = pytest.mark.skipif(
    not os.getenv("RECIWISE_TEST_DATABASE_URL"),
    reason="Explicit PostgreSQL test URL required; no SQLite fallback",
)


@pytest.fixture
def anchors():
    conn = connect()
    try:
        with transaction(conn, readonly=True):
            report = conn.execute("""SELECT r.id,r.citizen_id FROM public.reports r
                JOIN public.profiles p ON p.id=r.citizen_id AND p.role='ciudadano'
                WHERE EXISTS(SELECT 1 FROM public.report_photos ph WHERE ph.report_id=r.id)
                ORDER BY r.created_at,r.id LIMIT 1"""
            ).fetchone()
            shift = conn.execute("""SELECT s.id,s.vehicle_id,s.departure_site_id,s.disposal_site_id,
                s.created_by FROM public.shifts s
                JOIN public.vehicles v ON v.id=s.vehicle_id
                JOIN public.profiles p ON p.id=s.created_by AND p.role='encargado_municipal'
                WHERE v.label='Compactadora Piloto 01' AND s.status='programado'
                ORDER BY s.created_at,s.id LIMIT 1"""
            ).fetchone()
        if not report or not shift:
            pytest.skip("Existing report/photos and programmed pilot shift required; no records created")
        return dict(report=str(report[0]), citizen=str(report[1]), shift=str(shift[0]),
                    vehicle=str(shift[1]), departure=str(shift[2]), disposal=str(shift[3]),
                    manager=str(shift[4]))
    finally:
        conn.close()


@contextmanager
def server(anchors):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(RECIWISE_TEST_PORT=str(port), RECIWISE_TEST_CITIZEN_ID=anchors["citizen"],
               RECIWISE_TEST_MANAGER_ID=anchors["manager"])
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("_persistence_worker.py"))],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=35, trust_env=False) as client:
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                assert proc.poll() is None, "Persistence worker exited; no credentials logged"
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("Local persistence worker did not become ready")
            # Enforce safety in addition to database READ ONLY transactions.
            assert client.post("/health").status_code == 405
            yield client, proc.pid
    finally:
        # Only stop the process created by this test; leave existing FastAPI alone.
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)


def get(client, path, actor):
    response = client.get(path, headers={"x-reciwise-test-actor": actor})
    assert response.status_code == 200, f"GET {path.split('?')[0]} returned {response.status_code}"
    return response.json()


def api_snapshot(client, anchors):
    mine = get(client, "/reports/mine?limit=100", anchors["citizen"])
    report = get(client, f"/reports/{anchors['report']}", anchors["citizen"])
    assert any(row["id"] == anchors["report"] for row in mine)
    municipal = get(client, "/municipal/reports?limit=200", anchors["manager"])
    assert any(row["id"] == anchors["report"] for row in municipal)
    result = {"report": report}
    for key, path in [("vehicle", "vehicles"), ("shift", "shifts"),
                      ("departure", "sites"), ("disposal", "sites")]:
        rows = get(client, f"/municipal/{path}", anchors["manager"])
        matches = [row for row in rows if row["id"] == anchors[key]]
        assert len(matches) == 1, f"Existing {key} missing from API response"
        result[key] = matches[0]
    return result


def db_snapshot():
    conn = connect()
    try:
        with transaction(conn, readonly=True):
            return snapshot(conn)
    finally:
        conn.close()


def test_existing_records_survive_fastapi_restart(anchors):
    before_db = db_snapshot()
    with server(anchors) as (client, first_pid):
        first = api_snapshot(client, anchors)
    # This is a real OS process restart and fresh SQLAlchemy connection pool.
    with server(anchors) as (client, second_pid):
        second = api_snapshot(client, anchors)
    after_db = db_snapshot()
    unchanged = {key: digest(first[key]) == digest(second[key]) for key in first}
    evidence("persistence.json", {
        "authentication": "test-only existing-profile dependency override; no real user JWT",
        "database": "real PostgreSQL, explicit READ ONLY; existing records only",
        "process_ids": [first_pid, second_pid], "record_ids": anchors,
        "fields_before": {key: digest(value) for key, value in first.items()},
        "fields_after": {key: digest(value) for key, value in second.items()},
        "same_fields": unchanged, "all_s1_data_unchanged": before_db == after_db,
    })
    assert first_pid != second_pid
    assert all(unchanged.values()), "Existing API fields changed across restart"
    assert before_db == after_db, "S1 database fields changed across restart"


def photo_snapshot(client, anchors):
    photos = get(client, f"/reports/{anchors['report']}/photos", anchors["citizen"])
    assert photos, "Existing photo metadata not returned"
    result = []
    with httpx.Client(timeout=30, trust_env=False) as storage:
        for photo in photos:
            signed_url = photo.pop("signed_url")
            assert signed_url, "Storage did not return a signed URL"
            response = storage.get(signed_url)
            assert response.status_code == 200, f"Signed photo GET returned {response.status_code}"
            assert len(response.content) == photo["size_bytes"]
            result.append({"metadata": photo, "bytes_sha256": hashlib.sha256(response.content).hexdigest()})
    return sorted(result, key=lambda row: row["metadata"]["id"])


def test_existing_photographs_survive_fastapi_restart(anchors):
    if not os.getenv("RECIWISE_STORAGE_URL") or not os.getenv("RECIWISE_STORAGE_KEY"):
        pytest.skip("Real Storage configuration needed for signed image reads; no upload performed")
    before_db = db_snapshot()
    with server(anchors) as (client, first_pid):
        first = photo_snapshot(client, anchors)
    with server(anchors) as (client, second_pid):
        second = photo_snapshot(client, anchors)
    after_db = db_snapshot()
    evidence("photo-persistence.json", {
        "authentication": "test-only profile override; real Storage signer and object GET",
        "process_ids": [first_pid, second_pid],
        "photo_ids": [row["metadata"]["id"] for row in first],
        "before": first, "after": second, "unchanged": first == second,
        "all_s1_data_unchanged": before_db == after_db,
    })
    assert first_pid != second_pid
    assert first == second, "Photo IDs, metadata or object bytes changed across restart"
    assert before_db == after_db


@pytest.mark.parametrize("table", TABLES)
def test_anonymous_rest_cannot_read_protected_tables(table):
    base, key = os.getenv("RECIWISE_PUBLIC_URL"), os.getenv("RECIWISE_PUBLIC_KEY")
    if not base or not key:
        pytest.skip("Public Supabase URL/key required for anonymous REST check")
    response = httpx.get(f"{base.rstrip('/')}/rest/v1/{table}?select=*&limit=1",
                         headers={"apikey": key}, timeout=20, trust_env=False)
    # Assert explicit ACL denial, not just an empty result from a possibly empty table.
    assert response.status_code in (401, 403)
    assert response.json().get("code") == "42501"


def test_authenticated_user_rest_cannot_read_protected_tables():
    token = os.getenv("RECIWISE_CITIZEN_ACCESS_TOKEN")
    if not token:
        pytest.skip("No real citizen JWT: SQL SET ROLE checks do not replace a user session")
    base, key = os.getenv("RECIWISE_PUBLIC_URL"), os.getenv("RECIWISE_PUBLIC_KEY")
    if not base or not key:
        pytest.skip("Public Supabase URL/key required")
    with httpx.Client(timeout=20, trust_env=False) as client:
        # Verify the supplied JWT is accepted before interpreting permission denials.
        user = client.get(f"{base.rstrip('/')}/auth/v1/user",
                          headers={"apikey": key, "Authorization": f"Bearer {token}"})
        assert user.status_code == 200, "Provided citizen token is invalid or expired"
        for table in TABLES:
            response = client.get(f"{base.rstrip('/')}/rest/v1/{table}?select=*&limit=1",
                                  headers={"apikey": key, "Authorization": f"Bearer {token}"})
            assert response.status_code in (401, 403)
            assert response.json().get("code") == "42501"
