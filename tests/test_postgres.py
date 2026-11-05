"""Real deployed PostgreSQL constraints; all INSERTs are unconditionally rolled back."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from psycopg import sql

from postgres_support import TABLES, connect, evidence, snapshot, transaction

pytestmark = pytest.mark.skipif(
    not os.getenv("RECIWISE_TEST_DATABASE_URL")
    or os.getenv("RECIWISE_ALLOW_ROLLBACK_TESTS") != "1",
    reason="Explicit PostgreSQL URL and RECIWISE_ALLOW_ROLLBACK_TESTS=1 required",
)


@pytest.fixture(scope="module")
def connection():
    conn = connect()
    try:
        with transaction(conn, readonly=True):
            # Refuse writes if unknown user triggers/rules could have side effects.
            triggers = conn.execute("""
                SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relname=ANY(%s) AND NOT t.tgisinternal
            """, (list(TABLES),)).fetchone()[0]
            rules = conn.execute("""SELECT count(*) FROM pg_rules
                WHERE schemaname='public' AND tablename=ANY(%s)""", (list(TABLES),)).fetchone()[0]
            assert triggers == rules == 0, "Review custom triggers/rules before rollback writes"
            before = snapshot(conn)
            role = conn.execute("""SELECT current_setting('server_version'),
                r.rolsuper, r.rolbypassrls FROM pg_roles r WHERE r.rolname=current_user"""
            ).fetchone()
            constraints = conn.execute("""SELECT c.relname,p.conname,p.contype,p.convalidated,
                pg_get_constraintdef(p.oid) FROM pg_constraint p
                JOIN pg_class c ON c.oid=p.conrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relname=ANY(%s)
                ORDER BY c.relname,p.conname""", (list(TABLES),)).fetchall()
            policies = conn.execute("""SELECT tablename,policyname,roles,cmd
                FROM pg_policies WHERE schemaname='public' AND tablename=ANY(%s)""",
                (list(TABLES),)).fetchall()
            evidence("postgres-catalog.json", {
                "server_version": role[0], "custom_triggers": triggers, "custom_rules": rules,
                "constraints": constraints, "policies": policies,
            })
        yield conn
        with transaction(conn, readonly=True):
            after = snapshot(conn)
        evidence("postgres-unchanged.json", {
            "server_version": role[0], "administrative_superuser": role[1],
            "administrative_bypassrls": role[2], "before": before, "after": after,
            "unchanged": before == after,
        })
        assert before == after, "S1 data changed during tests; inspect external concurrent writes"
    finally:
        conn.close()


@pytest.fixture
def pg(connection):
    with transaction(connection) as conn:
        yield conn


def insert(pg, table, values):
    columns = list(values)
    return pg.execute(sql.SQL("INSERT INTO public.{} ({}) VALUES ({}) RETURNING id").format(
        sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    ), [values[column] for column in columns]).fetchone()[0]


@pytest.fixture
def records(pg):
    profiles = dict(pg.execute("SELECT role,id FROM public.profiles").fetchall())
    required = {"ciudadano", "encargado_municipal", "chofer"}
    if not required <= profiles.keys():
        pytest.skip("Existing citizen/manager/driver profiles required; no auth users created")
    now = datetime.now(timezone.utc)
    return {
        "profiles": profiles,
        "reports": dict(id=uuid.uuid4(), citizen_id=profiles["ciudadano"],
                        description="Prueba temporal con rollback", latitude=-12.0,
                        longitude=-77.0, observed_at=now, status="recibido"),
        "vehicles": dict(id=uuid.uuid4(), label=f"rollback-{uuid.uuid4()}",
                         vehicle_type="compactadora", capacity_kg=1000.0),
        "service_sites": dict(id=uuid.uuid4(), name="Sitio temporal rollback",
                              site_type="ambos", latitude=-12.0, longitude=-77.0),
        "now": now,
    }


def graph(pg, records):
    report = insert(pg, "reports", records["reports"])
    vehicle = insert(pg, "vehicles", records["vehicles"])
    departure = insert(pg, "service_sites", dict(records["service_sites"], site_type="salida"))
    disposal = insert(pg, "service_sites", dict(records["service_sites"],
                                               id=uuid.uuid4(), site_type="descarga"))
    photo = dict(id=uuid.uuid4(), report_id=report, slot=1,
                 storage_path=f"rollback-only/{uuid.uuid4()}.jpg",
                 content_type="image/jpeg", size_bytes=100)
    shift = dict(id=uuid.uuid4(), vehicle_id=vehicle, driver_id=records["profiles"]["chofer"],
                 departure_site_id=departure, disposal_site_id=disposal,
                 created_by=records["profiles"]["encargado_municipal"],
                 starts_at=records["now"], ends_at=records["now"] + timedelta(hours=1),
                 status="programado")
    return photo, shift


@pytest.mark.parametrize("table,field,value", [
    ("reports", "latitude", -90.01), ("reports", "latitude", 90.01),
    ("reports", "longitude", -180.01), ("reports", "longitude", 180.01),
    ("reports", "description", ""), ("reports", "description", "   "),
    ("reports", "description", " a "), ("reports", "description", " ab "),
    ("reports", "description", "x" * 2001),
    ("reports", "status", "inventado"),
    ("vehicles", "capacity_kg", 0), ("vehicles", "capacity_kg", -1),
    ("vehicles", "vehicle_type", "inventado"),
    ("service_sites", "site_type", "inventado"),
    ("service_sites", "latitude", -90.01), ("service_sites", "latitude", 90.01),
    ("service_sites", "longitude", -180.01), ("service_sites", "longitude", 180.01),
], ids=[
    "report-south", "report-north", "report-west", "report-east",
    "description-empty", "description-spaces", "description-trim-one",
    "description-trim-two", "description-long", "report-status",
    "capacity-zero", "capacity-negative", "vehicle-type", "site-type",
    "site-south", "site-north", "site-west", "site-east",
])
def test_check_constraints(pg, records, table, field, value):
    with pytest.raises(psycopg.errors.CheckViolation) as exc:
        insert(pg, table, dict(records[table], **{field: value}))
    assert exc.value.sqlstate == "23514"


@pytest.mark.parametrize("description", ["abc", " abc ", "x" * 2000, " " + "x" * 2000 + " "])
def test_description_valid_boundaries(pg, records, description):
    record_id = insert(pg, "reports", dict(records["reports"], description=description))
    assert pg.execute("SELECT description FROM public.reports WHERE id=%s", (record_id,)).fetchone()[0] == description


@pytest.mark.parametrize("latitude,longitude", [(-90, -180), (90, 180)])
def test_coordinate_valid_boundaries(pg, records, latitude, longitude):
    for table in ("reports", "service_sites"):
        insert(pg, table, dict(records[table], latitude=latitude, longitude=longitude))


@pytest.mark.parametrize("field,value", [("status", "inventado"), ("ends_at", 0), ("ends_at", -1)])
def test_shift_check_constraints(pg, records, field, value):
    _, shift = graph(pg, records)
    shift[field] = shift["starts_at"] + timedelta(seconds=value) if field == "ends_at" else value
    with pytest.raises(psycopg.errors.CheckViolation) as exc:
        insert(pg, "shifts", shift)
    assert exc.value.sqlstate == "23514"


@pytest.mark.parametrize("field", ["id", "label"])
def test_vehicle_unique_identifiers(pg, records, field):
    insert(pg, "vehicles", records["vehicles"])
    duplicate = dict(records["vehicles"], id=uuid.uuid4(), label=f"rollback-{uuid.uuid4()}")
    duplicate[field] = records["vehicles"][field]
    with pytest.raises(psycopg.errors.UniqueViolation) as exc:
        insert(pg, "vehicles", duplicate)
    assert exc.value.sqlstate == "23505"


@pytest.mark.parametrize("table,field", [
    ("profiles", "id"), ("reports", "citizen_id"), ("report_photos", "report_id"),
    ("shifts", "vehicle_id"), ("shifts", "driver_id"),
    ("shifts", "departure_site_id"), ("shifts", "disposal_site_id"), ("shifts", "created_by"),
])
def test_foreign_keys(pg, records, table, field):
    photo, shift = graph(pg, records)
    values = {"profiles": dict(id=uuid.uuid4(), role="ciudadano"),
              "reports": dict(records["reports"], id=uuid.uuid4()),
              "report_photos": photo, "shifts": shift}[table]
    values[field] = uuid.uuid4()
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as exc:
        insert(pg, table, values)
    assert exc.value.sqlstate == "23503"


def test_profile_report_photo_vehicle_site_shift_relationships(pg, records):
    photo, shift = graph(pg, records)
    photo_id = insert(pg, "report_photos", photo)
    shift_id = insert(pg, "shifts", shift)
    row = pg.execute("""SELECT p.role, ph.id, v.id, d.site_type, x.site_type, dr.role, m.role
        FROM public.reports r JOIN public.profiles p ON p.id=r.citizen_id
        JOIN public.report_photos ph ON ph.report_id=r.id
        JOIN public.shifts s ON s.id=%s JOIN public.vehicles v ON v.id=s.vehicle_id
        JOIN public.service_sites d ON d.id=s.departure_site_id
        JOIN public.service_sites x ON x.id=s.disposal_site_id
        JOIN public.profiles dr ON dr.id=s.driver_id JOIN public.profiles m ON m.id=s.created_by
        WHERE r.id=%s""", (shift_id, photo["report_id"])).fetchone()
    assert row == ("ciudadano", photo_id, shift["vehicle_id"], "salida", "descarga",
                   "chofer", "encargado_municipal")


def test_existing_relationships_are_consistent(pg):
    # Read existing rows, including auth.users FK; never modify those records.
    checks = [
        "SELECT count(*) FROM public.profiles p LEFT JOIN auth.users u ON u.id=p.id WHERE u.id IS NULL",
        """SELECT count(*) FROM public.reports r LEFT JOIN public.profiles p ON p.id=r.citizen_id
            WHERE p.id IS NULL OR p.role<>'ciudadano'""",
        """SELECT count(*) FROM public.report_photos ph LEFT JOIN public.reports r ON r.id=ph.report_id
            WHERE r.id IS NULL""",
        """SELECT count(*) FROM public.shifts s
            LEFT JOIN public.vehicles v ON v.id=s.vehicle_id
            LEFT JOIN public.profiles d ON d.id=s.driver_id
            LEFT JOIN public.profiles m ON m.id=s.created_by
            LEFT JOIN public.service_sites a ON a.id=s.departure_site_id
            LEFT JOIN public.service_sites b ON b.id=s.disposal_site_id
            WHERE v.id IS NULL OR d.id IS NULL OR m.id IS NULL OR a.id IS NULL OR b.id IS NULL
               OR d.role<>'chofer' OR m.role<>'encargado_municipal'
               OR a.site_type NOT IN ('salida','ambos') OR b.site_type NOT IN ('descarga','ambos')""",
    ]
    assert all(pg.execute(query).fetchone()[0] == 0 for query in checks)


@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize("table", TABLES)
def test_direct_access_denied_under_user_sql_role(pg, role, table):
    # Impersonates SQL role, NOT an authenticated Supabase JWT connection.
    pg.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
    assert pg.execute("SELECT current_user").fetchone()[0] == role
    assert pg.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone() == (False, False)
    with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc:
        pg.execute(sql.SQL("SELECT * FROM public.{} LIMIT 1").format(sql.Identifier(table)))
    assert exc.value.sqlstate == "42501"


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_rls_and_all_table_privileges(pg, role):
    rows = pg.execute("""SELECT c.relname,c.relrowsecurity,
        has_table_privilege(%s,c.oid,'SELECT'),has_table_privilege(%s,c.oid,'INSERT'),
        has_table_privilege(%s,c.oid,'UPDATE'),has_table_privilege(%s,c.oid,'DELETE')
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname=ANY(%s)""", (role, role, role, role, list(TABLES))).fetchall()
    assert len(rows) == len(TABLES)
    assert all(row[1:] == (True, False, False, False, False) for row in rows)
