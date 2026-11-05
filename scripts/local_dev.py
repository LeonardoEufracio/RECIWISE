"""Persistent, loopback-only development stack. Never reads a project .env.

init provisions only the labelled local volume; up never applies migrations.
Run using the repository .venv. No production authentication overrides.
"""
import argparse
from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".localdev"
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

import httpx
from sqlalchemy import URL, create_engine
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from isolated_postgres import bootstrap, connection
from integrated_services import PUBLIC_KEY, STORAGE_KEY
from local_dev_services import PersistentServices, atomic_write, write_json
from app.schema_guard import SchemaCheckError, verify_schema

MIGRATIONS = ("001_sprint1.sql", "002_sprint2_3_estructura.sql", "003_sprint1_concurrencia.sql")
OWNER_LABEL = "org.reciwise.local.owner"
WORKSPACE = hashlib.sha256(str(ROOT).lower().encode()).hexdigest()[:12]
HIDDEN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_docker_checked = False


class LocalError(RuntimeError):
    pass


def docker(*args, optional=False):
    global _docker_checked
    if not _docker_checked:
        explicit = os.environ.get("DOCKER_HOST", "")
        if explicit and not explicit.startswith(("npipe://", "unix://")):
            raise LocalError("remote_docker_context_refused")
        context = subprocess.run(["docker", "context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"],
                                 capture_output=True, text=True, creationflags=HIDDEN, timeout=15)
        if context.returncode or not json.loads(context.stdout).startswith(("npipe://", "unix://")):
            raise LocalError("remote_docker_context_refused")
        _docker_checked = True
    result = subprocess.run(["docker", *args], capture_output=True, text=True,
                            creationflags=HIDDEN, timeout=90)
    if result.returncode:
        if optional:
            return None
        raise LocalError("docker_command_failed")  # Never echo Docker stderr/config/secrets.
    return result.stdout.strip()


def hashes():
    return {name: hashlib.sha256((ROOT / "migrations" / name).read_bytes()).hexdigest() for name in MIGRATIONS}


def validate(config):
    owner = config.get("owner", "")
    if (config.get("format") != 1 or config.get("workspace") != WORKSPACE
            or len(owner) != 32 or any(c not in "0123456789abcdef" for c in owner)
            or config.get("database") != "reciwise_test_" + owner
            or config.get("container") != "reciwise-local-pg-" + WORKSPACE
            or config.get("volume") != "reciwise-local-pgdata-" + WORKSPACE):
        raise LocalError("local_identity_invalid")
    ports = config.get("ports", {})
    if (set(ports) != {"db", "api", "auth", "ui"} or len(set(ports.values())) != 4
            or any(type(n) is not int or n < 1024 or n > 65535 for n in ports.values())):
        raise LocalError("local_ports_invalid")
    return config


def config():
    if not (STATE / "config.json").is_file():
        raise LocalError("run_init_first")
    return validate(json.loads((STATE / "config.json").read_text()))


def credentials():
    return json.loads((STATE / "credentials.json").read_text())


def urls(c):
    return {k: "http://127.0.0.1:" + str(c["ports"][k]) for k in ("api", "auth", "ui")}


def environment(c):
    """All Settings and Vite connection fields explicitly shadow .env files."""
    target = URL.create("postgresql+psycopg", username="postgres", password=credentials()["database_password"],
                        host="127.0.0.1", port=c["ports"]["db"], database=c["database"])
    env = dict(os.environ)
    for name in list(env):
        if name.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"} or name.upper().startswith(("PG", "VITE_", "SUPABASE_", "RECIWISE_")):
            env.pop(name)
    addresses = urls(c)
    origins = addresses["ui"] + ",http://localhost:" + str(c["ports"]["ui"])
    env.update(DATABASE_URL=target.render_as_string(hide_password=False),
               RECIWISE_TEST_DATABASE_URL=target.render_as_string(hide_password=False),
               RECIWISE_ISOLATED_TOKEN=c["owner"], SUPABASE_URL=addresses["auth"],
               SUPABASE_SERVICE_ROLE_KEY=STORAGE_KEY, STORAGE_BUCKET="reciwise-reportes", CORS_ORIGINS=origins,
               VITE_API_URL=addresses["api"], VITE_SUPABASE_URL=addresses["auth"],
               VITE_SUPABASE_PUBLISHABLE_KEY=PUBLIC_KEY, VITE_ENABLE_DEMO="false")
    return env


