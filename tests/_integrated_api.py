"""Test-only launcher of the unchanged production API, with real JWT validation.

Only the photo persistence fault and sanitized HTTP observation are test hooks.
No get_current_actor/get_db/schema_guard dependency overrides are installed.
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from isolated_postgres import connection

if os.environ.get("DATABASE_URL") != os.environ.get("RECIWISE_TEST_DATABASE_URL"):
    raise SystemExit("Isolated API target mismatch")
service_url = os.environ["SUPABASE_URL"]
parsed = urlsplit(service_url)
if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
    raise SystemExit("Local integration services required")
guard = connection()
guard.close()

import httpx
import uvicorn
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import main
from app.models import PhotoUploadOperation, ReportPhoto

control_headers = {"x-test-control": os.environ["RECIWISE_INTEGRATED_CONTROL"]}


class FaultSession(Session):
    def commit(self):
        completing = any(isinstance(item, PhotoUploadOperation) and item.state == "complete"
                         for item in self.dirty)
        if completing:
            with httpx.Client(timeout=5, trust_env=False) as client:
                fault = client.post(service_url + "/__test/consume", headers=control_headers,
                                    json={"kind": "photo_persistence"})
                fault.raise_for_status()
            if fault.json()["active"]:
                photo = next(item for item in self.identity_map.values() if isinstance(item, ReportPhoto))
                # Actual PostgreSQL CHECK violation after a successful simulated upload.
                self.execute(text("UPDATE public.report_photos SET slot=0 WHERE id=:id"), {"id": photo.id})
        return super().commit()


original_service = main.PhotoUploads
main.PhotoUploads = lambda sessions, bucket, put, remove: original_service(
    lambda: FaultSession(main.get_engine(), expire_on_commit=False), bucket, put, remove)


@main.app.middleware("http")
async def safe_http_observation(request, call_next):
    response = await call_next(request)
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        await client.post(service_url + "/__test/event", headers=control_headers,
                          json={"method": request.method, "path": request.url.path,
                                "status": response.status_code})
    return response


assert not main.app.dependency_overrides, "Integration must preserve production dependencies"
if __name__ == "__main__":
    uvicorn.run(main.app, host="127.0.0.1", port=int(os.environ["RECIWISE_INTEGRATED_API_PORT"]),
                access_log=False, log_level="error")
