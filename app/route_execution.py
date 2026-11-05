"""D2 route decisions and driver execution. Never generates/verifies D3 results."""
import copy
import logging
import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .db import get_db
from .execution_contracts import (ApprovalReceipt, AuditEntry, DriverAction, ExecutionDetail,
    ExecutionStop, ExecutionSummary, IncidentOut, MunicipalDecision, OperationResult, RouteStatus, StopAction)
from .models import Profile, RoutePlan, RouteStop, ServiceSite, Shift, StopIncident, Vehicle
from .municipal_resources import MunicipalRoute
from .route_proposals import digest, lock_id, metadata
from .security import Actor, require_roles

logger = logging.getLogger(__name__)
NAMESPACE = "_municipal_execution_v1"
PROVIDER_BLOCKER = "provider_verification_unavailable"
municipal = require_roles("encargado_municipal")
driver = require_roles("chofer")
router = APIRouter(tags=["Decisiones y ejecución D2"], route_class=MunicipalRoute)


def ledger(plan):
    value = plan.configuration.get(NAMESPACE, {}) if isinstance(plan.configuration, dict) else None
    if value == {}:
        return {"version": 1, "operations": [], "verified_approval": None}
    if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("operations"), list):
        raise HTTPException(status_code=503, detail="Historial incompatible; requiere revisión administrativa")
    try:
        operations = [AuditEntry.model_validate(item) for item in value["operations"]]
        if len({item.operation_id for item in operations}) != len(operations) or len(operations) > 205:
            raise ValueError()
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(status_code=503, detail="Historial incompatible; requiere revisión administrativa") from None
    return {**value, "operations": operations}


def stops_for(db, plan):
    return list(db.scalars(select(RouteStop).where(RouteStop.route_plan_id == plan.id).order_by(RouteStop.stop_order)))


def stop_manifest(stops):
    return digest([{"id": str(s.id), "event_id": str(s.event_id), "order": s.stop_order,
                    "estimated_service_minutes": s.estimated_service_minutes} for s in stops])


def verified(plan, shift, stops, data):
    """Trust only the private, server-issued and snapshot-bound approval receipt."""
    try:
        receipt = ApprovalReceipt.model_validate(data.get("verified_approval"))
        meta = metadata(plan)
        core = plan.input_snapshot["operational"]
        return bool(plan.status in {"aprobada", "en_ejecucion", "finalizada"}
            and receipt.approved_by == plan.approved_by and receipt.approved_at == plan.approved_at
            and receipt.shift_id == shift.id and receipt.driver_id == shift.driver_id and receipt.vehicle_id == shift.vehicle_id
            and meta.get("result_origin") == "d3" and meta.get("calculation_status") == "completed"
            and meta.get("input_binding") == "matched"
            and receipt.input_hash == meta.get("input_hash") == digest(core)
            and receipt.result_hash == meta.get("result_hash")
            and receipt.provider_reference == meta.get("provider_reference")
            and receipt.stop_manifest_hash == stop_manifest(stops) and bool(stops)
            and core["driver"]["id"] == str(shift.driver_id) and core["vehicle"]["id"] == str(shift.vehicle_id)
            and core["shift"]["id"] == str(shift.id))
    except (ValidationError, KeyError, TypeError, ValueError):
        return False


def get_plan(db, route_id, actor, *, write=False):
    if write:
        # Same D2 advisory lock as result persistence: cancellation cannot race
        # a pending result and lose its audit. No adapter/contract changes.
        lock_id(db, route_id)
    query = select(RoutePlan).where(RoutePlan.id == route_id)
    if actor.role == "chofer":
        query = query.join(Shift, Shift.id == RoutePlan.shift_id).where(Shift.driver_id == actor.id)
    if write:
        query = query.with_for_update(of=RoutePlan)
    plan = db.scalar(query)
    if plan is None:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    return plan