@contextmanager
def exclusive():
    STATE.mkdir(exist_ok=True)
    with (STATE / "local.lock").open("a+b") as stream:
        if not stream.tell():
            stream.write(b"0"); stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise LocalError("local_environment_already_running") from None
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def owned(c):
    """Check BOTH Docker objects and exact loopback binding before any DB action."""
    volume = json.loads(docker("volume", "inspect", c["volume"]))[0]
    container = json.loads(docker("inspect", c["container"]))[0]
    labels = container["Config"].get("Labels") or {}
    mounts = container["Mounts"]
    binding = container["HostConfig"]["PortBindings"].get("5432/tcp")
    if (labels.get(OWNER_LABEL) != c["owner"] or (volume.get("Labels") or {}).get(OWNER_LABEL) != c["owner"]
            or binding != [{"HostIp": "127.0.0.1", "HostPort": str(c["ports"]["db"])}]
            or not any(m.get("Type") == "volume" and m.get("Name") == c["volume"]
                       and m.get("Destination") == "/var/lib/postgresql/data" for m in mounts)):
        raise LocalError("docker_ownership_or_binding_invalid")
    return container


def free_port(port):
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            raise LocalError("local_port_unavailable_" + str(port)) from None


def start_db(c):
    info = owned(c)
    if not info["State"]["Running"]:
        free_port(c["ports"]["db"])
        docker("start", c["container"])
    for _ in range(150):
        if docker("exec", c["container"], "pg_isready", "-h", "127.0.0.1", "-U", "postgres", optional=True):
            return
        time.sleep(.2)
    raise LocalError("local_database_not_ready")


def inspect_db(c):
    owned(c)
    env = environment(c)
    os.environ.update({k: env[k] for k in ("RECIWISE_TEST_DATABASE_URL", "RECIWISE_ISOLATED_TOKEN")})
    db = connection()  # Requires exact localhost database name AND in-database random marker.
    try:
        if not 170000 <= db.info.server_version < 180000:
            raise LocalError("local_postgresql_version_unsupported")
    finally:
        db.close()
    engine = create_engine(env["DATABASE_URL"], connect_args={"connect_timeout": 5})
    try:
        verify_schema(engine)  # Read-only approved manifest; no refresh, migration or bypass.
    finally:
        engine.dispose()


