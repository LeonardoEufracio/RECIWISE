import os
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")

from app.db import Base, get_db
from app.main import app
from app import main
from app.models import Profile
from app.security import Actor, get_current_actor


@pytest.fixture
def test_env(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:",
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def enable_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    # SQLite unit tests replace only verification; they do not prove schema 003.
    # The production app has no switch or environment variable to skip its guard.
    monkeypatch.setattr(main, "get_engine", lambda: engine)
    monkeypatch.setattr(main, "verify_schema", lambda engine: None)
    citizen_id, second_id, manager_id, driver_id = [uuid.uuid4() for _ in range(4)]
    with Session(engine) as db:
        for uid, role in [(citizen_id, "ciudadano"), (second_id, "ciudadano"),
                          (manager_id, "encargado_municipal"), (driver_id, "chofer")]:
            db.add(Profile(id=uid, role=role))
        db.commit()

    state = {"actor": Actor(citizen_id, "ciudadano"), "citizen": citizen_id,
             "second": second_id, "manager": manager_id, "driver": driver_id}
    def fake_db():
        with Session(engine, expire_on_commit=False) as db:
            yield db
    def fake_actor():
        return state["actor"]

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_actor] = fake_actor
    # Las dependencias de roles usan internamente get_current_actor; el override funciona.
    with TestClient(app) as client:
        yield client, state, engine
    app.dependency_overrides.clear()
    engine.dispose()
