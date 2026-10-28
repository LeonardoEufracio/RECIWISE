import uuid
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import get_settings
from .db import get_db
from .models import Profile, Report, ReportPhoto, ServiceSite, Shift, Vehicle
from .schemas import (ActorOut, AvailabilityPatch, PhotoOut, ReportCreate, ReportOut,
                      ShiftCreate, ShiftOut, SiteCreate, SiteOut, VehicleCreate, VehicleOut)
from .security import Actor, get_current_actor, require_roles
from .storage import put_private_image, signed_image_url

app = FastAPI(title="RECIWISE API", version="0.1.0", description="Sprint 1: reportes y recursos básicos")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().origins,
                   allow_credentials=False, allow_methods=["GET", "POST", "PATCH"],
                   allow_headers=["Authorization", "Content-Type"])


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


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
async def upload_photo(report_id: uuid.UUID, file: UploadFile = File(...),
                       db: Session = Depends(get_db), actor: Actor = Depends(require_roles("ciudadano"))):
    report = allowed_report(report_id, db, actor)
    if report.citizen_id != actor.id:
        raise HTTPException(status_code=403, detail="Solo el autor puede subir imágenes")
    size_limit = 5 * 1024 * 1024
    contents = await file.read(size_limit + 1)
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
    num_photos = db.query(ReportPhoto).filter(ReportPhoto.report_id == report_id).count()
    if num_photos >= 3:
        raise HTTPException(status_code=409, detail="Máximo 3 imágenes por reporte")
    photo_id = uuid.uuid4()
    path = f"reports/{actor.id}/{report_id}/{photo_id}.{kind[1]}"
    await put_private_image(path, contents, kind[0])
    photo = ReportPhoto(id=photo_id, report_id=report_id,
                        storage_path=path, content_type=kind[0], size_bytes=len(contents))
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo


@app.get("/reports/{report_id}/photos", response_model=list[PhotoOut])
async def list_photos(report_id: uuid.UUID, db: Session = Depends(get_db),
                      actor: Actor = Depends(get_current_actor)):
    allowed_report(report_id, db, actor)
    photos = db.scalars(select(ReportPhoto).where(ReportPhoto.report_id == report_id)).all()
    output = []
    for photo in photos:
        item = PhotoOut.model_validate(photo)
        item.signed_url = await signed_image_url(photo.storage_path)
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
    shift = Shift(**payload.model_dump(), created_by=actor.id)
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift
