"""Events: real, marked localhost PostgreSQL. No remote Auth/Storage or SQLite fallback."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from types import SimpleNamespace
import threading
import urllib.request
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event as sql_event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import security
from app.main import app
from app.models import Event, EventReport, GroupingDecision, Report
from app.schemas import EventOut
from concurrency_support import ISOLATED_ONLY, pg_case
from postgres_support import evidence
from test_security import jwt_keys

pytestmark = ISOLATED_ONLY
ROOT = "/municipal/events"


def payload(ids=None, **extra):
    return {"latitude": -12.0528, "longitude": -75.226, "intervention_type": "Recolección manual",
            "report_ids": [str(ids["report"])] if ids else [], **extra}


def create(client, value):
    response = client.post(ROOT, json=value)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def auth(pg_case, jwt_keys, monkeypatch):
    client, engine, ids, state = pg_case
    seed = create(client, payload())
    keys, _, jwks = jwt_keys
    app.dependency_overrides.pop(security.get_current_actor)
    security.jwks_client.cache_clear()
    url = "https://reciwise-events.test"
    monkeypatch.setattr(security, "get_settings", lambda: SimpleNamespace(supabase_url=url))

    def local_jwks(request, *args, **kwargs):
        target = request.full_url if isinstance(request, urllib.request.Request) else request
        assert target == url + "/auth/v1/.well-known/jwks.json"
        return BytesIO(json.dumps(jwks).encode())
    monkeypatch.setattr(urllib.request, "urlopen", local_jwks)
    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: SimpleNamespace(open=local_jwks))

    def headers(name="manager", algorithm="ES256"):
        token = jwt.encode({"sub": str(ids[name]), "iss": url + "/auth/v1", "aud": "authenticated",
                            "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                           keys[algorithm], algorithm=algorithm, headers={"kid": "test-" + algorithm})
        return {"Authorization": "Bearer " + token}
    try:
        yield client, engine, ids, seed, headers
    finally:
        security.jwks_client.cache_clear()


OPERATIONS = [("GET", ROOT), ("POST", ROOT), ("GET", ROOT + "/{id}"), ("GET", ROOT + "/{id}/reports")]


@pytest.mark.parametrize("method,path", OPERATIONS)
@pytest.mark.parametrize("header", [None, "Bearer malformed"])
def test_missing_or_malformed_jwt_is_401(auth, method, path, header):
    client, _, _, seed, _ = auth
    response = client.request(method, path.format(id=seed["id"]), json=payload() if method == "POST" else None,
                              headers={} if header is None else {"Authorization": header})
    assert response.status_code == 401


@pytest.mark.parametrize("method,path", OPERATIONS)
@pytest.mark.parametrize("name", ["citizen", "driver"])
def test_nonmunicipal_profiles_are_403(auth, method, path, name):
    client, _, _, seed, headers = auth
    response = client.request(method, path.format(id=seed["id"]), json=payload() if method == "POST" else None,
                              headers=headers(name))
    assert response.status_code == 403


def test_signed_identity_without_profile_is_403(auth):
    client, _, ids, _, headers = auth
    ids["without_profile"] = uuid.uuid4()
    assert client.get(ROOT, headers=headers("without_profile")).status_code == 403


def test_profile_database_failure_is_controlled_without_leaking_details(auth, caplog):
    client, engine, _, _, headers = auth
    def fail(connection, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT profiles."):
            raise OperationalError("private-profile-query", {}, RuntimeError("private-dsn"))
    sql_event.listen(engine, "before_cursor_execute", fail)
    try:
        response = client.get(ROOT, headers=headers())
        assert response.status_code == 503
    finally:
        sql_event.remove(engine, "before_cursor_execute", fail)
    assert "private-dsn" not in response.text + caplog.text
    assert "private-profile-query" not in response.text + caplog.text


@pytest.mark.parametrize("method,path", OPERATIONS)
@pytest.mark.parametrize("algorithm", ["ES256", "RS256"])
def test_municipal_signed_jwt_is_authorized(auth, method, path, algorithm):
    client, _, _, seed, headers = auth
    response = client.request(method, path.format(id=seed["id"]), json=payload() if method == "POST" else None,
                              headers=headers(algorithm=algorithm))
    assert response.status_code == (201 if method == "POST" else 200), response.text


def test_create_detail_relations_and_report_state_persist(pg_case):
    client, engine, ids, _ = pg_case
    result = create(client, payload(ids, intervention_type="  Recolección manual  "))
    assert result["latitude"] == -12.0528 and result["longitude"] == -75.226
    assert result["state"] == "en_revision" and result["priority"] is None
    assert result["restrictions"] is None and result["closed_at"] is None
    assert result["intervention_type"] == "Recolección manual"
    assert result["report_ids"] == [str(ids["report"])] and result["report_count"] == 1
    with Session(engine) as db:
        stored = db.get(Event, uuid.UUID(result["id"]))
        assert stored.latitude == result["latitude"] and stored.longitude == result["longitude"]
        link = db.get(EventReport, ids["report"])
        assert link.event_id == stored.id and link.linked_by == ids["manager"]
        assert link.linkage_method == "manual" and link.config_version is None
        decision = db.scalar(select(GroupingDecision).where(GroupingDecision.resulting_event_id == stored.id))
        assert decision.decided_by == ids["manager"] and decision.decision == "agrupar"
        assert db.get(Report, ids["report"]).status == "recibido"
    # New session/connection after pool disposal still retrieves committed data.
    engine.dispose()
    assert client.get(ROOT + "/" + result["id"]).json() == result
    reports = client.get(ROOT + "/" + result["id"] + "/reports").json()
    assert len(reports) == 1 and reports[0]["id"] == str(ids["report"])
    assert reports[0]["status"] == "recibido" and reports[0]["description"]
    evidence("events-persistence.json", {"event": result, "associated_report_id": str(ids["report"]),
                                       "report_status": reports[0]["status"], "fresh_connection": True})


def test_event_without_reports_is_valid_and_empty(pg_case):
    client, _, _, _ = pg_case
    result = create(client, {"latitude": 0, "longitude": 0})
    assert result["report_count"] == 0 and result["report_ids"] == []
    assert result["intervention_type"] is None
    assert client.get(ROOT + "/" + result["id"] + "/reports").json() == []


@pytest.mark.parametrize("overrides", [
    {"latitude": 90.1}, {"latitude": -90.1}, {"longitude": 180.1}, {"longitude": -180.1},
    {"latitude": None}, {"longitude": "invalid"}, {"intervention_type": ""},
    {"intervention_type": "   "}, {"intervention_type": "a" * 121},
    {"report_ids": ["invalid-uuid"]}, {"report_ids": None}, {"report_ids": [str(uuid.uuid4())] * 2},
    {"report_ids": [str(uuid.uuid4()) for _ in range(101)]},
    {"state": "atendido"}, {"state": "desconocido"}, {"closed_at": "2026-01-01T00:00:00Z"},
    {"priority_score": 99}, {"priority": {"score": 99}}, {"created_by": str(uuid.uuid4())},
    {"unknown": True},
])
def test_invalid_create_is_422_without_writes(pg_case, overrides):
    client, engine, _, _ = pg_case
    with Session(engine) as db:
        before = db.scalar(select(func.count()).select_from(Event))
    response = client.post(ROOT, json=payload(**overrides))
    assert response.status_code == 422, response.text
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Event)) == before


@pytest.mark.parametrize("field,value", [("latitude", float("nan")), ("latitude", float("inf")),
                                        ("longitude", -float("inf")), ("unknown", float("nan"))])
def test_nonfinite_wire_values_return_422_not_500(pg_case, field, value):
    client, _, _, _ = pg_case
    # Send raw bytes because httpx deliberately refuses to encode nonstandard numbers.
    response = client.post(ROOT, content=json.dumps(payload(**{field: value})),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 422


@pytest.mark.parametrize("latitude,longitude", [(90, 180), (-90, -180), (0, 0)])
def test_coordinate_boundaries_are_accepted(pg_case, latitude, longitude):
    client, _, _, _ = pg_case
    result = create(client, payload(latitude=latitude, longitude=longitude))
    assert result["latitude"] == latitude and result["longitude"] == longitude


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "offset=-1", "state=invalid", "limit=oops"])
def test_invalid_list_query_is_422(pg_case, query):
    client, _, _, _ = pg_case
    assert client.get(ROOT + "?" + query).status_code == 422


@pytest.mark.parametrize("suffix", ["", "/reports"])
def test_missing_and_invalid_event_ids(pg_case, suffix):
    client, _, _, _ = pg_case
    assert client.get(ROOT + "/" + str(uuid.uuid4()) + suffix).status_code == 404
    assert client.get(ROOT + "/invalid" + suffix).status_code == 422


def test_missing_report_rejects_entire_creation(pg_case):
    client, engine, ids, _ = pg_case
    with Session(engine) as db:
        before = db.scalar(select(func.count()).select_from(Event))
    response = client.post(ROOT, json=payload(report_ids=[str(ids["report"]), str(uuid.uuid4())]))
    assert response.status_code == 404
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Event)) == before
        assert db.get(EventReport, ids["report"]) is None


def test_existing_association_is_409_without_reassignment(pg_case):
    client, engine, ids, _ = pg_case
    first = create(client, payload(ids))
    response = client.post(ROOT, json=payload(ids))
    assert response.status_code == 409
    with Session(engine) as db:
        assert str(db.get(EventReport, ids["report"]).event_id) == first["id"]
        assert db.scalar(select(func.count()).select_from(GroupingDecision).where(GroupingDecision.report_id == ids["report"])) == 1
        assert db.get(Report, ids["report"]).status == "recibido"


def test_stable_pagination_state_filter_and_frontend_shape(pg_case):
    client, engine, _, _ = pg_case
    created = [create(client, payload()) for _ in range(3)]
    with Session(engine) as db:
        last = db.get(Event, uuid.UUID(created[0]["id"]))
        last.state = "cerrado"; last.closed_at = datetime.now(timezone.utc)
        db.commit()
        expected = [str(i) for i in db.scalars(select(Event.id).where(Event.state == "en_revision")
                    .order_by(Event.created_at.desc(), Event.id.desc()).limit(4)).all()]
    first = client.get(ROOT + "?state=en_revision&limit=2").json()
    second = client.get(ROOT + "?state=en_revision&limit=2&offset=2").json()
    assert [r["id"] for r in first + second] == expected
    for item in first:
        assert EventOut.model_validate(item).state == "en_revision"
        assert {"id", "latitude", "longitude", "state", "intervention_type", "report_ids", "priority", "restrictions", "created_at", "closed_at"} <= item.keys()
    closed = client.get(ROOT + "?state=cerrado&limit=200").json()
    assert any(e["id"] == created[0]["id"] and e["closed_at"] for e in closed)
    assert client.get(ROOT + "?offset=1000000").json() == []


def test_associated_reports_are_paginated(pg_case):
    client, engine, ids, _ = pg_case
    extra = uuid.uuid4()
    with Session(engine) as db:
        db.add(Report(id=extra, citizen_id=ids["citizen"], description="Otra observación ficticia",
                      latitude=-12, longitude=-75, observed_at=datetime.now(timezone.utc)))
        db.commit()
    result = create(client, payload(report_ids=[str(extra), str(ids["report"])]))
    path = ROOT + "/" + result["id"] + "/reports"
    a = client.get(path + "?limit=1").json(); b = client.get(path + "?limit=1&offset=1").json()
    assert {a[0]["id"], b[0]["id"]} == {str(extra), str(ids["report"])}
    assert client.get(path + "?limit=1&offset=2").json() == []
    assert client.get(path + "?limit=201").status_code == 422


@pytest.mark.parametrize("factors", [{"stored": {"value": 2}}, [{"label": "fixture", "value": "dato almacenado"}]])
def test_existing_priority_is_returned_without_inventing_a_d3_schema(pg_case, factors):
    client, engine, _, _ = pg_case
    created = create(client, payload())
    with Session(engine) as db:
        item = db.get(Event, uuid.UUID(created["id"]))
        item.priority_score = 2.5; item.priority_factors = factors; item.priority_config_version = "fixture-existing-v1"
        db.commit()
    assert client.get(ROOT + "/" + created["id"]).json()["priority"] == {"score": 2.5, "factors": factors, "version": "fixture-existing-v1"}


def test_nonfinite_stored_priority_is_controlled_503(pg_case):
    client, engine, _, _ = pg_case
    created = create(client, payload())
    with Session(engine) as db:
        db.get(Event, uuid.UUID(created["id"])).priority_score = float("nan")
        db.commit()
    assert client.get(ROOT + "/" + created["id"]).status_code == 503
    # Restore only our fictitious row so subsequent list tests remain independent.
    with Session(engine) as db:
        db.get(Event, uuid.UUID(created["id"])).priority_score = None
        db.commit()


def test_postgres_failure_rolls_back_event_links_and_audit(pg_case, caplog):
    client, engine, ids, _ = pg_case
    with Session(engine) as db:
        before = db.scalar(select(func.count()).select_from(Event))
    def fail(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO grouping_decisions"):
            connection.exec_driver_sql("SELECT 1 / 0")  # Actual PostgreSQL transaction error.
    sql_event.listen(engine, "before_cursor_execute", fail)
    try:
        response = client.post(ROOT, json=payload(ids))
        assert response.status_code == 503
    finally:
        sql_event.remove(engine, "before_cursor_execute", fail)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Event)) == before
        assert db.get(EventReport, ids["report"]) is None
        assert db.scalar(select(func.count()).select_from(GroupingDecision).where(GroupingDecision.report_id == ids["report"])) == 0
    assert "SELECT 1 / 0" not in response.text + caplog.text


def test_read_failure_is_503_without_connection_details(pg_case, caplog):
    client, engine, _, _ = pg_case
    def fail(connection, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT events."):
            raise OperationalError("private-sql", {}, RuntimeError("private-connection-detail"))
    sql_event.listen(engine, "before_cursor_execute", fail)
    try:
        response = client.get(ROOT)
        assert response.status_code == 503
    finally:
        sql_event.remove(engine, "before_cursor_execute", fail)
    assert "private-sql" not in response.text + caplog.text
    assert "private-connection-detail" not in response.text + caplog.text


def test_lost_commit_confirmation_is_503_without_retry_or_deletion(pg_case, monkeypatch, caplog):
    client, engine, ids, _ = pg_case
    original = Session.commit
    commits = []
    def commit(session):
        original(session)
        commits.append(True)
        raise OperationalError("secret-sql", {}, RuntimeError("private-connection-detail"))
    monkeypatch.setattr(Session, "commit", commit)
    response = client.post(ROOT, json=payload(ids))
    assert response.status_code == 503 and commits == [True]
    with Session(engine) as db:
        link = db.get(EventReport, ids["report"])
        assert link is not None
        assert db.get(Report, ids["report"]).status == "recibido"
        event_id = str(link.event_id)
    assert client.get(ROOT + "/" + event_id).status_code == 200
    assert "secret-sql" not in response.text + caplog.text
    assert "private-connection-detail" not in response.text + caplog.text


def test_competing_creations_link_a_report_only_once_in_postgresql(pg_case):
    client, engine, ids, _ = pg_case
    barrier = threading.Barrier(2)
    def synchronize(connection, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT reports.id") and "FOR UPDATE" in statement:
            barrier.wait(timeout=10)
    sql_event.listen(engine, "before_cursor_execute", synchronize)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: client.post(ROOT, json=payload(ids)), range(2)))
    finally:
        sql_event.remove(engine, "before_cursor_execute", synchronize)
    assert sorted(r.status_code for r in responses) == [201, 409]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(EventReport).where(EventReport.report_id == ids["report"])) == 1
        assert db.scalar(select(func.count()).select_from(GroupingDecision).where(GroupingDecision.report_id == ids["report"])) == 1
        assert db.get(Report, ids["report"]).status == "recibido"
    evidence("events-concurrency.json", {"http_statuses": sorted(r.status_code for r in responses),
                                       "links": 1, "audit_decisions": 1, "postgresql": True})
