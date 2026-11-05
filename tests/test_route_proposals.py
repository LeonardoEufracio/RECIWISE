"""Real marked localhost PostgreSQL, fixtures explicitly not real optimization."""
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import json
import os
import uuid
import pytest
import psycopg
from fastapi import HTTPException
from sqlalchemy import event as sql_event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import Event, Profile, RoutePlan, RouteStop, ServiceSite, Shift, Vehicle
from app.planner_adapter import register_planner_result
from app.route_contracts import PlannerResult
from app.security import Actor
from concurrency_support import ISOLATED_ONLY, pg_case, shift_payload
from postgres_support import evidence
from postgres_support import connect, transaction
from test_events import auth
from test_security import jwt_keys
from test_photo_restart import api_worker

pytestmark=ISOLATED_ONLY
ROOT="/municipal/route-proposals"

@pytest.fixture
def case(pg_case):
    client,engine,ids,state=pg_case
    response=client.post("/municipal/shifts",json=shift_payload(ids))
    assert response.status_code==201,response.text
    ids["shift"]=uuid.UUID(response.json()["id"])
    events=[]
    for i in range(3):
        response=client.post("/municipal/events",json={"latitude":-12.05-i*.001,"longitude":-75.226})
        assert response.status_code==201,response.text
        events.append(response.json()["id"])
    return client,engine,ids,events,state

def result(events,**extra):
    return {"algorithm_version":"controlled-fixture-v1","matrix_source":None,
        "stops":[{"event_id":events[1],"order":1},{"event_id":events[0],"order":2}],
        "excluded_events":[{"event_id":events[2],"reason":"Excluido en la fixture"}],
        "distance_m":None,"estimated_duration_seconds":None,
        "limitations":["Datos ficticios de prueba; no se ejecutó un optimizador"],**extra}

def command(ids,events,**extra):
    return {"proposal_id":str(uuid.uuid4()),"shift_id":str(ids["shift"]),"event_ids":events,
        "result":result(events),"test_data":True,**extra}

def create(client,value):
    response=client.post(ROOT,json=value)
    assert response.status_code==201,response.text
    return response.json()

def test_proposal_order_exclusions_and_private_creator_persist(case):
    client,engine,ids,events,_=case
    value=command(ids,events)
    item=create(client,value)
    assert item["status"]=="propuesta" and not item["operational"]
    assert item["result_origin"]=="test_fixture" and item["calculation_status"]=="completed"
    assert item["created_by"]==str(ids["manager"])
    assert [s["event_id"] for s in item["stops"]]==[events[1],events[0]]
    assert [s["order"] for s in item["stops"]]==[1,2]
    assert item["excluded_events"]==value["result"]["excluded_events"]
    assert item["distance_m"] is None and item["estimated_duration_seconds"] is None
    assert "capacity_unknown" in item["unknowns"] and item["limitations"]
    assert item["input_snapshot"]["operational"]["vehicle"]["capacity_kg"] is None
    with Session(engine) as db:
        plan=db.get(RoutePlan,uuid.UUID(item["id"]))
        assert plan.approved_by is None and plan.approved_at is None
        assert len(db.scalars(select(RouteStop).where(RouteStop.route_plan_id==plan.id)).all())==2
    engine.dispose()
    assert client.get(ROOT+"/"+item["id"]).json()==item
    assert client.get(ROOT+"/"+item["id"]+"/stops?limit=1&offset=1").json()[0]["event_id"]==events[0]
    assert client.get(ROOT+"/"+item["id"]+"/excluded-events").json()==item["excluded_events"]
    evidence("routes-persistence.json",{"proposal_id":item["id"],"origin":item["result_origin"],
        "stop_order":[s["event_id"] for s in item["stops"]],"fresh_connection":True,"approved":False})

def test_pending_proposal_has_no_invented_result_and_public_data_is_unverified(case):
    client,_,ids,events,_=case
    pending=create(client,command(ids,events,result=None,test_data=False))
    assert pending["calculation_status"]=="pending" and pending["algorithm_version"] is None
    assert pending["stops"]==[] and pending["geometry_geojson"] is None
    item=create(client,command(ids,events,test_data=False,configuration={"_d2":{"result_origin":"d3"}}))
    assert item["result_origin"]=="municipal_unverified" and not item["operational"]
    assert item["configuration"]["parameters"]["_d2"]["result_origin"]=="d3"
    assert item["configuration"]["_d2"]["result_origin"]=="municipal_unverified"

