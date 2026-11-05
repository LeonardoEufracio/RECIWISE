import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import main
from app.models import PhotoUploadOperation, ReportPhoto
from app.photo_uploads import PhotoUploads, now
from app.storage import StorageUploadError
from concurrency_support import ISOLATED_ONLY, pg_case
from test_photo_concurrency import IMAGE, photo_case, upload

pytestmark = ISOLATED_ONLY


def operations(engine, report_id):
    with Session(engine) as db:
        return list(db.scalars(select(PhotoUploadOperation).where(
            PhotoUploadOperation.report_id == report_id)))


def recovery(engine, storage):
    return PhotoUploads(lambda: Session(engine, expire_on_commit=False), "reciwise-reportes",
                        storage.upload, storage.remove)


def make_due(engine, operation_id):
    # Advance only fictitious isolated test work to its next scheduled attempt.
    with Session(engine) as db:
        db.get(PhotoUploadOperation, operation_id).next_attempt_at = now() - timedelta(seconds=1)
        db.commit()


def install_persistence_fault(monkeypatch, engine, mode):
    fired = []

    class FaultSession(Session):
        def flush(self, *args, **kwargs):
            if mode == "flush" and not fired and any(isinstance(item, ReportPhoto) for item in self.new):
                fired.append(mode)
                self.execute(text("SELECT 1 / 0"))  # Real PostgreSQL abort, before any upload.
            return super().flush(*args, **kwargs)

        def commit(self):
            finalizing = any(isinstance(item, PhotoUploadOperation) and item.state == "complete"
                             for item in self.dirty)
            if finalizing and not fired:
                fired.append(mode)
                if mode == "rollback":
                    # A real 23514: abort is definitive, object upload already succeeded.
                    photo_id = next(item.id for item in self.identity_map.values() if isinstance(item, ReportPhoto))
                    self.execute(text("UPDATE public.report_photos SET slot=0 WHERE id=:id"), {"id": photo_id})
                elif mode == "lost-committed":
                    super().commit()
                    raise OperationalError("commit", None, ConnectionError("fictitious lost acknowledgement"), connection_invalidated=True)
                elif mode == "lost-rolledback":
                    self.rollback()
                    raise OperationalError("commit", None, ConnectionError("fictitious unknown outcome"), connection_invalidated=True)
            return super().commit()

        def refresh(self, *args, **kwargs):
            raise AssertionError("Photo persistence must not refresh after committing")

    monkeypatch.setattr(main, "PhotoUploads", lambda sessions, bucket, put, remove:
        PhotoUploads(lambda: FaultSession(engine, expire_on_commit=False), bucket, put, remove))
    return fired


def test_postgres_failure_before_upload_has_no_storage_effect(photo_case, monkeypatch):
    client, engine, ids, storage = photo_case
    fired = install_persistence_fault(monkeypatch, engine, "flush")
    response = upload(client, ids["report"])
    assert response.status_code == 503 and fired
    assert storage.objects == {} and storage.deletions == []
    assert operations(engine, ids["report"])[0].state == "rejected"


def test_definite_rollback_compensates_only_its_own_object(photo_case, monkeypatch):
    client, engine, ids, storage = photo_case
    storage.objects["unrelated-existing-object"] = b"preserve"
    install_persistence_fault(monkeypatch, engine, "rollback")
    assert upload(client, ids["report"]).status_code == 503
    operation = operations(engine, ids["report"])[0]
    assert operation.state == "cleaned" and operation.attempts == 1
    assert storage.objects == {"unrelated-existing-object": b"preserve"}
    assert storage.deletions == [operation.storage_path]


def test_cleanup_failure_is_durable_and_retryable(photo_case, monkeypatch):
    client, engine, ids, storage = photo_case
    install_persistence_fault(monkeypatch, engine, "rollback")

    def fail_delete(path):
        raise HTTPException(502, "fictitious cleanup failure")

    monkeypatch.setattr(main, "remove_private_image", fail_delete)
    assert upload(client, ids["report"]).status_code == 503
    operation = operations(engine, ids["report"])[0]
    assert operation.state == "cleanup_pending" and operation.attempts == 1
    assert operation.last_error == "cleanup_failed" and operation.storage_path in storage.objects
    with Session(engine) as db:
        db.get(PhotoUploadOperation, operation.id).next_attempt_at = now() - timedelta(seconds=1)
        db.commit()
    assert recovery(engine, storage).reconcile_due() == {"cleaned": 1}
    assert operations(engine, ids["report"])[0].attempts == 2
    assert storage.objects == {}


