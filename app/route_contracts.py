"""Provisional planner integration contract; contains no optimization algorithm."""
import json
import uuid
from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, JsonValue, field_validator, model_validator

Origin = Literal["pending", "test_fixture", "municipal_unverified", "d3", "legacy_unknown"]
CalculationState = Literal["pending", "completed", "unknown"]
Nonnegative = Annotated[FiniteFloat, Field(strict=True, ge=0)]
Positive = Annotated[FiniteFloat, Field(strict=True, gt=0)]
Longitude = Annotated[FiniteFloat, Field(strict=True, ge=-180, le=180)]
Latitude = Annotated[FiniteFloat, Field(strict=True, ge=-90, le=90)]
VehicleKind = Literal["compactadora", "volquete", "camion_baranda", "otro"]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class RouteGeometry(StrictInput):
    type: Literal["LineString"]
    coordinates: list[tuple[Longitude, Latitude]] = Field(min_length=2, max_length=5000)


class PlannedStop(StrictInput):
    event_id: uuid.UUID
    order: int = Field(strict=True, ge=1)
    estimated_service_minutes: Positive | None = None


class ExcludedEvent(StrictInput):
    event_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=1000)


class VehicleRequirements(StrictInput):
    vehicle_types: list[VehicleKind] | None = Field(default=None, min_length=1, max_length=4)
    required_capacity_kg: Positive | None = None

    @field_validator("vehicle_types")
    @classmethod
    def unique_types(cls, value):
        if value and len(value) != len(set(value)):
            raise ValueError("No repitas tipos de vehículo")
        return value


class PlannerResult(StrictInput):
    algorithm_version: str = Field(min_length=1, max_length=120)
    matrix_source: str | None = Field(default=None, min_length=1, max_length=120)
    stops: list[PlannedStop] = Field(max_length=200)
    excluded_events: list[ExcludedEvent] = Field(default_factory=list, max_length=200)
    distance_m: Nonnegative | None = None
    estimated_duration_seconds: Nonnegative | None = None
    geometry_geojson: RouteGeometry | None = None
    limitations: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(default_factory=list, max_length=50)
    requirements: VehicleRequirements = Field(default_factory=VehicleRequirements)
    input_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def coherent_stops(self):
        if [s.order for s in self.stops] != list(range(1, len(self.stops)+1)):
            raise ValueError("El orden debe ser consecutivo desde 1 y coincidir con la lista")
        included = [s.event_id for s in self.stops]
        excluded = [s.event_id for s in self.excluded_events]
        if len(set(included+excluded)) != len(included+excluded):
            raise ValueError("No puede haber eventos repetidos ni incluidos y excluidos a la vez")
        if not self.stops and self.geometry_geojson is not None:
            raise ValueError("Una propuesta sin paradas no puede presentar geometría de recorrido")
        return self


class RouteProposalCreate(StrictInput):
    proposal_id: uuid.UUID
    shift_id: uuid.UUID
    event_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    configuration: dict[str, JsonValue] = Field(default_factory=dict)
    result: PlannerResult | None = None
    test_data: bool = Field(default=False, strict=True)

    @field_validator("configuration")
    @classmethod
    def finite_configuration(cls, value):
        try:
            encoded = json.dumps(value, allow_nan=False, ensure_ascii=False)
        except (ValueError, OverflowError):
            raise ValueError("La configuración debe ser JSON con números finitos") from None
        if len(encoded.encode("utf-8")) > 32768:
            raise ValueError("La configuración supera 32 KiB")
        return value

    @model_validator(mode="after")
    def coherent_events(self):
        if len(self.event_ids) != len(set(self.event_ids)):
            raise ValueError("No repitas eventos candidatos")
        if self.result:
            partition = {s.event_id for s in self.result.stops} | {e.event_id for e in self.result.excluded_events}
            if partition != set(self.event_ids):
                raise ValueError("Las paradas y exclusiones deben cubrir exactamente los eventos candidatos")
        elif self.test_data:
            raise ValueError("test_data requiere un resultado estructurado")
        return self


class RouteStopOut(BaseModel):
    id: uuid.UUID
    route_plan_id: uuid.UUID
    event_id: uuid.UUID
    order: int
    estimated_service_minutes: Positive | None
    status: str


class ProposalSummary(BaseModel):
    id: uuid.UUID
    shift_id: uuid.UUID
    status: Literal["propuesta"]
    created_by: uuid.UUID
    created_at: datetime
    calculation_status: CalculationState
    result_origin: Origin
    operational: Literal[False] = False
    input_hash: str | None
    algorithm_version: str | None
    matrix_source: str | None
    distance_m: Nonnegative | None
    estimated_duration_seconds: Nonnegative | None
    stop_count: int
    excluded_count: int
    limitations: list[str]
    unknowns: list[str]


class ProposalDetail(ProposalSummary):
    input_snapshot: dict[str, JsonValue]
    configuration: dict[str, JsonValue]
    geometry_geojson: RouteGeometry | None
    stops: list[RouteStopOut]
    excluded_events: list[ExcludedEvent]