def init(args):
    with exclusive():
        if (STATE / "config.json").exists():
            c = config()
            if not c.get("initialized"):
                raise LocalError("partial_local_initialization_requires_review")
            start_db(c); inspect_db(c)
            print("Local environment already initialized; no migrations or fixtures replayed.")
            return
        owner = uuid.uuid4().hex
        c = validate({"format": 1, "workspace": WORKSPACE, "owner": owner,
                      "database": "reciwise_test_" + owner,
                      "container": "reciwise-local-pg-" + WORKSPACE, "volume": "reciwise-local-pgdata-" + WORKSPACE,
                      "ports": {"db": args.db_port, "api": args.api_port, "auth": args.auth_port, "ui": args.ui_port},
                      "initialized": False})
        ignored = subprocess.run(["git", "check-ignore", "--quiet", "--", ".localdev/config.json"], cwd=ROOT,
                                 capture_output=True, creationflags=HIDDEN)
        if ignored.returncode:
            raise LocalError("private_local_directory_not_ignored")
        for port in c["ports"].values():
            free_port(port)
        docker("info", "--format", "{{.ServerVersion}}")
        if docker("inspect", c["container"], optional=True) or docker("volume", "inspect", c["volume"], optional=True):
            raise LocalError("existing_unowned_docker_resource_refused")
        private = {"database_password": secrets.token_urlsafe(32), "auth_password": secrets.token_urlsafe(24), "kid": uuid.uuid4().hex}
        key = ec.generate_private_key(ec.SECP256R1())
        atomic_write(STATE / "auth-signing.key", key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        write_json(STATE / "credentials.json", private)
        write_json(STATE / "config.json", c)
        # Environment-file path (not a password) is passed to Docker's command line.
        pg_env = "POSTGRES_USER=postgres\nPOSTGRES_DB=" + c["database"] + "\nPOSTGRES_PASSWORD=" + private["database_password"] + "\n"
        atomic_write(STATE / "postgres.env", pg_env.encode())
        docker("volume", "create", "--label", OWNER_LABEL + "=" + c["owner"], c["volume"])
        docker("create", "--name", c["container"], "--label", OWNER_LABEL + "=" + c["owner"],
               "--publish", "127.0.0.1:" + str(c["ports"]["db"]) + ":5432", "--env-file", str(STATE / "postgres.env"),
               "--mount", "type=volume,source=" + c["volume"] + ",target=/var/lib/postgresql/data", "postgres:17-alpine")
        start_db(c)
        env = environment(c)
        os.environ.update({k: env[k] for k in ("RECIWISE_ISOLATED_TOKEN", "RECIWISE_TEST_DATABASE_URL")})
        # An existing/partially migrated database is NEVER reset or repaired here.
        db = connection(verify=False)
        try:
            if db.execute("SELECT count(*) FROM pg_tables WHERE schemaname IN ('public','auth','storage')").fetchone()[0]:
                raise LocalError("nonempty_database_initialization_refused")
        finally:
            db.close()
        c["profiles"] = bootstrap(env["DATABASE_URL"])
        inspect_db(c)
        c.update(initialized=True, migration_sha256=hashes())
        write_json(STATE / "config.json", c)
        print("Initialized owned PostgreSQL volume: prerequisites + 001 + 002 + 003; schema verified.")
        print("Accounts: citizen@example.test, manager@example.test, driver@example.test, driver2@example.test")
        print("Fictitious local password: open .localdev/credentials.json in VS Code; never commit it.")


def stop_process(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=5)


def ready(process, address, *, api=False):
    deadline = time.monotonic() + 50
    with httpx.Client(trust_env=False, timeout=3) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise LocalError("local_process_startup_failed")
            try:
                response = client.get(address + ("/ready" if api else "/"))
                if response.status_code == 200 and (not api or response.json() == {"status": "ready", "schema": "003"}):
                    return
            except httpx.HTTPError:
                pass
            time.sleep(.3)
    raise LocalError("local_process_readiness_timeout")


def up():
    with exclusive():
        c = config()
        if not c.get("initialized") or c.get("migration_sha256") != hashes():
            raise LocalError("local_schema_source_changed_or_init_incomplete")
        for kind in ("api", "auth", "ui"):
            free_port(c["ports"][kind])
        start_db(c); inspect_db(c)
        env = environment(c)
        os.environ.update({k: env[k] for k in ("RECIWISE_ISOLATED_TOKEN", "RECIWISE_TEST_DATABASE_URL")})
        addresses = urls(c)
        instance = uuid.uuid4().hex
        runtime = {"instance": instance, "owner": c["owner"], "phase": "starting", "pid": os.getpid(), "urls": addresses}
        write_json(STATE / "runtime.json", runtime)
        backend = frontend = None
        try:
            origins = [addresses["ui"], "http://localhost:" + str(c["ports"]["ui"])]
            with ExitStack() as lifecycle:
                services = lifecycle.enter_context(PersistentServices(c["profiles"], origins, STATE, credentials()).serve(c["ports"]["auth"]))
                if services.base != addresses["auth"]:
                    raise LocalError("local_auth_issuer_mismatch")
                backend = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                    "--port", str(c["ports"]["api"]), "--no-access-log"], cwd=ROOT, env=env,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=HIDDEN)
                lifecycle.callback(stop_process, backend)
                ready(backend, addresses["api"], api=True)
                frontend = subprocess.Popen(["node", str(ROOT / "scripts/local_dev_vite.mjs"),
                    str(c["ports"]["ui"])], cwd=ROOT / "frontend", env=env,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=HIDDEN)
                lifecycle.callback(stop_process, frontend)
                ready(frontend, addresses["ui"])
                runtime.update(phase="ready", api_pid=backend.pid, ui_pid=frontend.pid)
                write_json(STATE / "runtime.json", runtime)
                print("LOCAL ONLY: React " + addresses["ui"] + " | FastAPI " + addresses["api"], flush=True)
                print("Ready: 001+002+003, schema guard and ES256/JWKS enabled. Auth/Storage are local simulators.", flush=True)
                print("Stop: Ctrl+C or python scripts/local_dev.py down. Persistent data is retained.", flush=True)
                while True:
                    if backend.poll() is not None or frontend.poll() is not None:
                        raise LocalError("local_child_process_exited")
                    stop_file = STATE / "stop.json"
                    if stop_file.exists() and json.loads(stop_file.read_text()).get("instance") == instance:
                        break
                    time.sleep(.4)
        except KeyboardInterrupt:
            pass
        except (LocalError, SchemaCheckError) as exc:
            runtime["error"] = exc.code if isinstance(exc, SchemaCheckError) else str(exc)
            raise
        finally:
            stop_process(frontend); stop_process(backend)
            if owned(c)["State"]["Running"]:
                docker("stop", "--time", "10", c["container"])
            runtime["phase"] = "stopped"
            write_json(STATE / "runtime.json", runtime)
            print("Local processes stopped; PostgreSQL volume and simulated photos retained.", flush=True)


