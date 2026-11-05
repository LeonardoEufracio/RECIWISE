"""Legacy subset runner. Shared-project execution is retired during 003 review.

Use run_isolated_postgres.py for automatic disposable provisioning and all checks.
This subset requires an already provisioned isolated localhost marker, never .env.
"""
import argparse
import os
import subprocess
import sys
import uuid
from pathlib import Path

from isolated_postgres import connection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-project-env", action="store_true",
                        help="Retired: always refuses to read project credentials")
    parser.add_argument("--suite", choices=("new", "d2"), default="d2")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    if args.from_project_env:
        parser.error("Shared-project runner retired during 003 review; use tests/run_isolated_postgres.py")
    if not env.get("RECIWISE_TEST_DATABASE_URL"):
        parser.error("An explicit PostgreSQL test URL is required")
    if not env.get("RECIWISE_ISOLATED_TOKEN"):
        parser.error("Only a marked disposable localhost database is allowed during 003 review")
    guard = connection()
    guard.close()
    env["RECIWISE_ALLOW_ROLLBACK_TESTS"] = "1"
    artifacts = root / ".test-artifacts" / f"postgres-{uuid.uuid4().hex}"
    artifacts.mkdir(parents=True)
    env["RECIWISE_TEST_EVIDENCE_DIR"] = str(artifacts)
    paths = ["tests/test_postgres.py", "tests/test_postgres_persistence.py"]
    if args.suite == "d2":
        paths = ["tests/test_api.py", "tests/test_frontend_contract.py", "tests/test_security.py"] + paths
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *paths,
               "--tb=short", "-rs", f"--junitxml={artifacts / 'pytest-d2.xml'}"]
    print(f"Evidence: {artifacts.relative_to(root)}", flush=True)
    return subprocess.run(command, cwd=root, env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