def test_alternatives_pagination_and_filters(case):
    client,_,ids,events,_=case
    a=create(client,command(ids,events)); b=create(client,command(ids,events,result=None,test_data=False))
    page=client.get(ROOT,params={"shift_id":str(ids["shift"]),"limit":1}).json()
    next_page=client.get(ROOT,params={"shift_id":str(ids["shift"]),"limit":1,"offset":1}).json()
    assert {page[0]["id"],next_page[0]["id"]}=={a["id"],b["id"]}
    filtered=client.get(ROOT,params={"shift_id":str(ids["shift"]),"calculation_status":"pending"}).json()
    assert [p["id"] for p in filtered]==[b["id"]]
    assert client.get(ROOT,params={"shift_id":str(ids["shift"]),"result_origin":"d3"}).json()==[]
    assert client.get(ROOT+"?offset=1000000").json()==[]

def test_fixture_adapter_completes_pending_input_atomically_and_replays(case):
    client,engine,ids,events,_=case
    pending=create(client,command(ids,events,result=None,test_data=False))
    output=PlannerResult.model_validate(result(events,input_hash=pending["input_hash"]))
    actor=Actor(ids["manager"],"encargado_municipal")
    with Session(engine) as db:
        stored=register_planner_result(db,actor,uuid.UUID(pending["id"]),output,
            origin="test_fixture",provider_reference="controlled-fixture")
    assert stored.result_origin=="test_fixture" and stored.stop_count==2 and not stored.operational
    with Session(engine) as db:
        replay=register_planner_result(db,actor,uuid.UUID(pending["id"]),output,
            origin="test_fixture",provider_reference="controlled-fixture")
    assert replay.model_dump()==stored.model_dump()
    assert create(client,{**command(ids,events,result=None,test_data=False),"proposal_id":pending["id"]})["id"]==pending["id"]

def test_geojson_is_only_received_not_generated(case):
    client,_,ids,events,_=case
    geometry={"type":"LineString","coordinates":[[-75.23,-12.06],[-75.225,-12.052],[-75.22,-12.05]]}
    item=create(client,command(ids,events,result=result(events,geometry_geojson=geometry)))
    assert item["geometry_geojson"]==geometry and item["result_origin"]=="test_fixture"
    assert create(client,command(ids,events))["geometry_geojson"] is None


@pytest.fixture
def secured(auth):
    client,engine,ids,seed,headers=auth
    response=client.post("/municipal/shifts",json=shift_payload(ids),headers=headers())
    assert response.status_code==201,response.text
    ids["shift"]=uuid.UUID(response.json()["id"])
    events=[seed["id"]]
    for _ in range(2):
        r=client.post("/municipal/events",json={"latitude":-12,"longitude":-75},headers=headers())
        assert r.status_code==201
        events.append(r.json()["id"])
    stored=client.post(ROOT,json=command(ids,events),headers=headers()).json()
    return client,engine,ids,events,headers,stored


ROUTES=[("GET",ROOT),("POST",ROOT),("GET",ROOT+"/{id}"),
        ("GET",ROOT+"/{id}/stops"),("GET",ROOT+"/{id}/excluded-events")]


@pytest.mark.parametrize("method,path",ROUTES)
@pytest.mark.parametrize("role",["missing","invalid","citizen","driver"])
def test_authentication_and_authorization(secured,method,path,role):
    client,_,ids,events,headers,stored=secured
    h={} if role=="missing" else {"Authorization":"Bearer invalid"} if role=="invalid" else headers(role)
    response=client.request(method,path.format(id=stored["id"]),headers=h,
        json=command(ids,events) if method=="POST" else None)
    assert response.status_code==(401 if role in ["missing","invalid"] else 403)


@pytest.mark.parametrize("method,path",ROUTES)
@pytest.mark.parametrize("algorithm",["ES256","RS256"])
def test_signed_municipal_access(secured,method,path,algorithm):
    client,_,ids,events,headers,stored=secured
    response=client.request(method,path.format(id=stored["id"]),headers=headers(algorithm=algorithm),
        json=command(ids,events) if method=="POST" else None)
    assert response.status_code==(201 if method=="POST" else 200),response.text


