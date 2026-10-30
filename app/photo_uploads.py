"""Photo quota + durable intent + conservative, idempotent compensation.

All methods are synchronous and run in a worker thread/maintenance process.
Each session belongs to that operation; no DB/HTTP waits run on the event loop.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from .db_errors import diagnostics
from .models import PhotoUploadOperation, Report, ReportPhoto
from .schemas import PhotoOut
from .storage import StorageUploadError

logger = logging.getLogger(__name__)
RECOVERABLE = ("pending", "cleanup_pending", "quarantined")
SAFE_ERROR_CODES = {
    "commit_unknown", "not_uploaded", "persistence_failed", "upload_unknown", "object_preexisting",
    "cleanup_failed", "late_upload_watch", "ownership_mismatch", "reference_mismatch",
}


def now():
    return datetime.now(timezone.utc)


def bounded_transaction(db):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.execute(text("SET LOCAL statement_timeout = '15s'"))


class PhotoUploads:
    def __init__(self, sessions, bucket, upload, remove):
        self.sessions, self.bucket = sessions, bucket
        self.upload, self.remove = upload, remove

    @staticmethod
    def owner(db, actor, report_id, *, lock=False):
        stmt = select(Report).where(Report.id == report_id)
        if lock:
            stmt = stmt.with_for_update()
        report = db.scalar(stmt)
        if report is None or actor.role != "ciudadano" or report.citizen_id != actor.id:
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
        return report

    def create(self, actor, report_id, contents, kind):
        operation_id = uuid.uuid4()
        path = f"reports/{actor.id}/{report_id}/{operation_id}.{kind[1]}"
        # No external effects before this intent is durably acknowledged.
        try:
            with self.sessions() as db:
                self.owner(db, actor, report_id)
                db.add(PhotoUploadOperation(id=operation_id, actor_id=actor.id, report_id=report_id,
                    bucket=self.bucket, storage_path=path, extension=kind[1],
                    next_attempt_at=now() + timedelta(seconds=60)))
                db.commit()
        except SQLAlchemyError as exc:
            raise HTTPException(503, "No se pudo preparar la fotografía; inténtalo más tarde") from exc

        entered_upload = uploaded = commit_attempted = False
        try:
            with self.sessions() as db:
                bounded_transaction(db)
                operation = db.scalar(select(PhotoUploadOperation).where(
                    PhotoUploadOperation.id == operation_id).with_for_update())
                if operation.state != "pending":
                    raise HTTPException(503, "La operación de fotografía ya no está activa")
                self.owner(db, actor, report_id, lock=True)
                used = set(db.scalars(select(ReportPhoto.slot).where(ReportPhoto.report_id == report_id)))
                free = sorted({1, 2, 3} - used)
                if not free:
                    raise HTTPException(409, "Máximo 3 imágenes por reporte")
                photo = ReportPhoto(id=operation_id, report_id=report_id, slot=free[0],
                    storage_path=path, content_type=kind[0], size_bytes=len(contents))
                db.add(photo)
                db.flush()
                result = PhotoOut.model_validate(photo)
                entered_upload = True
                self.upload(path, contents, kind[0])
                uploaded = True
                operation.state, operation.updated_at = "complete", now()
                commit_attempted = True
                db.commit()
                # No refresh/network/serialization of an expired ORM object after commit.
                return result
        except Exception as exc:
            state, constraint = diagnostics(exc)
            definitive_abort = state is not None and (state.startswith("23") or state in {"40001", "40P01"})
            if commit_attempted and not definitive_abort:
                saved = self.resolve_committed(operation_id)
                if saved is not None:
                    return saved
                # No DELETE on this request after an unknown commit result.
                self.mark(operation_id, "quarantined", "commit_unknown", delay=60)
                raise HTTPException(503, "No se pudo confirmar la fotografía; consulta el reporte antes de reintentar") from exc
            if isinstance(exc, StorageUploadError) and exc.collision:
                self.mark(operation_id, "review", "object_preexisting")
            elif not entered_upload or (isinstance(exc, StorageUploadError) and not exc.uncertain):
                self.mark(operation_id, "rejected", "not_uploaded")
            elif uploaded:
                if self.mark(operation_id, "cleanup_pending", "persistence_failed"):
                    self.reconcile(operation_id)
            else:
                # An upload timeout/server failure may finish late. Keep a tombstone.
                self.mark(operation_id, "quarantined", "upload_unknown", delay=60)
            if isinstance(exc, HTTPException):
                raise
            if state == "23505" and constraint == "report_photos_report_slot_key":
                raise HTTPException(409, "Máximo 3 imágenes por reporte") from exc
            if isinstance(exc, SQLAlchemyError):
                raise HTTPException(503, "No se pudo guardar la fotografía; inténtalo más tarde") from exc
            # Cleanup was attempted without masking an unexpected application error.
            raise

    def resolve_committed(self, operation_id):
        try:
            with self.sessions() as db:
                bounded_transaction(db)
                operation = db.scalar(select(PhotoUploadOperation).where(
                    PhotoUploadOperation.id == operation_id).with_for_update())
                photo = db.get(ReportPhoto, operation_id)
                if operation and photo and photo.storage_path == operation.storage_path:
                    return PhotoOut.model_validate(photo)
        except SQLAlchemyError:
            pass
        return None

    def mark(self, operation_id, state, reason, *, delay=0):
        try:
            with self.sessions() as db:
                bounded_transaction(db)
                operation = db.scalar(select(PhotoUploadOperation).where(
                    PhotoUploadOperation.id == operation_id).with_for_update())
                if operation is None or operation.state == "complete":
                    return False
                operation.state, operation.last_error = state, reason
                operation.updated_at = now()
                operation.next_attempt_at = now() + timedelta(seconds=delay)
                db.commit()
                return True
        except SQLAlchemyError:
            # Original committed intent still exists for a later recovery pass.
            logger.warning("Photo operation deferred: id=%s reason=%s", operation_id, reason)
            return False

    def _inspect(self, db, operation):
        if operation.state not in RECOVERABLE:
            return operation.state
        referenced = db.scalar(select(ReportPhoto.id).where(or_(
            ReportPhoto.id == operation.id, ReportPhoto.storage_path == operation.storage_path)).limit(1))
        if referenced:
            return "referenced"
        expected = f"reports/{operation.actor_id}/{operation.report_id}/{operation.id}.{operation.extension}"
        if operation.storage_path != expected or operation.bucket != self.bucket:
            return "review"
        return "pending"

    def diagnose(self, *, operation_id=None, limit=100):
        """MVCC observation only: no claims, row locks, writes or Storage calls."""
        with self.sessions() as db:
            try:
                if db.bind.dialect.name != "postgresql":
                    raise ValueError("PostgreSQL required for read-only diagnosis")
                db.connection().exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                db.connection().exec_driver_sql("SET LOCAL statement_timeout='15s'")
                db.connection().exec_driver_sql("SET LOCAL lock_timeout='2s'")
                if db.connection().exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
                    raise RuntimeError("Read-only diagnosis unavailable")
                conditions = [] if operation_id is None else [PhotoUploadOperation.id == operation_id]
                totals = db.execute(select(PhotoUploadOperation.state, func.count()).where(*conditions)
                                    .group_by(PhotoUploadOperation.state)).all()
                candidates = db.scalars(select(PhotoUploadOperation).where(*conditions)
                    .order_by(PhotoUploadOperation.next_attempt_at, PhotoUploadOperation.id).limit(limit)).all()
                timestamp = now()
                rows, results = [], {}
                for operation in candidates:
                    status = self._inspect(db, operation)
                    results[status] = results.get(status, 0) + 1
                    error = operation.last_error
                    rows.append({"id": str(operation.id), "state": operation.state, "inspection": status,
                        "attempts": operation.attempts, "next_attempt_at": operation.next_attempt_at.isoformat(),
                        "candidate_due": operation.state in RECOVERABLE and operation.next_attempt_at <= timestamp,
                        "last_error": error if error is None or error in SAFE_ERROR_CODES else "unrecognized_error"})
                if operation_id is not None and not candidates:
                    results["missing"] = 1
                return {"read_only": True, "summary": dict(totals), "operations": rows, "results": results,
                        "observed_at": timestamp.isoformat(), "claims_work": False}
            finally:
                db.rollback()

    def reconcile(self, operation_id, *, dry_run=False, stop_requested=None):
        if dry_run:
            results = self.diagnose(operation_id=operation_id)["results"]
            return next(iter(results))
        try:
            with self.sessions() as db:
                bounded_transaction(db)
                operation = db.scalar(select(PhotoUploadOperation).where(
                    PhotoUploadOperation.id == operation_id).with_for_update(skip_locked=True))
                if operation is None:
                    exists = db.scalar(select(PhotoUploadOperation.id).where(PhotoUploadOperation.id == operation_id))
                    return "busy" if exists else "missing"
                if stop_requested and stop_requested():
                    return "stopped"
                if operation.state not in RECOVERABLE:
                    return operation.state
                # Discovery is not a claim. Another pass can finish/reschedule the
                # candidate before this transaction acquires its row lock.
                deadline = operation.next_attempt_at
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                if deadline > now():
                    return "not_due"
                # Same lock order as uploads; current transaction must settle first.
                db.scalar(select(Report.id).where(Report.id == operation.report_id).with_for_update())
                referenced = db.scalar(select(ReportPhoto).where(or_(
                    ReportPhoto.id == operation.id, ReportPhoto.storage_path == operation.storage_path)).limit(1))
                expected = f"reports/{operation.actor_id}/{operation.report_id}/{operation.id}.{operation.extension}"
                if referenced:
                    operation.state = ("complete" if referenced.id == operation.id
                        and referenced.storage_path == operation.storage_path
                        and referenced.report_id == operation.report_id else "review")
                    operation.last_error = None if operation.state == "complete" else "reference_mismatch"
                    db.commit()
                    return operation.state
                if operation.storage_path != expected or operation.bucket != self.bucket:
                    operation.state, operation.last_error = "review", "ownership_mismatch"
                    db.commit()
                    return "review"
                uncertain = operation.state in {"pending", "quarantined"}
                if stop_requested and stop_requested():
                    return "stopped"
                operation.attempts += 1
                operation.updated_at = now()
                operation.next_attempt_at = now() + timedelta(seconds=min(3600, 30 * 2 ** min(operation.attempts, 7)))
                try:
                    self.remove(operation.storage_path)
                    # Keep uncertain tombstones: a timed-out upload may arrive after DELETE.
                    operation.state = "quarantined" if uncertain else "cleaned"
                    operation.last_error = "late_upload_watch" if uncertain else None
                except Exception as exc:
                    operation.state = "quarantined" if uncertain else "cleanup_pending"
                    operation.last_error = "cleanup_failed"
                    # Log stable codes, never Storage bodies/headers or exception repr.
                    cause = getattr(exc, "__cause__", None)
                    response = getattr(cause, "response", None)
                    status = getattr(response, "status_code", None)
                    reason = f"storage_http_{status}" if isinstance(status, int) else "storage_failed"
                    logger.warning("Photo cleanup deferred: id=%s reason=%s", operation_id, reason)
                db.commit()
                return operation.state
        except SQLAlchemyError:
            logger.warning("Photo reconciliation database unavailable: id=%s", operation_id)
            return "deferred"

    def reconcile_due(self, *, limit=100, dry_run=False, stop_requested=None):
        if dry_run:
            return self.diagnose(limit=limit)["results"]
        if stop_requested and stop_requested():
            return {"stopped": 1}
        with self.sessions() as db:
            bounded_transaction(db)
            ids = list(db.scalars(select(PhotoUploadOperation.id).where(
                PhotoUploadOperation.state.in_(RECOVERABLE), PhotoUploadOperation.next_attempt_at <= now()
            ).order_by(PhotoUploadOperation.next_attempt_at, PhotoUploadOperation.id).limit(limit)))
        results = {}
        for operation_id in ids:
            if stop_requested and stop_requested():
                results["stopped"] = 1
                break
            status = self.reconcile(operation_id, stop_requested=stop_requested)
            results[status] = results.get(status, 0) + 1
            if status == "stopped":
                break
        return results
