import uuid
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, JSON, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid
from .db import Base


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="ciudadano")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    citizen_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    waste_type: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="recibido")


class ReportPhoto(Base):
    __tablename__ = "report_photos"
    __table_args__ = (
        CheckConstraint("slot BETWEEN 1 AND 3", name="report_photos_slot_valid"),
        UniqueConstraint("report_id", "slot", name="report_photos_report_slot_key"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("reports.id"), nullable=False)
    slot: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(30), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PhotoUploadOperation(Base):
    __tablename__ = "photo_upload_operations"
    __table_args__ = (
        CheckConstraint("state IN ('pending','complete','cleanup_pending','quarantined','cleaned','rejected','review')"),
        CheckConstraint("attempts >= 0"),
        CheckConstraint("extension IN ('jpg','png','webp')"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    report_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("reports.id"), nullable=False)
    bucket: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    extension: Mapped[str] = mapped_column(String(4), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    vehicle_type: Mapped[str] = mapped_column(String(50), nullable=False)
    plate: Mapped[str | None] = mapped_column(String(20))
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    capacity_kg: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ServiceSite(Base):
    __tablename__ = "service_sites"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    site_type: Mapped[str] = mapped_column(String(30), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class Shift(Base):
    __tablename__ = "shifts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("vehicles.id"), nullable=False)
    driver_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    departure_site_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("service_sites.id"), nullable=False)
    disposal_site_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("service_sites.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="programado")
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Existing structures from 001. These mappings do not create or migrate tables.
class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90"),
        CheckConstraint("longitude BETWEEN -180 AND 180"),
        CheckConstraint("state IN ('en_revision','abierto','programado','atendido','cerrado','descartado')"),
        CheckConstraint("state <> 'cerrado' OR closed_at IS NOT NULL", name="events_closed_timestamp"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="en_revision")
    intervention_type: Mapped[str | None] = mapped_column(Text)
    priority_score: Mapped[float | None] = mapped_column(Float)
    priority_factors: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    priority_config_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EventReport(Base):
    __tablename__ = "event_reports"
    report_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("events.id"), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    linked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"))
    linkage_method: Mapped[str] = mapped_column(Text, nullable=False)
    factors: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    config_version: Mapped[str | None] = mapped_column(Text)


class GroupingDecision(Base):
    __tablename__ = "grouping_decisions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("reports.id"), nullable=False)
    candidate_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("events.id"))
    resulting_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("events.id"))
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    factors: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    config_version: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[str | None] = mapped_column(Text)


class RoutePlan(Base):
    __tablename__ = "route_plans"
    __table_args__ = (
        CheckConstraint("status IN ('propuesta','aprobada','en_ejecucion','finalizada','cancelada')"),
        CheckConstraint("distance_m >= 0"),
        CheckConstraint("estimated_duration_seconds >= 0"),
        CheckConstraint("(approved_by IS NULL AND approved_at IS NULL) OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shift_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("shifts.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="propuesta")
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    algorithm_version: Mapped[str] = mapped_column(Text, nullable=False)
    matrix_source: Mapped[str | None] = mapped_column(Text)
    input_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False)
    distance_m: Mapped[float | None] = mapped_column(Float)
    estimated_duration_seconds: Mapped[float | None] = mapped_column(Float)
    geometry_geojson: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    excluded_events: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    limitations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class RouteStop(Base):
    __tablename__ = "route_stops"
    __table_args__ = (
        UniqueConstraint("route_plan_id", "event_id"),
        UniqueConstraint("route_plan_id", "stop_order"),
        CheckConstraint("stop_order > 0"),
        CheckConstraint("estimated_service_minutes > 0"),
        CheckConstraint("status IN ('pendiente','atendida','incidencia','no_atendida')"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    route_plan_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("route_plans.id", ondelete="CASCADE"), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("events.id"), nullable=False)
    stop_order: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_service_minutes: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pendiente")
    visited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"))


class StopIncident(Base):
    """Mapping of the existing 002 table; does not create or migrate anything."""
    __tablename__ = "stop_incidents"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stop_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("route_stops.id"), nullable=False)
    reported_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    incident_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    evidence_storage_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
