import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app
from app import main
from app.models import Report, ServiceSite, Vehicle
from app.security import Actor, get_current_actor
from isolated_postgres import connection

ISOLATED_ONLY = pytest.mark.skipif(not os.getenv("RECIWISE_ISOLATED_TOKEN"),
    reason="Disposable marked localhost PostgreSQL required; never use shared Supabase")


@pytest.fixture
def pg_case(monkeypatch):
    engine = create_engine(os.environ["RECIWISE_TEST_DATABASE_URL"], pool_size=8, max_overflow=8)
    # Use the fixture engine, retaining the real PostgreSQL schema verifier.
    monkeypatch.setattr(main, "get_engine", lambda: engine)
    ids = {name: uuid.uuid4() for name in ("citizen", "manager", "driver", "driver2")}
    conn = connection()
    try:
        for name, role in (("citizen", "ciudadano"), ("manager", "encargado_municipal"),
                           ("driver", "chofer"), ("driver2", "chofer")):
            conn.execute("INSERT INTO auth.users(id) VALUES (%s)", (ids[name],))
            conn.execute("UPDATE public.profiles SET role=%s WHERE id=%s", (role, ids[name]))
    finally:
        conn.close()
    ids.update({name: uuid.uuid4() for name in ("report", "vehicle", "vehicle2", "departure", "disposal")})
    with Session(engine) as db:
        db.add(Report(id=ids["report"], citizen_id=ids["citizen"], description="Reporte aislado de concurrencia",
                      latitude=-12, longitude=-77, observed_at=datetime.now(timezone.utc)))
        for name in ("vehicle", "vehicle2"):
            db.add(Vehicle(id=ids[name], label="test-" + str(ids[name]), vehicle_type="otro", available=True))
        for name, kind in (("departure", "salida"), ("disposal", "descarga")):
            db.add(ServiceSite(id=ids[name], name="Sitio ficticio", site_type=kind, latitude=-12, longitude=-77))
        db.commit()
    state = {"actor": Actor(ids["manager"], "encargado_municipal")}

    def database():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_actor] = lambda: state["actor"]
    try:
        with TestClient(app) as client:
            yield client, engine, ids, state
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def shift_payload(ids, **overrides):
    start = datetime(2030, 1, 1, 8, tzinfo=timezone.utc)
    result = dict(vehicle_id=str(ids["vehicle"]), driver_id=str(ids["driver"]),
        departure_site_id=str(ids["departure"]), disposal_site_id=str(ids["disposal"]),
        starts_at=start.isoformat(), ends_at=(start + timedelta(hours=1)).isoformat())
    result.update(overrides)
    return result


class FakeStorage:
    """Explicit simulation; PostgreSQL in these tests is always real."""
    def __init__(self):
        self.objects = {}
        self.deletions = []
        self.lock = threading.Lock()
        self.barrier = None

    def upload(self, path, contents, content_type):
        if self.barrier:
            self.barrier.wait(timeout=10)
        with self.lock:
            assert path not in self.objects, "The service must not overwrite objects"
            self.objects[path] = contents

    def remove(self, path):
        with self.lock:
            self.deletions.append(path)
            self.objects.pop(path, None)
