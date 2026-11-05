"""Planner DTO unit tests, no database/network/optimizer."""
import uuid
import pytest
from pydantic import ValidationError
from app.route_contracts import PlannerResult, RouteGeometry, RouteProposalCreate

EVENTS=[str(uuid.uuid4()) for _ in range(3)]
def planner_result(**overrides):
    return {"algorithm_version":"fixture-v1","matrix_source":None,
        "stops":[{"event_id":EVENTS[0],"order":1},{"event_id":EVENTS[1],"order":2}],
        "excluded_events":[{"event_id":EVENTS[2],"reason":"Exclusión ficticia"}],
        "distance_m":None,"estimated_duration_seconds":None,
        "limitations":["Fixture controlada; no optimización real"],**overrides}

def proposal(**overrides):
    return {"proposal_id":str(uuid.uuid4()),"shift_id":str(uuid.uuid4()),"event_ids":EVENTS,
            "result":planner_result(),"test_data":True,**overrides}

@pytest.mark.parametrize("field,value",[
    ("distance_m",-1),("distance_m",float("inf")),("distance_m",float("nan")),("distance_m",True),
    ("estimated_duration_seconds",-1),("estimated_duration_seconds",float("nan")),
    ("algorithm_version","  "),("matrix_source"," "),
    ("geometry_geojson",{"type":"Point","coordinates":[-75,-12]}),
    ("stops",[{"event_id":EVENTS[0],"order":2}]),
    ("stops",[{"event_id":EVENTS[0],"order":True}]),
    ("stops",[{"event_id":EVENTS[0],"order":1},{"event_id":EVENTS[0],"order":2}]),
    ("stops",[{"event_id":EVENTS[2],"order":1}]),
    ("stops",[{"event_id":EVENTS[0],"order":1,"estimated_service_minutes":0}]),
    ("requirements",{"required_capacity_kg":-1}),
    ("requirements",{"vehicle_types":["compactadora","compactadora"]}),
    ("limitations",[" "]),("input_hash","invalid"),
])
def test_invalid_planner_result(field,value):
    with pytest.raises(ValidationError): PlannerResult.model_validate(planner_result(**{field:value}))

@pytest.mark.parametrize("coordinates",[
    [[181,-12],[-75,-12]], [[-75,-91],[-75,-12]], [[-75,float("nan")],[-75,-12]],
    [[-75,-12,3],[-75,-12]], [[-75,-12]], [[True,-12],[-75,-12]],
])
def test_invalid_geojson_coordinates(coordinates):
    with pytest.raises(ValidationError): RouteGeometry.model_validate({"type":"LineString","coordinates":coordinates})

@pytest.mark.parametrize("overrides",[
    {"created_by":str(uuid.uuid4())},{"approved_by":str(uuid.uuid4())},{"status":"aprobada"},
    {"result_origin":"d3"},{"provider_reference":"d3"},{"input_snapshot":{}},
    {"event_ids":[EVENTS[0],EVENTS[0]]},{"event_ids":[]},
    {"configuration":{"n":float("nan")}},{"configuration":{"x":"v"*32769}},
    {"test_data":True,"result":None},
    {"event_ids":[EVENTS[0]],"result":planner_result()},
])
def test_invalid_or_forged_public_proposal(overrides):
    with pytest.raises(ValidationError): RouteProposalCreate.model_validate(proposal(**overrides))

def test_unknown_estimates_and_pending_are_explicit():
    result=PlannerResult.model_validate(planner_result())
    assert result.distance_m is None and result.stops[0].estimated_service_minutes is None
    pending=RouteProposalCreate.model_validate(proposal(result=None,test_data=False))
    assert pending.result is None

def test_all_excluded_is_supported_without_fabricated_route():
    data=planner_result(stops=[],excluded_events=[{"event_id":eid,"reason":"No elegible"} for eid in EVENTS])
    assert RouteProposalCreate.model_validate(proposal(result=data)).result.stops==[]
    with pytest.raises(ValidationError):
        PlannerResult.model_validate({**data,"geometry_geojson":{"type":"LineString","coordinates":[[-75,-12],[-75,-11]]}})
