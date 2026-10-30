"""Independent worker tests: real disposable PostgreSQL and simulated Storage."""
import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import URL, create_engine, event, select
from sqlalchemy.orm import Session

from app import reconcile_photos as cli
from app.models import PhotoUploadOperation, Report, ReportPhoto
from app.photo_uploads import PhotoUploads, now
from concurrency_support import FakeStorage, ISOLATED_ONLY
from test_migration_003 import legacy_database
from test_photo_concurrency import IMAGE
from test_photo_restart import storage_server
from test_schema_guard import guarded_database

pytestmark = ISOLATED_ONLY


@pytest.fixture
def worker_case(guarded_database, monkeypatch):
    conn, engine, profiles, url = guarded_database
    report_id = uuid.uuid4()
    with Session(engine) as db:
        db.add(Report(id=report_id, citizen_id=uuid.UUID(profiles["citizen"]), description="Reporte ficticio de conciliación",
                      latitude=-12, longitude=-77, observed_at=now()))
        db.commit()
    storage = FakeStorage()
    service = PhotoUploads(lambda: Session(engine, expire_on_commit=False), "reciwise-reportes", storage.upload, storage.remove)
    monkeypatch.setattr(cli, "get_engine", lambda: engine)
    monkeypatch.setattr(cli, "get_settings", lambda: SimpleNamespace(storage_bucket="reciwise-reportes", supabase_service_role_key="isolated-test-only"))
    monkeypatch.setattr(cli, "put_private_image", storage.upload)
    monkeypatch.setattr(cli, "remove_private_image", storage.remove)
    return SimpleNamespace(conn=conn, engine=engine, profiles=profiles, url=url, report=report_id,
                           storage=storage, service=service)


def add_job(case, *, state="cleanup_pending", due=True):
    operation_id = uuid.uuid4()
    path = f"reports/{case.profiles['citizen']}/{case.report}/{operation_id}.jpg"
    with Session(case.engine) as db:
        db.add(PhotoUploadOperation(id=operation_id, actor_id=uuid.UUID(case.profiles["citizen"]),
            report_id=case.report, bucket="reciwise-reportes", storage_path=path, extension="jpg", state=state,
            next_attempt_at=now() + timedelta(seconds=-1 if due else 300)))
        db.commit()
    case.storage.objects[path] = IMAGE
    return operation_id, path


def job(case, operation_id):
    with Session(case.engine) as db:
        return db.get(PhotoUploadOperation, operation_id)


def due_again(case, operation_id):
    with Session(case.engine) as db:
        db.get(PhotoUploadOperation, operation_id).next_attempt_at = now() - timedelta(seconds=1)
        db.commit()


def worker_env(case, base):
    env = dict(os.environ, DATABASE_URL=case.url.render_as_string(hide_password=False),
        RECIWISE_TEST_DATABASE_URL=case.url.render_as_string(hide_password=False),
        SUPABASE_URL=base, SUPABASE_SERVICE_ROLE_KEY="isolated-test-only", STORAGE_BUCKET="reciwise-reportes")
    for key in list(env):
        if key.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}:
            env.pop(key)
    return env


def command(env, *args, crash=None):
    if crash:
        env = dict(env, RECIWISE_RECONCILER_CRASH=crash)
        program = [sys.executable, str(Path(__file__).with_name("_reconciler_worker.py"))]
    else:
        program = [sys.executable, "-m", "app.reconcile_photos"]
    return subprocess.Popen([*program, *args], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def finish(process, expected):
    try:
        output, errors = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=5)
        pytest.fail("Owned reconciler did not stop in time")
    assert process.returncode == expected, f"Unexpected reconciler exit {process.returncode}"
    return json.loads(output) if output.strip() else None


def test_cli_recovers_pending_and_repeated_execution_does_not_delete_again(worker_case, capsys):
    case = worker_case
    operation_id, path = add_job(case)
    assert cli.main(["--execute", "--operation-id", str(operation_id)]) == 0
    assert json.loads(capsys.readouterr().out)["results"] == {"cleaned": 1}
    assert cli.main(["--execute", "--operation-id", str(operation_id)]) == 0
    capsys.readouterr()
    assert case.storage.deletions == [path]
    assert job(case, operation_id).attempts == 1
    assert case.conn.execute("SELECT count(*) FROM public.reports").fetchone() == (1,)


def test_discovered_work_rechecks_next_attempt_under_lock(worker_case):
    case = worker_case
    operation_id, path = add_job(case, state="quarantined")
    assert case.service.reconcile(operation_id) == "quarantined"
    # Simulate another worker acting on the same previously discovered UUID.
    assert case.service.reconcile(operation_id) == "not_due"
    assert case.storage.deletions == [path] and job(case, operation_id).attempts == 1


