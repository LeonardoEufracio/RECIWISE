"""Loopback-only Auth/JWKS/Storage simulator for the isolated browser acceptance.

Not imported by app/. No production credentials, identity overrides or data.
"""
import hashlib
import json
import secrets
import threading
import time
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from psycopg.rows import dict_row

from isolated_postgres import connection
from postgres_support import transaction

PUBLIC_KEY = "sb_publishable_integrated_local_only"
STORAGE_KEY = "isolated-test-only"


def inspect_report(report_id):
    """Independent real PostgreSQL observation; always READ ONLY + ROLLBACK."""
    report_id = uuid.UUID(report_id)
    conn = connection()
    try:
        with transaction(conn, readonly=True):
            conn.row_factory = dict_row
            report = conn.execute("SELECT * FROM public.reports WHERE id=%s", (report_id,)).fetchone()
            photos = conn.execute("SELECT * FROM public.report_photos WHERE report_id=%s ORDER BY id",
                                  (report_id,)).fetchall()
            operations = conn.execute("""SELECT id,state,storage_path,attempts,last_error
                FROM public.photo_upload_operations WHERE report_id=%s ORDER BY created_at,id""",
                                      (report_id,)).fetchall()
            return json.loads(json.dumps({"read_only": True, "report": report, "photos": photos,
                                          "operations": operations}, default=str))
    finally:
        conn.close()