def resources(db, plan, *, lock=False):
    query = select(Shift).where(Shift.id == plan.shift_id)
    shift = db.scalar(query.with_for_update(read=True) if lock else query)
    if shift is None:
        raise HTTPException(status_code=503, detail="Asignación inconsistente; requiere revisión")
    query = select(Vehicle).where(Vehicle.id == shift.vehicle_id)
    # Exclusive vehicle lock also serializes starts in consecutive shifts when
    # an earlier route is still running past its scheduled end.
    vehicle = db.scalar(query.with_for_update() if lock else query)
    if lock:
        db.scalar(select(Profile).where(Profile.id == shift.driver_id).with_for_update())
    query = select(ServiceSite).where(ServiceSite.id.in_({shift.departure_site_id, shift.disposal_site_id})).order_by(ServiceSite.id)
    sites = {s.id: s for s in db.scalars(query.with_for_update(read=True) if lock else query)}
    if vehicle is None or len(sites) != len({shift.departure_site_id, shift.disposal_site_id}):
        raise HTTPException(status_code=503, detail="Recursos inconsistentes; requiere revisión")
    return shift, vehicle, sites


def current_revision(data):
    return data["operations"][-1].operation_id if data["operations"] else None


def summary(db, plan):
    data = ledger(plan)
    shift, vehicle, _ = resources(db, plan)
    good = verified(plan, shift, stops_for(db, plan), data)
    return ExecutionSummary(id=plan.id, shift_id=shift.id, driver_id=shift.driver_id,
        vehicle_id=vehicle.id, vehicle_label=vehicle.label, starts_at=shift.starts_at, ends_at=shift.ends_at,
        status=plan.status, created_at=plan.created_at, revision=current_revision(data),
        approved_by=plan.approved_by, approved_at=plan.approved_at, approval_verified=good,
        approval_blockers=[] if good else [PROVIDER_BLOCKER])


def detail(db, plan):
    value = summary(db, plan)
    data = ledger(plan)
    shift, vehicle, sites = resources(db, plan)
    stops = stops_for(db, plan)
    incidents = {}
    if stops:
        for incident in db.scalars(select(StopIncident).where(StopIncident.stop_id.in_([s.id for s in stops]))
                .order_by(StopIncident.created_at, StopIncident.id)):
            incidents.setdefault(incident.stop_id, []).append(IncidentOut.model_validate(incident))
    if not isinstance(plan.input_snapshot, dict):
        raise HTTPException(status_code=503, detail="Instantánea incompatible; requiere revisión administrativa")
    core = plan.input_snapshot.get("operational", {})
    if not isinstance(core, dict) or not isinstance(core.get("events", []), list):
        raise HTTPException(status_code=503, detail="Instantánea incompatible; requiere revisión administrativa")
    events = {str(e.get("id")): e for e in core.get("events", []) if isinstance(e, dict)}
    def point(stop):
        event = events.get(str(stop.event_id), {})
        lat, lon = event.get("latitude"), event.get("longitude")
        return (lat, lon) if all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                    for v in (lat, lon)) and -90 <= lat <= 90 and -180 <= lon <= 180 else (None, None)
    def site_value(site):
        return {"id": str(site.id), "name": site.name, "site_type": site.site_type, "active": site.active,
                "latitude": site.latitude, "longitude": site.longitude}
    return ExecutionDetail(**value.model_dump(), shift_status=shift.status, vehicle_available=vehicle.available,
        departure=site_value(sites[shift.departure_site_id]), disposal=site_value(sites[shift.disposal_site_id]),
        stops=[ExecutionStop(id=s.id, event_id=s.event_id, order=s.stop_order, latitude=point(s)[0], longitude=point(s)[1],
            status=s.status, estimated_service_minutes=s.estimated_service_minutes, visited_at=s.visited_at,
            recorded_by=s.recorded_by, incidents=incidents.get(s.id, [])) for s in stops],
        history=data["operations"], distance_m=plan.distance_m, estimated_duration_seconds=plan.estimated_duration_seconds,
        geometry_geojson=plan.geometry_geojson, limitations=plan.limitations, excluded_events=plan.excluded_events)


def require_execution(db, plan):
    shift, _, _ = resources(db, plan)
    if not verified(plan, shift, stops_for(db, plan), ledger(plan)):
        raise HTTPException(status_code=409, detail="Ruta sin aprobación de procedencia verificada; no es ejecutable")
    return shift


def command_hash(payload, actor, route_id, stop_id=None):
    return digest({"actor": str(actor.id), "route_id": str(route_id), "stop_id": str(stop_id) if stop_id else None,
                   "command": payload.model_dump(mode="json")})


