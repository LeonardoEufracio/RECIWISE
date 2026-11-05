"""Real local HTTP/browser smoke test; reuses labelled persistent fixtures.

Never contacts Supabase. Auth/Storage are the persistent loopback simulators.
No credentials, JWTs, signed URLs or raw exceptions are printed or retained.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

import httpx
import jwt
from psycopg.rows import dict_row

import local_dev as dev
from local_dev_services import DiskObjects, write_json
from isolated_postgres import connection


def redact(value, private):
    for secret in private.values():
        if isinstance(secret, str):
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"eyJ[\w-]+\.[\w-]+\.[\w-]+", "[REDACTED_JWT]", value)
    return re.sub(r"([?&]token=)[^\s\"'<>]+", r"\1[REDACTED]", value)


def run():
    c = dev.config(); dev.inspect_db(c)
    addresses = dev.urls(c)
    private = dev.credentials()
    runtime = json.loads((dev.STATE / "runtime.json").read_text())
    if runtime.get("phase") != "ready" or runtime.get("owner") != c["owner"] or runtime.get("urls") != addresses:
        raise dev.LocalError("local_stack_not_ready")
    artifact = dev.ROOT / ".test-artifacts/local-dev" / uuid.uuid4().hex
    artifact.mkdir(parents=True)
    checks = []
    fixture_file = dev.STATE / "check-data.json"
    fixtures = json.loads(fixture_file.read_text()) if fixture_file.exists() else {}

    def checked(name, condition):
        if not condition:
            raise dev.LocalError("local_check_failed_" + name)
        checks.append({"name": name, "passed": True})

    with httpx.Client(trust_env=False, timeout=15, follow_redirects=False) as client:
        base = addresses["api"]
        response = client.get(base + "/ready")
        checked("ready_schema_003", response.status_code == 200 and response.json() == {"status": "ready", "schema": "003"})
        checked("health_process_available", client.get(base + "/health").status_code == 200)
        checked("no_token_401", client.get(base + "/me").status_code == 401)
        checked("malformed_token_401", client.get(base + "/me", headers={"Authorization": "Bearer a.b.c"}).status_code == 401)
        jwks = client.get(addresses["auth"] + "/auth/v1/.well-known/jwks.json").json()
        headers = {}
        for name, role in (("citizen", "ciudadano"), ("manager", "encargado_municipal"), ("driver", "chofer")):
            response = client.post(addresses["auth"] + "/auth/v1/token?grant_type=password", headers={"apikey": dev.PUBLIC_KEY},
                                   json={"email": name + "@example.test", "password": private["auth_password"]})
            checked(name + "_auth_login", response.status_code == 200)
            token = response.json()["access_token"]
            key = jwt.PyJWK.from_dict(jwks["keys"][0]).key
            claims = jwt.decode(token, key, algorithms=["ES256"], audience="authenticated", issuer=addresses["auth"] + "/auth/v1")
            checked(name + "_es256_sub", claims["sub"] == c["profiles"][name] and jwt.get_unverified_header(token)["alg"] == "ES256")
            headers[name] = {"Authorization": "Bearer " + token}
            response = client.get(base + "/me", headers=headers[name])
            checked(name + "_me_profile", response.status_code == 200 and response.json() == {"id": c["profiles"][name], "role": role})
        for area in ("events", "groupings", "route-proposals"):
            checked(area + "_citizen_403", client.get(base + "/municipal/" + area, headers=headers["citizen"]).status_code == 403)
            response = client.get(base + "/municipal/" + area, headers=headers["manager"])
            checked(area + "_manager_200", response.status_code == 200 and isinstance(response.json(), list))
        preflight = client.options(base + "/municipal/events", headers={"Origin": addresses["ui"], "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
        checked("cors_react_origin", preflight.status_code == 200 and preflight.headers.get("access-control-allow-origin") == addresses["ui"])

        def get(path, actor="manager"):
            r = client.get(base + path, headers=headers[actor])
            if r.status_code != 200:
                raise dev.LocalError("local_fixture_read_failed")
            return r.json()

        def ensure(name, path, data, actor="manager"):
            if name in fixtures:
                return get(path + "/" + fixtures[name], actor)
            r = client.post(base + path, headers=headers[actor], json=data)
            if r.status_code != 201:
                raise dev.LocalError("local_fixture_creation_failed_" + name)
            value = r.json()
            fixtures[name] = value["id"]
            write_json(fixture_file, fixtures)
            return value

        report = ensure("report", "/reports", {"description": "LOCALDEV: reporte ficticio persistente de verificación", "latitude": -12.05,
            "longitude": -75.22, "observed_at": "2026-10-30T15:00:00Z", "waste_type": "Prueba local"}, "citizen")
        photos = get("/reports/" + report["id"] + "/photos", "citizen")
        if not photos:
            import base64
            png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
            response = client.post(base + "/reports/" + report["id"] + "/photos", headers=headers["citizen"], files={"file": ("ficticia.png", png, "image/png")})
            checked("local_photo_upload", response.status_code == 201)
            fixtures["photo"] = response.json()["id"]
            write_json(fixture_file, fixtures)
        event = ensure("event", "/municipal/events", {"latitude": -12.05, "longitude": -75.22, "intervention_type": "LOCALDEV: revisión ficticia", "report_ids": [report["id"]]})
        operation_id = str(uuid.uuid5(uuid.UUID(c["owner"]), "localdev-review"))
        decision = client.get(base + "/municipal/groupings/decisions/" + operation_id, headers=headers["manager"])
        if decision.status_code == 404:
            relation = get("/municipal/groupings/reports/" + report["id"])
            decision = client.post(base + "/municipal/groupings/decisions", headers=headers["manager"], json={
                "operation_id": operation_id, "report_id": report["id"], "decision": "revisar", "candidate_event_id": event["id"],
                "expected_event_id": relation["event_id"], "expected_decision_id": relation["last_decision_id"], "notes": "Verificación local; no es una sugerencia D3"})
        checked("grouping_review_persisted", decision.status_code == 200)
        fixtures["decision"] = operation_id; write_json(fixture_file, fixtures)
        vehicle = ensure("vehicle", "/municipal/vehicles", {"label": "LOCALDEV: unidad ficticia", "vehicle_type": "compactadora", "available": True, "capacity_kg": None, "plate": None}) if "vehicle" not in fixtures else {"id": fixtures["vehicle"]}
        # Resources have list endpoints; reuse IDs instead of assuming unsupported detail routes.
        start = ensure("start", "/municipal/sites", {"name": "LOCALDEV: salida ficticia", "site_type": "salida", "latitude": -12.05, "longitude": -75.22}) if "start" not in fixtures else {"id": fixtures["start"]}
        end = ensure("end", "/municipal/sites", {"name": "LOCALDEV: descarga ficticia", "site_type": "descarga", "latitude": -12.07, "longitude": -75.24}) if "end" not in fixtures else {"id": fixtures["end"]}
        shift = ensure("shift", "/municipal/shifts", {"vehicle_id": vehicle["id"], "driver_id": c["profiles"]["driver"], "departure_site_id": start["id"], "disposal_site_id": end["id"], "starts_at": "2031-11-19T13:00:00Z", "ends_at": "2031-11-19T18:00:00Z"}) if "shift" not in fixtures else {"id": fixtures["shift"]}
        proposal = ensure("proposal", "/municipal/route-proposals", {"proposal_id": str(uuid.uuid5(uuid.UUID(c["owner"]), "localdev-pending-proposal")), "shift_id": shift["id"], "event_ids": [event["id"]], "configuration": {"scenario": "LOCALDEV-fixture"}})
        checked("proposal_pending_not_operational", proposal["calculation_status"] == "pending" and proposal["operational"] is False)
        for name, path in (("event_reports", "/municipal/events/" + event["id"] + "/reports"),
                           ("candidates", "/municipal/groupings/candidates?report_id=" + report["id"]),
                           ("decisions", "/municipal/groupings/decisions?report_id=" + report["id"]),
                           ("stops", "/municipal/route-proposals/" + proposal["id"] + "/stops"),
                           ("exclusions", "/municipal/route-proposals/" + proposal["id"] + "/excluded-events")):
            get(path); checked(name + "_200", True)

    # Independent READ ONLY snapshot: no migrations, writes or FK/RLS substitutes.
    db = connection()
    try:
        db.execute("BEGIN READ ONLY"); db.row_factory = dict_row
        snapshot = {}
        for label, table, field, value in (("report", "reports", "id", fixtures["report"]),
            ("photos", "report_photos", "report_id", fixtures["report"]), ("event", "events", "id", fixtures["event"]),
            ("decision", "grouping_decisions", "id", fixtures["decision"]), ("shift", "shifts", "id", fixtures["shift"]),
            ("proposal", "route_plans", "id", fixtures["proposal"])):
            # Identifiers are fixed literals above; values are always bound parameters.
            snapshot[label] = db.execute("SELECT * FROM public." + table + " WHERE " + field + "=%s ORDER BY id", (value,)).fetchall()
        db.rollback()
    finally:
        db.close()
    disk = DiskObjects(dev.STATE / "storage")
    snapshot["photo_sha256"] = {row["id"].hex: hashlib.sha256(disk[row["storage_path"]]).hexdigest() for row in snapshot["photos"]}
    snapshot["control_sha256"] = hashlib.sha256(disk["controls/keep.png"]).hexdigest()
    snapshot = json.loads(json.dumps(snapshot, default=str))
    baseline_file = dev.STATE / "acceptance-baseline.json"
    if baseline_file.exists():
        checked("persistent_ids_fields_and_files_unchanged", json.loads(baseline_file.read_text()) == snapshot)
    else:
        write_json(baseline_file, snapshot)
    write_json(artifact / "persistence.json", snapshot)

    env = dev.environment(c)
    env.update(RECIWISE_LOCAL_DEV_EVIDENCE=str(artifact), PLAYWRIGHT_CHANNEL=os.environ.get("PLAYWRIGHT_CHANNEL", "chrome"))
    result = subprocess.run(["node", str(dev.ROOT / "frontend/node_modules/@playwright/test/cli.js"), "test", "--config", str(dev.ROOT / "scripts/local_dev_playwright.config.cjs")],
        cwd=dev.ROOT, env=env, creationflags=dev.HIDDEN, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (artifact / "browser.log").write_text(redact(result.stdout + result.stderr, private), encoding="utf-8")
    for file in list(artifact.rglob("*.xml")) + list(artifact.rglob("*.md")):
        file.write_text(redact(file.read_text(encoding="utf-8"), private), encoding="utf-8")
    write_json(artifact / "results.json", {"checks": checks, "http_passed": len(checks), "browser_exit_code": result.returncode,
        "database": "persistent owned PostgreSQL 17; 001+002+003", "fastapi": "production app, guard and JWT verification active",
        "auth": "persistent local ES256/JWKS simulator", "storage": "persistent local HTTP/disk simulator", "tiles": "simulated in browser check",
        "remote_supabase_contacted": False})
    print("HTTP checks passed: " + str(len(checks)) + "; browser exit: " + str(result.returncode))
    print("Evidence: " + str(artifact.relative_to(dev.ROOT)))
    return result.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except dev.LocalError as exc:
        print("Local check refused: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        print("Local check failed safely; no secrets or remote fallback.", file=sys.stderr)
        raise SystemExit(1) from None
