"""Municipal events over existing 001 tables. No automatic grouping or D3 calls."""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .db import get_db
from .models import Event, EventReport, GroupingDecision, Report
from .schemas import EventCreate, EventOut, EventPriorityOut, EventState, ReportOut
from .security import Actor, require_roles

logger = logging.getLogger(__name__)


class EventRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError as exc:
                # Echoing nonfinite "input" values turns a validation 422 into a
                # JSON serialization 500. Return only safe standard error fields.
                return JSONResponse(status_code=422, content={"detail": [
                    {"type": issue["type"], "loc": issue["loc"], "msg": issue["msg"]}
                    for issue in exc.errors()
                ]})
            except SQLAlchemyError:
                # Also cover a database outage during profile/role resolution,
                # before the endpoint's own transaction handler is entered.
                logger.warning("Event operation unavailable: dependency")
                return JSONResponse(status_code=503, content={"detail":
                    "Servicio de eventos no disponible; consulta el resultado antes de reintentar"})
        return handler


router = APIRouter(prefix="/municipal/events", tags=["Eventos municipales"], route_class=EventRoute)
municipal = require_roles("encargado_municipal")


def rollback(db: Session):
    try:
        db.rollback()
    except SQLAlchemyError:
        pass


def unavailable(db: Session, *, write=False):
    # No exception/SQL/DSN is logged or returned, even if rollback also fails.
    rollback(db)
    logger.warning("Event operation unavailable: %s", "write_unconfirmed" if write else "read")
    detail = ("No se pudo confirmar el evento; consulta los eventos antes de reintentar"
              if write else "No se pudieron consultar los eventos temporalmente")
    return HTTPException(status_code=503, detail=detail)


def serialize_events(db: Session, events: list[Event]) -> list[EventOut]:
    links: dict[uuid.UUID, list[uuid.UUID]] = {item.id: [] for item in events}
    if links:
        for event_id, report_id in db.execute(select(EventReport.event_id, EventReport.report_id)
                .where(EventReport.event_id.in_(links)).order_by(EventReport.report_id)):
            links[event_id].append(report_id)
    result = []
    for item in events:
        priority = None
        if any(v is not None for v in (item.priority_score, item.priority_factors, item.priority_config_version)):
            priority = EventPriorityOut(score=item.priority_score, factors=item.priority_factors,
                                        version=item.priority_config_version)
        result.append(EventOut(id=item.id, latitude=item.latitude, longitude=item.longitude,
            state=item.state, intervention_type=item.intervention_type, priority=priority,
            report_ids=links[item.id], report_count=len(links[item.id]),
            created_at=item.created_at, closed_at=item.closed_at))
    return result


def existing_event(db: Session, event_id: uuid.UUID):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    return event


@router.get("", response_model=list[EventOut])
def list_events(state: EventState | None = None, limit: int = Query(50, ge=1, le=200),
                offset: int = Query(0, ge=0), db: Session = Depends(get_db),
                actor: Actor = Depends(municipal)):
    try:
        query = select(Event)
        if state is not None:
            query = query.where(Event.state == state)
        events = db.scalars(query.order_by(Event.created_at.desc(), Event.id.desc()).offset(offset).limit(limit)).all()
        return serialize_events(db, list(events))
    except (SQLAlchemyError, ValidationError):
        raise unavailable(db) from None


@router.get("/{event_id}", response_model=EventOut)
def event_detail(event_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    try:
        return serialize_events(db, [existing_event(db, event_id)])[0]
    except (SQLAlchemyError, ValidationError):
        raise unavailable(db) from None


@router.get("/{event_id}/reports", response_model=list[ReportOut])
def event_reports(event_id: uuid.UUID, limit: int = Query(50, ge=1, le=200),
                  offset: int = Query(0, ge=0), db: Session = Depends(get_db),
                  actor: Actor = Depends(municipal)):
    try:
        existing_event(db, event_id)
        reports = db.scalars(select(Report).join(EventReport, EventReport.report_id == Report.id)
            .where(EventReport.event_id == event_id)
            .order_by(Report.created_at.desc(), Report.id.desc()).offset(offset).limit(limit)).all()
        return [ReportOut.model_validate(report) for report in reports]
    except (SQLAlchemyError, ValidationError):
        raise unavailable(db) from None


@router.post("", response_model=EventOut, status_code=201)
def create_event(payload: EventCreate, db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    try:
        # Sort row locks to avoid conflicting lock orders. The PK on event_reports
        # remains the final PostgreSQL protection against concurrent association.
        ids = sorted(payload.report_ids)
        if ids:
            found = db.scalars(select(Report.id).where(Report.id.in_(ids))
                               .order_by(Report.id).with_for_update()).all()
            if len(found) != len(ids):
                raise HTTPException(status_code=404, detail="Uno o más reportes no existen")
            if db.scalar(select(EventReport.report_id).where(EventReport.report_id.in_(ids)).limit(1)):
                raise HTTPException(status_code=409, detail="Un reporte ya está asociado a un evento; requiere revisión municipal")
            if db.scalar(select(GroupingDecision.id).where(GroupingDecision.report_id.in_(ids)).limit(1)):
                raise HTTPException(status_code=409, detail="El reporte tiene historial; usa la revisión municipal con estado esperado")
        item = Event(latitude=payload.latitude, longitude=payload.longitude, intervention_type=payload.intervention_type)
        db.add(item)
        db.flush()
        for report_id in ids:
            db.add(EventReport(report_id=report_id, event_id=item.id, linked_by=actor.id,
                               linkage_method="manual"))
            db.add(GroupingDecision(report_id=report_id, resulting_event_id=item.id,
                decision="agrupar", decided_by=actor.id, factors={},
                notes="Asociación manual durante la creación municipal del evento"))
        db.flush()
        # Materialize before commit; never retry a commit whose result is unknown.
        result = serialize_events(db, [item])[0]
        db.commit()
        return result
    except HTTPException:
        rollback(db)
        raise
    except IntegrityError:
        rollback(db)
        raise HTTPException(status_code=409, detail="Conflicto al asociar los reportes; actualiza la información") from None
    except (SQLAlchemyError, ValidationError):
        raise unavailable(db, write=True) from None