def replay_or_check(db, plan, data, payload, actor, stop_id=None):
    fingerprint = command_hash(payload, actor, plan.id, stop_id)
    old = next((item for item in data["operations"] if item.operation_id == payload.operation_id), None)
    if old:
        if old.actor_id != actor.id or old.request_hash != fingerprint:
            raise HTTPException(status_code=409, detail="operation_id ya utilizado para otra petición")
        return OperationResult(operation=old, route=detail(db, plan), replayed=True)
    if payload.expected_status != plan.status or payload.expected_revision != current_revision(data):
        raise HTTPException(status_code=409, detail="La ruta cambió; actualiza y vuelve a confirmar")
    if len(data["operations"]) >= 205:
        raise HTTPException(status_code=409, detail="Historial completo; requiere revisión administrativa")
    return None


def persist(db, plan, data, payload, actor, action, previous, stop_id=None):
    entry = AuditEntry(operation_id=payload.operation_id, actor_id=actor.id, action=action,
        at=db.scalar(select(func.clock_timestamp())), previous_status=previous, resulting_status=plan.status,
        stop_id=stop_id, notes=payload.notes, request_hash=command_hash(payload, actor, plan.id, stop_id))
    config = copy.deepcopy(plan.configuration)
    config[NAMESPACE] = {**data, "operations": [e.model_dump(mode="json") for e in [*data["operations"], entry]]}
    plan.configuration = config
    db.flush()
    output = OperationResult(operation=entry, route=detail(db, plan), replayed=False)
    # An unknown commit is never retried here. The UUID lookup/replay resolves it.
    db.commit()
    return output


