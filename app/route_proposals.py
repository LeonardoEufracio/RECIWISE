"""Administrative proposals only. No optimizer, approval, assignment or execution."""
import hashlib
import json
import logging
import math
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .db import get_db
from .events import EventRoute, municipal, rollback
from .models import Event, EventReport, GroupingDecision, Profile, RoutePlan, RouteStop, ServiceSite, Shift, Vehicle
from .route_contracts import (CalculationState, ExcludedEvent, Origin, PlannerResult, ProposalDetail,
                              ProposalSummary, RouteProposalCreate, RouteStopOut)
from .security import Actor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/municipal/route-proposals", tags=["Propuestas de rutas"], route_class=EventRoute)
ACTIVE_EVENTS = {"en_revision", "abierto"}
EXPLANATIONS = {
    "calculation_pending": "Propuesta pendiente de cálculo; no contiene un recorrido calculado.",
    "test_fixture": "Datos de prueba: no representan una optimización real.",
    "municipal_unverified": "Resultado aportado por un encargado; procedencia del motor no verificada.",
    "capacity_unknown": "Capacidad del vehículo desconocida; no se ha comprobado suficiencia.",
    "required_load_unknown": "Carga requerida desconocida; no se infiere desde descripciones.",
    "vehicle_type_compatibility_unknown": "No hay requisitos normalizados para verificar compatibilidad de tipo de vehículo.",
    "intervention_compatibility_unknown": "Compatibilidad por intervención/acceso no verificada.",
    "distance_unknown": "Distancia estimada no disponible.",
    "duration_unknown": "Duración estimada no disponible.",
    "matrix_unknown": "No se ha identificado una matriz vial fiable.",
    "geometry_unknown": "Sin geometría recibida; no se unen marcadores para simular un recorrido.",
    "service_time_unknown": "Hay tiempos de servicio no disponibles.",
    "events_under_review": "Hay eventos en revisión; esta propuesta no autoriza su atención.",
    "no_stops": "El resultado no contiene paradas elegibles.",
    "legacy_unknown": "La procedencia de esta propuesta histórica no está registrada.",
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def unavailable(db):
    rollback(db)
    logger.warning("Route proposal unavailable; query proposal_id before retrying writes")
    return HTTPException(status_code=503, detail="Servicio de propuestas no disponible; consulta proposal_id antes de reintentar")


def metadata(plan):
    value = plan.configuration.get("_d2", {}) if isinstance(plan.configuration, dict) else {}
    return value if isinstance(value, dict) and value.get("version") == 1 else {}


def lock_id(db, proposal_id):
    db.execute(text("SET LOCAL lock_timeout='3s'"))
    db.execute(text("SET LOCAL statement_timeout='15s'"))
    key = int.from_bytes(hashlib.sha256(b"route-proposal:" + proposal_id.bytes).digest()[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def verify_actor(db, actor):
    profile = db.get(Profile, actor.id)
    if actor.role != "encargado_municipal" or profile is None or profile.role != "encargado_municipal":
        raise HTTPException(status_code=403, detail="Se requiere un encargado municipal habilitado")


def collect_input(db, actor, shift_id, event_ids, parameters, result=None):
    """Lock resources/events, never reports (avoids reversing grouping's report->event order)."""
    shift = db.scalar(select(Shift).where(Shift.id == shift_id).with_for_update())
    if shift is None:
        raise HTTPException(status_code=404, detail="Turno no encontrado")
    now = db.scalar(select(func.clock_timestamp()))
    if shift.status != "programado" or shift.ends_at <= now or shift.ends_at <= shift.starts_at:
        raise HTTPException(status_code=409, detail="El turno no está disponible para preparar propuestas")
    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == shift.vehicle_id).with_for_update())
    driver = db.scalar(select(Profile).where(Profile.id == shift.driver_id).with_for_update())
    sites = {s.id: s for s in db.scalars(select(ServiceSite)
        .where(ServiceSite.id.in_({shift.departure_site_id, shift.disposal_site_id}))
        .order_by(ServiceSite.id).with_for_update())}
    if not vehicle or not vehicle.available:
        raise HTTPException(status_code=409, detail="El vehículo no está disponible")
    if vehicle.capacity_kg is not None and (not math.isfinite(vehicle.capacity_kg) or vehicle.capacity_kg <= 0):
        raise HTTPException(status_code=409, detail="La capacidad registrada no es válida")
    if not driver or driver.role != "chofer":
        raise HTTPException(status_code=409, detail="El chofer del turno no está habilitado")
    departure, disposal = sites.get(shift.departure_site_id), sites.get(shift.disposal_site_id)
    if (not departure or not departure.active or departure.site_type not in {"salida", "ambos"}
            or not disposal or not disposal.active or disposal.site_type not in {"descarga", "ambos"}):
        raise HTTPException(status_code=409, detail="Los puntos operativos del turno no son compatibles")
    found = {e.id: e for e in db.scalars(select(Event).where(Event.id.in_(event_ids)).order_by(Event.id).with_for_update())}
    if len(found) != len(event_ids):
        raise HTTPException(status_code=404, detail="Uno o más eventos no existen")
    included = {s.event_id for s in result.stops} if result else set(event_ids)
    if any(found[eid].state not in ACTIVE_EVENTS or found[eid].closed_at is not None for eid in included):
        raise HTTPException(status_code=409, detail="Un evento incluido no admite planificación")
    latest = (select(GroupingDecision.id).where(GroupingDecision.report_id == EventReport.report_id)
        .order_by(GroupingDecision.decided_at.desc(), GroupingDecision.id.desc())
        .limit(1).correlate(EventReport).scalar_subquery())
    links = {eid: [] for eid in event_ids}
    for eid, rid, revision in db.execute(select(EventReport.event_id, EventReport.report_id, latest)
            .where(EventReport.event_id.in_(event_ids)).order_by(EventReport.report_id)):
        links[eid].append({"report_id": str(rid), "last_decision_id": str(revision) if revision else None})
    def site_value(site):
        return {"id": str(site.id), "name": site.name, "site_type": site.site_type,
            "latitude": site.latitude, "longitude": site.longitude, "active": site.active}
    core = {
        "requested_by": str(actor.id), "event_ids": [str(eid) for eid in event_ids], "parameters": parameters,
        "shift": {"id": str(shift.id), "starts_at": shift.starts_at.isoformat(), "ends_at": shift.ends_at.isoformat(),
                  "status": shift.status, "driver_id": str(driver.id)},
        "vehicle": {"id": str(vehicle.id), "label": vehicle.label, "vehicle_type": vehicle.vehicle_type,
                    "capacity_kg": vehicle.capacity_kg, "available": vehicle.available},
        "driver": {"id": str(driver.id), "role": driver.role},
        "departure": site_value(departure), "disposal": site_value(disposal),
        "events": [{"id": str(eid), "latitude": found[eid].latitude, "longitude": found[eid].longitude,
            "state": found[eid].state, "closed_at": found[eid].closed_at.isoformat() if found[eid].closed_at else None,
            "intervention_type": found[eid].intervention_type, "reports": links[eid]} for eid in event_ids],
    }
    return core, now


def result_values(plan, result, origin, actor, core, provider_reference=None):
    included = {s.event_id for s in result.stops} if result else set()
    if result:
        covered = included | {e.event_id for e in result.excluded_events}
        if covered != {uuid.UUID(eid) for eid in core["event_ids"]}:
            raise HTTPException(status_code=422, detail="El resultado no corresponde a los eventos solicitados")
        if result.input_hash is not None and result.input_hash != digest(core):
            raise HTTPException(status_code=409, detail="La huella de entrada no coincide")
        requirements = result.requirements
        if requirements.vehicle_types is not None and core["vehicle"]["vehicle_type"] not in requirements.vehicle_types:
            raise HTTPException(status_code=409, detail="El tipo de vehículo es incompatible con los requisitos")
        capacity, needed = core["vehicle"]["capacity_kg"], requirements.required_capacity_kg
        if capacity is not None and needed is not None and needed > capacity:
            raise HTTPException(status_code=409, detail="La capacidad conocida es insuficiente")
    unknowns = ["intervention_compatibility_unknown"]
    if origin in EXPLANATIONS: unknowns.append(origin)
    if core["vehicle"]["capacity_kg"] is None: unknowns.append("capacity_unknown")
    if not result or result.requirements.required_capacity_kg is None: unknowns.append("required_load_unknown")
    if not result or result.requirements.vehicle_types is None: unknowns.append("vehicle_type_compatibility_unknown")
    if not result: unknowns.append("calculation_pending")
    if not result or result.distance_m is None: unknowns.append("distance_unknown")
    if not result or result.estimated_duration_seconds is None: unknowns.append("duration_unknown")
    if not result or result.matrix_source is None: unknowns.append("matrix_unknown")
    if not result or result.geometry_geojson is None: unknowns.append("geometry_unknown")
    if result and any(s.estimated_service_minutes is None for s in result.stops): unknowns.append("service_time_unknown")
    if any(e["state"] == "en_revision" and (not result or uuid.UUID(e["id"]) in included) for e in core["events"]):
        unknowns.append("events_under_review")
    if result and not result.stops: unknowns.append("no_stops")
    meta = dict(metadata(plan))
    meta.update({"version": 1, "calculation_status": "completed" if result else "pending",
        "result_origin": origin, "unknowns": unknowns, "input_hash": digest(core),
        "registered_by": str(actor.id), "provider_reference": provider_reference,
        "input_binding": "matched" if result and result.input_hash else "unverified" if result else "pending",
        "result_hash": digest({"result": result.model_dump(mode="json"), "origin": origin,
                               "provider": provider_reference, "actor": str(actor.id)}) if result else None})
    plan.configuration = {"parameters": core["parameters"],
        "requirements": result.requirements.model_dump(mode="json") if result else None, "_d2": meta}
    plan.algorithm_version = result.algorithm_version if result else "pending"
    plan.matrix_source = result.matrix_source if result else None
    plan.distance_m = result.distance_m if result else None
    plan.estimated_duration_seconds = result.estimated_duration_seconds if result else None
    plan.geometry_geojson = result.geometry_geojson.model_dump(mode="json") if result and result.geometry_geojson else None
    plan.excluded_events = [e.model_dump(mode="json") for e in result.excluded_events] if result else []
    plan.limitations = list(dict.fromkeys((result.limitations if result else []) + [EXPLANATIONS[k] for k in unknowns]))


def stop_out(item):
    return RouteStopOut(id=item.id, route_plan_id=item.route_plan_id, event_id=item.event_id,
        order=item.stop_order, estimated_service_minutes=item.estimated_service_minutes, status=item.status)


def summary(plan, count=0):
    meta = metadata(plan)
    origin, state = meta.get("result_origin", "legacy_unknown"), meta.get("calculation_status", "unknown")
    limitations = list(plan.limitations)
    if not meta: limitations.append(EXPLANATIONS["legacy_unknown"])
    return ProposalSummary(id=plan.id, shift_id=plan.shift_id, status=plan.status,
        created_by=plan.created_by, created_at=plan.created_at, calculation_status=state,
        result_origin=origin, input_hash=meta.get("input_hash"),
        algorithm_version=None if state == "pending" else plan.algorithm_version,
        matrix_source=plan.matrix_source, distance_m=plan.distance_m,
        estimated_duration_seconds=plan.estimated_duration_seconds,
        stop_count=count, excluded_count=len(plan.excluded_events), limitations=limitations,
        unknowns=meta.get("unknowns", ["legacy_unknown"]))


def detail(db, plan):
    stops = list(db.scalars(select(RouteStop).where(RouteStop.route_plan_id == plan.id).order_by(RouteStop.stop_order)))
    return ProposalDetail(**summary(plan, len(stops)).model_dump(), input_snapshot=plan.input_snapshot,
        configuration=plan.configuration, geometry_geojson=plan.geometry_geojson,
        stops=[stop_out(s) for s in stops], excluded_events=plan.excluded_events)


def existing(db, proposal_id):
    plan = db.get(RoutePlan, proposal_id)
    if plan is None or plan.status != "propuesta":
        raise HTTPException(status_code=404, detail="Propuesta no encontrada")
    return plan


def append_stops(db, plan, result):
    if result:
        db.add_all([RouteStop(route_plan_id=plan.id, event_id=s.event_id, stop_order=s.order,
            estimated_service_minutes=s.estimated_service_minutes) for s in result.stops])


@router.post("", response_model=ProposalDetail, status_code=201)
def create(payload: RouteProposalCreate, db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    try:
        verify_actor(db, actor)
        lock_id(db, payload.proposal_id)
        request_hash = digest({"actor": str(actor.id), "request": payload.model_dump(mode="json")})
        stored = db.get(RoutePlan, payload.proposal_id)
        if stored:
            if metadata(stored).get("request_hash") != request_hash or stored.status != "propuesta":
                raise HTTPException(status_code=409, detail="proposal_id ya fue utilizado para otra petición")
            output = detail(db, stored); rollback(db); return output
        core, now = collect_input(db, actor, payload.shift_id, payload.event_ids, payload.configuration, payload.result)
        origin = "test_fixture" if payload.test_data else "municipal_unverified" if payload.result else "pending"
        plan = RoutePlan(id=payload.proposal_id, shift_id=payload.shift_id, created_by=actor.id,
            input_snapshot={"schema": "route-input-v1", "captured_at": now.isoformat(), "operational": core},
            configuration={"_d2": {"version": 1, "request_hash": request_hash}})
        result_values(plan, payload.result, origin, actor, core)
        db.add(plan); db.flush()
        append_stops(db, plan, payload.result); db.flush()
        output = detail(db, plan)
        db.commit()
        return output
    except HTTPException:
        rollback(db); raise
    except IntegrityError:
        rollback(db)
        raise HTTPException(status_code=409, detail="Conflicto al guardar propuesta y paradas") from None
    except (SQLAlchemyError, ValidationError, ValueError, TypeError):
        raise unavailable(db) from None


@router.get("", response_model=list[ProposalSummary])
def listing(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
            status: Literal["propuesta"] = "propuesta",
            shift_id: uuid.UUID | None = None, calculation_status: CalculationState | None = None,
            result_origin: Origin | None = None, db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    try:
        query = select(RoutePlan).where(RoutePlan.status == status)
        if shift_id: query = query.where(RoutePlan.shift_id == shift_id)
        if calculation_status:
            field = RoutePlan.configuration["_d2"]["calculation_status"].as_string()
            query = query.where(func.coalesce(field, "unknown") == calculation_status)
        if result_origin:
            field = RoutePlan.configuration["_d2"]["result_origin"].as_string()
            query = query.where(func.coalesce(field, "legacy_unknown") == result_origin)
        plans = list(db.scalars(query.order_by(RoutePlan.created_at.desc(), RoutePlan.id.desc()).offset(offset).limit(limit)))
        counts = dict(db.execute(select(RouteStop.route_plan_id, func.count()).where(
            RouteStop.route_plan_id.in_([p.id for p in plans])).group_by(RouteStop.route_plan_id)).all()) if plans else {}
        return [summary(p, counts.get(p.id, 0)) for p in plans]
    except (SQLAlchemyError, ValidationError, ValueError, TypeError):
        raise unavailable(db) from None


@router.get("/{proposal_id}", response_model=ProposalDetail)
def get_detail(proposal_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    try: return detail(db, existing(db, proposal_id))
    except (SQLAlchemyError, ValidationError, ValueError, TypeError): raise unavailable(db) from None


@router.get("/{proposal_id}/stops", response_model=list[RouteStopOut])
def get_stops(proposal_id: uuid.UUID, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
              db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    try:
        existing(db, proposal_id)
        return [stop_out(s) for s in db.scalars(select(RouteStop).where(RouteStop.route_plan_id == proposal_id)
                .order_by(RouteStop.stop_order).offset(offset).limit(limit))]
    except (SQLAlchemyError, ValidationError): raise unavailable(db) from None


@router.get("/{proposal_id}/excluded-events", response_model=list[ExcludedEvent])
def get_excluded(proposal_id: uuid.UUID, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    try: return [ExcludedEvent.model_validate(e) for e in existing(db, proposal_id).excluded_events[offset:offset+limit]]
    except (SQLAlchemyError, ValidationError, TypeError): raise unavailable(db) from None
