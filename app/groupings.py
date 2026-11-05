"""Municipal grouping commands, snapshots and append-only audit over 001 tables."""
from datetime import timedelta
import hashlib
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import or_, select, text, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .db import get_db
from .events import EventRoute, municipal, rollback, serialize_events
from .grouping_contracts import (DecisionKind, DecisionResult, EventBrief, GroupingDecisionCreate,
    GroupingDecisionOut, GroupingOut, ManualCandidatesOut)
from .models import Event, EventReport, GroupingDecision, Report
from .schemas import ReportOut
from .security import Actor

router = APIRouter(prefix="/municipal/groupings", tags=["Agrupaciones municipales"], route_class=EventRoute)
logger = logging.getLogger(__name__)
EDITABLE_STATES = {"en_revision", "abierto"}


def unavailable(db, write=False):
    rollback(db)
    logger.warning("Grouping unavailable: %s", "write_unconfirmed" if write else "read")
    return HTTPException(status_code=503, detail=(
        "No se pudo confirmar la decisión; consulta su operation_id antes de reintentar"
        if write else "No se pudieron consultar las agrupaciones temporalmente"))


def latest_query():
    return (select(GroupingDecision).where(GroupingDecision.report_id == Report.id)
            .order_by(GroupingDecision.decided_at.desc(), GroupingDecision.id.desc())
            .limit(1).correlate(Report))


def relation_query():
    latest_id = latest_query().with_only_columns(GroupingDecision.id).scalar_subquery()
    latest_kind = latest_query().with_only_columns(GroupingDecision.decision).scalar_subquery()
    return (select(Report, EventReport, Event, latest_id.label("last_decision_id"), latest_kind.label("last_kind")).select_from(Report)
            .outerjoin(EventReport, EventReport.report_id == Report.id)
            .outerjoin(Event, Event.id == EventReport.event_id))


def relation_out(row):
    report, link, event, revision, kind = row
    return GroupingOut(report=ReportOut.model_validate(report),
        event_id=link.event_id if link else None, event=EventBrief.model_validate(event) if event else None,
        last_decision_id=revision, pending_review=kind == "revisar",
        linked_at=link.linked_at if link else None, linked_by=link.linked_by if link else None,
        linkage_method=link.linkage_method if link else None, config_version=link.config_version if link else None)


