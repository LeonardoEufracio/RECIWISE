"""Test-only crash points; refusing non-isolated targets before installing hooks."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from isolated_postgres import connection

guard = connection()
guard.close()

from sqlalchemy import event
from sqlalchemy.orm import Session
from app import reconcile_photos as cli
from app.models import PhotoUploadOperation

stage = os.environ["RECIWISE_RECONCILER_CRASH"]
if stage == "after-delete":
    remove = cli.remove_private_image
    def remove_then_exit(path):
        remove(path)
        os._exit(74)
    cli.remove_private_image = remove_then_exit
elif stage == "after-commit":
    @event.listens_for(Session, "after_commit")
    def exit_after_commit(session):
        if any(isinstance(item, PhotoUploadOperation) and item.state == "cleaned" for item in session.identity_map.values()):
            os._exit(75)
else:
    raise SystemExit("Unknown test crash stage")

raise SystemExit(cli.main())
