"""Local GET-only test process; never use this entry point to deploy RECIWISE.

Uses real FastAPI handlers/PostgreSQL/Storage. Authentication alone is substituted
with existing profile IDs, because no real user access tokens are available.
"""
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = os.environ["RECIWISE_TEST_DATABASE_URL"]
os.environ["SUPABASE_URL"] = os.environ.get("RECIWISE_STORAGE_URL", "https://example.supabase.co")
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = os.environ.get("RECIWISE_STORAGE_KEY", "")

import uvicorn
from fastapi import Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db, get_engine
from app.main import app
from app.models import Profile
from app.security import Actor, get_current_actor


def readonly_db():
    with Session(get_engine()) as session:
        try:
            session.connection().exec_driver_sql("SET TRANSACTION READ ONLY")
            assert session.connection().exec_driver_sql("SHOW transaction_read_only").scalar_one() == "on"
            session.connection().exec_driver_sql("SET LOCAL statement_timeout = '12s'")
            yield session
        finally:
            session.rollback()


def test_actor(x_reciwise_test_actor: str = Header(), db: Session = Depends(get_db)):
    allowed = {os.environ["RECIWISE_TEST_CITIZEN_ID"], os.environ["RECIWISE_TEST_MANAGER_ID"]}
    if x_reciwise_test_actor not in allowed:
        raise HTTPException(403)
    profile = db.get(Profile, uuid.UUID(x_reciwise_test_actor))
    if profile is None:
        raise HTTPException(403)
    return Actor(profile.id, profile.role)


@app.middleware("http")
async def get_only(request, call_next):
    if request.method != "GET":
        return JSONResponse({"detail": "Read-only persistence test worker"}, status_code=405)
    return await call_next(request)


app.dependency_overrides[get_db] = readonly_db
app.dependency_overrides[get_current_actor] = test_actor

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ["RECIWISE_TEST_PORT"]),
                access_log=False, log_level="error")
