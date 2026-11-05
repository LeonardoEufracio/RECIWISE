import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, JsonValue, field_validator, model_validator


class ORMOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ActorOut(BaseModel):
    id: uuid.UUID
    role: Literal["ciudadano", "encargado_municipal", "chofer"]


class ReportCreate(BaseModel):
    description: str = Field(min_length=3, max_length=2000)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    observed_at: datetime
    waste_type: str | None = Field(default=None, max_length=80)

    # Recortar antes de aplicar min_length/max_length del campo.
    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("La descripción no puede estar vacía")
        return v

    @field_validator("observed_at")
    @classmethod
    def valid_date(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("La fecha debe incluir zona horaria")
        if v > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("La observación no puede estar en el futuro")
        return v


class ReportOut(ORMOut):
    id: uuid.UUID
    citizen_id: uuid.UUID
    description: str
    latitude: float
    longitude: float
    observed_at: datetime
    created_at: datetime
    waste_type: str | None
    status: str


class PhotoOut(ORMOut):
    id: uuid.UUID
    report_id: uuid.UUID
    content_type: str
    size_bytes: int
    created_at: datetime
    signed_url: str | None = None


class VehicleCreate(BaseModel):
    label: str = Field(min_length=2, max_length=100)
    vehicle_type: Literal["compactadora", "volquete", "camion_baranda", "otro"]
    plate: str | None = Field(default=None, max_length=20)
    capacity_kg: float | None = Field(default=None, gt=0)
    available: bool = False


class VehicleOut(ORMOut):
    id: uuid.UUID
    label: str
    vehicle_type: str
    plate: str | None
    capacity_kg: float | None
    available: bool


class AvailabilityPatch(BaseModel):
    available: bool


class SiteCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    site_type: Literal["salida", "descarga", "ambos"]
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class SiteOut(ORMOut):
    id: uuid.UUID
    name: str
    site_type: str
    latitude: float
    longitude: float
    active: bool


class ShiftCreate(BaseModel):
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID
    departure_site_id: uuid.UUID
    disposal_site_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def check_time(self):
        if (self.starts_at.tzinfo is None or self.starts_at.utcoffset() is None
                or self.ends_at.tzinfo is None or self.ends_at.utcoffset() is None):
            raise ValueError("Las fechas del turno requieren zona horaria")
        if self.ends_at <= self.starts_at:
            raise ValueError("El fin del turno debe ser posterior al inicio")
        return self


class ShiftOut(ORMOut):
    id: uuid.UUID
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID
    departure_site_id: uuid.UUID
    disposal_site_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    status: str
    created_by: uuid.UUID


EventState = Literal["en_revision", "abierto", "programado", "atendido", "cerrado", "descartado"]


class EventCreate(BaseModel):
    # State, closure and priority are deliberately server-owned in this increment.
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    intervention_type: str | None = Field(default=None, min_length=1, max_length=120)
    report_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)

    @field_validator("intervention_type", mode="before")
    @classmethod
    def trim_intervention(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("report_ids")
    @classmethod
    def unique_reports(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Los identificadores de reportes no pueden repetirse")
        return value


class EventPriorityOut(BaseModel):
    score: FiniteFloat | None
    # Preserve stored JSON; D3 has not agreed on a list of label/value factors.
    factors: JsonValue
    version: str | None


class EventOut(BaseModel):
    id: uuid.UUID
    latitude: float
    longitude: float
    state: EventState
    intervention_type: str | None
    priority: EventPriorityOut | None
    restrictions: None = None  # No column or verified operational restrictions yet.
    report_ids: list[uuid.UUID]
    report_count: int
    created_at: datetime
    closed_at: datetime | None
