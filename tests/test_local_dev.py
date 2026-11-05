"""Tooling unit tests: temporary files/mocks, not PostgreSQL integration."""
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
dev = importlib.import_module("local_dev")
services = importlib.import_module("local_dev_services")


@pytest.fixture
def local_config():
    owner = "a" * 32
    return {"format": 1, "workspace": dev.WORKSPACE, "owner": owner, "database": "reciwise_test_" + owner,
            "container": "reciwise-local-pg-" + dev.WORKSPACE, "volume": "reciwise-local-pgdata-" + dev.WORKSPACE,
            "ports": {"db": 54329, "api": 8000, "auth": 54321, "ui": 5173}}


@pytest.mark.parametrize("key,value", [("workspace", "other"), ("owner", "bad"),
    ("database", "shared"), ("container", "production"), ("volume", "another-volume")])
def test_refuses_nonlocal_identity(local_config, key, value):
    with pytest.raises(dev.LocalError, match="identity_invalid"):
        dev.validate({**local_config, key: value})


@pytest.mark.parametrize("ports", [{"db": 5432}, {"db": 8000, "api": 8000, "auth": 54321, "ui": 5173},
    {"db": "54329", "api": 8000, "auth": 54321, "ui": 5173}, {"db": 1, "api": 8000, "auth": 54321, "ui": 5173}])
def test_refuses_invalid_ports(local_config, ports):
    with pytest.raises(dev.LocalError, match="ports_invalid"):
        dev.validate({**local_config, "ports": ports})


def test_process_configuration_shadows_remote_settings(local_config, monkeypatch):
    monkeypatch.setattr(dev, "credentials", lambda: {"database_password": "fictitious-unit-only"})
    monkeypatch.setenv("DATABASE_URL", "postgresql://unreachable.invalid/shared")
    monkeypatch.setenv("SUPABASE_URL", "https://unreachable.supabase.co")
    monkeypatch.setenv("VITE_SECRET_EXAMPLE", "must-be-removed")
    env = dev.environment(local_config)
    target = make_url(env["DATABASE_URL"])
    assert target.host == "127.0.0.1" and target.database == local_config["database"]
    assert env["SUPABASE_URL"] == "http://127.0.0.1:54321"
    assert env["VITE_API_URL"] == "http://127.0.0.1:8000"
    assert "VITE_SECRET_EXAMPLE" not in env
    assert env["SUPABASE_SERVICE_ROLE_KEY"] == services.LocalServices.__init__.__globals__["STORAGE_KEY"]


@pytest.mark.parametrize("path", ["../escape", "/absolute", "reports/../../escape", "reports\\escape", "a//b", "", "a\x00b"])
def test_storage_paths_cannot_escape(tmp_path, path):
    objects = services.DiskObjects(tmp_path / "objects")
    with pytest.raises(KeyError):
        objects[path] = b"fake"
    assert list(objects) == []


def test_storage_bytes_survive_new_instance(tmp_path):
    path = "reports/actor/report/operation.png"
    objects = services.DiskObjects(tmp_path / "objects")
    objects[path] = b"fictitious-image"
    restarted = services.DiskObjects(tmp_path / "objects")
    assert restarted[path] == b"fictitious-image"
    assert restarted.pop(path) == b"fictitious-image"
    assert restarted.pop(path, None) is None


def test_signed_tokens_persist_but_expire(tmp_path, monkeypatch):
    monkeypatch.setattr(services.time, "time", lambda: 100)
    path = tmp_path / "tokens.json"
    tokens = services.DiskTokens(path, 300)
    tokens["fictitious"] = "reports/fake.png"
    assert services.DiskTokens(path, 300)["fictitious"] == "reports/fake.png"
    monkeypatch.setattr(services.time, "time", lambda: 401)
    assert services.DiskTokens(path, 300).get("fictitious") is None


