"""D2 integration DTOs, not D3 algorithms. The suggestion contract is provisional."""
import json
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, JsonValue, field_validator, model_validator

from .schemas import EventOut, EventState, ReportOut

DecisionKind = Literal["agrupar", "separar", "mantener_separado", "revisar"]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class D3Suggestion(StrictInput):
    """Proposed cosine DTO; must still be reviewed with D3. Never an authorization."""
    reporte_nuevo_id: uuid.UUID
    evento_candidato_id: uuid.UUID
    similitud_texto: FiniteFloat | None = Field(ge=-1, le=1)
    distancia_metros: FiniteFloat | None = Field(ge=0)
    diferencia_horas: FiniteFloat | None = Field(ge=0)
    sugerencia: Literal["agrupar_candidato", "requiere_revision", "mantener_separado"]
    motivos: list[str] = Field(min_length=1, max_length=20)
    version_configuracion: str = Field(min_length=1, max_length=120)

    @field_validator("version_configuracion", mode="before")
    @classmethod
    def trim_version(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("motivos")
    @classmethod
    def reasons(cls, values):
        values = [value.strip() for value in values]
        if any(not value or len(value) > 1000 for value in values):
            raise ValueError("Cada motivo debe tener entre 1 y 1000 caracteres")
        return values


class GroupingDecisionCreate(StrictInput):
    operation_id: uuid.UUID
    report_id: uuid.UUID
    decision: DecisionKind
    candidate_event_id: uuid.UUID | None = None
    # Required even when null: omission must never become an unconditional write.
    expected_event_id: uuid.UUID | None
    expected_decision_id: uuid.UUID | None
    notes: str | None = Field(default=None, max_length=2000)
    factors: dict[str, JsonValue] = Field(default_factory=dict)
    config_version: str | None = Field(default=None, min_length=1, max_length=120)
    suggestion: D3Suggestion | None = None

    @field_validator("notes", "config_version", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("factors")
    @classmethod
    def bounded_finite_json(cls, value):
        try:
            encoded = json.dumps(value, allow_nan=False, ensure_ascii=False)
        except (ValueError, OverflowError):
            raise ValueError("Los factores deben ser JSON con números finitos") from None
        if len(encoded.encode("utf-8")) > 32768:
            raise ValueError("Los factores superan 32 KiB")
        return value

    @model_validator(mode="after")
    def compatible_fields(self):
        if self.decision == "separar":
            if self.candidate_event_id is not None or self.expected_event_id is None or self.suggestion is not None:
                raise ValueError("Separar requiere la asociación esperada y no admite candidato ni sugerencia")
        elif self.candidate_event_id is None:
            raise ValueError("Esta decisión requiere un evento candidato")
        if self.suggestion:
            if (self.suggestion.reporte_nuevo_id != self.report_id
                    or self.suggestion.evento_candidato_id != self.candidate_event_id):
                raise ValueError("La sugerencia debe corresponder al reporte y candidato")
            if self.config_version and self.config_version != self.suggestion.version_configuracion:
                raise ValueError("La versión debe coincidir con la sugerencia")
            self.config_version = self.suggestion.version_configuracion
        return self


class EventBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    latitude: float
    longitude: float
    state: EventState
    intervention_type: str | None
    closed_at: datetime | None


class GroupingOut(BaseModel):
    report: ReportOut
    event_id: uuid.UUID | None
    event: EventBrief | None
    last_decision_id: uuid.UUID | None
    pending_review: bool
    linked_at: datetime | None
    linked_by: uuid.UUID | None
    linkage_method: str | None
    config_version: str | None


class GroupingDecisionOut(BaseModel):
    id: uuid.UUID
    report_id: uuid.UUID
    candidate_event_id: uuid.UUID | None
    resulting_event_id: uuid.UUID | None
    previous_event_id: uuid.UUID | None
    previous_event_known: bool
    operation: str | None
    decision: DecisionKind
    factors: JsonValue
    config_version: str | None
    decided_by: uuid.UUID | None
    decided_at: datetime
    notes: str | None


class DecisionResult(BaseModel):
    decision: GroupingDecisionOut
    relation: GroupingOut
    replayed: bool


class ManualCandidatesOut(BaseModel):
    report_id: uuid.UUID
    event_id: uuid.UUID | None
    last_decision_id: uuid.UUID | None
    source: Literal["manual"] = "manual"
    d3_available: Literal[False] = False
    candidates: list[EventOut]