@router.get("/municipal/routes", response_model=list[ExecutionSummary])
def routes(status: RouteStatus | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
           db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    query = select(RoutePlan)
    if status:
        query = query.where(RoutePlan.status == status)
    return [summary(db, p) for p in db.scalars(query.order_by(RoutePlan.created_at.desc(), RoutePlan.id.desc()).offset(offset).limit(limit))]


@router.get("/municipal/routes/{route_id}", response_model=ExecutionDetail)
def municipal_detail(route_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    return detail(db, get_plan(db, route_id, actor))


@router.get("/municipal/routes/{route_id}/history", response_model=list[AuditEntry])
def history(route_id: uuid.UUID, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
            db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    return list(reversed(ledger(get_plan(db, route_id, actor))["operations"]))[offset:offset+limit]


@router.post("/municipal/routes/{route_id}/decisions", response_model=OperationResult)
def decide(route_id: uuid.UUID, payload: MunicipalDecision, db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    plan = get_plan(db, route_id, actor, write=True)
    data = ledger(plan)
    replay = replay_or_check(db, plan, data, payload, actor)
    if replay:
        return replay
    if payload.decision == "approve":
        raise HTTPException(status_code=409, detail="Aprobación bloqueada: proveedor operativo todavía no verificado")
    allowed = {"propuesta"} if payload.decision == "reject" else {"propuesta", "aprobada"}
    if plan.status not in allowed:
        raise HTTPException(status_code=409, detail="El estado de la ruta no permite esta decisión")
    previous = plan.status
    plan.status = "cancelada"
    return persist(db, plan, data, payload, actor, payload.decision, previous)


@router.get("/driver/routes", response_model=list[ExecutionSummary])
def driver_routes(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                  db: Session = Depends(get_db), actor: Actor = Depends(driver)):
    query = select(RoutePlan).join(Shift, Shift.id == RoutePlan.shift_id).where(Shift.driver_id == actor.id,
        RoutePlan.status.in_(["aprobada", "en_ejecucion", "finalizada"])).order_by(RoutePlan.created_at.desc(), RoutePlan.id.desc())
    # Iterate in bounded batches and paginate after authorization, so unverified
    # legacy approvals cannot hide legitimate assignments behind an empty page.
    output, accepted = [], 0
    for plan in db.scalars(query.execution_options(yield_per=100)):
        item = summary(db, plan)
        if item.approval_verified:
            if accepted >= offset:
                output.append(item)
            accepted += 1
        if len(output) == limit:
            break
    return output


@router.get("/driver/routes/{route_id}", response_model=ExecutionDetail)
def driver_detail(route_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(driver)):
    plan = get_plan(db, route_id, actor)
    require_execution(db, plan)
    return detail(db, plan)


def find_operation(db, route_id, operation_id, actor):
    plan = get_plan(db, route_id, actor)
    entry = next((e for e in ledger(plan)["operations"] if e.operation_id == operation_id), None)
    if entry is None or (actor.role == "chofer" and entry.actor_id != actor.id):
        raise HTTPException(status_code=404, detail="Operación no encontrada")
    return entry


@router.get("/municipal/routes/{route_id}/operations/{operation_id}", response_model=AuditEntry)
def municipal_operation(route_id: uuid.UUID, operation_id: uuid.UUID, db: Session = Depends(get_db),
                        actor: Actor = Depends(municipal)):
    return find_operation(db, route_id, operation_id, actor)


@router.get("/driver/routes/{route_id}/operations/{operation_id}", response_model=AuditEntry)
def driver_operation(route_id: uuid.UUID, operation_id: uuid.UUID, db: Session = Depends(get_db),
                     actor: Actor = Depends(driver)):
    return find_operation(db, route_id, operation_id, actor)


@router.post("/driver/routes/{route_id}/actions", response_model=OperationResult)
def driver_action(route_id: uuid.UUID, payload: DriverAction, db: Session = Depends(get_db), actor: Actor = Depends(driver)):
    plan = get_plan(db, route_id, actor, write=True)
    data = ledger(plan)
    require_execution(db, plan)
    replay = replay_or_check(db, plan, data, payload, actor)
    if replay:
        return replay
    previous = plan.status
    if payload.action == "start":
        shift, vehicle, sites = resources(db, plan, lock=True)
        profile = db.get(Profile, actor.id)
        now = db.scalar(select(func.clock_timestamp()))
        if plan.status != "aprobada" or shift.status != "programado" or not shift.starts_at <= now < shift.ends_at:
            raise HTTPException(status_code=409, detail="La ruta o el horario del turno no permiten iniciar")
        departure, disposal = sites[shift.departure_site_id], sites[shift.disposal_site_id]
        if not vehicle.available or not profile or profile.role != "chofer" or not departure.active or not disposal.active or departure.site_type not in {"salida", "ambos"} or disposal.site_type not in {"descarga", "ambos"}:
            raise HTTPException(status_code=409, detail="Los recursos asignados no están disponibles")
        if db.scalar(select(RoutePlan.id).join(Shift, Shift.id == RoutePlan.shift_id).where(
                RoutePlan.id != plan.id, RoutePlan.status == "en_ejecucion",
                or_(Shift.vehicle_id == vehicle.id, Shift.driver_id == actor.id)).limit(1)):
            raise HTTPException(status_code=409, detail="Vehículo o chofer todavía tiene otro recorrido en ejecución")
        plan.status = "en_ejecucion"
    else:
        stops = stops_for(db, plan)
        if plan.status != "en_ejecucion" or not stops or any(s.status == "pendiente" for s in stops):
            raise HTTPException(status_code=409, detail="Registra todas las paradas antes de finalizar la ruta")
        plan.status = "finalizada"
    return persist(db, plan, data, payload, actor, payload.action, previous)


@router.post("/driver/routes/{route_id}/stops/{stop_id}/actions", response_model=OperationResult)
def stop_action(route_id: uuid.UUID, stop_id: uuid.UUID, payload: StopAction,
                db: Session = Depends(get_db), actor: Actor = Depends(driver)):
    plan = get_plan(db, route_id, actor, write=True)
    data = ledger(plan)
    require_execution(db, plan)
    replay = replay_or_check(db, plan, data, payload, actor, stop_id)
    if replay:
        return replay
    stops = stops_for(db, plan)
    stop = next((s for s in stops if s.id == stop_id), None)
    if stop is None:
        raise HTTPException(status_code=404, detail="Parada no encontrada en esta ruta")
    next_stop = next((s for s in stops if s.status == "pendiente"), None)
    if plan.status != "en_ejecucion" or stop.status != "pendiente" or next_stop is None or next_stop.id != stop.id:
        raise HTTPException(status_code=409, detail="Registra la siguiente parada pendiente de una ruta en ejecución")
    stop.status = {"attend": "atendida", "incident": "incidencia", "not_attended": "no_atendida"}[payload.action]
    stop.visited_at = db.scalar(select(func.clock_timestamp()))
    stop.recorded_by = actor.id
    if payload.action != "attend":
        db.add(StopIncident(stop_id=stop.id, reported_by=actor.id,
            incident_type=payload.incident_type if payload.action == "incident" else "no_atendida", description=payload.notes))
    # Deliberately no automatic report/event closure: that business rule has
    # not been agreed, and grouping does not mean attention.
    return persist(db, plan, data, payload, actor, payload.action, plan.status, stop_id)
