"""Run one guarded recovery pass. Default is strict READ ONLY diagnosis.

Schedule --execute periodically only after reviewing deployment/configuration.
Unknown-upload tombstones remain quarantined and are never silently retired.
"""
import argparse
import json
import logging
import signal
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_engine
from .photo_uploads import PhotoUploads
from .schema_guard import REQUIRED_SCHEMA, SchemaCheckError, verify_schema
from .storage import put_private_image, remove_private_image

logger = logging.getLogger(__name__)


@contextmanager
def stop_control(stop_file=None):
    requested = threading.Event()
    previous = {}
    def request_stop(signum, frame):
        requested.set()
    def should_stop():
        try:
            return requested.is_set() or (stop_file is not None and stop_file.exists())
        except OSError:
            logger.warning("Reconciler stop marker unavailable; stopping without new work")
            requested.set()
            return True
    if threading.current_thread() is threading.main_thread():
        for number in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGBREAK", None)):
            if number is not None:
                previous[number] = signal.signal(number, request_stop)
    try:
        yield should_stop
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Allow deletion of owned unreferenced failed uploads")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--operation-id", type=uuid.UUID, help="Restrict this pass to one known operation")
    parser.add_argument("--stop-file", type=Path, help="Existing marker requests a graceful stop; never created or removed by this command")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 1000:
        parser.error("limit must be between 1 and 1000")
    engine = None
    try:
        with stop_control(args.stop_file) as should_stop:
            engine = get_engine()
            verify_schema(engine)  # Always before diagnosis, claims or Storage calls.
            settings = get_settings()
            service = PhotoUploads(lambda: Session(engine, expire_on_commit=False),
                settings.storage_bucket, put_private_image, remove_private_image)
            diagnostic = None
            if should_stop():
                result = {"stopped": 1}
            elif not args.execute:
                diagnostic = service.diagnose(operation_id=args.operation_id, limit=args.limit)
                result = diagnostic["results"]
            elif not settings.supabase_service_role_key.strip():
                print(json.dumps({"error": "storage_not_configured", "dry_run": False}))
                return 2
            elif args.operation_id:
                status = service.reconcile(args.operation_id, stop_requested=should_stop)
                result = {status: 1}
            else:
                result = service.reconcile_due(limit=args.limit, stop_requested=should_stop)
            stopped = bool(should_stop() or "stopped" in result)
            output = {"dry_run": not args.execute, "schema": REQUIRED_SCHEMA,
                      "results": result, "stop_requested": stopped}
            if diagnostic is not None:
                output["diagnostic"] = diagnostic
            print(json.dumps(output))
            if stopped:
                return 130
            actionable = ("pending", "deferred", "cleanup_pending", "quarantined", "review", "missing")
            pending = diagnostic["summary"] if diagnostic is not None else result
            return 1 if any(pending.get(key, 0) for key in actionable) or result.get("missing", 0) else 0
    except SchemaCheckError as exc:
        print(json.dumps({"error": "schema_not_ready", "code": exc.code,
                          "message": "No se ejecutó la conciliación: esquema requerido 003 no verificado"}))
        return 2
    except SQLAlchemyError:
        print(json.dumps({"error": "database_unavailable", "message": "No se pudo completar la pasada; el registro durable conserva el trabajo"}))
        return 2
    except Exception:
        print(json.dumps({"error": "reconciler_failed", "message": "Pasada interrumpida; revisar registro y códigos de error sin repetir cambios manualmente"}))
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
