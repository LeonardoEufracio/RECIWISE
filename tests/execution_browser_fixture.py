"""Fictitious approval receipt ONLY in the owned disposable browser-test DB.

Not a provider verifier, CLI, production startup hook, or local-dev seed.
The actual approval endpoint remains blocked. This fixture tests conditional
execution in anticipation of a separately reviewed provider integration.
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from isolated_postgres import ROOT, connection


def seed(profiles):
    # connection() verifies the ephemeral DB name AND per-run marker.
    checked = connection()
    checked.close()
    sys.path.insert(0, str(ROOT))
    from app.models import Event, RoutePlan, RouteStop, ServiceSite, Shift, Vehicle
    from app.route_execution import NAMESPACE, stop_manifest
    from app.route_proposals import digest
    engine = create_engine(os.environ["RECIWISE_TEST_DATABASE_URL"])
    try:
        with Session(engine) as db:
            now = datetime.now(timezone.utc)
            driver, manager = uuid.UUID(profiles["driver"]), uuid.UUID(profiles["manager"])
            vehicle = Vehicle(id=uuid.uuid4(), label="TEST ONLY · Autorización ficticia de ejecución", vehicle_type="otro", available=True)
            departure = ServiceSite(id=uuid.uuid4(), name="Salida ficticia de ejecución", site_type="salida", latitude=-12.05, longitude=-75.22)
            disposal = ServiceSite(id=uuid.uuid4(), name="Descarga ficticia de ejecución", site_type="descarga", latitude=-12.07, longitude=-75.24)
            events = [Event(id=uuid.uuid4(), latitude=-12.051-i*.001, longitude=-75.22, intervention_type="Parada ficticia del chofer") for i in range(3)]
            db.add_all([vehicle, departure, disposal, *events]); db.flush()
            shift = Shift(id=uuid.uuid4(), vehicle_id=vehicle.id, driver_id=driver, departure_site_id=departure.id,
                disposal_site_id=disposal.id, starts_at=now-timedelta(minutes=5), ends_at=now+timedelta(hours=2), created_by=manager)
            db.add(shift); db.flush()
            core = {"shift": {"id": str(shift.id)}, "driver": {"id": str(driver)}, "vehicle": {"id": str(vehicle.id)},
                "events": [{"id": str(e.id), "latitude": e.latitude, "longitude": e.longitude} for e in events]}
            plan = RoutePlan(id=uuid.uuid4(), shift_id=shift.id, status="aprobada", created_by=manager,
                approved_by=manager, approved_at=now, algorithm_version="execution-authorization-fixture-v1",
                input_snapshot={"operational": core}, configuration={}, limitations=[
                    "Autorización ficticia insertada solo por el arnés en PostgreSQL desechable.",
                    "No demuestra aprobación real ni verificación de D3. Sin optimizador ni matriz vial."])
            db.add(plan); db.flush()
            stops = [RouteStop(id=uuid.uuid4(), route_plan_id=plan.id, event_id=e.id, stop_order=i+1) for i, e in enumerate(events)]
            db.add_all(stops); db.flush()
            meta = {"version": 1, "result_origin": "d3", "calculation_status": "completed", "input_binding": "matched",
                    "input_hash": digest(core), "result_hash": digest({"test": "authorization-fixture-only"}),
                    "provider_reference": "fictitious-isolated-authorization-not-real-d3"}
            receipt = {"authority": "verified-provider-v1", "approval_id": str(uuid.uuid4()), "approved_by": str(manager),
                "approved_at": now.isoformat(), "shift_id": str(shift.id), "driver_id": str(driver), "vehicle_id": str(vehicle.id),
                "input_hash": meta["input_hash"], "result_hash": meta["result_hash"], "stop_manifest_hash": stop_manifest(stops),
                "provider_reference": meta["provider_reference"]}
            plan.configuration = {"_d2": meta, NAMESPACE: {"version": 1, "operations": [], "verified_approval": receipt}}
            db.commit()
            return {"id": str(plan.id), "shift_id": str(shift.id), "fixture": "fictitious trusted approval assumption; not real D3"}
    finally:
        engine.dispose()