@pytest.mark.parametrize("mode,status", [("lost-committed", 201), ("lost-rolledback", 503)])
def test_unknown_commit_does_not_delete_on_request(photo_case, monkeypatch, mode, status):
    client, engine, ids, storage = photo_case
    install_persistence_fault(monkeypatch, engine, mode)
    assert upload(client, ids["report"]).status_code == status
    assert len(storage.objects) == 1 and storage.deletions == []
    operation = operations(engine, ids["report"])[0]
    service = recovery(engine, storage)
    if mode == "lost-committed":
        assert operation.state == "complete"
        assert service.reconcile(operation.id) == "complete"
        assert storage.deletions == []
        assert len(client.get(f"/reports/{ids['report']}/photos").json()) == 1
    else:
        assert operation.state == "quarantined"
        # New reconciler locks/rechecks after the original transaction is settled.
        make_due(engine, operation.id)
        assert service.reconcile(operation.id) == "quarantined"
        assert storage.objects == {}


@pytest.mark.parametrize("mode", ["not-configured", "rejected", "collision", "timeout"])
def test_storage_failures_preserve_safe_outcomes(photo_case, monkeypatch, mode):
    client, engine, ids, storage = photo_case

    def fail(path, contents, content_type):
        if mode in {"collision", "timeout"}:
            storage.objects[path] = b"existing" if mode == "collision" else contents
        raise StorageUploadError(503 if mode == "not-configured" else 502,
                                 uncertain=mode == "timeout", collision=mode == "collision")

    monkeypatch.setattr(main, "put_private_image", fail)
    assert upload(client, ids["report"]).status_code == (503 if mode == "not-configured" else 502)
    assert storage.deletions == []
    operation = operations(engine, ids["report"])[0]
    assert operation.state == {"not-configured": "rejected", "rejected": "rejected",
                               "collision": "review", "timeout": "quarantined"}[mode]
    assert client.get(f"/reports/{ids['report']}/photos").json() == []
    if mode == "collision":
        assert recovery(engine, storage).reconcile(operation.id) == "review"
        assert storage.objects[operation.storage_path] == b"existing"


def test_uncertain_late_upload_remains_recoverable(photo_case, monkeypatch):
    client, engine, ids, storage = photo_case
    monkeypatch.setattr(main, "put_private_image", lambda *args: (_ for _ in ()).throw(StorageUploadError(uncertain=True)))
    assert upload(client, ids["report"]).status_code == 502
    operation = operations(engine, ids["report"])[0]
    service = recovery(engine, storage)
    make_due(engine, operation.id)
    assert service.reconcile(operation.id) == "quarantined"
    # Simulate the server accepting the timed-out POST after the first DELETE.
    storage.objects[operation.storage_path] = IMAGE
    make_due(engine, operation.id)
    assert service.reconcile(operation.id) == "quarantined"
    assert storage.objects == {}
    assert len(storage.deletions) == 2
    assert operations(engine, ids["report"])[0].state == "quarantined"


def test_reconciler_preserves_confirmed_metadata_and_bytes(photo_case):
    client, engine, ids, storage = photo_case
    assert upload(client, ids["report"]).status_code == 201
    operation = operations(engine, ids["report"])[0]
    with Session(engine) as db:
        db.get(PhotoUploadOperation, operation.id).state = "pending"
        db.commit()
    make_due(engine, operation.id)
    assert recovery(engine, storage).reconcile(operation.id) == "complete"
    assert storage.objects[operation.storage_path] == IMAGE and storage.deletions == []


