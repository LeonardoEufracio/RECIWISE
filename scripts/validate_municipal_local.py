"""Browser acceptance against the owned persistent local stack; never migrates.

Reuses original fixtures. At most one labelled report/event/unavailable vehicle
is created through React when missing. All independent SQL is READ ONLY.
"""
from contextlib import contextmanager
import hashlib
import json
import os
import subprocess
import sys
import uuid

import httpx
from psycopg.rows import dict_row

import local_dev as dev
from check_local_dev import redact
from isolated_postgres import connection
from local_dev_services import DiskObjects, write_json

TABLES = ("reports", "report_photos", "events", "event_reports", "grouping_decisions",
          "vehicles", "service_sites", "shifts")
MARKER = "PRUEBA MUNICIPAL LOCAL S2"
KEY = {table: ("report_id" if table == "event_reports" else "id") for table in TABLES}


@contextmanager
def exclusive_validation():
    with (dev.STATE / "municipal-validation.lock").open("a+b") as stream:
        if not stream.tell():
            stream.write(b"0"); stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def snapshot():
    db = connection()
    try:
        db.execute("BEGIN READ ONLY")
        db.row_factory = dict_row
        rows = {table: db.execute("SELECT * FROM public." + table + " ORDER BY " + KEY[table]).fetchall() for table in TABLES}
        db.rollback()
    finally:
        db.close()
    disk = DiskObjects(dev.STATE / "storage")
    rows["files"] = {str(p["id"]): hashlib.sha256(disk[p["storage_path"]]).hexdigest() for p in rows["report_photos"]}
    rows["files"]["control"] = hashlib.sha256(disk["controls/keep.png"]).hexdigest()
    return json.loads(json.dumps(rows, default=str))


def compare(before, after, profiles):
    added = {}
    for table in TABLES:
        old = {r[KEY[table]]: r for r in before[table]}
        current = {r[KEY[table]]: r for r in after[table]}
        if any(current.get(key) != value for key, value in old.items()):
            raise dev.LocalError("existing_rows_changed_" + table)
        added[table] = [row for key, row in current.items() if key not in old]
    if before["files"] != after["files"]:
        raise dev.LocalError("existing_files_changed")
    for table in ("report_photos", "service_sites", "shifts"):
        if added[table]:
            raise dev.LocalError("unexpected_insertion_" + table)
    for table in ("reports", "events", "vehicles", "event_reports", "grouping_decisions"):
        if len(added[table]) > 1:
            raise dev.LocalError("duplicate_test_fixtures_" + table)
    for r in added["reports"]:
        if r["description"] != MARKER + ": reporte para asociación manual" or r["status"] != "recibido" or r["citizen_id"] != profiles["citizen"]:
            raise dev.LocalError("unexpected_report")
    for r in added["events"]:
        if r["intervention_type"] != MARKER + ": revisión manual" or r["state"] != "en_revision":
            raise dev.LocalError("unexpected_event")
    for r in added["vehicles"]:
        if r["label"] != MARKER + ": unidad NO OPERATIVA" or r["available"]:
            raise dev.LocalError("unexpected_vehicle")
    test_reports = {r["id"] for r in after["reports"] if r["description"] == MARKER + ": reporte para asociación manual"}
    test_events = {r["id"] for r in after["events"] if r["intervention_type"] == MARKER + ": revisión manual"}
    if len(test_reports) > 1 or len(test_events) > 1:
        raise dev.LocalError("duplicate_labelled_fixtures")
    for r in after["reports"]:
        if r["id"] in test_reports and r["status"] != "recibido":
            raise dev.LocalError("associated_report_status_changed")
    if test_events:
        links = [r for r in after["event_reports"] if r["event_id"] in test_events]
        decisions = [r for r in after["grouping_decisions"] if r["resulting_event_id"] in test_events]
        if (len(links) != 1 or len(decisions) != 1 or links[0]["report_id"] not in test_reports
                or links[0]["linkage_method"] != "manual" or links[0]["linked_by"] != profiles["manager"]
                or decisions[0]["report_id"] not in test_reports or decisions[0]["decision"] != "agrupar"
                or decisions[0]["decided_by"] != profiles["manager"]):
            raise dev.LocalError("manual_association_or_audit_inconsistent")
    for table, event_field in (("event_reports", "event_id"), ("grouping_decisions", "resulting_event_id")):
        for r in added[table]:
            # Association and its audit record must concern only our labelled fixture.
            if r["report_id"] not in test_reports or r[event_field] not in test_events:
                raise dev.LocalError("unexpected_association")
    return {key: len(value) for key, value in added.items()}


def run():
    c = dev.config(); dev.inspect_db(c)
    addresses = dev.urls(c)
    runtime = json.loads((dev.STATE / "runtime.json").read_text())
    if runtime.get("phase") != "ready" or runtime.get("owner") != c["owner"] or runtime.get("urls") != addresses:
        raise dev.LocalError("local_stack_not_ready")
    with httpx.Client(trust_env=False, timeout=10, follow_redirects=False) as client:
        r = client.get(addresses["api"] + "/ready")
        if r.status_code != 200 or r.json() != {"status": "ready", "schema": "003"}:
            raise dev.LocalError("schema_not_ready")
    artifact = dev.ROOT / ".test-artifacts/municipal-local" / uuid.uuid4().hex
    artifact.mkdir(parents=True)
    print("Evidence: " + str(artifact.relative_to(dev.ROOT)), flush=True)
    with exclusive_validation():
        before = snapshot()
        write_json(artifact / "before.json", before)
        env = dev.environment(c)
        env["RECIWISE_MUNICIPAL_EVIDENCE"] = str(artifact)
        result = subprocess.run(["node", str(dev.ROOT / "frontend/node_modules/@playwright/test/cli.js"),
                                 "test", "--config", str(dev.ROOT / "scripts/municipal_validation.config.cjs")],
                                cwd=dev.ROOT, env=env, creationflags=dev.HIDDEN, capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
        private = dev.credentials()
        (artifact / "browser.log").write_text(redact(result.stdout + result.stderr, private), encoding="utf-8")
        for file in list(artifact.rglob("*.xml")) + list(artifact.rglob("*.md")):
            file.write_text(redact(file.read_text(encoding="utf-8"), private), encoding="utf-8")
        after = snapshot()
        write_json(artifact / "after.json", after)
        additions = compare(before, after, c["profiles"])
        write_json(artifact / "results.json", {"browser_exit_code": result.returncode,
            "existing_rows_and_file_hashes_unchanged": True, "added_labelled_fixtures": additions,
            "database": "real persistent owned PostgreSQL 17, 001+002+003",
            "business_http": "real FastAPI; explicit UI error injection recorded separately",
            "auth_storage_tiles": "local simulators", "remote_supabase_contacted": False})
    print("Browser exit: " + str(result.returncode) + "; original rows/files unchanged")
    print("Added labelled fixtures: " + json.dumps(additions))
    print("Evidence: " + str(artifact.relative_to(dev.ROOT)))
    return result.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except dev.LocalError as exc:
        print("Municipal validation refused: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        print("Municipal validation failed safely; inspect local evidence. No remote fallback.", file=sys.stderr)
        raise SystemExit(1) from None
