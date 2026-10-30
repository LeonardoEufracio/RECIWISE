-- RECIWISE D2 / 003. Apply only to the explicitly isolated test database for now.
-- Stop writes during application; deploy the matching backend before resuming.
-- 001 and 002 are intentionally unchanged. Never repair conflicting data here.
BEGIN;
SET LOCAL lock_timeout = '5s';
LOCK TABLE public.shifts, public.report_photos IN ACCESS EXCLUSIVE MODE;

DO $$ BEGIN
  IF EXISTS (
    SELECT 1 FROM public.shifts a JOIN public.shifts b ON a.id < b.id
      AND (a.vehicle_id=b.vehicle_id OR a.driver_id=b.driver_id)
      AND a.starts_at < b.ends_at AND b.starts_at < a.ends_at
    WHERE a.status='programado' AND b.status='programado'
  ) THEN
    RAISE EXCEPTION '003 blocked: existing overlapping scheduled shifts';
  END IF;
  IF EXISTS (SELECT 1 FROM public.report_photos GROUP BY report_id HAVING count(*)>3) THEN
    RAISE EXCEPTION '003 blocked: existing reports with more than three photos';
  END IF;
END $$;

-- Respect an existing extension schema (including Supabase's extensions schema).
CREATE EXTENSION IF NOT EXISTS btree_gist;
DO $$ DECLARE extension_schema text; BEGIN
  SELECT n.nspname INTO extension_schema FROM pg_extension e
    JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='btree_gist';
  PERFORM set_config('search_path', format('pg_catalog, public, %I', extension_schema), true);
END $$;

ALTER TABLE public.shifts ADD CONSTRAINT shifts_vehicle_no_overlap
  EXCLUDE USING gist (vehicle_id WITH =, tstzrange(starts_at,ends_at,'[)') WITH &&)
  WHERE (status='programado');
ALTER TABLE public.shifts ADD CONSTRAINT shifts_driver_no_overlap
  EXCLUDE USING gist (driver_id WITH =, tstzrange(starts_at,ends_at,'[)') WITH &&)
  WHERE (status='programado');

ALTER TABLE public.report_photos ADD COLUMN slot smallint;
WITH numbered AS (
  SELECT id,row_number() OVER (PARTITION BY report_id ORDER BY created_at,id) AS position
  FROM public.report_photos
) UPDATE public.report_photos p SET slot=n.position FROM numbered n WHERE n.id=p.id;
ALTER TABLE public.report_photos ALTER COLUMN slot SET NOT NULL;
ALTER TABLE public.report_photos ADD CONSTRAINT report_photos_slot_valid CHECK (slot BETWEEN 1 AND 3);
ALTER TABLE public.report_photos ADD CONSTRAINT report_photos_report_slot_key UNIQUE (report_id,slot);

-- Durable intent is committed before uploading. Successful metadata and the
-- 'complete' state are committed together. No credentials or image bytes here.
CREATE TABLE public.photo_upload_operations (
  id uuid PRIMARY KEY,
  actor_id uuid NOT NULL REFERENCES public.profiles(id),
  report_id uuid NOT NULL REFERENCES public.reports(id),
  bucket text NOT NULL CHECK (char_length(bucket) BETWEEN 1 AND 100),
  storage_path text NOT NULL UNIQUE,
  extension text NOT NULL CHECK (extension IN ('jpg','png','webp')),
  state text NOT NULL DEFAULT 'pending' CHECK (state IN
    ('pending','complete','cleanup_pending','quarantined','cleaned','rejected','review')),
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts>=0),
  last_error varchar(80),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  next_attempt_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT photo_operation_owned_path CHECK (
    storage_path='reports/' || actor_id::text || '/' || report_id::text || '/' || id::text || '.' || extension
  )
);
CREATE INDEX photo_operations_due_idx ON public.photo_upload_operations(next_attempt_at,id)
  WHERE state IN ('pending','cleanup_pending','quarantined');
ALTER TABLE public.photo_upload_operations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.photo_upload_operations FROM PUBLIC,anon,authenticated;
COMMIT;
