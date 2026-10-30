"""Only localhost + a per-run database name + an in-database random marker.

Never read .env. This guard is mandatory before tests that commit or migrate.
"""
import os
import uuid
from pathlib import Path

import psycopg
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def connection(url=None, *, verify=True):
    target = make_url(url or os.environ["RECIWISE_TEST_DATABASE_URL"])
    marker = os.environ.get("RECIWISE_ISOLATED_TOKEN", "")
    if (target.get_backend_name() != "postgresql" or target.host != "127.0.0.1"
            or not marker or target.database != "reciwise_test_" + marker):
        raise RuntimeError("Refusing a database without the isolated localhost identity")
    conn = psycopg.connect(host=target.host, port=target.port, dbname=target.database,
                           user=target.username, autocommit=True, connect_timeout=5)
    if verify:
        try:
            row = conn.execute("SELECT token FROM public.reciwise_test_environment").fetchone()
            assert row == (marker,), "Isolated database marker mismatch"
        except BaseException:
            conn.close()
            raise
    return conn


def bootstrap(url, *, migrated=True, roles=True):
    conn = connection(url, verify=False)
    try:
        if roles:
            conn.execute("CREATE ROLE anon NOLOGIN NOSUPERUSER NOBYPASSRLS")
            conn.execute("CREATE ROLE authenticated NOLOGIN NOSUPERUSER NOBYPASSRLS")
        # Stubs for foreign schemas, not a substitute for testing Supabase Auth/Storage.
        conn.execute("CREATE SCHEMA auth; CREATE TABLE auth.users(id uuid PRIMARY KEY)")
        conn.execute("""CREATE SCHEMA storage; CREATE TABLE storage.buckets(
            id text PRIMARY KEY,name text,public boolean,file_size_limit bigint,allowed_mime_types text[])"""
        )
        conn.execute("CREATE TABLE public.reciwise_test_environment(token text NOT NULL)")
        conn.execute("INSERT INTO public.reciwise_test_environment VALUES (%s)",
                     (os.environ["RECIWISE_ISOLATED_TOKEN"],))
        conn.execute((ROOT / "migrations/001_sprint1.sql").read_text(encoding="utf-8"))
        if migrated:
            conn.execute((ROOT / "migrations/003_sprint1_concurrencia.sql").read_text(encoding="utf-8"))
        profiles = {}
        for name, role in [("citizen", "ciudadano"), ("manager", "encargado_municipal"),
                           ("driver", "chofer"), ("driver2", "chofer")]:
            key = uuid.uuid4()
            conn.execute("INSERT INTO auth.users(id) VALUES (%s)", (key,))
            conn.execute("UPDATE public.profiles SET role=%s WHERE id=%s", (role, key))
            profiles[name] = str(key)
        return profiles
    finally:
        conn.close()