@pytest.mark.parametrize("change",[
    "vehicle_unavailable","capacity_invalid","driver_role","departure_inactive","disposal_type",
    "shift_cancelled","shift_expired","event_closed","event_programmed","event_stale_closed_at",
])
def test_operational_conflicts_do_not_create_partial_proposals(case,change):
    client,engine,ids,events,_=case
    with Session(engine) as db:
        if change=="vehicle_unavailable": db.get(Vehicle,ids["vehicle"]).available=False
        if change=="capacity_invalid": db.get(Vehicle,ids["vehicle"]).capacity_kg=float("nan")
        if change=="driver_role": db.get(Profile,ids["driver"]).role="ciudadano"
        if change=="departure_inactive": db.get(ServiceSite,ids["departure"]).active=False
        if change=="disposal_type": db.get(ServiceSite,ids["disposal"]).site_type="salida"
        if change=="shift_cancelled": db.get(Shift,ids["shift"]).status="cancelado"
        if change=="shift_expired":
            shift=db.get(Shift,ids["shift"])
            shift.starts_at=datetime.now(timezone.utc)-timedelta(hours=2)
            shift.ends_at=datetime.now(timezone.utc)-timedelta(hours=1)
        if change in ["event_closed","event_programmed","event_stale_closed_at"]:
            item=db.get(Event,uuid.UUID(events[0]))
            if change=="event_programmed": item.state="programado"
            else: item.closed_at=datetime.now(timezone.utc)
            if change=="event_closed": item.state="cerrado"
        db.commit()
    value=command(ids,events)
    response=client.post(ROOT,json=value)
    assert response.status_code==409,response.text
    with Session(engine) as db: assert db.get(RoutePlan,uuid.UUID(value["proposal_id"])) is None


@pytest.mark.parametrize("requirements",[
    {"vehicle_types":["compactadora"]},{"vehicle_types":["otro"],"required_capacity_kg":1001},
])
def test_known_vehicle_requirements_are_checked(case,requirements):
    client,engine,ids,events,_=case
    with Session(engine) as db:
        db.get(Vehicle,ids["vehicle"]).capacity_kg=1000
        db.commit()
    r=client.post(ROOT,json=command(ids,events,result=result(events,requirements=requirements)))
    assert r.status_code==409


def test_unknown_capacity_is_never_replaced_with_an_invented_capacity(case):
    client,_,ids,events,_=case
    output=create(client,command(ids,events,result=result(events,requirements={"required_capacity_kg":1200})))
    assert "capacity_unknown" in output["unknowns"]
    assert output["input_snapshot"]["operational"]["vehicle"]["capacity_kg"] is None


@pytest.mark.parametrize("field",["shift_id","event_ids"])
def test_missing_resources_are_404(case,field):
    client,_,ids,events,_=case
    value=command(ids,events)
    if field=="shift_id": value[field]=str(uuid.uuid4())
    else:
        value[field]=[str(uuid.uuid4()),*events[1:]]
        value["result"]["stops"][1]["event_id"]=value[field][0]
    assert client.post(ROOT,json=value).status_code==404


@pytest.mark.parametrize("suffix",["","/stops","/excluded-events"])
def test_unknown_and_invalid_proposal_ids(case,suffix):
    client,_,_,_,_=case
    assert client.get(ROOT+"/"+str(uuid.uuid4())+suffix).status_code==404
    assert client.get(ROOT+"/invalid"+suffix).status_code==422


@pytest.mark.parametrize("query",["limit=0","limit=201","offset=-1","status=aprobada","shift_id=bad",
                                 "calculation_status=ready","result_origin=engine_fake"])
def test_invalid_filters_and_pagination_are_422(case,query):
    client,_,_,_,_=case
    assert client.get(ROOT+"?"+query).status_code==422


@pytest.mark.parametrize("extra",[
    {"created_by":str(uuid.uuid4())},{"result_origin":"d3"},{"approved_by":str(uuid.uuid4())},
    {"status":"aprobada"},{"configuration":{"x":float("nan")}},
])
def test_public_forgery_and_nonfinite_json_are_422(case,extra):
    client,_,ids,events,_=case
    value=command(ids,events,**extra)
    r=client.post(ROOT,content=json.dumps(value),headers={"Content-Type":"application/json"})
    assert r.status_code==422,r.text


