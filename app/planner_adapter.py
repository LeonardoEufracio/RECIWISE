"""Internal trusted boundary. No public route, D3 import, scheduler or optimizer."""
import uuid
from typing import Literal
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .models import RoutePlan
from .route_contracts import PlannerResult
from .route_proposals import (append_stops, collect_input, detail, digest, existing, lock_id,
                              metadata, result_values, rollback, unavailable, verify_actor)


def register_planner_result(db, actor, proposal_id: uuid.UUID, result: PlannerResult | dict, *,
                            origin: Literal["test_fixture", "d3"], provider_reference: str):
    """Call in a worker/thread with validated municipal context, never client-selected origin.

    The future D3 connector must authenticate its provider before choosing origin='d3'.
    No such provider/HTTP integration is activated by this module.
    """
    try:
        proposal_id = uuid.UUID(str(proposal_id))
        result = PlannerResult.model_validate(result)
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Resultado estructurado o identificador no válido") from None
    try:
        if not isinstance(provider_reference, str):
            raise HTTPException(status_code=422, detail="Procedencia interna no válida")
        provider_reference = provider_reference.strip()
        if origin not in {"test_fixture", "d3"} or not provider_reference.strip() or len(provider_reference) > 120:
            raise HTTPException(status_code=422, detail="Procedencia interna no válida")
        if result.input_hash is None:
            raise HTTPException(status_code=422, detail="El resultado interno requiere input_hash")
        verify_actor(db, actor)
        lock_id(db, proposal_id)
        plan = existing(db, proposal_id)
        meta = metadata(plan)
        signature = digest({"result": result.model_dump(mode="json"), "origin": origin,
                            "provider": provider_reference, "actor": str(actor.id)})
        if meta.get("calculation_status") != "pending":
            if meta.get("result_hash") == signature:
                output = detail(db, plan); rollback(db); return output
            raise HTTPException(status_code=409, detail="La propuesta ya contiene un resultado; registra una alternativa")
        if result.input_hash != meta.get("input_hash"):
            raise HTTPException(status_code=409, detail="El resultado no corresponde al snapshot de la propuesta")
        core = plan.input_snapshot["operational"]
        # Recheck actual operational data without attributing a new input to an old calculation.
        from .security import Actor
        owner = Actor(plan.created_by, "encargado_municipal")
        fresh, _ = collect_input(db, owner, plan.shift_id,
            [uuid.UUID(eid) for eid in core["event_ids"]], core["parameters"], result)
        if digest(fresh) != result.input_hash:
            raise HTTPException(status_code=409, detail="Los datos operativos cambiaron; solicita una propuesta nueva")
        result_values(plan, result, origin, actor, fresh, provider_reference.strip())
        append_stops(db, plan, result); db.flush()
        output = detail(db, plan)
        db.commit()
        return output
    except HTTPException:
        rollback(db); raise
    except IntegrityError:
        rollback(db)
        raise HTTPException(status_code=409, detail="Conflicto al registrar el resultado del planificador") from None
    except (SQLAlchemyError, ValidationError, ValueError, KeyError, TypeError):
        raise unavailable(db) from None