def test_exclusive_supervisor_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, "STATE", tmp_path)
    with dev.exclusive():
        with pytest.raises(dev.LocalError, match="already_running"):
            with dev.exclusive():
                pytest.fail("Concurrent supervisor accepted")
    with dev.exclusive():
        pass


def docker_objects(c):
    return ({"Labels": {dev.OWNER_LABEL: c["owner"]}},
            {"Config": {"Labels": {dev.OWNER_LABEL: c["owner"]}},
             "HostConfig": {"PortBindings": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(c["ports"]["db"])}]}},
             "Mounts": [{"Type": "volume", "Name": c["volume"], "Destination": "/var/lib/postgresql/data"}]})


@pytest.mark.parametrize("change", ["label", "host", "volume"])
def test_ownership_checked_before_database_actions(local_config, monkeypatch, change):
    volume, container = docker_objects(local_config)
    if change == "label": container["Config"]["Labels"][dev.OWNER_LABEL] = "other-owner"
    if change == "host": container["HostConfig"]["PortBindings"]["5432/tcp"][0]["HostIp"] = "0.0.0.0"
    if change == "volume": container["Mounts"][0]["Name"] = "other-volume"
    monkeypatch.setattr(dev, "docker", lambda *args, **kw: json.dumps([volume if args[0] == "volume" else container]))
    with pytest.raises(dev.LocalError, match="ownership_or_binding"):
        dev.start_db(local_config)


def test_bootstrap_guard_transmits_local_password_without_printing(monkeypatch):
    import isolated_postgres
    marker = "b" * 32
    called = {}
    conn = SimpleNamespace(execute=lambda *a: SimpleNamespace(fetchone=lambda: (marker,)), close=lambda: None)
    def connect(**kw):
        called.update(kw)
        return conn
    monkeypatch.setenv("RECIWISE_ISOLATED_TOKEN", marker)
    monkeypatch.setattr(isolated_postgres.psycopg, "connect", connect)
    assert isolated_postgres.connection("postgresql+psycopg://postgres:local-unit-only@127.0.0.1:54329/reciwise_test_" + marker) is conn
    assert called["password"] == "local-unit-only"


def test_api_startup_rejects_health_200_without_readiness(monkeypatch):
    class Client:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, path):
            assert path.endswith('/ready')
            return SimpleNamespace(status_code=200, json=lambda: {"status": "ok"})
    clock = iter((0, 1, 60))
    monkeypatch.setattr(dev.httpx, "Client", lambda **kw: Client())
    monkeypatch.setattr(dev.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(dev.time, "sleep", lambda _: None)
    with pytest.raises(dev.LocalError, match="readiness_timeout"):
        dev.ready(SimpleNamespace(poll=lambda: None), 'http://127.0.0.1:8000', api=True)


@pytest.mark.parametrize("target", ['tcp://127.0.0.1:2375', 'tcp://remote.invalid:2376', 'ssh://remote.invalid'])
def test_remote_docker_override_refused_before_any_command(monkeypatch, target):
    monkeypatch.setattr(dev, '_docker_checked', False)
    monkeypatch.setenv('DOCKER_HOST', target)
    def unexpected(*args, **kw): pytest.fail('A Docker operation was attempted')
    monkeypatch.setattr(dev.subprocess, 'run', unexpected)
    with pytest.raises(dev.LocalError, match='remote_docker_context_refused'):
        dev.docker('start', 'anything')


def test_remote_docker_current_context_refused(monkeypatch):
    monkeypatch.setattr(dev, '_docker_checked', False)
    monkeypatch.delenv('DOCKER_HOST', raising=False)
    called=[]
    def run(args, **kw):
        called.append(args)
        return SimpleNamespace(returncode=0, stdout='"ssh://remote.invalid"')
    monkeypatch.setattr(dev.subprocess, 'run', run)
    with pytest.raises(dev.LocalError, match='remote_docker_context_refused'):
        dev.docker('start', 'anything')
    assert len(called)==1 and called[0][1:3]==['context','inspect']
