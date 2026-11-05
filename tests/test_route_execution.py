"""Real isolated PostgreSQL, fictitious authorization receipts, no optimizer.

Receipts are inserted ONLY by this fixture in the owned disposable database to
exercise the future execution boundary. No public approval path issues them.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import copy
import uuid

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import Event, Report, RoutePlan, RouteStop, Shift, StopIncident, Vehicle
from app.route_execution import NAMESPACE, stop_manifest
from app.route_proposals import digest
from app.security import Actor
from concurrency_support import ISOLATED_ONLY, pg_case, shift_payload
from test_events import auth, jwt_keys
from test_route_proposals import case, command, create

pytestmark = ISOLATED_ONLY
M = "/municipal/routes"
D = "/driver/routes"


def cmd(status="propuesta", revision=None, **extra):
    return {"operation_id": str(uuid.uuid4()), "expected_status": status,
            "expected_revision": revision, "notes": "Motivo ficticio de prueba", **extra}


@pytest.fixture
def proposal(case):
    client, engine, ids, events, state = case
    item = create(client, command(ids, events))
    return client, engine, ids, state, item


@pytest.fixture
def executable(proposal):
    client, engine, ids, state, item = proposal
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        plan = db.get(RoutePlan, uuid.UUID(item["id"]))
        shift = db.get(Shift, plan.shift_id)
        shift.starts_at, shift.ends_at = now - timedelta(minutes=10), now + timedelta(hours=1)
        plan.approved_by, plan.approved_at, plan.status = ids["manager"], now, "aprobada"
        snapshot = copy.deepcopy(plan.input_snapshot)
        snapshot["operational"]["shift"].update(starts_at=shift.starts_at.isoformat(), ends_at=shift.ends_at.isoformat())
        plan.input_snapshot = snapshot
        config = copy.deepcopy(plan.configuration)
        config["_d2"].update(result_origin="d3", input_binding="matched", provider_reference="isolated-receipt-fixture",
                             input_hash=digest(snapshot["operational"]))
        stops = list(db.scalars(select(RouteStop).where(RouteStop.route_plan_id == plan.id).order_by(RouteStop.stop_order)))
        config[NAMESPACE] = {"version": 1, "operations": [], "verified_approval": {
            "authority": "verified-provider-v1", "approval_id": str(uuid.uuid4()),
            "approved_by": str(ids["manager"]), "approved_at": now.isoformat(), "shift_id": str(shift.id),
            "driver_id": str(shift.driver_id), "vehicle_id": str(shift.vehicle_id),
            "input_hash": config["_d2"]["input_hash"], "result_hash": config["_d2"]["result_hash"],
            "stop_manifest_hash": stop_manifest(stops), "provider_reference": "isolated-receipt-fixture"}}
        plan.configuration = config
        db.commit()
    state["actor"] = Actor(ids["driver"], "chofer")
    return client, engine, ids, state, item


def get(client, item):
    r = client.get(D + "/" + item["id"])
    assert r.status_code == 200, r.text
    return r.json()


def action(client, item, name, stop=None, **extra):
    route = get(client, item)
    body = cmd(route["status"], route["revision"], action=name, **extra)
    path = D + "/" + item["id"] + ("/stops/" + stop + "/actions" if stop else "/actions")
    return client.post(path, json=body), body


M_PATHS = [("GET", M), ("GET", M + "/{id}"), ("GET", M + "/{id}/history"),
           ("GET", M + "/{id}/operations/{op}"), ("POST", M + "/{id}/decisions")]
D_PATHS = [("GET", D), ("GET", D + "/{id}"), ("GET", D + "/{id}/operations/{op}"),
           ("POST", D + "/{id}/actions"), ("POST", D + "/{id}/stops/{stop}/actions")]


@pytest.mark.parametrize("method,path", M_PATHS + D_PATHS)
@pytest.mark.parametrize("role", [None, "citizen", "wrong_role"])
def test_endpoint_permissions_use_signed_es256(auth, method, path, role):
    client, _, _, _, headers = auth
    if role == "wrong_role":
        role = "driver" if path.startswith(M) else "manager"
    h = {} if role is None else headers(role)
    body = cmd(decision="cancel") if path.startswith(M) else cmd("aprobada", action="start")
    response = client.request(method, path.format(id=uuid.uuid4(), op=uuid.uuid4(), stop=uuid.uuid4()), json=body, headers=h)
    assert response.status_code == (401 if role is None else 403)


def test_municipal_review_reject_history_persist_and_old_proposal_contract_is_unchanged(proposal):
    client, engine, ids, _, item = proposal
    route = client.get(M + "/" + item["id"]).json()
    assert route["can_approve"] is False and route["approval_verified"] is False
    assert route["vehicle_id"] == str(ids["vehicle"]) and route["driver_id"] == str(ids["driver"])
    body = cmd(decision="reject")
    response = client.post(M + "/" + item["id"] + "/decisions", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["route"]["status"] == "cancelada"
    engine.dispose()
    assert client.get(M + "/" + item["id"] + "/history").json()[0]["actor_id"] == str(ids["manager"])
    assert client.get(M + "/" + item["id"] + "/operations/" + body["operation_id"]).status_code == 200
    assert client.get("/municipal/route-proposals/" + item["id"]).status_code == 404
    with Session(engine) as db:
        assert all(e.state == "en_revision" for e in db.scalars(select(Event).where(Event.id.in_([uuid.UUID(s["event_id"]) for s in item["stops"]]))))
        assert db.get(Report, ids["report"]).status == "recibido"


@pytest.mark.parametrize("origin", ["test_fixture", "municipal_unverified", "d3", "legacy_unknown"])
def test_origin_flag_does_not_allow_operational_approval(proposal, origin):
    client, engine, _, _, item = proposal
    with Session(engine) as db:
        plan = db.get(RoutePlan, uuid.UUID(item["id"]))
        config = copy.deepcopy(plan.configuration)
        config["_d2"]["result_origin"] = origin
        config["parameters"][NAMESPACE] = {"verified_approval": True}
        plan.configuration = config
        db.commit()
    r = client.post(M + "/" + item["id"] + "/decisions", json=cmd(decision="approve"))
    assert r.status_code == 409
    assert client.get(M + "/" + item["id"] + "/history").json() == []
    assert client.get(M + "/" + item["id"]).json()["status"] == "propuesta"


@pytest.mark.parametrize("extra", [{"approved_by": str(uuid.uuid4())}, {"decision": "assign"}, {"expected_revision": "bad"},
                                  {"notes": "  "}, {"can_approve": True}])
def test_decision_contract_rejects_forgery_or_invalid_values(proposal, extra):
    client, _, _, _, item = proposal
    assert client.post(M + "/" + item["id"] + "/decisions", json=cmd(decision="cancel", **{k:v for k,v in extra.items() if k != "decision"}) if "decision" not in extra else cmd(**extra)).status_code == 422


def test_decision_requires_explicit_expected_revision(proposal):
    client, _, _, _, item = proposal
    body = cmd(decision="cancel"); body.pop("expected_revision")
    assert client.post(M + "/" + item["id"] + "/decisions", json=body).status_code == 422


def test_simultaneous_conflicting_municipal_decisions_are_serialized(proposal):
    client, _, _, _, item = proposal
    path = M + "/" + item["id"] + "/decisions"
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda name: client.post(path, json=cmd(decision=name)), ["reject", "cancel"]))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert len(client.get(M + "/" + item["id"] + "/history").json()) == 1


def test_same_operation_concurrently_replays_without_duplicate_audit(proposal):
    client, _, _, _, item = proposal
    body = cmd(decision="cancel"); path = M + "/" + item["id"] + "/decisions"
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda _: client.post(path, json=body), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert sorted(r.json()["replayed"] for r in responses) == [False, True]
    assert len(client.get(M + "/" + item["id"] + "/history").json()) == 1
    assert client.post(path, json={**body, "notes": "Otro motivo"}).status_code == 409


@pytest.mark.parametrize("phase", ["before_commit", "acknowledgement_lost"])
def test_commit_failures_recover_by_uuid_without_losing_audit_or_duplicate(proposal, monkeypatch, caplog, phase):
    client, engine, _, _, item = proposal
    body = cmd(decision="cancel"); path = M + "/" + item["id"] + "/decisions"
    original = Session.commit
    def fail(db):
        if phase == "acknowledgement_lost":
            original(db)
        raise OperationalError("private-query", {}, RuntimeError("private-dsn"))
    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail)
        response = client.post(path, json=body)
        assert response.status_code == 503
    operation = client.get(M + "/" + item["id"] + "/operations/" + body["operation_id"])
    assert operation.status_code == (200 if phase == "acknowledgement_lost" else 404)
    engine.dispose()
    assert client.post(path, json=body).status_code == 200
    assert len(client.get(M + "/" + item["id"] + "/history").json()) == 1
    assert "private-dsn" not in response.text + caplog.text


def test_proposal_and_legacy_unverified_approval_are_not_executable(proposal):
    client, engine, ids, state, item = proposal
    state["actor"] = Actor(ids["driver"], "chofer")
    assert item["id"] not in {p["id"] for p in client.get(D).json()}
    assert client.get(D + "/" + item["id"]).status_code == 409
    assert client.post(D + "/" + item["id"] + "/actions", json=cmd(action="start")).status_code == 409
    with Session(engine) as db:
        db.get(RoutePlan, uuid.UUID(item["id"])).status = "aprobada"
        db.commit()
    assert item["id"] not in {p["id"] for p in client.get(D).json()}
    assert client.get(D + "/" + item["id"]).status_code == 409


def test_only_assigned_driver_can_read_or_mutate(executable):
    client, _, ids, state, item = executable
    assert item["id"] in {p["id"] for p in client.get(D).json()}
    route = get(client, item)
    assert route["approval_verified"] is True
    state["actor"] = Actor(ids["driver2"], "chofer")
    assert item["id"] not in {p["id"] for p in client.get(D).json()}
    assert client.get(D + "/" + item["id"]).status_code == 404
    assert client.post(D + "/" + item["id"] + "/actions", json=cmd("aprobada", action="start")).status_code == 404
    assert client.post(D + "/" + item["id"] + "/stops/" + route["stops"][0]["id"] + "/actions", json=cmd("aprobada", action="attend")).status_code == 404


@pytest.mark.parametrize("change", ["receipt_missing", "input_changed", "stop_changed", "driver_changed", "vehicle_changed"])
def test_receipt_is_bound_to_assignment_input_and_stops(executable, change):
    client, engine, ids, _, item = executable
    with Session(engine) as db:
        plan = db.get(RoutePlan, uuid.UUID(item["id"]))
        config = copy.deepcopy(plan.configuration)
        if change == "receipt_missing":
            config[NAMESPACE]["verified_approval"] = None
        if change == "input_changed":
            snapshot = copy.deepcopy(plan.input_snapshot)
            snapshot["operational"]["events"][0]["latitude"] = -13
            plan.input_snapshot = snapshot
        if change == "stop_changed":
            stop = db.scalar(select(RouteStop).where(RouteStop.route_plan_id == plan.id).limit(1))
            stop.estimated_service_minutes = 17
        if change == "driver_changed":
            db.get(Shift, plan.shift_id).driver_id = ids["driver2"]
        if change == "vehicle_changed":
            db.get(Shift, plan.shift_id).vehicle_id = ids["vehicle2"]
        plan.configuration = config
        db.commit()
    assert item["id"] not in {p["id"] for p in client.get(D).json()}
    assert client.get(D + "/" + item["id"]).status_code in {404, 409}


def test_driver_flow_records_all_stop_outcomes_and_preserves_citizen_reports(executable):
    client, engine, ids, _, item = executable
    route = get(client, item)
    assert route["stops"][0]["latitude"] == item["input_snapshot"]["operational"]["events"][1]["latitude"]
    response, _ = action(client, item, "start")
    assert response.status_code == 200
    assert action(client, item, "finish")[0].status_code == 409
    assert action(client, item, "attend", route["stops"][1]["id"])[0].status_code == 409
    response, _ = action(client, item, "attend", route["stops"][0]["id"])
    assert response.status_code == 200
    response, body = action(client, item, "incident", route["stops"][1]["id"], incident_type="acceso_bloqueado")
    assert response.status_code == 200, response.text
    replay = client.post(D + "/" + item["id"] + "/stops/" + route["stops"][1]["id"] + "/actions", json=body)
    assert replay.status_code == 200 and replay.json()["replayed"]
    response, _ = action(client, item, "finish")
    assert response.status_code == 200 and response.json()["route"]["status"] == "finalizada"
    engine.dispose()
    after = get(client, item)
    assert [s["status"] for s in after["stops"]] == ["atendida", "incidencia"]
    assert all(s["recorded_by"] == str(ids["driver"]) and s["visited_at"] for s in after["stops"])
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(StopIncident).where(StopIncident.stop_id == uuid.UUID(route["stops"][1]["id"]))) == 1
        assert db.get(Report, ids["report"]).status == "recibido"


def test_not_attended_has_durable_reason_and_requires_notes(executable):
    client, _, _, _, item = executable
    assert action(client, item, "start")[0].status_code == 200
    stop = get(client, item)["stops"][0]["id"]
    assert action(client, item, "not_attended", stop, notes=None)[0].status_code == 422
    response, _ = action(client, item, "not_attended", stop, notes="Zona inaccesible")
    assert response.status_code == 200
    record = response.json()["route"]["stops"][0]
    assert record["status"] == "no_atendida" and record["incidents"][0]["description"] == "Zona inaccesible"


def test_concurrent_stop_actions_cannot_overwrite_each_other(executable):
    client, engine, _, _, item = executable
    assert action(client, item, "start")[0].status_code == 200
    route = get(client, item); stop = route["stops"][0]
    bodies = [cmd(route["status"], route["revision"], action="attend"),
              cmd(route["status"], route["revision"], action="incident", incident_type="inaccesible")]
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda body: client.post(D + "/" + item["id"] + "/stops/" + stop["id"] + "/actions", json=body), bodies))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert len(get(client, item)["history"]) == 2


def test_incident_and_route_audit_rollback_together_on_database_failure(executable):
    client, engine, _, _, item = executable
    assert action(client, item, "start")[0].status_code == 200
    stop = get(client, item)["stops"][0]
    def fail(conn, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO stop_incidents"):
            conn.exec_driver_sql("SELECT 1/0")
    event.listen(engine, "before_cursor_execute", fail)
    try:
        assert action(client, item, "incident", stop["id"], incident_type="acceso")[0].status_code == 503
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    route = get(client, item)
    assert route["stops"][0]["status"] == "pendiente" and route["stops"][0]["incidents"] == []
    assert len(route["history"]) == 1


@pytest.mark.parametrize("change", ["vehicle_unavailable", "out_of_window", "cancelled_shift"])
def test_driver_cannot_start_with_unavailable_assignment(executable, change):
    client, engine, ids, _, item = executable
    with Session(engine) as db:
        if change == "vehicle_unavailable":
            db.get(Vehicle, ids["vehicle"]).available = False
        else:
            shift = db.get(Shift, ids["shift"])
            if change == "out_of_window":
                shift.ends_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            else:
                shift.status = "cancelado"
        db.commit()
    assert action(client, item, "start")[0].status_code == 409


@pytest.mark.parametrize("busy", ["vehicle", "driver"])
def test_late_previous_route_blocks_start_even_with_nonoverlapping_bookings(executable, busy):
    client, engine, ids, _, item = executable
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        previous_shift = Shift(vehicle_id=ids["vehicle"] if busy == "vehicle" else ids["vehicle2"],
            driver_id=ids["driver2"] if busy == "vehicle" else ids["driver"],
            departure_site_id=ids["departure"], disposal_site_id=ids["disposal"],
            starts_at=now-timedelta(hours=3), ends_at=now-timedelta(hours=2), created_by=ids["manager"])
        db.add(previous_shift); db.flush()
        db.add(RoutePlan(shift_id=previous_shift.id, status="en_ejecucion", created_by=ids["manager"],
            algorithm_version="fictitious-previous-late-route", input_snapshot={}, configuration={}))
        db.commit()
    response, _ = action(client, item, "start")
    assert response.status_code == 409
    assert "otro recorrido" in response.json()["detail"]
    assert get(client, item)["status"] == "aprobada"


def test_public_configuration_cannot_issue_private_approval_receipt(executable):
    client, engine, ids, state, item = executable
    state["actor"] = Actor(ids["manager"], "encargado_municipal")
    with Session(engine) as db:
        private = copy.deepcopy(db.get(RoutePlan, uuid.UUID(item["id"])).configuration[NAMESPACE])
    response = client.post("/municipal/route-proposals", json={
        "proposal_id": str(uuid.uuid4()), "shift_id": str(ids["shift"]),
        "event_ids": [e["id"] for e in item["input_snapshot"]["operational"]["events"]],
        "configuration": {NAMESPACE: private, "_d2": {"result_origin": "d3"}}})
    assert response.status_code == 201, response.text
    value = response.json()
    assert NAMESPACE not in value["configuration"]
    assert NAMESPACE in value["configuration"]["parameters"]
    assert client.get(M + "/" + value["id"]).json()["approval_verified"] is False
    assert client.post(M + "/" + value["id"] + "/decisions", json=cmd(decision="approve")).status_code == 409