def test_stop_failure_rolls_back_parent_and_children(case,caplog):
    client,engine,ids,events,_=case
    value=command(ids,events)
    def fail(connection,cursor,statement,parameters,context,many):
        if statement.startswith("INSERT INTO route_stops"): connection.exec_driver_sql("SELECT 1/0")
    sql_event.listen(engine,"before_cursor_execute",fail)
    try:
        response=client.post(ROOT,json=value)
        assert response.status_code==503
    finally: sql_event.remove(engine,"before_cursor_execute",fail)
    with Session(engine) as db:
        assert db.get(RoutePlan,uuid.UUID(value["proposal_id"])) is None
        assert db.scalar(select(func.count()).select_from(RouteStop).where(RouteStop.route_plan_id==uuid.UUID(value["proposal_id"])))==0
    assert "SELECT 1/0" not in caplog.text+response.text


def test_lost_commit_and_same_id_replay_never_duplicate_a_proposal(case,monkeypatch,caplog):
    client,engine,ids,events,_=case
    value=command(ids,events); commits=[]; original=Session.commit
    def lost(session):
        original(session); commits.append(True)
        raise OperationalError("private-query",{},RuntimeError("private-dsn"))
    monkeypatch.setattr(Session,"commit",lost)
    assert client.post(ROOT,json=value).status_code==503
    restored=client.get(ROOT+"/"+value["proposal_id"])
    assert restored.status_code==200
    assert create(client,value)==restored.json() and commits==[True]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(RouteStop).where(RouteStop.route_plan_id==uuid.UUID(value["proposal_id"])))==2
    assert "private-dsn" not in caplog.text


def test_simultaneous_same_id_is_one_persisted_proposal(case):
    client,engine,ids,events,_=case
    value=command(ids,events)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:client.post(ROOT,json=value),range(2)))
    assert [r.status_code for r in responses]==[201,201]
    assert responses[0].json()==responses[1].json()
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(RouteStop).where(RouteStop.route_plan_id==uuid.UUID(value["proposal_id"])))==2
    changed={**value,"configuration":{"different":True}}
    assert client.post(ROOT,json=changed).status_code==409


def test_actual_fastapi_process_restart_preserves_proposal_and_stops(case):
    client,_,ids,events,_=case
    item=create(client,command(ids,events))
    env=dict(os.environ,RECIWISE_WORKER_CITIZEN=str(ids["citizen"]),RECIWISE_WORKER_MANAGER=str(ids["manager"]))
    headers={"x-reciwise-test-actor":str(ids["manager"])}
    with api_worker(env) as (http,process):
        before=process.pid
        assert http.get(ROOT+"/"+item["id"],headers=headers).json()==item
    with api_worker(env) as (http,process):
        assert process.pid!=before
        assert http.get(ROOT+"/"+item["id"],headers=headers).json()==item
        evidence("routes-process-restart.json",{"proposal_id":item["id"],"before_pid":before,
            "after_pid":process.pid,"unchanged":True,"test_auth_header_only_in_existing_isolated_worker":True})


@pytest.mark.parametrize("change",["hash","grouping","configuration"])
def test_internal_adapter_rejects_stale_or_wrong_inputs(case,change):
    client,engine,ids,events,_=case
    if change=="grouping":
        from test_groupings import body, apply
        apply(client,body(client,ids["report"],events[0]))
    pending=create(client,command(ids,events,result=None,test_data=False))
    if change=="grouping":
        from test_groupings import body, apply
        apply(client,body(client,ids["report"],events[1]))
    if change=="configuration":
        with Session(engine) as db:
            db.get(Event,uuid.UUID(events[0])).intervention_type="Dato modificado"; db.commit()
    value=result(events,input_hash="0"*64 if change=="hash" else pending["input_hash"])
    with Session(engine) as db:
        with pytest.raises(HTTPException) as exc:
            register_planner_result(db,Actor(ids["manager"],"encargado_municipal"),uuid.UUID(pending["id"]),
                value,origin="test_fixture",provider_reference="fixture")
        assert exc.value.status_code==409
    assert client.get(ROOT+"/"+pending["id"]).json()["calculation_status"]=="pending"


def test_internal_invalid_result_does_not_turn_into_a_persistence_failure(case):
    _,engine,ids,_,_=case
    with Session(engine) as db:
        with pytest.raises(HTTPException) as exc:
            register_planner_result(db,Actor(ids["manager"],"encargado_municipal"),uuid.uuid4(),
                {"algorithm_version":""},origin="test_fixture",provider_reference="fixture")
        assert exc.value.status_code==422


