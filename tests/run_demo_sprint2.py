"""Disposable three-profile demo. Invoke only through run_isolated_postgres.py.

No production hooks, .env changes or persistent credentials. Reuses the existing
Auth/Storage simulator, execution fixture and local Vite launcher.
"""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import httpx

from demo_support import require_disposable, require_local_docker
from execution_browser_fixture import seed
from integrated_services import LocalServices, PUBLIC_KEY, inspect_report
from isolated_postgres import ROOT, connection
from run_integrated_sprint1 import port, redact, stop, wait_ready
from run_isolated_postgres import docker

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")


def run():
    artifact = Path(os.environ.get("RECIWISE_TEST_EVIDENCE_DIR", "")).resolve()
    token = os.environ.get("RECIWISE_ISOLATED_TOKEN", "")
    if artifact != (ROOT / ".test-artifacts" / ("reciwise-d2-test-" + token)).resolve():
        raise RuntimeError("Demo must use its owned artifact directory")
    require_local_docker(docker)
    container = os.environ.get("RECIWISE_DEMO_CONTAINER_ID", "")
    if not container:
        raise RuntimeError("Run the disposable parent launcher")
    target = os.environ.get("RECIWISE_TEST_DATABASE_URL", "")
    if target != os.environ.get("DATABASE_URL"):
        raise RuntimeError("Demo database target mismatch")
    require_disposable(json.loads(docker("inspect", container))[0], target, token, container)
    guard = connection(); guard.close()
    profiles = json.loads(os.environ["RECIWISE_ISOLATED_PROFILES"])
    fixture = seed(profiles)  # Only after exact disposable container/binding/mount checks.
    api_port, ui_port = port(), port()
    while ui_port == api_port:
        ui_port = port()
    api, ui = "http://127.0.0.1:" + str(api_port), "http://127.0.0.1:" + str(ui_port)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    backend = vite = browser = None
    checked = os.environ.get("RECIWISE_DEMO_CHECK") == "1"
    env = dict(os.environ)
    for name in list(env):
        if name.upper().startswith(("VITE_", "SUPABASE_")) or name.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}:
            env.pop(name)
    with LocalServices(profiles, ui).serve() as services:
        env.update(SUPABASE_URL=services.base, SUPABASE_SERVICE_ROLE_KEY="isolated-test-only",
            STORAGE_BUCKET="reciwise-reportes", CORS_ORIGINS=ui, VITE_API_URL=api,
            VITE_SUPABASE_URL=services.base, VITE_SUPABASE_PUBLISHABLE_KEY=PUBLIC_KEY, VITE_ENABLE_DEMO="false",
            RECIWISE_DEMO_API=api, RECIWISE_DEMO_UI=ui, RECIWISE_DEMO_SERVICES=services.base,
            RECIWISE_DEMO_PASSWORD=services.password)
        private_values = lambda: (services.password, services.control, *services.refresh, *services.read_tokens)

        def launch_api():
            child = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                "--port", str(api_port), "--no-access-log", "--log-level", "error"], cwd=ROOT, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            try:
                wait_ready(child, api + "/ready")
                return child
            except BaseException:
                stop(child); raise

        try:
            backend = launch_api()
            vite = subprocess.Popen(["node", str(ROOT / "scripts/local_dev_vite.mjs"), str(ui_port)],
                cwd=ROOT / "frontend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            wait_ready(vite, ui)
            checks = []
            with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
                def check(label, condition):
                    if not condition:
                        raise RuntimeError("Demo readiness failed: " + label)
                    checks.append(label)

                headers = {}
                ready = client.get(api + "/ready")
                check("schema_003_ready", ready.status_code == 200 and ready.json() == {"status": "ready", "schema": "003"})
                for actor, role in (("citizen", "ciudadano"), ("manager", "encargado_municipal"), ("driver", "chofer"), ("driver2", "chofer")):
                    response = client.post(services.base + "/auth/v1/token?grant_type=password", headers={"apikey": PUBLIC_KEY},
                                           json={"email": actor + "@example.test", "password": services.password})
                    check(actor + "_login", response.status_code == 200)
                    headers[actor] = {"Authorization": "Bearer " + response.json()["access_token"]}
                    response = client.get(api + "/me", headers=headers[actor])
                    check(actor + "_profile", response.status_code == 200 and response.json() == {"id": profiles[actor], "role": role})

                def post(route, data, actor="manager"):
                    response = client.post(api + route, headers=headers[actor], json=data)
                    if response.status_code != 201:
                        raise RuntimeError("Demo seed rejected; no automatic POST retry")
                    return response.json()

                report = post("/reports", {"description": "DEMO FICTICIA: reporte inicial con fotografía",
                    "latitude": -12.05, "longitude": -75.22, "observed_at": datetime.now(timezone.utc).isoformat(), "waste_type": "Prueba de integración"}, "citizen")
                free_report = post("/reports", {"description": "DEMO FICTICIA: reporte disponible para asociación manual",
                    "latitude": -12.051, "longitude": -75.221, "observed_at": datetime.now(timezone.utc).isoformat()}, "citizen")
                response = client.post(api + "/reports/" + report["id"] + "/photos", headers=headers["citizen"],
                    files={"file": ("DEMO-imagen-tecnica.png", PNG, "image/png")})
                check("photo_uploaded", response.status_code == 201)
                event = post("/municipal/events", {"latitude": report["latitude"], "longitude": report["longitude"],
                    "intervention_type": "DEMO FICTICIA: revisión manual inicial", "report_ids": [report["id"]]})
                vehicle = post("/municipal/vehicles", {"label": "DEMO FICTICIA: unidad para revisión", "vehicle_type": "otro", "available": True})
                post("/municipal/vehicles", {"label": "DEMO FICTICIA: unidad NO DISPONIBLE", "vehicle_type": "otro", "available": False})
                sites = client.get(api + "/municipal/sites", headers=headers["manager"]).json()
                start = datetime.now(timezone.utc) + timedelta(days=2)
                shift = post("/municipal/shifts", {"vehicle_id": vehicle["id"], "driver_id": profiles["driver2"],
                    "departure_site_id": next(s["id"] for s in sites if s["site_type"] == "salida"),
                    "disposal_site_id": next(s["id"] for s in sites if s["site_type"] == "descarga"),
                    "starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=4)).isoformat()})
                proposals = [post("/municipal/route-proposals", {"proposal_id": str(uuid.uuid5(uuid.UUID(token), action)),
                    "shift_id": shift["id"], "event_ids": [event["id"]], "configuration": {"demo": "fictitious-" + action}})
                    for action in ("reject", "cancel")]
                check("pending_proposals_not_operational", all(p["operational"] is False and p["calculation_status"] == "pending" for p in proposals))
                check("citizen_municipal_403", client.get(api + "/municipal/reports", headers=headers["citizen"]).status_code == 403)
                check("driver_municipal_403", client.get(api + "/municipal/routes", headers=headers["driver"]).status_code == 403)
                check("other_driver_404", client.get(api + "/driver/routes/" + fixture["id"], headers=headers["driver2"]).status_code == 404)
                response = client.post(api + "/municipal/routes/" + proposals[0]["id"] + "/decisions", headers=headers["manager"],
                    json={"operation_id": str(uuid.uuid4()), "expected_status": "propuesta", "expected_revision": None,
                          "decision": "approve", "notes": "DEMO: aprobación debe permanecer bloqueada"})
                check("unverified_approval_409", response.status_code == 409)
                route_before = client.get(api + "/driver/routes/" + fixture["id"], headers=headers["driver"]).json()
                check("driver_fixture_assigned", route_before["approval_verified"] and route_before["driver_id"] == profiles["driver"] and len(route_before["stops"]) == 3)
                public = {"ui": ui, "api": api, "auth_storage": services.base, "report": report["id"],
                    "free_report": free_report["id"], "event": event["id"], "driver_route": fixture["id"],
                    "proposals": {action: p["id"] for action, p in zip(("reject", "cancel"), proposals)},
                    "fictitious_approval": True, "disposable_only": True, "source": "NOT verified D3", "photo": "technical 1x1 PNG"}
                (artifact / "demo.json").write_text(json.dumps(public, indent=2), encoding="utf-8")
                (artifact / "DEMO-imagen-tecnica.png").write_bytes(PNG)
                before = inspect_report(report["id"])
                env["RECIWISE_DEMO_FIXTURES"] = json.dumps(public)
                print("DEMO FICTICIA, DESECHABLE. NO acredita un proveedor D3 verificado.", flush=True)
                print("React: " + ui + " | FastAPI: " + api, flush=True)
                print("Three independent browser sessions; Ctrl+C stops and discards this demo only.", flush=True)
                browser = subprocess.Popen(["node", str(ROOT / "scripts/demo_profiles.cjs")], cwd=ROOT, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", creationflags=flags)
                announced = False
                while browser.poll() is None:
                    if not announced and (artifact / "demo-ready.json").is_file():
                        print("DEMO READY: citizen@example.test, manager@example.test, driver@example.test", flush=True)
                        announced = True
                    if (artifact / "demo.stop").exists():
                        break
                    time.sleep(.2)
                output, _ = browser.communicate(timeout=15)
                (artifact / "demo-browser.log").write_text(redact(output, private_values()), encoding="utf-8")
                check("browser_sessions_ready", browser.returncode == 0)
                if checked:
                    stop(backend); backend = launch_api()
                    after = client.get(api + "/driver/routes/" + fixture["id"], headers=headers["driver"])
                    check("driver_fixture_survives_api_restart", after.status_code == 200 and after.json() == route_before)
                    check("report_photo_survives_api_restart", inspect_report(report["id"]) == before)
                check("control_object_preserved", services.objects.get("controls/keep.png") == b"fictitious-control-do-not-delete")
                result = {"checks": checks, "passed": len(checks), "mode": "headless-check" if checked else "interactive",
                    "auth_storage_tiles": "simulated", "react_fastapi_postgresql": "real",
                    "fictitious_approval": "assumption only in owned disposable DB", "shared_supabase_contacted": False,
                    "control_sha256": hashlib.sha256(services.objects["controls/keep.png"]).hexdigest()}
                (artifact / "demo-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                print("Demo checks passed: " + str(len(checks)), flush=True)
                return 0
        finally:
            (artifact / "demo.stop").touch()
            if browser is not None and browser.poll() is None:
                try:
                    browser.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    stop(browser)
            stop(vite); stop(backend)
            for file in list(artifact.rglob("*.json")) + list(artifact.rglob("*.log")):
                file.write_text(redact(file.read_text(encoding="utf-8"), private_values()), encoding="utf-8")


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except KeyboardInterrupt:
        raise SystemExit(0) from None
    except Exception:
        print("Demo refused or failed safely; no credentials printed, no remote fallback.", flush=True)
        raise SystemExit(1) from None
