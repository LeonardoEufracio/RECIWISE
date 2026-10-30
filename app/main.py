import logging
import uuid
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import or_, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from .config import get_settings
from .db import get_db, get_engine
from .db_errors import SHIFT_EXCLUSIONS, diagnostics
from .models import Profile, Report, ReportPhoto, ServiceSite, Shift, Vehicle
from .photo_uploads import PhotoUploads
from .schemas import (ActorOut, AvailabilityPatch, PhotoOut, ReportCreate, ReportOut,
                      ShiftCreate, ShiftOut, SiteCreate, SiteOut, VehicleCreate, VehicleOut)
from .security import Actor, get_current_actor, require_roles
from .schema_guard import REQUIRED_SCHEMA, SchemaCheckError, verify_schema
from .storage import put_private_image, remove_private_image, signed_image_url

logger = logging.getLogger(__name__)


def check_configured_schema():
    try:
        verify_schema(get_engine())
    except SchemaCheckError:
        raise
    except Exception:
        raise SchemaCheckError("database_unavailable") from None


@asynccontextmanager
async def lifespan(application):
    application.state.schema_guard_started = False
    application.state.schema_compatible = False
    try:
        await run_in_threadpool(check_configured_schema)
    except SchemaCheckError as exc:
        logger.error("RECIWISE startup refused: %s", exc.code)
        raise exc from None
    application.state.schema_guard_started = True
    application.state.schema_compatible = True
    try:
        yield
    finally:
        application.state.schema_guard_started = False
        application.state.schema_compatible = False


