"""Read-only D2 deployment inventory. Does not migrate, repair, lock rows or clean Storage.

An inventory is not a release approval or a runtime schema gate. Credentials are
read in memory only, never printed or accepted as command-line values.
"""
import argparse
import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("profiles", "reports", "report_photos", "vehicles", "service_sites", "shifts", "photo_upload_operations")
QUERIES = {
    "role": """SELECT current_setting('server_version') AS server_version,
        rolsuper AS superuser,rolbypassrls AS bypassrls,
        has_database_privilege(current_database(),'CREATE') AS database_create,
        has_schema_privilege('public','CREATE') AS public_create
        FROM pg_roles WHERE rolname=current_user""",
    "relations": """SELECT c.relname,c.relkind,c.relrowsecurity,c.relforcerowsecurity,
        pg_has_role(c.relowner,'USAGE') AS owner_privileges,
        pg_total_relation_size(c.oid) AS total_bytes
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname=ANY(%s) ORDER BY c.relname""",
    "extensions": """SELECT a.name,a.default_version,a.installed_version,n.nspname AS installed_schema,
        v.trusted,v.superuser FROM pg_available_extensions a
        LEFT JOIN pg_extension e ON e.extname=a.name
        LEFT JOIN pg_namespace n ON n.oid=e.extnamespace
        LEFT JOIN pg_available_extension_versions v ON v.name=a.name AND v.version=a.default_version
        WHERE a.name='btree_gist'""",
    "columns": """SELECT table_name,column_name,data_type,is_nullable,column_default
        FROM information_schema.columns WHERE table_schema='public' AND table_name=ANY(%s)
        ORDER BY table_name,ordinal_position""",
    "constraints": """SELECT c.relname,p.conname,p.contype,p.convalidated,p.condeferrable,
        pg_get_constraintdef(p.oid) AS definition,i.indisvalid,i.indisready
        FROM pg_constraint p JOIN pg_class c ON c.oid=p.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace LEFT JOIN pg_index i ON i.indexrelid=p.conindid
        WHERE n.nspname='public' AND c.relname=ANY(%s) ORDER BY c.relname,p.conname""",
    "name_collisions": """SELECT c.relname,c.relkind FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
        AND c.relname IN ('photo_upload_operations','photo_operations_due_idx',
          'photo_upload_operations_archive_003','photo_operations_archive_003_due_idx',
          'photo_upload_operations_archive_003_pkey','photo_upload_operations_archive_003_storage_path_key')
        ORDER BY c.relname""",
    "conflicts": """SELECT
        (SELECT count(*) FROM public.shifts a JOIN public.shifts b ON a.id<b.id
          AND a.vehicle_id=b.vehicle_id AND a.starts_at<b.ends_at AND b.starts_at<a.ends_at
          WHERE a.status='programado' AND b.status='programado') AS vehicle_overlap_pairs,
        (SELECT count(*) FROM public.shifts a JOIN public.shifts b ON a.id<b.id
          AND a.driver_id=b.driver_id AND a.starts_at<b.ends_at AND b.starts_at<a.ends_at
          WHERE a.status='programado' AND b.status='programado') AS driver_overlap_pairs,
        (SELECT count(*) FROM (SELECT report_id FROM public.report_photos GROUP BY report_id HAVING count(*)>3) t)
          AS reports_over_three_photos,
        (SELECT count(*) FROM public.shifts WHERE ends_at<=starts_at) AS invalid_intervals""",
    "counts": """SELECT (SELECT count(*) FROM public.profiles) AS profiles,
        (SELECT count(*) FROM public.reports) AS reports,
        (SELECT count(*) FROM public.report_photos) AS report_photos,
        (SELECT count(*) FROM public.vehicles) AS vehicles,
        (SELECT count(*) FROM public.service_sites) AS service_sites,
        (SELECT count(*) FROM public.shifts) AS shifts""",
    "relationships": """SELECT
        (SELECT count(*) FROM public.reports r LEFT JOIN public.profiles p ON p.id=r.citizen_id
          WHERE p.id IS NULL OR p.role<>'ciudadano') AS invalid_report_owner,
        (SELECT count(*) FROM public.report_photos ph LEFT JOIN public.reports r ON r.id=ph.report_id
          WHERE r.id IS NULL) AS orphan_photo_metadata,
        (SELECT count(*) FROM public.shifts s
          LEFT JOIN public.vehicles v ON v.id=s.vehicle_id
          LEFT JOIN public.profiles d ON d.id=s.driver_id
          LEFT JOIN public.profiles m ON m.id=s.created_by
          LEFT JOIN public.service_sites a ON a.id=s.departure_site_id
          LEFT JOIN public.service_sites b ON b.id=s.disposal_site_id
          WHERE v.id IS NULL OR d.id IS NULL OR m.id IS NULL OR a.id IS NULL OR b.id IS NULL
          OR d.role<>'chofer' OR m.role<>'encargado_municipal'
          OR a.site_type NOT IN ('salida','ambos') OR b.site_type NOT IN ('descarga','ambos')) AS invalid_shift_relationships""",
    "table_access": """SELECT r.rolname,c.relname,c.relrowsecurity,
        has_table_privilege(r.oid,c.oid,'SELECT') AS can_select,
        has_table_privilege(r.oid,c.oid,'INSERT') AS can_insert,
        has_table_privilege(r.oid,c.oid,'UPDATE') AS can_update,
        has_table_privilege(r.oid,c.oid,'DELETE') AS can_delete
        FROM pg_roles r CROSS JOIN pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE r.rolname IN ('anon','authenticated') AND n.nspname='public' AND c.relname=ANY(%s)
        ORDER BY c.relname,r.rolname""",
    "policies": """SELECT tablename,policyname,roles,cmd,qual,with_check FROM pg_policies
        WHERE schemaname='public' AND tablename=ANY(%s) ORDER BY tablename,policyname""",
    "transactions": """SELECT count(*) FILTER (WHERE xact_start<now()-interval '1 minute') AS transactions_over_one_minute,
        count(*) FILTER (WHERE state='idle in transaction') AS idle_in_transaction,
        count(*) FILTER (WHERE wait_event_type='Lock') AS lock_waiters
        FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()""",
    "bucket": """SELECT public AS bucket_public,file_size_limit,allowed_mime_types
        FROM storage.buckets WHERE id=%s""",
    "storage_metadata": """SELECT
        (SELECT count(*) FROM public.report_photos p WHERE NOT EXISTS
          (SELECT 1 FROM storage.objects o WHERE o.bucket_id=%s AND o.name=p.storage_path)) AS photos_missing_storage_catalog,
        (SELECT count(*) FROM storage.objects o WHERE o.bucket_id=%s AND o.name LIKE 'reports/%%'
          AND NOT EXISTS(SELECT 1 FROM public.report_photos p WHERE p.storage_path=o.name)) AS unreferenced_storage_candidates""",
    "journal": """SELECT state,count(*) AS count,min(created_at) AS oldest_created,
        min(next_attempt_at) AS oldest_due,max(attempts) AS max_attempts
        FROM public.photo_upload_operations GROUP BY state ORDER BY state""",
    "journal_references": """SELECT
        count(*) FILTER (WHERE o.state='complete' AND p.id IS NULL) AS complete_without_matching_photo,
        count(*) FILTER (WHERE o.state IN ('cleaned','rejected') AND p.id IS NOT NULL) AS terminal_with_photo
        FROM public.photo_upload_operations o LEFT JOIN public.report_photos p
          ON p.id=o.id AND p.storage_path=o.storage_path""",
}


