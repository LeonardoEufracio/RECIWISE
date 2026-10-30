"""Fail-closed, catalog-only verification of the approved 001 + 003 contract.

The manifest is a reviewed build artifact from disposable PostgreSQL, never
learned from the runtime database. There is no migration or bypass switch here.
"""
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

REQUIRED_SCHEMA = "003"
MANIFEST = Path(__file__).with_name("schema_003.json")
TABLES = ("profiles", "reports", "report_photos", "vehicles", "service_sites", "shifts", "photo_upload_operations")

QUERIES = {
    "tables": """SELECT c.relname AS table_name,c.relkind,c.relpersistence,
        c.relrowsecurity,c.relforcerowsecurity
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname=ANY(:tables) ORDER BY c.relname""",
    "columns": """SELECT c.relname AS table_name,a.attname AS column_name,
        format_type(a.atttypid,a.atttypmod) AS type,a.attnotnull AS not_null,
        a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid) AS default_expression
        FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
        WHERE n.nspname='public' AND c.relname=ANY(:tables) AND a.attnum>0 AND NOT a.attisdropped
        ORDER BY c.relname,a.attnum""",
    "constraints": """SELECT c.relname AS table_name,p.conname,p.contype,p.convalidated,
        p.condeferrable,p.condeferred,pg_get_constraintdef(p.oid) AS definition
        FROM pg_constraint p JOIN pg_class c ON c.oid=p.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname=ANY(:tables) ORDER BY c.relname,p.conname""",
    "foreign_key_triggers": """SELECT c.relname AS table_name,p.conname,
        ns.nspname AS function_schema,f.proname,t.tgtype,t.tgenabled
        FROM pg_constraint p JOIN pg_class c ON c.oid=p.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_trigger t ON t.tgconstraint=p.oid
        JOIN pg_proc f ON f.oid=t.tgfoid JOIN pg_namespace ns ON ns.oid=f.pronamespace
        WHERE n.nspname='public' AND c.relname=ANY(:tables) AND p.contype='f'
        ORDER BY c.relname,p.conname,f.proname,t.tgtype""",
    "indexes": """SELECT t.relname AS table_name,c.relname AS index_name,am.amname,
        i.indisunique,i.indisprimary,i.indisexclusion,i.indisvalid,i.indisready,i.indislive,
        i.indnullsnotdistinct,i.indnkeyatts,i.indnatts,
        ARRAY(SELECT pg_get_indexdef(i.indexrelid,k,true) FROM generate_series(1,i.indnatts) k ORDER BY k) AS keys,
        pg_get_expr(i.indpred,i.indrelid) AS predicate,
        ARRAY(SELECT CASE WHEN e.extname='btree_gist' THEN 'btree_gist.' || op.opcname
                    ELSE ns.nspname || '.' || op.opcname END
              FROM unnest(i.indclass) WITH ORDINALITY v(oid,position)
              JOIN pg_opclass op ON op.oid=v.oid JOIN pg_namespace ns ON ns.oid=op.opcnamespace
              LEFT JOIN pg_depend dep ON dep.classid='pg_opclass'::regclass AND dep.objid=op.oid AND dep.deptype='e'
              LEFT JOIN pg_extension e ON e.oid=dep.refobjid ORDER BY v.position) AS operator_classes
        FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
        JOIN pg_class t ON t.oid=i.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace
        JOIN pg_am am ON am.oid=c.relam
        WHERE n.nspname='public' AND t.relname=ANY(:tables) ORDER BY t.relname,c.relname""",
    "client_access": """SELECT c.relname AS table_name,r.rolname,
        has_table_privilege(r.oid,c.oid,'SELECT') AS can_select,
        has_table_privilege(r.oid,c.oid,'INSERT') AS can_insert,
        has_table_privilege(r.oid,c.oid,'UPDATE') AS can_update,
        has_table_privilege(r.oid,c.oid,'DELETE') AS can_delete,
        has_table_privilege(r.oid,c.oid,'TRUNCATE') AS can_truncate,
        has_table_privilege(r.oid,c.oid,'REFERENCES') AS can_reference,
        has_table_privilege(r.oid,c.oid,'TRIGGER') AS can_trigger,
        has_any_column_privilege(r.oid,c.oid,'SELECT') AS column_select,
        has_any_column_privilege(r.oid,c.oid,'INSERT') AS column_insert,
        has_any_column_privilege(r.oid,c.oid,'UPDATE') AS column_update
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN pg_roles r
        WHERE n.nspname='public' AND c.relname=ANY(:tables) AND r.rolname IN ('anon','authenticated')
        ORDER BY c.relname,r.rolname""",
    "policies": """SELECT tablename,policyname,permissive,roles,cmd,qual,with_check
        FROM pg_policies WHERE schemaname='public' AND tablename=ANY(:tables) ORDER BY tablename,policyname""",
    "triggers": """SELECT c.relname AS table_name,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid) AS definition
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname=ANY(:tables) AND NOT t.tgisinternal ORDER BY c.relname,t.tgname""",
    "rules": """SELECT tablename,rulename,definition FROM pg_rules
        WHERE schemaname='public' AND tablename=ANY(:tables) ORDER BY tablename,rulename""",
}


class SchemaCheckError(RuntimeError):
    """Only stable public codes/messages. Never attach raw driver exceptions."""
    def __init__(self, code):
        self.code = code
        super().__init__("Servicio no preparado: no se pudo verificar el esquema requerido 003")


def capture_catalog(engine):
    if engine.dialect.name != "postgresql":
        raise SchemaCheckError("schema_incompatible")
    with engine.connect() as conn:
        try:
            conn.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            conn.exec_driver_sql("SET LOCAL statement_timeout='10s'")
            conn.exec_driver_sql("SET LOCAL lock_timeout='2s'")
            conn.exec_driver_sql("SET LOCAL search_path=pg_catalog,public")
            if conn.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
                raise SchemaCheckError("schema_check_failed")
            return {name: [dict(row) for row in conn.execute(text(query), {"tables": list(TABLES)}).mappings()]
                    for name, query in QUERIES.items()}
        finally:
            conn.rollback()


def load_manifest():
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        catalog = manifest["catalog"]
        tables = {row["table_name"] for row in catalog["tables"]}
        names = {row["conname"] for row in catalog["constraints"]}
        required = {"shifts_vehicle_no_overlap", "shifts_driver_no_overlap",
                    "report_photos_slot_valid", "report_photos_report_slot_key", "photo_operation_owned_path"}
        if manifest["schema"] != REQUIRED_SCHEMA or tables != set(TABLES) or not required <= names:
            raise ValueError("Invalid manifest")
        if set(catalog) != set(QUERIES):
            raise ValueError("Incomplete manifest")
        return catalog
    except (OSError, ValueError, KeyError, TypeError):
        raise SchemaCheckError("schema_checker_invalid") from None


def verify_schema(engine):
    expected = load_manifest()
    try:
        actual = capture_catalog(engine)
    except SchemaCheckError:
        raise
    except SQLAlchemyError:
        raise SchemaCheckError("database_unavailable") from None
    except Exception:
        raise SchemaCheckError("schema_check_failed") from None
    # A conservative contract: drift is reviewed instead of being silently accepted.
    # Operator class labels identify btree_gist membership, not its install schema.
    if actual != expected:
        raise SchemaCheckError("schema_incompatible")