def test_closed_events_can_only_be_explicitly_excluded_and_no_route_is_invented(case):
    client,engine,ids,events,_=case
    with Session(engine) as db:
        item=db.get(Event,uuid.UUID(events[2])); item.state="cerrado"; item.closed_at=datetime.now(timezone.utc); db.commit()
    output=create(client,command(ids,events))
    assert output["excluded_events"][0]["event_id"]==events[2]
    all_excluded=result(events,stops=[],excluded_events=[{"event_id":eid,"reason":"No elegible en la fixture"} for eid in events])
    output=create(client,command(ids,events,result=all_excluded))
    assert output["stops"]==[] and output["geometry_geojson"] is None and "no_stops" in output["unknowns"]


def test_no_approval_or_execution_endpoint_is_exposed(case):
    client,_,ids,events,_=case
    item=create(client,command(ids,events))
    for suffix in ["/approval","/assign","/execute"]:
        assert client.post(ROOT+"/"+item["id"]+suffix,json={}).status_code==404


@pytest.mark.parametrize("table",["route_plans","route_stops"])
@pytest.mark.parametrize("role",["anon","authenticated"])
def test_client_sql_roles_cannot_read_protected_route_tables(case,table,role):
    connection=connect()
    try:
        with transaction(connection):
            connection.execute(psycopg.sql.SQL("SET LOCAL ROLE {}").format(psycopg.sql.Identifier(role)))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(psycopg.sql.SQL("SELECT * FROM public.{} LIMIT 1").format(psycopg.sql.Identifier(table)))
    finally: connection.close()


@pytest.mark.parametrize("violation",["event_duplicate","order_duplicate","nonpositive_order","missing_event"])
def test_postgres_stop_constraints_are_real(case,violation):
    client,_,ids,events,_=case
    item=create(client,command(ids,events))
    event_id,position=events[0],3
    expected="23505"
    if violation=="order_duplicate": event_id,position=events[2],1
    if violation=="nonpositive_order": event_id,position,expected=events[2],0,"23514"
    if violation=="missing_event": event_id,position,expected=str(uuid.uuid4()),3,"23503"
    connection=connect()
    try:
        with transaction(connection):
            with pytest.raises(psycopg.Error) as exc:
                connection.execute("INSERT INTO public.route_stops(id,route_plan_id,event_id,stop_order) VALUES(%s,%s,%s,%s)",
                    (uuid.uuid4(),uuid.UUID(item["id"]),uuid.UUID(event_id),position))
            assert exc.value.sqlstate==expected
    finally: connection.close()
    assert len(client.get(ROOT+"/"+item["id"]+"/stops").json())==2


def test_existing_partial_index_restricts_executable_plans_but_not_alternatives(case):
    client,_,ids,events,_=case
    first=create(client,command(ids,events)); second=create(client,command(ids,events))
    connection=connect()
    try:
        with transaction(connection):
            connection.execute("UPDATE public.route_plans SET status='aprobada' WHERE id=%s",(first["id"],))
            with pytest.raises(psycopg.errors.UniqueViolation):
                connection.execute("UPDATE public.route_plans SET status='aprobada' WHERE id=%s",(second["id"],))
    finally: connection.close()
    assert client.get(ROOT+"/"+first["id"]).json()["status"]=="propuesta"
    assert client.get(ROOT+"/"+second["id"]).json()["status"]=="propuesta"


def test_internal_stop_failure_preserves_pending_proposal_for_recovery(case):
    client,engine,ids,events,_=case
    pending=create(client,command(ids,events,result=None,test_data=False))
    value=result(events,input_hash=pending["input_hash"])
    def fail(connection,cursor,statement,parameters,context,many):
        if statement.startswith("INSERT INTO route_stops"): connection.exec_driver_sql("SELECT 1/0")
    sql_event.listen(engine,"before_cursor_execute",fail)
    try:
        with Session(engine) as db:
            with pytest.raises(HTTPException) as exc:
                register_planner_result(db,Actor(ids["manager"],"encargado_municipal"),uuid.UUID(pending["id"]),value,
                    origin="test_fixture",provider_reference="fixture")
            assert exc.value.status_code==503
    finally: sql_event.remove(engine,"before_cursor_execute",fail)
    assert client.get(ROOT+"/"+pending["id"]).json()==pending
