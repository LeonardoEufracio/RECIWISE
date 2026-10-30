import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.db_errors import diagnostics
from app.db import get_db
from app.main import app
from app.models import Shift
from concurrency_support import ISOLATED_ONLY, pg_case, shift_payload

pytestmark = ISOLATED_ONLY


@pytest.mark.parametrize("same", ["vehicle", "driver", "both"])
def test_simultaneous_reservations_are_excluded_by_postgres(pg_case, same):
    client, engine, ids, _ = pg_case
    a = shift_payload(ids)
    b = shift_payload(ids, driver_id=str(ids["driver2"]) if same == "vehicle" else str(ids["driver"]),
                      vehicle_id=str(ids["vehicle2"]) if same == "driver" else str(ids["vehicle"]))
    barrier = threading.Barrier(2, timeout=10)

    def both_read_before_insert(conn, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT shifts.id") and "shifts.starts_at <" in statement:
            barrier.wait()

    event.listen(engine, "after_cursor_execute", both_read_before_insert)
    try:
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(client.post, "/municipal/shifts", json=payload) for payload in (a, b)]
            responses = [future.result(timeout=20) for future in futures]
    finally:
        event.remove(engine, "after_cursor_execute", both_read_before_insert)
    assert sorted(r.status_code for r in responses) == [201, 409]
    conflict = next(r for r in responses if r.status_code == 409)
    assert conflict.json()["detail"] == "Vehículo o chofer ya reservado en ese horario"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Shift).where(Shift.vehicle_id.in_([ids['vehicle'], ids['vehicle2']]))) == 1


@pytest.mark.parametrize("mode", ["adjacent", "different-resources"])
def test_compatible_reservations_remain_allowed(pg_case, mode):
    client, _, ids, _ = pg_case
    a = shift_payload(ids)
    b = shift_payload(ids, starts_at="2030-01-01T09:00:00Z", ends_at="2030-01-01T10:00:00Z") if mode == "adjacent" else shift_payload(
        ids, vehicle_id=str(ids["vehicle2"]), driver_id=str(ids["driver2"]))
    assert client.post("/municipal/shifts", json=a).status_code == 201
    assert client.post("/municipal/shifts", json=b).status_code == 201


@pytest.mark.parametrize("status", ["cancelado", "finalizado"])
def test_inactive_shift_can_overlap_but_cannot_reactivate(pg_case, status):
    client, engine, ids, _ = pg_case
    a = client.post("/municipal/shifts", json=shift_payload(ids))
    assert a.status_code == 201
    with Session(engine) as db:
        shift = db.get(Shift, uuid.UUID(a.json()["id"]))
        shift.status = status
        db.commit()
        shift_id = shift.id
    assert client.post("/municipal/shifts", json=shift_payload(ids)).status_code == 201
    with Session(engine) as db:
        db.get(Shift, shift_id).status = "programado"
        with pytest.raises(IntegrityError) as exc:
            db.commit()
        assert diagnostics(exc.value)[0] == "23P01"
        db.rollback()


@pytest.mark.parametrize("state", ["40001", "40P01"])
def test_known_postgres_abort_retries_without_duplicate(pg_case, state):
    client, engine, ids, _ = pg_case
    attempts = []
    def abort_once(conn, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO shifts"):
            attempts.append(True)
            if len(attempts) == 1:
                conn.exec_driver_sql("DO $$ BEGIN RAISE SQLSTATE '" + state + "'; END $$")
    event.listen(engine, "after_cursor_execute", abort_once)
    try:
        assert client.post("/municipal/shifts", json=shift_payload(ids)).status_code == 201
    finally:
        event.remove(engine, "after_cursor_execute", abort_once)
    assert len(attempts) == 2
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Shift).where(Shift.vehicle_id == ids["vehicle"])) == 1


def test_retry_exhaustion_returns_503_without_reservation(pg_case):
    client, engine, ids, _ = pg_case
    attempts = []
    def abort_always(conn, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO shifts"):
            attempts.append(True)
            conn.exec_driver_sql("DO $$ BEGIN RAISE SQLSTATE '40001'; END $$")
    event.listen(engine, "after_cursor_execute", abort_always)
    try:
        assert client.post("/municipal/shifts", json=shift_payload(ids)).status_code == 503
    finally:
        event.remove(engine, "after_cursor_execute", abort_always)
    assert len(attempts) == 3
    with Session(engine) as db:
        assert db.scalar(select(Shift).where(Shift.vehicle_id == ids["vehicle"])) is None


def test_unknown_shift_commit_is_not_retried(pg_case):
    client, engine, ids, _ = pg_case
    commits = []
    class LostSession(Session):
        def commit(self):
            has_shift = any(isinstance(item, Shift) for item in self.identity_map.values())
            super().commit()
            if has_shift:
                commits.append(True)
                raise OperationalError("commit", None, ConnectionError("fictitious lost acknowledgement"), connection_invalidated=True)
    def database():
        with LostSession(engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    assert client.post("/municipal/shifts", json=shift_payload(ids)).status_code == 503
    assert commits == [True]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Shift).where(Shift.vehicle_id == ids["vehicle"])) == 1