def relation(db, report_id):
    row = db.execute(relation_query().where(Report.id == report_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    return relation_out(row)


def decision_out(item):
    factors = item.factors
    meta = factors.get("_d2", {}) if isinstance(factors, dict) else {}
    known = isinstance(meta, dict) and meta.get("version") == 1
    return GroupingDecisionOut(id=item.id, report_id=item.report_id,
        candidate_event_id=item.candidate_event_id, resulting_event_id=item.resulting_event_id,
        previous_event_id=meta.get("previous_event_id") if known else None,
        previous_event_known=known, operation=meta.get("operation") if known else None,
        decision=item.decision, factors=factors, config_version=item.config_version,
        decided_by=item.decided_by, decided_at=item.decided_at, notes=item.notes)


@router.get("", response_model=list[GroupingOut])
def list_groupings(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                   event_id: uuid.UUID | None = None, linked: bool | None = None,
                   pending_review: bool | None = None, db: Session = Depends(get_db),
                   actor: Actor = Depends(municipal)):
    try:
        query = relation_query()
        if event_id is not None:
            query = query.where(EventReport.event_id == event_id)
        if linked is not None:
            query = query.where(EventReport.event_id.is_not(None) if linked else EventReport.event_id.is_(None))
        if pending_review is not None:
            last_kind = latest_query().with_only_columns(GroupingDecision.decision).scalar_subquery()
            query = query.where(last_kind == "revisar" if pending_review else or_(last_kind.is_(None), last_kind != "revisar"))
        return [relation_out(row) for row in db.execute(query.order_by(Report.created_at.desc(), Report.id.desc()).offset(offset).limit(limit))]
    except (SQLAlchemyError, ValidationError):
        raise unavailable(db) from None


@router.get("/reports/{report_id}", response_model=GroupingOut)
def grouping_detail(report_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    try:
        return relation(db, report_id)
    except (SQLAlchemyError, ValidationError):
        raise unavailable(db) from None


@router.get("/candidates", response_model=ManualCandidatesOut)
def candidates(report_id: uuid.UUID, limit: int = Query(50, ge=1, le=200),
               offset: int = Query(0, ge=0), db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    try:
        current = relation(db, report_id)
        query = select(Event).where(Event.state.in_(EDITABLE_STATES), Event.closed_at.is_(None))
        if current.event_id:
            query = query.where(Event.id != current.event_id)
        values = db.scalars(query.order_by(Event.created_at.desc(), Event.id.desc()).offset(offset).limit(limit)).all()
        return ManualCandidatesOut(report_id=report_id, event_id=current.event_id,
            last_decision_id=current.last_decision_id, candidates=serialize_events(db, list(values)))
    except (SQLAlchemyError, ValidationError):
        raise unavailable(db) from None


@router.get("/decisions", response_model=list[GroupingDecisionOut])
def history(report_id: uuid.UUID | None = None, event_id: uuid.UUID | None = None,
            decision: DecisionKind | None = None, limit: int = Query(50, ge=1, le=200),
            offset: int = Query(0, ge=0), db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    try:
        query = select(GroupingDecision)
        if report_id:
            query = query.where(GroupingDecision.report_id == report_id)
        if event_id:
            query = query.where(or_(GroupingDecision.candidate_event_id == event_id,
                GroupingDecision.resulting_event_id == event_id,
                GroupingDecision.factors["_d2"]["previous_event_id"].as_string() == str(event_id)))
        if decision:
            query = query.where(GroupingDecision.decision == decision)
        return [decision_out(item) for item in db.scalars(query.order_by(
            GroupingDecision.decided_at.desc(), GroupingDecision.id.desc()).offset(offset).limit(limit))]
    except (SQLAlchemyError, ValidationError):
        raise unavailable(db) from None


@router.get("/decisions/{decision_id}", response_model=GroupingDecisionOut)
def decision_detail(decision_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    try:
        item = db.get(GroupingDecision, decision_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Decisión no encontrada")
        return decision_out(item)
    except (SQLAlchemyError, ValidationError):
        raise unavailable(db) from None


def request_hash(payload, actor):
    value = {"actor": str(actor.id), "command": payload.model_dump(mode="json")}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@router.post("/decisions", response_model=DecisionResult, status_code=200)
def decide(payload: GroupingDecisionCreate, db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    try:
        db.execute(text("SET LOCAL lock_timeout='3s'"))
        db.execute(text("SET LOCAL statement_timeout='15s'"))
        report = db.scalar(select(Report).where(Report.id == payload.report_id).with_for_update())
        if report is None:
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
        fingerprint = request_hash(payload, actor)
        replay = db.get(GroupingDecision, payload.operation_id)
        if replay is not None:
            meta = replay.factors.get("_d2", {}) if isinstance(replay.factors, dict) else {}
            if meta.get("request_hash") != fingerprint:
                raise HTTPException(status_code=409, detail="operation_id ya fue utilizado para otra petición")
            result = DecisionResult(decision=decision_out(replay), relation=relation(db, payload.report_id), replayed=True)
            rollback(db)  # Release read/row locks without a second commit.
            return result
        link = db.get(EventReport, report.id)
        current_id = link.event_id if link else None
        last = db.scalar(select(GroupingDecision).where(GroupingDecision.report_id == report.id)
                         .order_by(GroupingDecision.decided_at.desc(), GroupingDecision.id.desc()).limit(1))
        if (current_id != payload.expected_event_id
                or (last.id if last else None) != payload.expected_decision_id):
            raise HTTPException(status_code=409, detail="La relación o su revisión cambiaron; actualiza antes de decidir")
        ids = sorted({v for v in (current_id, payload.candidate_event_id) if v is not None})
        locked = {item.id: item for item in db.scalars(select(Event).where(Event.id.in_(ids))
                    .order_by(Event.id).with_for_update())} if ids else {}
        if len(locked) != len(ids):
            raise HTTPException(status_code=404, detail="Evento no encontrado")
        target = locked.get(payload.candidate_event_id)
        source = locked.get(current_id)
        changing = payload.decision in {"agrupar", "separar"}
        if changing and source and (source.state not in EDITABLE_STATES or source.closed_at is not None):
            raise HTTPException(status_code=409, detail="La asociación de origen pertenece a un evento no editable")
        if payload.decision == "agrupar":
            if target.state not in EDITABLE_STATES or target.closed_at is not None:
                raise HTTPException(status_code=409, detail="El evento candidato no admite agrupaciones")
            if current_id == target.id:
                raise HTTPException(status_code=409, detail="El reporte ya pertenece al evento candidato")
            operation = "reassign" if link else "confirm"
        elif payload.decision == "separar":
            if not link:
                raise HTTPException(status_code=409, detail="El reporte ya está separado")
            operation = "separate"
        elif payload.decision == "mantener_separado":
            if current_id == payload.candidate_event_id:
                raise HTTPException(status_code=409, detail="Separa explícitamente la asociación antes de mantenerla separada")
            operation = "keep_separate"
        else:
            operation = "review"
        timestamp = db.scalar(select(func.clock_timestamp()))
        if last:
            timestamp = max(timestamp, last.decided_at + timedelta(microseconds=1))
        factors = {"municipal": payload.factors,
            "suggestion": payload.suggestion.model_dump(mode="json") if payload.suggestion else None,
            "_d2": {"version": 1, "operation": operation,
                "suggestion_source": "municipal_input_unverified" if payload.suggestion else None,
                "previous_event_id": str(current_id) if current_id else None,
                "expected_decision_id": str(payload.expected_decision_id) if payload.expected_decision_id else None,
                "request_hash": fingerprint}}
        resulting_id = current_id
        if payload.decision == "agrupar":
            resulting_id = target.id
            if link is None:
                link = EventReport(report_id=report.id, event_id=target.id)
                db.add(link)
            link.event_id = target.id
            link.linked_by = actor.id
            link.linked_at = timestamp
            link.linkage_method = "manual"
            link.factors = factors
            link.config_version = payload.config_version
        elif payload.decision == "separar":
            db.delete(link)  # Only the relationship. Never delete a report/event.
            resulting_id = None
        item = GroupingDecision(id=payload.operation_id, report_id=report.id,
            candidate_event_id=payload.candidate_event_id if target else current_id,
            resulting_event_id=resulting_id, decision=payload.decision, factors=factors,
            config_version=payload.config_version, decided_by=actor.id, decided_at=timestamp, notes=payload.notes)
        db.add(item)
        db.flush()
        result = DecisionResult(decision=decision_out(item), relation=relation(db, report.id), replayed=False)
        db.commit()
        return result
    except HTTPException:
        rollback(db)
        raise
    except IntegrityError:
        rollback(db)
        raise HTTPException(status_code=409, detail="Conflicto concurrente al guardar la decisión; actualiza la relación") from None
    except (SQLAlchemyError, ValidationError):
        raise unavailable(db, write=True) from None
