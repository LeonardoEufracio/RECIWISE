import inspect
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO

import psycopg
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import main
from app.db_errors import diagnostics
from app.models import PhotoUploadOperation, Report, ReportPhoto
from app.security import Actor
from concurrency_support import FakeStorage, ISOLATED_ONLY, pg_case
from isolated_postgres import connection

pytestmark = ISOLATED_ONLY
IMAGE = b"\xff\xd8\xffsynthetic-image"


@pytest.fixture
def photo_case(pg_case, monkeypatch):
    client, engine, ids, state = pg_case
    state["actor"] = Actor(ids["citizen"], "ciudadano")
    storage = FakeStorage()
    monkeypatch.setattr(main, "put_private_image", storage.upload)
    monkeypatch.setattr(main, "remove_private_image", storage.remove)
    monkeypatch.setattr(main, "signed_image_url", lambda path: "https://storage.invalid/signed")
    return client, engine, ids, storage


def upload(client, report_id):
    return client.post(f"/reports/{report_id}/photos", files={
        "file": ("photo.jpg", BytesIO(IMAGE), "image/jpeg")})


@pytest.mark.parametrize("existing", [0, 2])
def test_parallel_uploads_never_exceed_three_postgres(photo_case, existing):
    client, engine, ids, storage = photo_case
    for _ in range(existing):
        assert upload(client, ids["report"]).status_code == 201
    barrier = threading.Barrier(6, timeout=10)

    def simultaneous():
        barrier.wait()
        return upload(client, ids["report"])

    with ThreadPoolExecutor(6) as pool:
        responses = list(pool.map(lambda _: simultaneous(), range(6)))
    assert sorted(r.status_code for r in responses) == sorted([201] * (3 - existing) + [409] * (3 + existing))
    with Session(engine) as db:
        photos = list(db.scalars(select(ReportPhoto).where(ReportPhoto.report_id == ids["report"])))
        assert sorted(photo.slot for photo in photos) == [1, 2, 3]
        assert set(photo.storage_path for photo in photos) == set(storage.objects)
    assert len(storage.objects) == 3
    assert storage.deletions == []
    successful = next(r for r in responses if r.status_code == 201)
    assert set(successful.json()) == {"id", "report_id", "content_type", "size_bytes", "created_at", "signed_url"}
    assert len(client.get(f"/reports/{ids['report']}/photos").json()) == 3


def test_different_reports_upload_independently(photo_case):
    client, engine, ids, storage = photo_case
    second_id = uuid.uuid4()
    with Session(engine) as db:
        db.add(Report(id=second_id, citizen_id=ids["citizen"], description="Otro reporte aislado",
            latitude=-12, longitude=-77, observed_at=datetime.now(timezone.utc)))
        db.commit()
    storage.barrier = threading.Barrier(2)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda rid: upload(client, rid), [ids["report"], second_id]))
    assert [r.status_code for r in results] == [201, 201]
    assert len(storage.objects) == 2
    assert not inspect.iscoroutinefunction(main.upload_photo)
    assert not inspect.iscoroutinefunction(main.list_photos)


@pytest.mark.parametrize("contents,status", [(b"not-an-image", 415), (b"x" * (5 * 1024 * 1024 + 1), 413)])
def test_invalid_photo_is_rejected_before_intent_or_storage(photo_case, contents, status):
    client, engine, ids, storage = photo_case
    response = client.post(f"/reports/{ids['report']}/photos", files={"file": ("photo.jpg", contents, "image/jpeg")})
    assert response.status_code == status
    assert storage.objects == {} and storage.deletions == []
    with Session(engine) as db:
        assert db.scalar(select(ReportPhoto).where(ReportPhoto.report_id == ids["report"])) is None
        assert db.scalar(select(PhotoUploadOperation).where(PhotoUploadOperation.report_id == ids["report"])) is None


def test_existing_report_endpoints_work_with_postgres(pg_case):
    client, _, ids, state = pg_case
    state["actor"] = Actor(ids["citizen"], "ciudadano")
    response = client.post("/reports", json={"description": "Reporte nuevo desde FastAPI",
        "latitude": -12.5, "longitude": -77.1, "observed_at": datetime.now(timezone.utc).isoformat()})
    assert response.status_code == 201
    report = response.json()
    assert report["citizen_id"] == str(ids["citizen"]) and report["latitude"] == -12.5
    assert report["id"] in {row["id"] for row in client.get("/reports/mine").json()}
    assert client.get(f"/reports/{report['id']}").json() == report
    assert client.get("/municipal/reports").status_code == 403
    state["actor"] = Actor(ids["manager"], "encargado_municipal")
    assert report["id"] in {row["id"] for row in client.get("/municipal/reports?limit=200").json()}


@pytest.mark.parametrize("slot,expected", [(None, "23502"), (0, "23514"), (4, "23514"), (1, "23505")])
def test_direct_sql_cannot_bypass_photo_slot_constraints(photo_case, slot, expected):
    client, engine, ids, _ = photo_case
    assert upload(client, ids["report"]).status_code == 201
    with Session(engine) as db:
        db.add(ReportPhoto(report_id=ids["report"], slot=slot, storage_path="direct-test/" + str(uuid.uuid4()),
                           content_type="image/jpeg", size_bytes=1))
        with pytest.raises(IntegrityError) as exc:
            db.commit()
        assert diagnostics(exc.value)[0] == expected
        db.rollback()


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_upload_journal_has_no_direct_user_access(photo_case, role):
    conn = connection()
    try:
        conn.execute("BEGIN")
        conn.execute("SET LOCAL ROLE " + role)  # parameter comes only from the two literals above
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT * FROM public.photo_upload_operations")
    finally:
        conn.execute("ROLLBACK")
        conn.close()
