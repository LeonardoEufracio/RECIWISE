"""Test-only loopback FastAPI worker; requires our isolated database marker."""
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from isolated_postgres import connection

guard = connection()
guard.close()

import uvicorn
from fastapi import Depends, Header, HTTPException
from sqlalchemy import event
from sqlalchemy.orm import Session

from app import main
from app.db import get_db
from app.models import PhotoUploadOperation, Profile, ReportPhoto
from app.security import Actor, get_current_actor

mode = os.getenv("RECIWISE_CRASH_STAGE", "")


@event.listens_for(Session, "before_flush")
def track(session, context, instances):
    if any(isinstance(item, PhotoUploadOperation) for item in session.new):
        session.info["test_intent"] = True
    if any(isinstance(item, ReportPhoto) for item in session.new):
        session.info["test_photo"] = True


@event.listens_for(Session, "after_commit")
def crash(session):
    if mode == "intent" and session.info.get("test_intent"):
        os._exit(71)
    if mode == "commit" and session.info.get("test_photo"):
        os._exit(73)


if mode == "upload":
    put = main.put_private_image
    def put_then_crash(*args):
        put(*args)
        os._exit(72)
    main.put_private_image = put_then_crash


def actor(x_reciwise_test_actor: str = Header(), db: Session = Depends(get_db)):
    if x_reciwise_test_actor not in {os.environ["RECIWISE_WORKER_CITIZEN"], os.environ["RECIWISE_WORKER_MANAGER"]}:
        raise HTTPException(403)
    profile = db.get(Profile, uuid.UUID(x_reciwise_test_actor))
    if not profile:
        raise HTTPException(403)
    return Actor(profile.id, profile.role)


main.app.dependency_overrides[get_current_actor] = actor
if __name__ == "__main__":
    uvicorn.run(main.app, host="127.0.0.1", port=int(os.environ["RECIWISE_WORKER_PORT"]),
                access_log=False, log_level="error")