def down():
    c = config()
    runtime_file = STATE / "runtime.json"
    if runtime_file.exists():
        r = json.loads(runtime_file.read_text())
        if r.get("owner") != c["owner"]:
            raise LocalError("local_runtime_identity_invalid")
        if r.get("phase") in {"ready", "starting"}:
            write_json(STATE / "stop.json", {"instance": r["instance"]})
            for _ in range(100):
                if json.loads(runtime_file.read_text()).get("phase") == "stopped":
                    print("Stopped; persistent volume and local identities/photos retained."); return
                time.sleep(.3)
            raise LocalError("supervisor_not_responding_no_process_was_force_killed")
    if owned(c)["State"]["Running"]:
        docker("stop", "--time", "10", c["container"])
    print("Owned PostgreSQL stopped; volume retained. No data removed.")


def status():
    c = config(); info = owned(c)
    report = {"postgresql_running": info["State"]["Running"], "local_only": True, "urls": urls(c), "schema": "unverified"}
    if info["State"]["Running"]:
        inspect_db(c); report["schema"] = "001+002+003 compatible"
    with httpx.Client(trust_env=False, timeout=3) as client:
        try:
            response = client.get(urls(c)["api"] + "/ready")
            report["api_ready"] = response.status_code == 200 and response.json() == {"status": "ready", "schema": "003"}
        except httpx.HTTPError:
            report["api_ready"] = False
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "up", "down", "status"))
    for name, value in (("db", 54329), ("api", 8000), ("auth", 54321), ("ui", 5173)):
        parser.add_argument("--" + name + "-port", type=int, default=value)
    args = parser.parse_args()
    try:
        {"init": lambda: init(args), "up": up, "down": down, "status": status}[args.command]()
        return 0
    except SchemaCheckError as exc:
        print("Local environment refused: " + exc.code, file=sys.stderr)
    except LocalError as exc:
        print("Local environment refused: " + str(exc), file=sys.stderr)
    except Exception:
        print("Local environment failed safely; no remote fallback or secret diagnostics.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