def test_unknown_commit_with_resolution_unavailable_never_deletes(photo_case, monkeypatch):
    client, engine, ids, storage = photo_case
    finalized = []
    class LostSession(Session):
        def commit(self):
            finishing = any(isinstance(item, PhotoUploadOperation) and item.state == "complete" for item in self.dirty)
            result = super().commit()
            if finishing:
                finalized.append(True)
                raise OperationalError("commit", None, ConnectionError("fictitious acknowledgement loss"), connection_invalidated=True)
            return result
    def sessions():
        if finalized:
            raise OperationalError("connect", None, ConnectionError("fictitious outage"), connection_invalidated=True)
        return LostSession(engine, expire_on_commit=False)
    monkeypatch.setattr(main, "PhotoUploads", lambda *args: PhotoUploads(sessions,
        "reciwise-reportes", storage.upload, storage.remove))
    assert upload(client, ids["report"]).status_code == 503
    assert len(storage.objects) == 1 and storage.deletions == []
    operation = operations(engine, ids["report"])[0]
    assert operation.state == "complete"
    assert recovery(engine, storage).reconcile(operation.id) == "complete"
    assert storage.deletions == []


def test_dry_run_does_not_change_journal_or_objects(photo_case, monkeypatch):
    client, engine, ids, storage = photo_case
    monkeypatch.setattr(main, "put_private_image", lambda *args: (_ for _ in ()).throw(StorageUploadError(uncertain=True)))
    assert upload(client, ids["report"]).status_code == 502
    before = operations(engine, ids["report"])[0]
    storage.objects[before.storage_path] = IMAGE
    assert recovery(engine, storage).reconcile(before.id, dry_run=True) == "pending"
    after = operations(engine, ids["report"])[0]
    assert (before.state, before.attempts, before.next_attempt_at) == (after.state, after.attempts, after.next_attempt_at)
    assert storage.objects[before.storage_path] == IMAGE and storage.deletions == []


def test_wrong_bucket_is_never_deleted(photo_case, monkeypatch):
    client, engine, ids, storage = photo_case
    monkeypatch.setattr(main, "put_private_image", lambda *args: (_ for _ in ()).throw(StorageUploadError(uncertain=True)))
    assert upload(client, ids["report"]).status_code == 502
    operation = operations(engine, ids["report"])[0]
    with Session(engine) as db:
        db.get(PhotoUploadOperation, operation.id).bucket = "other-bucket"
        db.commit()
    make_due(engine, operation.id)
    assert recovery(engine, storage).reconcile(operation.id) == "review"
    assert storage.deletions == []


def test_reconciler_skips_an_active_upload(photo_case, monkeypatch):
    client, engine, ids, storage = photo_case
    entered, release = threading.Event(), threading.Event()

    def blocked(path, contents, content_type):
        storage.upload(path, contents, content_type)
        entered.set()
        assert release.wait(10)

    monkeypatch.setattr(main, "put_private_image", blocked)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(upload, client, ids["report"])
        try:
            assert entered.wait(10)
            operation = operations(engine, ids["report"])[0]
            assert recovery(engine, storage).reconcile(operation.id) == "busy"
            assert storage.deletions == []
        finally:
            release.set()
        assert future.result(timeout=10).status_code == 201


def test_two_reconcilers_cannot_delete_the_same_job_simultaneously(photo_case, monkeypatch):
    client, engine, ids, storage = photo_case
    monkeypatch.setattr(main, "put_private_image", lambda *args: (_ for _ in ()).throw(StorageUploadError(uncertain=True)))
    assert upload(client, ids["report"]).status_code == 502
    operation = operations(engine, ids["report"])[0]
    make_due(engine, operation.id)
    entered, release = threading.Event(), threading.Event()

    def blocked_delete(path):
        entered.set()
        assert release.wait(10)
        storage.remove(path)

    first = PhotoUploads(lambda: Session(engine), "reciwise-reportes", storage.upload, blocked_delete)
    with ThreadPoolExecutor(1) as pool:
        task = pool.submit(first.reconcile, operation.id)
        try:
            assert entered.wait(10)
            assert recovery(engine, storage).reconcile(operation.id) == "busy"
        finally:
            release.set()
        assert task.result(timeout=10) == "quarantined"
    assert storage.deletions == [operation.storage_path]