def test_transient_storage_failure_waits_and_recovers(worker_case, monkeypatch, capsys, caplog):
    case = worker_case
    operation_id, path = add_job(case)
    def fail(path):
        raise HTTPException(502, "fictitious_secret must not be logged")
    monkeypatch.setattr(cli, "remove_private_image", fail)
    assert cli.main(["--execute", "--operation-id", str(operation_id)]) == 1
    output = capsys.readouterr().out
    first = job(case, operation_id)
    assert first.state == "cleanup_pending" and first.attempts == 1 and first.last_error == "cleanup_failed"
    assert first.next_attempt_at > first.updated_at and path in case.storage.objects
    assert "fictitious_secret" not in output + caplog.text
    assert cli.main(["--execute", "--operation-id", str(operation_id)]) == 0
    assert json.loads(capsys.readouterr().out)["results"] == {"not_due": 1}
    due_again(case, operation_id)
    monkeypatch.setattr(cli, "remove_private_image", case.storage.remove)
    assert cli.main(["--execute", "--operation-id", str(operation_id)]) == 0
    capsys.readouterr()
    assert path not in case.storage.objects and job(case, operation_id).attempts == 2


def test_diagnosis_is_readonly_does_not_lock_or_expose_private_errors(worker_case, capsys):
    case = worker_case
    operation_id, path = add_job(case)
    with Session(case.engine) as db:
        db.get(PhotoUploadOperation, operation_id).last_error = "fictitious_private_key"
        db.commit()
    before = case.conn.execute("SELECT row_to_json(o) FROM public.photo_upload_operations o").fetchall()
    statements, commits = [], []
    def trace(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    def commit(connection):
        commits.append(True)
    event.listen(case.engine, "before_cursor_execute", trace)
    event.listen(case.engine, "commit", commit)
    # An unresolved writer holds the row: an observation must not try FOR UPDATE.
    case.conn.execute("BEGIN")
    case.conn.execute("SELECT id FROM public.photo_upload_operations WHERE id=%s FOR UPDATE", (operation_id,))
    try:
        assert cli.main(["--operation-id", str(operation_id)]) == 1
    finally:
        case.conn.execute("ROLLBACK")
        event.remove(case.engine, "before_cursor_execute", trace)
        event.remove(case.engine, "commit", commit)
    output = capsys.readouterr().out
    diagnostic = json.loads(output)["diagnostic"]
    assert diagnostic["read_only"] is True and diagnostic["claims_work"] is False
    assert diagnostic["operations"][0]["last_error"] == "unrecognized_error"
    assert "fictitious_private_key" not in output
    assert commits == [] and not any("FOR UPDATE" in statement for statement in statements)
    assert all(statement.lstrip().split()[0] in {"SET", "SHOW", "SELECT"} for statement in statements)
    assert case.storage.deletions == [] and case.storage.objects[path] == IMAGE
    assert case.conn.execute("SELECT row_to_json(o) FROM public.photo_upload_operations o").fetchall() == before


@pytest.mark.parametrize("execute", [False, True])
def test_incompatible_schema_is_rejected_before_processing(worker_case, execute, capsys):
    case = worker_case
    operation_id, path = add_job(case)
    case.conn.execute("ALTER TABLE public.shifts DROP CONSTRAINT shifts_driver_no_overlap")
    assert cli.main(["--execute"] if execute else []) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "schema_not_ready"
    assert case.storage.deletions == [] and path in case.storage.objects
    assert job(case, operation_id).attempts == 0


@pytest.mark.parametrize("execute", [False, True])
def test_001_only_is_rejected(monkeypatch, execute, capsys):
    with legacy_database(monkeypatch) as (conn, _):
        engine = create_engine(URL.create("postgresql+psycopg", username="postgres", host=conn.info.host,
                                          port=conn.info.port, database=conn.info.dbname))
        monkeypatch.setattr(cli, "get_engine", lambda: engine)
        assert cli.main(["--execute"] if execute else []) == 2
        assert json.loads(capsys.readouterr().out)["code"] == "schema_incompatible"
        assert conn.execute("SELECT to_regclass('public.photo_upload_operations')").fetchone() == (None,)


def test_missing_storage_configuration_blocks_execute_but_not_diagnosis(worker_case, monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_settings", lambda: SimpleNamespace(storage_bucket="reciwise-reportes", supabase_service_role_key=""))
    operation_id, _ = add_job(worker_case, state="pending")
    assert cli.main(["--execute"]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "storage_not_configured"
    assert cli.main([]) == 1  # Pending intent must not be reported as an empty queue.
    diagnostic = json.loads(capsys.readouterr().out)["diagnostic"]
    assert diagnostic["read_only"] is True and diagnostic["summary"] == {"pending": 1}
    assert job(worker_case, operation_id).attempts == 0


def test_cli_two_independent_processes_claim_safely(worker_case):
    case = worker_case
    operation_id, path = add_job(case)
    entered, release = threading.Event(), threading.Event()
    def blocked(key):
        entered.set()
        assert release.wait(25)
    with storage_server(on_delete=blocked) as (base, objects, deletions):
        objects[path], objects["control/keep.jpg"] = IMAGE, b"preserve"
        env = worker_env(case, base)
        first = command(env, "--execute", "--operation-id", str(operation_id))
        try:
            assert entered.wait(15)
            second = command(env, "--execute", "--operation-id", str(operation_id))
            assert finish(second, 0)["results"] == {"busy": 1}
        finally:
            release.set()
        assert finish(first, 0)["results"] == {"cleaned": 1}
        assert finish(command(env, "--execute", "--operation-id", str(operation_id)), 0)["results"] == {"cleaned": 1}
        assert deletions == [path] and objects == {"control/keep.jpg": b"preserve"}


@pytest.mark.parametrize("outcome", ["commit", "rollback"])
def test_unknown_upload_commit_is_resolved_before_any_delete(worker_case, outcome):
    case = worker_case
    operation_id, path = add_job(case, state="pending")
    with storage_server() as (base, objects, deletions):
        objects[path] = IMAGE
        env = worker_env(case, base)
        with Session(case.engine) as original:
            operation = original.scalar(select(PhotoUploadOperation).where(PhotoUploadOperation.id == operation_id).with_for_update())
            original.add(ReportPhoto(id=operation_id, report_id=case.report, slot=1, storage_path=path,
                                    content_type="image/jpeg", size_bytes=len(IMAGE)))
            operation.state = "complete"
            original.flush()
            assert finish(command(env, "--execute", "--operation-id", str(operation_id)), 0)["results"] == {"busy": 1}
            assert deletions == []
            original.commit() if outcome == "commit" else original.rollback()
        result = finish(command(env, "--execute", "--operation-id", str(operation_id)), 0 if outcome == "commit" else 1)
        if outcome == "commit":
            assert result["results"] == {"complete": 1} and deletions == [] and objects[path] == IMAGE
        else:
            assert result["results"] == {"quarantined": 1} and deletions == [path] and path not in objects


@pytest.mark.parametrize("stage,exit_code,delete_calls", [("after-delete", 74, 2), ("after-commit", 75, 1)])
def test_worker_crash_and_restart_is_idempotent(worker_case, stage, exit_code, delete_calls):
    case = worker_case
    operation_id, path = add_job(case)
    with storage_server() as (base, objects, deletions):
        objects[path], objects["control/keep.jpg"] = IMAGE, b"preserve"
        env = worker_env(case, base)
        finish(command(env, "--execute", "--operation-id", str(operation_id), crash=stage), exit_code)
        assert path not in objects
        assert finish(command(env, "--execute", "--operation-id", str(operation_id)), 0)["results"] == {"cleaned": 1}
        assert len(deletions) == delete_calls
        assert objects == {"control/keep.jpg": b"preserve"}
        assert job(case, operation_id).state == "cleaned"


def test_stop_file_drains_current_job_and_preserves_next(worker_case, tmp_path):
    case = worker_case
    first_id, first_path = add_job(case)
    second_id, second_path = add_job(case)
    entered, release = threading.Event(), threading.Event()
    marker = tmp_path / "reconciler.stop"
    def blocked(key):
        entered.set()
        assert release.wait(20)
    with storage_server(on_delete=blocked) as (base, objects, deletions):
        objects[first_path], objects[second_path] = IMAGE, IMAGE
        env = worker_env(case, base)
        process = command(env, "--execute", "--stop-file", str(marker))
        try:
            assert entered.wait(15)
            marker.write_text("stop requested", encoding="utf-8")
        finally:
            release.set()
        result = finish(process, 130)
        assert result["stop_requested"] is True and len(deletions) == 1
        assert sorted([job(case, first_id).state, job(case, second_id).state]) == ["cleaned", "cleanup_pending"]
        # The CLI never removes the marker; a new, explicitly resumed invocation can finish.
        assert marker.exists()
        assert finish(command(env, "--execute"), 0)["results"] == {"cleaned": 1}
        assert objects == {} and len(deletions) == 2
