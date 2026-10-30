import json
import os
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest
from sqlalchemy.orm import Session

from app.models import PhotoUploadOperation
from app.photo_uploads import now
from concurrency_support import ISOLATED_ONLY, pg_case
from test_photo_recovery import operations
from test_photo_concurrency import IMAGE

pytestmark = ISOLATED_ONLY


@contextmanager
def storage_server(*, on_delete=None):
    objects, deletions = {}, []
    lock = threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, status, value):
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.headers.get("apikey") != "isolated-test-only":
                return self.send_json(403, {})
            contents = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.path.startswith("/storage/v1/object/sign/"):
                relative = self.path.removeprefix("/storage/v1")
                return self.send_json(200, {"signedURL": relative + "?token=fictitious"})
            prefix = "/storage/v1/object/reciwise-reportes/"
            if not self.path.startswith(prefix):
                return self.send_json(404, {})
            key = unquote(self.path.removeprefix(prefix))
            with lock:
                if key in objects:
                    return self.send_json(409, {})
                objects[key] = contents
            self.send_json(200, {})

        def do_DELETE(self):
            if self.headers.get("apikey") != "isolated-test-only":
                return self.send_json(403, {})
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            assert len(data["prefixes"]) == 1
            if on_delete is not None:
                on_delete(data["prefixes"][0])
            with lock:
                for key in data["prefixes"]:
                    objects.pop(key, None)
                    deletions.append(key)
            self.send_json(200, [])

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", objects, deletions
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def api_worker(env, stage=""):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    child = dict(env, RECIWISE_WORKER_PORT=str(port), RECIWISE_CRASH_STAGE=stage)
    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("_concurrency_worker.py"))],
        env=child, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=15) as client:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                assert process.poll() is None, "Owned API worker failed startup"
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("Owned API worker readiness timeout")
            yield client, process
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@pytest.mark.parametrize("stage,exit_code,photo_count", [("intent", 71, 0), ("upload", 72, 0), ("commit", 73, 1)])
def test_real_process_crash_and_reconciler_restart(pg_case, stage, exit_code, photo_count):
    _, engine, ids, _ = pg_case
    with storage_server() as (base, objects, deletions):
        env = dict(os.environ, SUPABASE_URL=base, SUPABASE_SERVICE_ROLE_KEY="isolated-test-only",
                   RECIWISE_WORKER_CITIZEN=str(ids["citizen"]), RECIWISE_WORKER_MANAGER=str(ids["manager"]))
        # Proxy settings must not redirect test HTTP traffic away from localhost.
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
            env.pop(key, None)
        headers = {"x-reciwise-test-actor": str(ids["citizen"])}
        path = f"/reports/{ids['report']}/photos"
        with api_worker(env, stage) as (client, process):
            first_pid = process.pid
            with pytest.raises(httpx.TransportError):
                client.post(path, headers=headers, files={"file": ("photo.jpg", IMAGE, "image/jpeg")})
            assert process.wait(timeout=10) == exit_code
        operation = operations(engine, ids["report"])[0]
        assert len(objects) == (0 if stage == "intent" else 1)
        with Session(engine) as db:
            db.get(PhotoUploadOperation, operation.id).next_attempt_at = now() - timedelta(seconds=1)
            db.commit()
        result = subprocess.run([sys.executable, "-m", "app.reconcile_photos", "--execute", "--operation-id", str(operation.id)],
            env=env, capture_output=True, text=True, timeout=20)
        assert result.returncode in (0, 1), "Reconciler process failed"
        assert json.loads(result.stdout)["dry_run"] is False
        if stage == "commit":
            assert objects[operation.storage_path] == IMAGE and deletions == []
        else:
            assert operation.storage_path not in objects and operation.storage_path in deletions
        with api_worker(env) as (client, process):
            assert process.pid != first_pid
            response = client.get(path, headers=headers)
            assert response.status_code == 200
            assert len(response.json()) == photo_count
            if stage == "commit":
                assert response.json()[0]["id"] == str(operation.id)
                assert response.json()[0]["size_bytes"] == len(IMAGE)
            else:
                assert client.post(path, headers=headers, files={"file": ("photo.jpg", IMAGE, "image/jpeg")}).status_code == 201
