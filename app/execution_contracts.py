"""D2 execution API, separate from and without changes to the D3 contracts."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, FiniteFloat, model_validator

RouteStatus = Literal["propuesta", "aprobada", "en_ejecucion", "finalizada", "cancelada"]
StopStatus = Literal["pendiente", "atendida", "incidencia", "no_atendida"]


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    operation_id: uuid.UUID
    expected_status: RouteStatus
    expected_revision: uuid.UUID | None  # required, including an explicit null
    notes: str | None = Field(default=None, min_length=3, max_length=2000)


class MunicipalDecision(Command):
    decision: Literal["approve", "reject", "cancel"]


class DriverAction(Command):
    action: Literal["start", "finish"]


class StopAction(Command):
    action: Literal["attend", "incident", "not_attended"]
    incident_type: str | None = Field(default=None, min_length=2, max_length=80)

    @model_validator(mode="after")
    def details(self):
        if self.action != "attend" and self.notes is None:
            raise ValueError("Indica el motivo de la incidencia o de la no atención")
        if self.action == "incident" and self.incident_type is None:
            raise ValueError("Indica el tipo de incidencia")
        if self.action != "incident" and self.incident_type is not None:
            raise ValueError("El tipo solo corresponde a una incidencia")
        return self


class AuditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: uuid.UUID
    actor_id: uuid.UUID
    action: Literal["approve", "reject", "cancel", "start", "finish", "attend", "incident", "not_attended"]
    at: AwareDatetime
    previous_status: RouteStatus
    resulting_status: RouteStatus
    stop_id: uuid.UUID | None = None
    notes: str | None
    request_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ApprovalReceipt(BaseModel):
    """Reserved server namespace. No endpoint in this release issues receipts.

    A future independently reviewed provider verifier must issue and bind this
    receipt. An origin flag, public parameters or imported legacy approval do
    not authorize execution. Tests may seed receipts ONLY in disposable PG.
    """
    model_config = ConfigDict(extra="forbid")
    authority: Literal["verified-provider-v1"]
    approval_id: uuid.UUID
    approved_by: uuid.UUID
    approved_at: AwareDatetime
    shift_id: uuid.UUID
    driver_id: uuid.UUID
    vehicle_id: uuid.UUID
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    result_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    stop_manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_reference: str = Field(min_length=1, max_length=120)


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    stop_id: uuid.UUID
    reported_by: uuid.UUID
    incident_type: str
    description: str | None
    created_at: datetime


class ExecutionStop(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    order: int
    latitude: FiniteFloat | None
    longitude: FiniteFloat | None
    status: StopStatus
    estimated_service_minutes: float | None
    visited_at: datetime | None
    recorded_by: uuid.UUID | None
    incidents: list[IncidentOut]


class ExecutionSummary(BaseModel):
    id: uuid.UUID
    shift_id: uuid.UUID
    driver_id: uuid.UUID
    vehicle_id: uuid.UUID
    vehicle_label: str
    starts_at: datetime
    ends_at: datetime
    status: RouteStatus
    created_at: datetime
    revision: uuid.UUID | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    approval_verified: bool
    can_approve: Literal[False] = False
    approval_blockers: list[str]


class ExecutionDetail(ExecutionSummary):
    shift_status: str
    vehicle_available: bool
    departure: dict
    disposal: dict
    stops: list[ExecutionStop]
    history: list[AuditEntry]
    distance_m: float | None
    estimated_duration_seconds: float | None
    geometry_geojson: dict | None
    limitations: list[str]
    excluded_events: list[dict]


class OperationResult(BaseModel):
    operation: AuditEntry
    route: ExecutionDetail
    replayed: bool
