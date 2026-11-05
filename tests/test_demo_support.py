"""Unit tests of the new launcher boundary, not replacement business tests."""
from copy import deepcopy
import json

import pytest

from demo_support import require_disposable, require_local_docker

TOKEN = "a" * 32
IDENTITY = "b" * 64
URL = "postgresql+psycopg://postgres@127.0.0.1:55444/reciwise_test_" + TOKEN


def owned():
    return {"Id": IDENTITY, "Name": "/reciwise-d2-test-" + TOKEN, "State": {"Running": True},
        "Config": {"Labels": {"org.reciwise.d2.isolated": TOKEN}}, "HostConfig": {"Binds": None},
        "NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55444"}]}},
        "Mounts": [{"Type": "volume", "Name": "c" * 64, "Destination": "/var/lib/postgresql/data"}]}


def test_accepts_only_owned_disposable_identity():
    require_disposable(owned(), URL, TOKEN, IDENTITY)


@pytest.mark.parametrize("case", ["persistent", "label", "mount", "named_volume", "port", "remote", "database", "id", "stopped"])
def test_rejects_persistent_shared_or_mismatched_target(case):
    info = deepcopy(owned()); url = URL
    if case == "persistent": info["Name"] = "/reciwise-local-pg-existing"
    elif case == "label": info["Config"]["Labels"] = {"org.reciwise.local.owner": TOKEN}
    elif case == "mount": info["HostConfig"]["Binds"] = ["existing:/var/lib/postgresql/data"]
    elif case == "named_volume": info["Mounts"][0]["Name"] = "reciwise-local-pgdata-existing"
    elif case == "port": info["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostIp"] = "0.0.0.0"
    elif case == "remote": url = URL.replace("127.0.0.1", "shared.supabase.invalid")
    elif case == "database": url = URL.replace("reciwise_test_" + TOKEN, "postgres")
    elif case == "id": info["Id"] = "d" * 64
    elif case == "stopped": info["State"]["Running"] = False
    with pytest.raises(RuntimeError, match="disposable"):
        require_disposable(info, url, TOKEN, IDENTITY)


@pytest.mark.parametrize("endpoint,explicit,accepted", [
    ("npipe://docker_engine", "", True), ("unix:///var/run/docker.sock", "", True),
    ("ssh://remote", "", False), ("npipe://docker_engine", "tcp://remote:2375", False)])
def test_docker_context_checked_before_demo_provisioning(monkeypatch, endpoint, explicit, accepted):
    monkeypatch.setenv("DOCKER_HOST", explicit)
    run = lambda *args: json.dumps(endpoint)
    if accepted:
        require_local_docker(run)
    else:
        with pytest.raises(RuntimeError, match="remote"):
            require_local_docker(run)