@contextmanager
def readonly(conn):
    conn.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
    try:
        conn.execute("SET LOCAL statement_timeout='10s'")
        conn.execute("SET LOCAL lock_timeout='2s'")
        assert conn.execute("SHOW transaction_read_only").fetchone()[0] == "on"
        yield
    finally:
        conn.execute("ROLLBACK")


def collect(conn, *, bucket="reciwise-reportes"):
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "sections": {}}
    with readonly(conn):
        report["transaction_read_only"] = conn.execute("SHOW transaction_read_only").fetchone()[0]
        report["transaction_isolation"] = conn.execute("SHOW transaction_isolation").fetchone()[0]
        def read(name, params=None):
            conn.execute("SAVEPOINT audit_section")
            try:
                cursor = conn.execute(QUERIES[name], params)
                result = [dict(zip((column.name for column in cursor.description), row)) for row in cursor.fetchall()]
            except psycopg.Error as exc:
                conn.execute("ROLLBACK TO SAVEPOINT audit_section")
                result = {"unavailable": True, "sqlstate": exc.sqlstate, "error_type": type(exc).__name__}
            finally:
                conn.execute("RELEASE SAVEPOINT audit_section")
            report["sections"][name] = result
            return result
        for name in ("role", "extensions", "name_collisions", "conflicts", "counts", "relationships", "transactions"):
            read(name)
        for name in ("relations", "columns", "constraints", "table_access", "policies"):
            read(name, (list(TABLES),))
        read("bucket", (bucket,))
        read("storage_metadata", (bucket, bucket))
        relations = report["sections"]["relations"]
        if isinstance(relations, list) and any(row["relname"] == "photo_upload_operations" for row in relations):
            read("journal")
            read("journal_references")
        else:
            report["sections"]["journal"] = {"not_present": True}
    report["query_errors"] = [name for name, rows in report["sections"].items()
                              if isinstance(rows, dict) and rows.get("unavailable")]
    report["migration_sha256"] = {name: hashlib.sha256((ROOT / "migrations" / name).read_bytes()).hexdigest()
        for name in ("003_sprint1_concurrencia.sql", "rollback/003_sprint1_concurrencia.sql")}
    report["scope"] = "Database diagnostics only; no runtime version gate or deployment approval"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-project-env", action="store_true", help="Read existing .env in memory for SELECT-only audit")
    parser.add_argument("--output", type=Path, help="Optional JSON file under .test-artifacts only")
    args = parser.parse_args()
    if args.output and not args.output.resolve().is_relative_to((ROOT / ".test-artifacts").resolve()):
        parser.error("Audit output must stay under .test-artifacts")
    config = dotenv_values(ROOT / ".env") if args.from_project_env else os.environ
    raw_url = config.get("DATABASE_URL") if args.from_project_env else config.get("RECIWISE_AUDIT_DATABASE_URL")
    if not raw_url:
        parser.error("Explicit RECIWISE_AUDIT_DATABASE_URL or --from-project-env required")
    try:
        url = make_url(raw_url)
        if url.get_backend_name() != "postgresql":
            raise ValueError("PostgreSQL required")
        options = dict(url.query)
        if url.host not in {"127.0.0.1", "localhost", "::1"}:
            options["sslmode"] = "require"
        conn = psycopg.connect(host=url.host, port=url.port or 5432, dbname=url.database,
            user=url.username, password=url.password, **options,
            connect_timeout=10, autocommit=True, application_name="reciwise_d2_readonly_audit")
        try:
            report = collect(conn, bucket=config.get("STORAGE_BUCKET") or "reciwise-reportes")
        finally:
            conn.close()
    except Exception as exc:
        print(json.dumps({"audit_completed": False, "error_type": type(exc).__name__, "sqlstate": getattr(exc, "sqlstate", None)}))
        return 2
    output = json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    # Deliberately no URL, username, passwords, private keys, descriptions or coordinates.
    print(output)
    return 2 if report["query_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
