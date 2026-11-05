"""Grouping commands on real marked localhost PostgreSQL; no SQLite substitute."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import threading
import uuid

import pytest
from sqlalchemy import event as sql_event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.main import app
from app.models import Event, EventReport, GroupingDecision, Profile, Report
from concurrency_support import ISOLATED_ONLY, pg_case
from postgres_support import evidence
from test_events import auth
from test_security import jwt_keys
from test_grouping_contracts import suggestion

pytestmark = ISOLATED_ONLY
ROOT = "/municipal/groupings"

@pytest.fixture
def case(pg_case):
    client, engine, ids, state = pg_case
    events = [client.post("/municipal/events", json={"latitude": -12.05-i*.001, "longitude": -75.226}).json()["id"] for i in range(3)]
    return client, engine, ids, events, state

def current(client, report_id):
    response = client.get(ROOT + "/reports/" + str(report_id))
    assert response.status_code == 200, response.text
    return response.json()

def body(client, report_id, event_id, kind="agrupar", **extra):
    snapshot = current(client, report_id)
    return {"operation_id": str(uuid.uuid4()), "report_id": str(report_id), "decision": kind,
        "candidate_event_id": event_id, "expected_event_id":snapshot["event_id"],
        "expected_decision_id":snapshot["last_decision_id"], **extra}

def apply(client, value, status=200):
    response = client.post(ROOT + "/decisions", json=value)
    assert response.status_code == status, response.text
    return response.json()

def count(db, report_id):
    return db.scalar(select(func.count()).select_from(GroupingDecision).where(GroupingDecision.report_id == report_id))

def test_complete_municipal_flow_persists_relations_and_append_only_history(case):
    client, engine, ids, events, _ = case
    before = current(client, ids["report"])["report"]
    snapshots = []
    for kind, target in [("revisar",events[0]),("mantener_separado",events[0]),
                         ("agrupar",events[0]),("agrupar",events[1]),("separar",None)]:
        result = apply(client, body(client, ids["report"], target, kind, notes="Decisión municipal ficticia"))
        snapshots.append(result)
        assert result["relation"]["report"] == before
        assert result["decision"]["decided_by"] == str(ids["manager"])
    assert [r["decision"]["operation"] for r in snapshots] == ["review","keep_separate","confirm","reassign","separate"]
    assert snapshots[0]["relation"]["pending_review"]
    assert not snapshots[1]["relation"]["pending_review"]
    assert snapshots[3]["decision"]["previous_event_id"] == events[0]
    assert snapshots[3]["decision"]["resulting_event_id"] == events[1]
    assert snapshots[4]["relation"]["event_id"] is None
    engine.dispose()
    assert current(client, ids["report"])["last_decision_id"] == snapshots[-1]["decision"]["id"]
    history = client.get(ROOT + "/decisions", params={"report_id":str(ids["report"])}).json()
    assert [r["id"] for r in history] == [r["decision"]["id"] for r in reversed(snapshots)]
    for result in snapshots:
        assert client.get(ROOT + "/decisions/" + result["decision"]["id"]).json() == result["decision"]
    with Session(engine) as db:
        assert db.get(EventReport, ids["report"]) is None and count(db, ids["report"]) == 5
        assert db.get(Report, ids["report"]).status == "recibido"
    evidence("groupings-flow.json", {"operations":[r["decision"]["operation"] for r in snapshots],
        "report_id":str(ids["report"]), "last_decision_id":history[0]["id"], "report_preserved":True})

def test_correction_is_visible_in_events_and_original_report_endpoints(case):
    client, _, ids, events, state = case
    apply(client, body(client, ids["report"], events[0]))
    original = client.get("/reports/" + str(ids["report"])).json()
    result = apply(client, body(client, ids["report"], events[1]))
    assert client.get("/municipal/events/" + events[0]).json()["report_count"] == 0
    assert client.get("/municipal/events/" + events[1] + "/reports").json()[0] == original
    assert client.get("/reports/" + str(ids["report"])).json() == original
    assert result["relation"]["event"]["id"] == events[1]
    state["actor"] = type(state["actor"])(ids["citizen"],"ciudadano")
    assert any(r["id"] == str(ids["report"]) and r["status"] == "recibido" for r in client.get("/reports/mine").json())

def test_identical_operation_replays_once_and_does_not_reapply_later(case):
    client, engine, ids, events, _ = case
    value = body(client, ids["report"], events[0])
    first = apply(client, value)
    replay = apply(client, value)
    assert replay["replayed"] and replay["decision"] == first["decision"]
    apply(client, body(client, ids["report"], None, "separar"))
    replay = apply(client, value)
    assert replay["replayed"] and replay["relation"]["event_id"] is None
    with Session(engine) as db: assert count(db, ids["report"]) == 2
    changed = {**value,"notes":"Otro comando"}
    apply(client, changed, 409)

def test_duplicate_new_operation_and_stale_revision_are_409(case):
    client, _, ids, events, _ = case
    old = body(client, ids["report"], events[0])
    apply(client, old)
    apply(client, {**old,"operation_id":str(uuid.uuid4())},409)
    apply(client, body(client, ids["report"], events[0]),409)
    # ABA: it is unlinked again, but the old null revision must never be accepted.
    apply(client, body(client, ids["report"], None, "separar"))
    apply(client, {**old,"operation_id":str(uuid.uuid4())},409)

@pytest.mark.parametrize("state", ["programado","atendido","cerrado","descartado"])
@pytest.mark.parametrize("source", [False,True])
def test_noneditable_source_or_target_is_409(case, state, source):
    client, engine, ids, events, _ = case
    if source: apply(client, body(client, ids["report"], events[0]))
    with Session(engine) as db:
        item = db.get(Event, uuid.UUID(events[0])); item.state = state
        if state == "cerrado": item.closed_at = datetime.now(timezone.utc)
        db.commit()
    apply(client, body(client, ids["report"], events[1] if source else events[0]),409)
    if source: apply(client, body(client, ids["report"], None,"separar"),409)

def test_keep_separate_never_contradicts_current_relation_and_review_does_not_edit_it(case):
    client, _, ids, events, _ = case
    apply(client, body(client, ids["report"], events[0]))
    apply(client, body(client, ids["report"], events[0],"mantener_separado"),409)
    result = apply(client, body(client, ids["report"], events[1],"revisar"))
    assert result["relation"]["event_id"] == events[0] and result["relation"]["pending_review"]

def test_manual_candidates_are_real_eligible_events_without_simulated_metrics(case):
    client, engine, ids, events, _ = case
    apply(client, body(client, ids["report"], events[0]))
    with Session(engine) as db:
        item = db.get(Event,uuid.UUID(events[1])); item.state = "cerrado"; item.closed_at = datetime.now(timezone.utc); db.commit()
        inconsistent = Event(latitude=-12, longitude=-75, state="abierto", closed_at=datetime.now(timezone.utc))
        db.add(inconsistent); db.commit()
        inconsistent_id = str(inconsistent.id)
    response = client.get(ROOT + "/candidates",params={"report_id":str(ids["report"]),"limit":200}).json()
    assert response["source"] == "manual" and response["d3_available"] is False
    values = {item["id"] for item in response["candidates"]}
    assert events[2] in values and events[0] not in values and events[1] not in values
    assert inconsistent_id not in values
    assert all(item["state"] in ["en_revision","abierto"] for item in response["candidates"])

def test_pending_review_list_and_history_filters_are_paginated(case):
    client, _, ids, events, _ = case
    first = apply(client, body(client, ids["report"], events[0],"revisar"))
    listed = client.get(ROOT,params={"pending_review":"true","limit":200}).json()
    assert any(item["report"]["id"] == str(ids["report"]) for item in listed)
    apply(client, body(client, ids["report"], events[0]))
    apply(client, body(client, ids["report"], events[1]))
    records = client.get(ROOT+"/decisions",params={"report_id":str(ids["report"]),"limit":1,"offset":1}).json()
    assert len(records)==1 and records[0]["operation"]=="confirm"
    by_event = client.get(ROOT+"/decisions",params={"report_id":str(ids["report"]),"event_id":events[0]}).json()
    assert len(by_event)==3  # Includes correction whose previous event was event[0].
    filtered = client.get(ROOT,params={"event_id":events[1],"linked":"true"}).json()
    assert len(filtered)==1 and not filtered[0]["pending_review"]
    assert client.get(ROOT+"/decisions",params={"report_id":str(ids["report"]),"decision":"revisar"}).json()[0]["id"] == first["decision"]["id"]

def test_candidate_suggestion_is_preserved_but_never_changes_the_human_choice(case):
    client, _, ids, events, _ = case
    sample = suggestion(reporte_nuevo_id=str(ids["report"]), evento_candidato_id=events[0])
    value = body(client,ids["report"],events[0],"mantener_separado",suggestion=sample,factors={"observacion":"No corresponde"})
    result = apply(client,value)
    assert result["relation"]["event_id"] is None
    assert result["decision"]["factors"]["suggestion"]==sample
    assert result["decision"]["config_version"]=="propuesta-v1"
    assert result["decision"]["factors"]["_d2"]["suggestion_source"]=="municipal_input_unverified"

@pytest.mark.parametrize("kind",["agrupar","separar","revisar","mantener_separado"])
def test_transaction_failure_reverts_both_relation_and_audit(case,kind):
    client, engine, ids, events, _ = case
    if kind=="separar": apply(client,body(client,ids["report"],events[0]))
    before=current(client,ids["report"]); target=None if kind=="separar" else events[1]
    value=body(client,ids["report"],target,kind)
    def fail(connection,cursor,statement,parameters,context,many):
        if statement.startswith("INSERT INTO grouping_decisions"): connection.exec_driver_sql("SELECT 1/0")
    sql_event.listen(engine,"before_cursor_execute",fail)
    try: apply(client,value,503)
    finally: sql_event.remove(engine,"before_cursor_execute",fail)
    assert current(client,ids["report"])==before
    assert client.get(ROOT+"/decisions/"+value["operation_id"]).status_code==404

def test_initial_event_creation_cannot_bypass_existing_decision_revision(case):
    client, _, ids, events, _=case
    apply(client,body(client,ids["report"],events[0],"mantener_separado"))
    response=client.post("/municipal/events",json={"latitude":-12,"longitude":-75,"report_ids":[str(ids["report"])]})
    assert response.status_code==409 and current(client,ids["report"])["event_id"] is None


@pytest.fixture
def secure(auth):
    client, engine, ids, seed, headers = auth
    events = [seed["id"]]
    for _ in range(2):
        response = client.post("/municipal/events",json={"latitude":-12,"longitude":-75},headers=headers())
        assert response.status_code==201
        events.append(response.json()["id"])
    with Session(engine) as db:
        db.get(Profile,ids["driver2"]).role="encargado_municipal"
        db.commit()
    return client,engine,ids,events,headers


def signed_body(client, report_id, target, headers, kind="agrupar"):
    snapshot=client.get(ROOT+"/reports/"+str(report_id),headers=headers).json()
    return {"operation_id":str(uuid.uuid4()),"report_id":str(report_id),"candidate_event_id":target,
        "decision":kind,"expected_event_id":snapshot["event_id"],"expected_decision_id":snapshot["last_decision_id"]}


ROUTES=[("GET",ROOT),("GET",ROOT+"/reports/{report}"),("GET",ROOT+"/candidates?report_id={report}"),
        ("GET",ROOT+"/decisions"),("GET",ROOT+"/decisions/{decision}"),("POST",ROOT+"/decisions")]


@pytest.mark.parametrize("method,path",ROUTES)
@pytest.mark.parametrize("role",["missing","invalid","citizen","driver"])
def test_jwt_and_roles_protect_all_grouping_routes(secure,method,path,role):
    client,_,ids,events,headers=secure
    h={} if role=="missing" else {"Authorization":"Bearer invalid"} if role=="invalid" else headers(role)
    value=signed_body(client,ids["report"],events[0],headers(),"revisar")
    response=client.request(method,path.format(report=ids["report"],decision=uuid.uuid4()),
        headers=h,json=value if method=="POST" else None)
    assert response.status_code==(401 if role in ["missing","invalid"] else 403)


@pytest.mark.parametrize("method,path",ROUTES)
@pytest.mark.parametrize("algorithm",["ES256","RS256"])
def test_signed_municipal_requests_are_authorized(secure,method,path,algorithm):
    client,_,ids,events,headers=secure
    value=signed_body(client,ids["report"],events[0],headers(),"revisar")
    seed=client.post(ROOT+"/decisions",json=value,headers=headers()).json()["decision"]["id"]
    value=signed_body(client,ids["report"],events[0],headers())
    response=client.request(method,path.format(report=ids["report"],decision=seed),
        headers=headers(algorithm=algorithm),json=value if method=="POST" else None)
    assert response.status_code==200,response.text


@pytest.mark.parametrize("scenario",["reassign","separate_vs_reassign","confirm","review_vs_confirm"])
def test_two_managers_cannot_lose_a_concurrent_correction(secure,scenario):
    client,engine,ids,events,headers=secure
    if scenario in ["reassign","separate_vs_reassign"]:
        response=client.post(ROOT+"/decisions",json=signed_body(client,ids["report"],events[0],headers()),headers=headers())
        assert response.status_code==200
    first=signed_body(client,ids["report"],events[1],headers())
    second=signed_body(client,ids["report"],events[2],headers("driver2"))
    if scenario=="separate_vs_reassign": first.update(decision="separar",candidate_event_id=None)
    if scenario=="review_vs_confirm": first.update(decision="revisar")
    barrier=threading.Barrier(2)
    def synchronize(connection,cursor,statement,parameters,context,many):
        if statement.startswith("SELECT reports.id") and "FOR UPDATE" in statement: barrier.wait(timeout=10)
    sql_event.listen(engine,"before_cursor_execute",synchronize)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(client.post,ROOT+"/decisions",json=value,headers=h)
                for value,h in [(first,headers()),(second,headers("driver2"))]]
            responses=[future.result(timeout=20) for future in futures]
    finally: sql_event.remove(engine,"before_cursor_execute",synchronize)
    assert sorted(r.status_code for r in responses)==[200,409]
    winner=next(r.json() for r in responses if r.status_code==200)
    assert client.get(ROOT+"/reports/"+str(ids["report"]),headers=headers()).json()["last_decision_id"]==winner["decision"]["id"]
    with Session(engine) as db:
        assert count(db,ids["report"])==(2 if scenario in ["reassign","separate_vs_reassign"] else 1)
        assert db.get(Report,ids["report"]).status=="recibido"
    evidence("groupings-race-"+scenario+".json",{"http":[r.status_code for r in responses],
        "different_verified_managers":True,"last_decision_id":winner["decision"]["id"],
        "report_status_unchanged":True})


def test_concurrent_replay_of_same_operation_creates_one_decision(case):
    client,engine,ids,events,_=case
    value=body(client,ids["report"],events[0])
    barrier=threading.Barrier(2)
    def synchronize(connection,cursor,statement,parameters,context,many):
        if statement.startswith("SELECT reports.id") and "FOR UPDATE" in statement: barrier.wait(timeout=10)
    sql_event.listen(engine,"before_cursor_execute",synchronize)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda _:client.post(ROOT+"/decisions",json=value),range(2)))
    finally: sql_event.remove(engine,"before_cursor_execute",synchronize)
    assert [r.status_code for r in responses]==[200,200]
    assert sorted(r.json()["replayed"] for r in responses)==[False,True]
    with Session(engine) as db: assert count(db,ids["report"])==1


def test_lost_commit_is_recovered_by_operation_id_without_a_second_write(case,monkeypatch,caplog):
    client,engine,ids,events,_=case
    value=body(client,ids["report"],events[0])
    original=Session.commit
    commits=[]
    def lost(session):
        original(session); commits.append(True)
        raise OperationalError("private-sql",{},RuntimeError("private-connection"))
    monkeypatch.setattr(Session,"commit",lost)
    apply(client,value,503)
    assert commits==[True]
    stored=client.get(ROOT+"/decisions/"+value["operation_id"])
    assert stored.status_code==200
    replay=apply(client,value)
    assert replay["replayed"] and commits==[True]
    with Session(engine) as db: assert count(db,ids["report"])==1
    assert "private-connection" not in caplog.text and "private-sql" not in caplog.text


def test_real_postgresql_lock_timeout_is_controlled(case):
    client,engine,ids,events,_=case
    value=body(client,ids["report"],events[0])
    with Session(engine) as locker:
        locker.scalar(select(Report).where(Report.id==ids["report"]).with_for_update())
        apply(client,value,503)
        locker.rollback()
    assert client.get(ROOT+"/decisions/"+value["operation_id"]).status_code==404


@pytest.mark.parametrize("field",["report_id","candidate_event_id"])
def test_missing_report_or_candidate_is_404(case,field):
    client,_,ids,events,_=case
    value=body(client,ids["report"],events[0]); value[field]=str(uuid.uuid4())
    apply(client,value,404)
    assert client.get(ROOT+"/decisions/"+value["operation_id"]).status_code==404


@pytest.mark.parametrize("extra",[
    {"expected_event_id":"bad"},{"decision":"auto"},{"candidate_event_id":None},
    {"decided_by":str(uuid.uuid4())},{"latitude":91},{"factors":{"x":float("nan")}},
    {"suggestion":{"similitud_texto":float("inf")}},
])
def test_invalid_json_returns_422_without_internal_errors(case,extra):
    client,_,ids,events,_=case
    value=body(client,ids["report"],events[0]); value.update(extra)
    response=client.post(ROOT+"/decisions",content=json.dumps(value),headers={"Content-Type":"application/json"})
    assert response.status_code==422,response.text
    assert current(client,ids["report"])["last_decision_id"] is None


@pytest.mark.parametrize("suffix",["?limit=0","?limit=201","?offset=-1","?event_id=invalid"])
def test_invalid_pagination_and_filters(case,suffix):
    client,_,_,_,_=case
    assert client.get(ROOT+suffix).status_code==422
    assert client.get(ROOT+"/decisions"+suffix).status_code==422


def test_legacy_event_decisions_remain_readable_without_invented_previous_event(case):
    client,_,ids,events,_=case
    created=client.post("/municipal/events",json={"latitude":-12,"longitude":-75,"report_ids":[str(ids["report"])]})
    assert created.status_code==201
    record=client.get(ROOT+"/decisions",params={"report_id":str(ids["report"])}).json()[0]
    assert record["operation"] is None and not record["previous_event_known"]
    assert record["factors"]=={} and record["resulting_event_id"]==created.json()["id"]


def test_replay_rejects_same_operation_owned_by_other_manager(secure):
    client,_,ids,events,headers=secure
    value=signed_body(client,ids["report"],events[0],headers())
    assert client.post(ROOT+"/decisions",json=value,headers=headers()).status_code==200
    assert client.post(ROOT+"/decisions",json=value,headers=headers("driver2")).status_code==409


def test_integrated_api_flow_starts_with_a_signed_citizen_report(secure):
    client,_,ids,events,headers=secure
    response=client.post("/reports",headers=headers("citizen"),json={
        "description":"Reporte ficticio del recorrido integrado de agrupaciones",
        "latitude":-12.0528,"longitude":-75.226,
        "observed_at":datetime.now(timezone.utc).isoformat(),"waste_type":None})
    assert response.status_code==201,response.text
    original=response.json(); rid=original["id"]
    candidates=client.get(ROOT+"/candidates",params={"report_id":rid},headers=headers()).json()
    assert any(e["id"]==events[0] for e in candidates["candidates"])
    operations=[]
    for kind,target in [("revisar",events[0]),("mantener_separado",events[0]),
                         ("agrupar",events[0]),("agrupar",events[1]),("separar",None)]:
        value=signed_body(client,rid,target,headers(),kind)
        result=client.post(ROOT+"/decisions",json=value,headers=headers())
        assert result.status_code==200,result.text
        operations.append(result.json()["decision"]["operation"])
        assert client.get("/reports/"+rid,headers=headers("citizen")).json()==original
    history=client.get(ROOT+"/decisions",params={"report_id":rid},headers=headers()).json()
    assert len(history)==5
    mine=client.get("/reports/mine",headers=headers("citizen")).json()
    assert next(r for r in mine if r["id"]==rid)==original
    assert client.get(ROOT+"/reports/"+rid,headers=headers("citizen")).status_code==403
    evidence("groupings-api-e2e.json",{"report_id":rid,"coordinates":[original["latitude"],original["longitude"]],
        "verified_local_jwt":True,"operations":operations,"history_count":len(history),
        "original_report_preserved":True,"ui_or_supabase_real":False})