class LocalServices:
    def __init__(self, profiles, origin):
        guard = connection()
        guard.close()
        self.profiles, self.origin = profiles, origin
        self.password = secrets.token_urlsafe(24)
        self.control = secrets.token_urlsafe(32)
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.kid = uuid.uuid4().hex
        self.accounts = {name + "@example.test": user_id for name, user_id in profiles.items()}
        self.refresh = {}
        self.objects = {"controls/keep.png": b"fictitious-control-do-not-delete"}
        self.read_tokens = {}
        self.lock = threading.Lock()
        self.faults = set()
        self.events = []
        self.jwks_fetches = 0
        self.logins = 0
        self.deletions = []
        self.restart = None

    def session(self, user_id):
        expires = int(time.time()) + 3600
        claims = {"sub": user_id, "iss": self.base + "/auth/v1", "aud": "authenticated",
                  "exp": expires, "iat": int(time.time()), "role": "authenticated"}
        token = jwt.encode(claims, self.key, algorithm="ES256", headers={"kid": self.kid})
        refresh = secrets.token_urlsafe(24)
        self.refresh[refresh] = user_id
        return {"access_token": token, "refresh_token": refresh, "token_type": "bearer",
                "expires_in": 3600, "expires_at": expires, "user": self.user(user_id)}

    def user(self, user_id):
        return {"id": user_id, "aud": "authenticated", "role": "authenticated",
                "email": next(email for email, uid in self.accounts.items() if uid == user_id),
                "app_metadata": {}, "user_metadata": {"role": "encargado_municipal"},
                "created_at": "2026-01-01T00:00:00Z"}

    def consume(self, kind):
        with self.lock:
            active = kind in self.faults
            self.faults.discard(kind)
            return active

    @contextmanager
    def serve(self):
        services = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass  # No Authorization, passwords, signed URLs or response bodies.

            def send(self, code, data, content_type="application/json"):
                raw = json.dumps(data, default=str).encode() if content_type == "application/json" else data
                self.send_response(code)
                if self.headers.get("Origin") == services.origin:
                    self.send_header("Access-Control-Allow-Origin", services.origin)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def body(self):
                return self.rfile.read(int(self.headers.get("Content-Length", 0)))

            def do_OPTIONS(self):
                self.send_response(204)
                if self.headers.get("Origin") == services.origin:
                    self.send_header("Access-Control-Allow-Origin", services.origin)
                    self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE")
                    self.send_header("Access-Control-Allow-Headers",
                                     self.headers.get("Access-Control-Request-Headers", ""))
                self.end_headers()

            def do_GET(self):
                url = urlsplit(self.path)
                if url.path == "/auth/v1/.well-known/jwks.json":
                    services.jwks_fetches += 1
                    key = jwt.algorithms.ECAlgorithm.to_jwk(services.key.public_key(), as_dict=True)
                    key.update(kid=services.kid, alg="ES256", use="sig")
                    return self.send(200, {"keys": [key]})
                if url.path == "/auth/v1/user":
                    try:
                        claims = jwt.decode(self.headers.get("Authorization", "").removeprefix("Bearer "),
                            services.key.public_key(), algorithms=["ES256"], audience="authenticated",
                            issuer=services.base + "/auth/v1")
                        return self.send(200, services.user(claims["sub"]))
                    except (jwt.PyJWTError, KeyError, StopIteration):
                        return self.send(401, {"error": "invalid_token"})
                if url.path.startswith("/storage/v1/object/sign/reciwise-reportes/"):
                    path = unquote(url.path.removeprefix("/storage/v1/object/sign/reciwise-reportes/"))
                    token = parse_qs(url.query).get("token", [""])[0]
                    with services.lock:
                        valid = services.read_tokens.get(token) == path
                        contents = services.objects.get(path)
                    if not valid or contents is None:
                        return self.send(403, {})
                    return self.send(200, contents, "image/png")
                if url.path.startswith("/__test/") and self.headers.get("x-test-control") == services.control:
                    if url.path.startswith("/__test/report/"):
                        return self.send(200, inspect_report(url.path.rsplit("/", 1)[1]))
                    if url.path == "/__test/state":
                        with services.lock:
                            state = {"jwks_fetches": services.jwks_fetches, "logins": services.logins,
                                     "object_hashes": {p: hashlib.sha256(b).hexdigest() for p,b in services.objects.items()},
                                     "deletions": list(services.deletions), "events": list(services.events)}
                        return self.send(200, state)
                return self.send(404, {})

            def do_POST(self):
                url = urlsplit(self.path)
                raw = self.body()
                if url.path.startswith("/__test/"):
                    if self.headers.get("x-test-control") != services.control:
                        return self.send(403, {})
                    data = json.loads(raw or b"{}")
                    if url.path == "/__test/fault":
                        if data.get("kind") not in {"storage_upload", "photo_persistence"}:
                            return self.send(422, {})
                        with services.lock:
                            services.faults.add(data["kind"])
                        return self.send(200, {})
                    if url.path == "/__test/consume":
                        return self.send(200, {"active": services.consume(data["kind"])})
                    if url.path == "/__test/event":
                        # A safe HTTP history without bodies, headers or query strings.
                        with services.lock:
                            services.events.append({k: data[k] for k in ("method", "path", "status")})
                        return self.send(200, {})
                    if url.path == "/__test/restart" and services.restart:
                        return self.send(200, services.restart())
                    return self.send(404, {})
                if url.path.startswith("/auth/v1/"):
                    if self.headers.get("apikey") != PUBLIC_KEY:
                        return self.send(401, {})
                    if url.path == "/auth/v1/logout":
                        return self.send(200, {})
                    if url.path == "/auth/v1/token":
                        data = json.loads(raw)
                        grant = parse_qs(url.query).get("grant_type", [""])[0]
                        if grant == "password":
                            user_id = services.accounts.get(data.get("email"))
                            if not user_id or data.get("password") != services.password:
                                return self.send(400, {"error": "invalid_grant", "msg": "Credenciales de prueba incorrectas"})
                        else:
                            user_id = services.refresh.get(data.get("refresh_token"))
                            if not user_id:
                                return self.send(400, {"error": "invalid_grant"})
                        services.logins += 1
                        return self.send(200, services.session(user_id))
                    return self.send(404, {})
                if self.headers.get("apikey") != STORAGE_KEY:
                    return self.send(403, {})
                prefix = "/storage/v1/object/"
                if url.path.startswith(prefix + "sign/reciwise-reportes/"):
                    path = unquote(url.path.removeprefix(prefix + "sign/reciwise-reportes/"))
                    token = secrets.token_urlsafe(24)
                    with services.lock:
                        services.read_tokens[token] = path
                    return self.send(200, {"signedURL": "/object/sign/reciwise-reportes/" + path + "?token=" + token})
                if url.path.startswith(prefix + "reciwise-reportes/"):
                    if services.consume("storage_upload"):
                        return self.send(503, {})  # External service failure, uncertain upload.
                    path = unquote(url.path.removeprefix(prefix + "reciwise-reportes/"))
                    with services.lock:
                        if path in services.objects:
                            return self.send(409, {})
                        services.objects[path] = raw
                    return self.send(200, {})
                return self.send(404, {})

            def do_DELETE(self):
                data = json.loads(self.body())
                if self.path != "/storage/v1/object/reciwise-reportes" or self.headers.get("apikey") != STORAGE_KEY:
                    return self.send(403, {})
                paths = data.get("prefixes", [])
                if len(paths) != 1 or not paths[0].startswith("reports/"):
                    return self.send(422, {})
                with services.lock:
                    services.objects.pop(paths[0], None)
                    services.deletions.append(paths[0])
                return self.send(200, [])

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:" + str(server.server_port)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield self
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
