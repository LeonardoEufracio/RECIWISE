"""Resource management on owned PostgreSQL; signed fictitious JWT/JWKS."""
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models import ServiceSite, Shift, Vehicle
from concurrency_support import ISOLATED_ONLY, pg_case, shift_payload
from test_events import auth, jwt_keys

pytestmark = ISOLATED_ONLY


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/municipal/drivers", None),
    ("PATCH", "/municipal/sites/{id}", {"name": "Punto corregido"}),
])
@pytest.mark.parametrize("role,expected", [(None, 401), ("citizen", 403), ("driver", 403), ("manager", 200)])
def test_resource_permissions_with_verified_jwt(auth, method, path, body, role, expected):
    client, _, ids, _, headers = auth
    response = client.request(method, path.format(id=ids["departure"]), json=body,
                              headers=headers(role) if role else {})
    assert response.status_code == expected


def test_driver_directory_only_publishes_authorized_ids_and_paginates(pg_case):
    client, _, ids, _ = pg_case
    drivers = []
    while True:
        page = client.get("/municipal/drivers", params={"limit": 200, "offset": len(drivers)}).json()
        drivers.extend(page)
        if len(page) < 200:
            break
    assert {str(ids["driver"]), str(ids["driver2"])} <= {d["id"] for d in drivers}
    assert all(set(d) == {"id", "role"} and d["role"] == "chofer" for d in drivers)
    first = client.get("/municipal/drivers?limit=1&offset=0").json()
    second = client.get("/municipal/drivers?limit=1&offset=1").json()
    assert first != second
    assert client.get("/municipal/drivers?limit=201").status_code == 422


@pytest.mark.parametrize("body", [{}, {"name": " "}, {"name": None}, {"active": "false"},
    {"latitude": -12}, {"latitude": 91, "longitude": -77}, {"site_type": "cualquiera"},
    {"role": "encargado_municipal"}])
def test_invalid_site_edits_are_422(pg_case, body):
    client, _, ids, _ = pg_case
    assert client.patch(f"/municipal/sites/{ids['departure']}", json=body).status_code == 422


def test_site_edit_persists_and_missing_is_404(pg_case):
    client, engine, ids, _ = pg_case
    changes = {"name": "  Punto nuevo  ", "latitude": -12.03, "longitude": -77.04, "active": False}
    response = client.patch(f"/municipal/sites/{ids['departure']}", json=changes)
    assert response.status_code == 200
    with Session(engine) as db:
        site = db.get(ServiceSite, ids["departure"])
        assert (site.name, site.latitude, site.longitude, site.active) == ("Punto nuevo", -12.03, -77.04, False)
    assert client.patch(f"/municipal/sites/{uuid.uuid4()}", json={"active": False}).status_code == 404


@pytest.mark.parametrize("body", [{"active": False}, {"site_type": "descarga"}, {"latitude": -13, "longitude": -77}])
def test_reserved_site_cannot_change_use_location_or_availability(pg_case, body):
    client, _, ids, _ = pg_case
    assert client.post("/municipal/shifts", json=shift_payload(ids)).status_code == 201
    path = f"/municipal/sites/{ids['departure']}"
    assert client.patch(path, json=body).status_code == 409
    assert client.patch(path, json={"name": "Nombre corregido"}).status_code == 200


def test_reservation_waits_for_resource_change_and_revalidates(pg_case):
    client, engine, ids, _ = pg_case
    reached = threading.Event()
    def before(conn, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT vehicles.") and "FOR SHARE" in statement:
            reached.set()
    event.listen(engine, "before_cursor_execute", before)
    try:
        with Session(engine) as db, ThreadPoolExecutor(1) as pool:
            unit = db.scalar(select(Vehicle).where(Vehicle.id == ids["vehicle"]).with_for_update())
            pending = pool.submit(client.post, "/municipal/shifts", json=shift_payload(ids))
            assert reached.wait(5)
            assert not pending.done()
            unit.available = False
            db.commit()
            assert pending.result(10).status_code == 422
        with Session(engine) as db:
            assert db.scalar(select(Shift.id).where(Shift.vehicle_id == ids["vehicle"])) is None
    finally:
        event.remove(engine, "before_cursor_execute", before)


def test_site_edit_waits_for_simultaneous_reservation(pg_case):
    client, engine, ids, _ = pg_case
    inserting, editing, release = threading.Event(), threading.Event(), threading.Event()
    def before(conn, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO shifts"):
            inserting.set()
            assert release.wait(8)
        if statement.startswith("SELECT service_sites.") and "FOR UPDATE" in statement:
            editing.set()
    event.listen(engine, "before_cursor_execute", before)
    try:
        with ThreadPoolExecutor(2) as pool:
            reservation = pool.submit(client.post, "/municipal/shifts", json=shift_payload(ids))
            assert inserting.wait(5)
            correction = pool.submit(client.patch, f"/municipal/sites/{ids['departure']}", json={"active": False})
            assert editing.wait(5)
            assert not correction.done()
            release.set()
            assert reservation.result(10).status_code == 201
            assert correction.result(10).status_code == 409
    finally:
        release.set()
        event.remove(engine, "before_cursor_execute", before)
