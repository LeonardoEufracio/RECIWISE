"""Additional fail-closed guards for the disposable, interactive demonstration."""
import json
import os
import re

from sqlalchemy.engine import make_url


def require_local_docker(run):
    endpoint = json.loads(run("context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"))
    explicit = os.environ.get("DOCKER_HOST", "")
    if (not isinstance(endpoint, str) or not endpoint.startswith(("npipe://", "unix://"))
            or explicit and not explicit.startswith(("npipe://", "unix://"))):
        raise RuntimeError("Demo refuses a remote Docker context")


def require_disposable(info, database_url, token, expected_id):
    """Reject the persistent local container as well as all remote/shared targets."""
    target = make_url(database_url)
    bindings = info.get("NetworkSettings", {}).get("Ports", {}).get("5432/tcp")
    host = info.get("HostConfig", {})
    mounts = info.get("Mounts", [])
    if (not re.fullmatch(r"[0-9a-f]{32}", token or "")
            or not re.fullmatch(r"[0-9a-f]{64}", expected_id or "")
            or info.get("Id") != expected_id or not info.get("State", {}).get("Running")
            or info.get("Name") != "/reciwise-d2-test-" + token
            or info.get("Config", {}).get("Labels", {}).get("org.reciwise.d2.isolated") != token
            or target.get_backend_name() != "postgresql" or target.host != "127.0.0.1"
            or target.database != "reciwise_test_" + token or not target.port
            or bindings != [{"HostIp": "127.0.0.1", "HostPort": str(target.port)}]
            or host.get("Binds") or host.get("Mounts") or len(mounts) != 1
            or mounts[0].get("Type") != "volume"
            or mounts[0].get("Destination") != "/var/lib/postgresql/data"
            or not re.fullmatch(r"[0-9a-f]{64}", mounts[0].get("Name", ""))):
        raise RuntimeError("Demo requires its own running disposable loopback PostgreSQL")
