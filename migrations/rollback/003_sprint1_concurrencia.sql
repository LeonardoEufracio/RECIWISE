-- Reversal is NOT authorized on shared Supabase. Stop writers/reconciler first.
-- Refuse to discard unfinished cleanup work. Export/archive the journal first.
BEGIN;
SET LOCAL lock_timeout = '5s';
LOCK TABLE public.shifts,public.report_photos,public.photo_upload_operations IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM public.photo_upload_operations
             WHERE state NOT IN ('complete','cleaned','rejected')) THEN
    RAISE EXCEPTION '003 rollback blocked: unresolved photo operations';
  END IF;
END $$;
-- Preserve the journal, including its RLS/ACLs. No data rows or objects deleted.
ALTER TABLE public.photo_upload_operations RENAME TO photo_upload_operations_archive_003;
ALTER INDEX public.photo_operations_due_idx RENAME TO photo_operations_archive_003_due_idx;
ALTER TABLE public.photo_upload_operations_archive_003 RENAME CONSTRAINT photo_upload_operations_pkey
  TO photo_upload_operations_archive_003_pkey;
ALTER TABLE public.photo_upload_operations_archive_003 RENAME CONSTRAINT photo_upload_operations_storage_path_key
  TO photo_upload_operations_archive_003_storage_path_key;
ALTER TABLE public.report_photos DROP CONSTRAINT report_photos_report_slot_key;
ALTER TABLE public.report_photos DROP CONSTRAINT report_photos_slot_valid;
ALTER TABLE public.report_photos DROP COLUMN slot;
ALTER TABLE public.shifts DROP CONSTRAINT shifts_driver_no_overlap;
ALTER TABLE public.shifts DROP CONSTRAINT shifts_vehicle_no_overlap;
-- Do not drop btree_gist: other database objects can depend on it.
COMMIT;
