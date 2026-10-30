"""Provision/migrate only our own disposable local Docker PostgreSQL; never .env."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid

from isolated_postgres import ROOT, bootstrap, connection


def docker(*args):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"Docker {args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("shifts", "photos", "recovery", "audit", "schema", "reconciler", "integrated", "all"), default="all")
    parser.add_argument("--refresh-schema-manifest", action="store_true",
                        help="Build the reviewed manifest only from this fresh, owned local database")
    args = parser.parse_args()
    token = uuid.uuid4().hex
    name = "reciwise-d2-test-" + token
    database = "reciwise_test_" + token
    artifact = ROOT / ".test-artifacts" / name
    artifact.mkdir(parents=True)
    owned_id = None
    try:
        docker("info", "--format", "{{.ServerVersion}}")
        owned_id = docker("run", "--detach", "--name", name,
            "--label", "org.reciwise.d2.isolated=" + token,
            "--publish", "127.0.0.1::5432", "--env", "POSTGRES_HOST_AUTH_METHOD=trust",
            "--env", "POSTGRES_DB=" + database, "postgres:17-alpine")
        info = json.loads(docker("inspect", owned_id))[0]
        assert info["Config"]["Labels"]["org.reciwise.d2.isolated"] == token
        binding = info["NetworkSettings"]["Ports"]["5432/tcp"]
        assert len(binding) == 1 and binding[0]["HostIp"] == "127.0.0.1"
        port = int(binding[0]["HostPort"])
        for _ in range(100):
            probe = subprocess.run(["docker", "exec", owned_id, "pg_isready", "-h", "127.0.0.1", "-U", "postgres",
                                    "-d", database], capture_output=True, timeout=5)
            if probe.returncode == 0:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Isolated PostgreSQL failed readiness; no fallback allowed")
        url = f"postgresql+psycopg://postgres@127.0.0.1:{port}/{database}"
        os.environ["RECIWISE_ISOLATED_TOKEN"] = token
        profiles = bootstrap(url)
        if args.refresh_schema_manifest:
            sys.path.insert(0, str(ROOT))
            from sqlalchemy import create_engine
            from app.schema_guard import MANIFEST, capture_catalog
            schema_engine = create_engine(url)
            try:
                approved = {"schema": "003", "source": "fresh isolated PostgreSQL; unchanged migrations 001 + 003",
                    "migration_sha256": {name: hashlib.sha256((ROOT / "migrations" / name).read_bytes()).hexdigest()
                        for name in ("001_sprint1.sql", "003_sprint1_concurrencia.sql")},
                    "catalog": capture_catalog(schema_engine)}
                MANIFEST.write_text(json.dumps(approved, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                print("Manifest generated from fresh isolated migrations; review the artifact before release.")
            finally:
                schema_engine.dispose()
            return 0
        check = connection(url)
        try:
            server_version = check.execute("SHOW server_version").fetchone()[0]
            assert 170000 <= check.info.server_version < 180000
        finally:
            check.close()
        env = os.environ.copy()
        # Explicit fake service configuration prevents accidental .env fallbacks.
        env.update(DATABASE_URL=url, SUPABASE_URL="https://storage.invalid",
            SUPABASE_SERVICE_ROLE_KEY="isolated-test-only", STORAGE_BUCKET="reciwise-reportes",
            RECIWISE_TEST_DATABASE_URL=url, RECIWISE_ALLOW_ROLLBACK_TESTS="1",
            RECIWISE_ISOLATED_PROFILES=json.dumps(profiles), RECIWISE_TEST_EVIDENCE_DIR=str(artifact))
        for key in ("RECIWISE_PUBLIC_URL", "RECIWISE_PUBLIC_KEY", "RECIWISE_STORAGE_URL",
                    "RECIWISE_STORAGE_KEY", "RECIWISE_CITIZEN_ACCESS_TOKEN"):
            env.pop(key, None)
        paths = {"shifts": ["tests/test_shift_concurrency.py"],
                 "photos": ["tests/test_photo_concurrency.py"],
                 "recovery": ["tests/test_photo_recovery.py", "tests/test_photo_restart.py"],
                 "audit": ["tests/test_deployment_readiness.py"],
                 "schema": ["tests/test_schema_guard.py"],
                 "reconciler": ["tests/test_reconciler.py"]}
        selected = paths.get(args.phase, ["tests/test_api.py", "tests/test_frontend_contract.py",
            "tests/test_security.py", "tests/test_postgres.py", "tests/test_postgres_persistence.py", "tests/test_shift_concurrency.py",
            "tests/test_photo_concurrency.py", "tests/test_photo_recovery.py",
            "tests/test_photo_restart.py", "tests/test_storage_failures.py", "tests/test_migration_003.py"])
        if args.phase == "all":
            selected += ["tests/test_deployment_readiness.py", "tests/test_schema_guard.py", "tests/test_reconciler.py"]
        manifest = {"container": name, "image_id": info["Image"], "server_version": server_version, "localhost_only": True,
                    "schema_contract_sha256": hashlib.sha256((ROOT / "app/schema_003.json").read_bytes()).hexdigest(),
                    "isolated_database": database, "migrations": ["001", "003"],
                    "migration_sha256": {name: hashlib.sha256((ROOT / "migrations" / name).read_bytes()).hexdigest()
                        for name in ("001_sprint1.sql", "003_sprint1_concurrencia.sql", "rollback/003_sprint1_concurrencia.sql")},
                    "supabase_schemas": "minimal local stubs; no remote Auth/Storage", "phase": args.phase}
        (artifact / "environment.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Isolated PostgreSQL only; evidence: {artifact.relative_to(ROOT)}", flush=True)
        if args.phase == "integrated":
            result = subprocess.run([sys.executable, str(ROOT / "tests/run_integrated_sprint1.py")],
                                    cwd=ROOT, env=env)
            return result.returncode
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            *selected, "--tb=short", "-rs", f"--junitxml={artifact / 'pytest.xml'}"], cwd=ROOT, env=env)
        return result.returncode
    finally:
        if owned_id:
            info = json.loads(docker("inspect", owned_id))[0]
            if (info["Id"] == owned_id and info["Config"]["Labels"].get("org.reciwise.d2.isolated") == token):
                docker("rm", "--force", "--volumes", owned_id)
                print("Owned disposable PostgreSQL removed; shared databases were never contacted.", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
