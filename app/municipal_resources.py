"""Resource additions over 001. No Auth directory or role mutation API."""
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator
from sqlalchemy import or_, select, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .db import get_db
from .models import Profile, ServiceSite, Shift
from .schemas import SiteOut
from .security import require_roles, Actor

logger = logging.getLogger(__name__)


class MunicipalRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError as exc:
                return JSONResponse(status_code=422, content={"detail": [
                    {"type": e["type"], "loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]})
            except SQLAlchemyError:
                logger.warning("Municipal operation unavailable; no database diagnostics retained")
                return JSONResponse(status_code=503, content={"detail": "Servicio temporalmente no disponible; consulta el resultado antes de reintentar"})
        return handler


class DriverOut(BaseModel):
    id: uuid.UUID
    role: Literal["chofer"]
    model_config = ConfigDict(from_attributes=True)


class SitePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    site_type: Literal["salida", "descarga", "ambos"] | None = None
    latitude: FiniteFloat | None = Field(default=None, ge=-90, le=90)
    longitude: FiniteFloat | None = Field(default=None, ge=-180, le=180)
    active: bool | None = Field(default=None, strict=True)

    @model_validator(mode="before")
    @classmethod
    def valid_patch(cls, values):
        if not isinstance(values, dict) or not values or any(value is None for value in values.values()):
            raise ValueError("Envía al menos un campo, sin valores nulos")
        if ("latitude" in values) != ("longitude" in values):
            raise ValueError("Las coordenadas se corrigen juntas")
        return values


municipal = require_roles("encargado_municipal")
router = APIRouter(prefix="/municipal", tags=["Gestión de recursos"], route_class=MunicipalRoute)


@router.get("/drivers", response_model=list[DriverOut])
def drivers(limit: int = Query(200, ge=1, le=200), offset: int = Query(0, ge=0),
            db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    return db.scalars(select(Profile).where(Profile.role == "chofer").order_by(Profile.id).offset(offset).limit(limit)).all()


@router.patch("/sites/{site_id}", response_model=SiteOut)
def edit_site(site_id: uuid.UUID, payload: SitePatch, db: Session = Depends(get_db), actor: Actor = Depends(municipal)):
    site = db.scalar(select(ServiceSite).where(ServiceSite.id == site_id).with_for_update())
    if site is None:
        raise HTTPException(status_code=404, detail="Sitio no encontrado")
    changes = payload.model_dump(exclude_unset=True)
    relevant = any(k in changes and getattr(site, k) != changes[k] for k in ("active", "site_type", "latitude", "longitude"))
    # create_shift locks this site before insertion: a concurrent reservation
    # either observes the new state or commits before this check can proceed.
    if relevant and db.scalar(select(Shift.id).where(Shift.status == "programado", Shift.ends_at > func.now(),
            or_(Shift.departure_site_id == site_id, Shift.disposal_site_id == site_id)).limit(1)):
        raise HTTPException(status_code=409, detail="El sitio participa en un turno programado; conserva su ubicación, uso y disponibilidad")
    for key, value in changes.items():
        setattr(site, key, value)
    db.flush()
    result = SiteOut.model_validate(site)
    db.commit()
    return result