app = FastAPI(title="RECIWISE API", version="0.1.0", description="Sprint 1: reportes y recursos básicos", lifespan=lifespan)
app.state.schema_guard_started = False
app.state.schema_compatible = False
@app.middleware("http")
async def require_prepared_service(request, call_next):
    diagnostics = {"/health", "/ready", "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
    if request.url.path not in diagnostics and not (
        app.state.schema_guard_started and app.state.schema_compatible
    ):
        return JSONResponse({"detail": "Servicio no preparado; comprueba compatibilidad del esquema"}, status_code=503)
    return await call_next(request)


app.add_middleware(CORSMiddleware, allow_origins=get_settings().origins,
                   allow_credentials=False, allow_methods=["GET", "POST", "PATCH"],
                   allow_headers=["Authorization", "Content-Type"])


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/ready", include_in_schema=False)
def ready():
    # A probe cannot replace startup or enable a process run with lifespan disabled.
    if not app.state.schema_guard_started:
        return JSONResponse({"status": "not_ready", "schema": "unverified"}, status_code=503)
    try:
        check_configured_schema()
    except SchemaCheckError as exc:
        app.state.schema_compatible = False
        logger.warning("RECIWISE readiness refused: %s", exc.code)
        return JSONResponse({"status": "not_ready", "schema": "unverified"}, status_code=503)
    app.state.schema_compatible = True
    return {"status": "ready", "schema": REQUIRED_SCHEMA}


@app.get("/me", response_model=ActorOut)
def me(actor: Actor = Depends(get_current_actor)):
    return actor


@app.post("/reports", response_model=ReportOut, status_code=201)
def create_report(payload: ReportCreate, db: Session = Depends(get_db),
                  actor: Actor = Depends(require_roles("ciudadano"))):
    report = Report(citizen_id=actor.id, description=payload.description,
                    latitude=payload.latitude, longitude=payload.longitude,
                    observed_at=payload.observed_at, waste_type=payload.waste_type)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@app.get("/reports/mine", response_model=list[ReportOut])
def my_reports(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
               db: Session = Depends(get_db), actor: Actor = Depends(require_roles("ciudadano"))):
    return db.scalars(select(Report).where(Report.citizen_id == actor.id)
                      .order_by(Report.created_at.desc(), Report.id.desc())
                      .offset(offset).limit(limit)).all()


def allowed_report(report_id: uuid.UUID, db: Session, actor: Actor) -> Report:
    report = db.get(Report, report_id)
    if not report or (actor.role != "encargado_municipal" and
                      (actor.role != "ciudadano" or report.citizen_id != actor.id)):
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    return report


@app.get("/reports/{report_id}", response_model=ReportOut)
def report_detail(report_id: uuid.UUID, db: Session = Depends(get_db),
                  actor: Actor = Depends(get_current_actor)):
    return allowed_report(report_id, db, actor)


@app.post("/reports/{report_id}/photos", response_model=PhotoOut, status_code=201)
def upload_photo(report_id: uuid.UUID, file: UploadFile = File(...),
                       db: Session = Depends(get_db), actor: Actor = Depends(require_roles("ciudadano"))):
    report = allowed_report(report_id, db, actor)
    if report.citizen_id != actor.id:
        raise HTTPException(status_code=403, detail="Solo el autor puede subir imágenes")
    size_limit = 5 * 1024 * 1024
    contents = file.file.read(size_limit + 1)
    if len(contents) > size_limit:
        raise HTTPException(status_code=413, detail="La imagen supera 5 MB")
    kind = None
    if contents.startswith(b"\xff\xd8\xff"):
        kind = ("image/jpeg", "jpg")
    elif contents.startswith(b"\x89PNG\r\n\x1a\n"):
        kind = ("image/png", "png")
    elif contents.startswith(b"RIFF") and contents[8:12] == b"WEBP":
        kind = ("image/webp", "webp")
    if kind is None:
        raise HTTPException(status_code=415, detail="Formato inválido: JPG, PNG o WebP")
    service = PhotoUploads(lambda: Session(db.get_bind(), expire_on_commit=False),
                           get_settings().storage_bucket, put_private_image, remove_private_image)
    return service.create(actor, report_id, contents, kind)


@app.get("/reports/{report_id}/photos", response_model=list[PhotoOut])
def list_photos(report_id: uuid.UUID, db: Session = Depends(get_db),
                      actor: Actor = Depends(get_current_actor)):
    allowed_report(report_id, db, actor)
    photos = db.scalars(select(ReportPhoto).where(ReportPhoto.report_id == report_id)).all()
    output = []
    for photo in photos:
        item = PhotoOut.model_validate(photo)
        item.signed_url = signed_image_url(photo.storage_path)
        output.append(item)
    return output


@app.get("/municipal/reports", response_model=list[ReportOut])
def municipal_reports(status: str | None = None,
                      north: float | None = Query(default=None, ge=-90, le=90),
                      south: float | None = Query(default=None, ge=-90, le=90),
                      west: float | None = Query(default=None, ge=-180, le=180),
                      east: float | None = Query(default=None, ge=-180, le=180),
                      limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
                      db: Session = Depends(get_db),
                      actor: Actor = Depends(require_roles("encargado_municipal"))):
    stmt = select(Report)
    if status is not None:
        stmt = stmt.where(Report.status == status)
    bounds = (north, south, west, east)
    if any(v is not None for v in bounds):
        if any(v is None for v in bounds) or north < south or east < west:
            raise HTTPException(status_code=422, detail="Límites inválidos: north, south, west y east")
        stmt = stmt.where(Report.latitude.between(south, north), Report.longitude.between(west, east))
    return db.scalars(stmt.order_by(Report.created_at.desc(), Report.id.desc())
                      .offset(offset).limit(limit)).all()


@app.get("/municipal/vehicles", response_model=list[VehicleOut])
def vehicles(db: Session = Depends(get_db), actor: Actor = Depends(require_roles("encargado_municipal"))):
    return db.scalars(select(Vehicle).order_by(Vehicle.label)).all()


@app.post("/municipal/vehicles", response_model=VehicleOut, status_code=201)
def create_vehicle(payload: VehicleCreate, db: Session = Depends(get_db),
                   actor: Actor = Depends(require_roles("encargado_municipal"))):
    vehicle = Vehicle(**payload.model_dump())
    db.add(vehicle)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Identificador de vehículo duplicado") from exc
    db.refresh(vehicle)
    return vehicle


@app.patch("/municipal/vehicles/{vehicle_id}/availability", response_model=VehicleOut)
def update_vehicle(vehicle_id: uuid.UUID, payload: AvailabilityPatch,
                   db: Session = Depends(get_db),
                   actor: Actor = Depends(require_roles("encargado_municipal"))):
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    vehicle.available = payload.available
    db.commit()
    db.refresh(vehicle)
    return vehicle


@app.get("/municipal/sites", response_model=list[SiteOut])
def sites(db: Session = Depends(get_db), actor: Actor = Depends(require_roles("encargado_municipal"))):
    return db.scalars(select(ServiceSite).order_by(ServiceSite.name)).all()


@app.post("/municipal/sites", response_model=SiteOut, status_code=201)
def create_site(payload: SiteCreate, db: Session = Depends(get_db),
                actor: Actor = Depends(require_roles("encargado_municipal"))):
    site = ServiceSite(**payload.model_dump())
    db.add(site)
    db.commit()
    db.refresh(site)
    return site


@app.get("/municipal/shifts", response_model=list[ShiftOut])
def shifts(db: Session = Depends(get_db), actor: Actor = Depends(require_roles("encargado_municipal"))):
    return db.scalars(select(Shift).order_by(Shift.starts_at.desc()).limit(100)).all()


@app.post("/municipal/shifts", response_model=ShiftOut, status_code=201)
def create_shift(payload: ShiftCreate, db: Session = Depends(get_db),
                 actor: Actor = Depends(require_roles("encargado_municipal"))):
    vehicle = db.get(Vehicle, payload.vehicle_id)
    driver = db.get(Profile, payload.driver_id)
    departure = db.get(ServiceSite, payload.departure_site_id)
    disposal = db.get(ServiceSite, payload.disposal_site_id)
    if vehicle is None or not vehicle.available:
        raise HTTPException(status_code=422, detail="El vehículo no existe o no está disponible")
    if driver is None or driver.role != "chofer":
        raise HTTPException(status_code=422, detail="Chofer no válido")
    if departure is None or not departure.active or departure.site_type not in ("salida", "ambos"):
        raise HTTPException(status_code=422, detail="Punto de salida no válido")
    if disposal is None or not disposal.active or disposal.site_type not in ("descarga", "ambos"):
        raise HTTPException(status_code=422, detail="Punto de descarga no válido")
    overlap = db.scalar(select(Shift.id).where(
        Shift.status == "programado",
        Shift.starts_at < payload.ends_at,
        Shift.ends_at > payload.starts_at,
        or_(Shift.vehicle_id == payload.vehicle_id, Shift.driver_id == payload.driver_id),
    ).limit(1))
    if overlap:
        raise HTTPException(status_code=409, detail="Vehículo o chofer ya reservado en ese horario")
    # GiST exclusion checks can deadlock between simultaneous INSERTs. A known
    # aborted transaction is safe to retry; a lost commit confirmation is not.
    for attempt in range(3):
        shift = Shift(**payload.model_dump(), created_by=actor.id)
        db.add(shift)
        try:
            db.flush()
            result = ShiftOut.model_validate(shift)
            db.commit()
            return result
        except DBAPIError as exc:
            db.rollback()
            state, constraint = diagnostics(exc)
            if state == "23P01" and constraint in SHIFT_EXCLUSIONS:
                raise HTTPException(status_code=409, detail="Vehículo o chofer ya reservado en ese horario") from exc
            if state in {"40001", "40P01"} and attempt < 2:
                continue
            if not isinstance(exc, IntegrityError) or state in {"40001", "40P01", "55P03", "57014"}:
                raise HTTPException(status_code=503, detail="No se pudo confirmar el turno; consulta los turnos antes de reintentar") from exc
            raise
