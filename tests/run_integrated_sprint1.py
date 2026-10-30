"""Child of run_isolated_postgres.py --phase integrated; never use project .env."""
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from isolated_postgres import ROOT, connection
from integrated_services import LocalServices, PUBLIC_KEY


def redact(value, secret_values=()):
    value = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
                   "[REDACTED_JWT]", value)
    for secret in secret_values:
        value = value.replace(secret, "[REDACTED]")
    return value


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def wait_ready(process, url):
    deadline = time.monotonic() + 45
    with httpx.Client(timeout=2, trust_env=False) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Owned integration process failed startup")
            try:
                response = client.get(url)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
    raise RuntimeError("Owned integration process readiness timeout")


def run():
    conn = connection()
    try:
        profiles = json.loads(os.environ["RECIWISE_ISOLATED_PROFILES"])
        profiles["citizen2"] = str(uuid.uuid4())
        conn.execute("INSERT INTO auth.users(id) VALUES (%s)", (profiles["citizen2"],))
    finally:
        conn.close()
    artifact = Path(os.environ["RECIWISE_TEST_EVIDENCE_DIR"]).resolve()
    if not artifact.is_relative_to((ROOT / ".test-artifacts").resolve()):
        raise RuntimeError("Integration artifacts must stay in the test workspace")
    api_port, ui_port = port(), port()
    api = "http://127.0.0.1:" + str(api_port)
    ui = "http://127.0.0.1:" + str(ui_port)
    backend = vite = None
    env = dict(os.environ)
    for name in list(env):
        if name.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}:
            env.pop(name)
    env.update(CORS_ORIGINS=ui, RECIWISE_INTEGRATED_API_PORT=str(api_port),
               RECIWISE_INTEGRATED_API_URL=api, RECIWISE_INTEGRATED_UI_URL=ui,
               RECIWISE_INTEGRATED_ARTIFACT=str(artifact))
    with LocalServices(profiles, ui).serve() as services:
        env.update(SUPABASE_URL=services.base, SUPABASE_SERVICE_ROLE_KEY="isolated-test-only",
            STORAGE_BUCKET="reciwise-reportes", RECIWISE_INTEGRATED_SERVICES_URL=services.base,
            RECIWISE_INTEGRATED_CONTROL=services.control, RECIWISE_INTEGRATED_PASSWORD=services.password,
            VITE_API_URL=api, VITE_SUPABASE_URL=services.base, VITE_SUPABASE_PUBLISHABLE_KEY=PUBLIC_KEY)
        # Vite's process variables override existing .env files; files remain untouched.
        assert env["DATABASE_URL"] == env["RECIWISE_TEST_DATABASE_URL"]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        def launch_api():
            process = subprocess.Popen([sys.executable, str(ROOT / "tests/_integrated_api.py")],
                cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            try:
                wait_ready(process, api + "/ready")
                return process
            except BaseException:
                stop(process)
                raise
        def restart():
            nonlocal backend
            before = backend.pid
            stop(backend)
            backend = launch_api()
            return {"before_pid": before, "after_pid": backend.pid}
        services.restart = restart
        try:
            backend = launch_api()
            vite = subprocess.Popen(["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1",
                "--port", str(ui_port), "--strictPort"], cwd=ROOT / "frontend", env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            wait_ready(vite, ui)
            frontend_env = dict(env, PLAYWRIGHT_CHANNEL=env.get("PLAYWRIGHT_CHANNEL", "chrome"))
            # Build/check production source with fictitious public configuration only.
            checks = []
            for label, args in (("typescript", ["node", "node_modules/typescript/bin/tsc", "--noEmit"]),
                         ("vitest", ["node", "node_modules/vitest/vitest.mjs", "run", "--reporter=json",
                                     "--outputFile=" + str(artifact / "vitest.json")]),
                         ("vite_build", ["node", "node_modules/vite/bin/vite.js", "build",
                          "--outDir", str(artifact / "frontend-build")])):
                result = subprocess.run(args, cwd=ROOT / "frontend", env=frontend_env, creationflags=flags,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                        encoding="utf-8", errors="replace")
                (artifact / (label + ".log")).write_text(result.stdout, encoding="utf-8")
                checks.append({"check": label, "exit_code": result.returncode})
                print("Frontend " + label + ": exit " + str(result.returncode), flush=True)
                if result.returncode:
                    return result.returncode
            result = subprocess.run(["node", "node_modules/@playwright/test/cli.js", "test",
                "--config", "e2e/integrated.config.ts"], cwd=ROOT / "frontend", env=frontend_env,
                creationflags=flags, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace")
            # Even a failed APIRequestContext may include request headers in its
            # diagnostics. Redact before displaying or retaining test output.
            secret_values = (services.password, services.control, *services.refresh, *services.read_tokens)
            (artifact / "browser.log").write_text(redact(result.stdout, secret_values), encoding="utf-8")
            targets = [p for p in artifact.iterdir() if p.suffix in {".xml", ".json", ".log"}]
            targets += list((artifact / "browser-output").rglob("*.md"))
            for target in targets:
                if target.is_file():
                    target.write_text(redact(target.read_text(encoding="utf-8"), secret_values), encoding="utf-8")
            print("Browser integration: exit " + str(result.returncode), flush=True)
            summary = {"postgresql": "real isolated 001+003", "fastapi": "real HTTP; production JWT/schema guard",
                "react_leaflet_browser": "real Chrome", "auth": "local simulator; ephemeral ES256 and HTTP JWKS",
                "storage": "local HTTP simulator", "tiles": "simulated; no external downloads",
                "jwks_fetches": services.jwks_fetches, "logins": services.logins,
                "control_object_preserved": services.objects.get("controls/keep.png") == b"fictitious-control-do-not-delete",
                "shared_supabase_contacted": False, "browser_exit_code": result.returncode,
                "frontend_checks": checks,
                "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                    for name in ("app/main.py", "app/security.py", "app/schema_guard.py", "app/storage.py",
                                 "frontend/src/App.tsx", "frontend/src/ReportForm.tsx", "frontend/src/MapView.tsx")}}
            (artifact / "integrated-environment.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print("Integrated evidence saved; credentials, JWT and private keys excluded.", flush=True)
            return result.returncode
        finally:
            stop(vite)
            stop(backend)


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception:
        print("Integrated runner failed safely; inspect test readiness/results without project secrets.", flush=True)
        raise SystemExit(2) from None
