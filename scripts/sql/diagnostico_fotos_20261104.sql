-- SOLO LECTURA. Ejecutar manualmente en SQL Editor; Codex no lo ejecuta remoto.
-- No generar URLs firmadas ni mover/borrar/reasociar objetos durante el diagnóstico.
BEGIN TRANSACTION READ ONLY;

SELECT current_setting('transaction_read_only') AS transaccion_solo_lectura;

-- 1. Conteo autoritativo, incluso si un ID no existe en este proyecto/esquema.
WITH objetivos(id, etiqueta) AS (
  VALUES
    ('d73343b5-ba92-4ba2-aeb1-f5df2f7ffc64'::uuid, 'nuevo'),
    ('4a474173-d8be-4073-b5f7-08ea1c3bfa4a'::uuid, 'anterior')
)
SELECT t.etiqueta, t.id AS id_buscado, r.id IS NOT NULL AS existe,
       r.description, r.status, r.citizen_id,
       r.created_at, r.created_at AT TIME ZONE 'America/Lima' AS reporte_creado_hora_peru,
       count(p.id) AS fotografias_registradas,
       min(p.created_at) AS primera_foto, max(p.created_at) AS ultima_foto
FROM objetivos t
LEFT JOIN public.reports r ON r.id = t.id
LEFT JOIN public.report_photos p ON p.report_id = r.id
GROUP BY t.etiqueta, t.id, r.id
ORDER BY t.etiqueta;

-- 2. La asociación real es report_photos.report_id; no el nombre de la imagen.
-- Fotos heredadas anteriores a 003 pueden no tener operación durable: NULL no
-- significa corrupción. La migración 003 no reescribe storage_path legado.
SELECT p.id AS photo_id, p.report_id, r.description, p.slot,
       p.content_type, p.size_bytes, p.created_at,
       p.created_at AT TIME ZONE 'America/Lima' AS foto_creada_hora_peru,
       (p.created_at AT TIME ZONE 'America/Lima')::date = DATE '2026-11-04'
         AS registrada_el_04_nov_2026,
       p.storage_path, o.id AS operation_id, o.bucket, o.state AS operation_state,
       CASE WHEN o.id IS NOT NULL THEN p.report_id = o.report_id END
         AS coincide_reporte_con_operacion,
       CASE WHEN o.id IS NOT NULL THEN p.storage_path = o.storage_path END
         AS coincide_ruta_con_operacion,
       CASE WHEN o.id IS NOT NULL THEN
         p.storage_path = 'reports/' || o.actor_id::text || '/' || o.report_id::text
           || '/' || o.id::text || '.' || o.extension
       END AS coincide_ruta_propietaria
FROM public.report_photos p
JOIN public.reports r ON r.id = p.report_id
LEFT JOIN public.photo_upload_operations o ON o.id = p.id
WHERE p.report_id IN (
  'd73343b5-ba92-4ba2-aeb1-f5df2f7ffc64'::uuid,
  '4a474173-d8be-4073-b5f7-08ea1c3bfa4a'::uuid)
ORDER BY p.created_at, p.id;

-- 3. Intentos, incluso cuando no hay fila en report_photos.
-- El OR también revela una referencia inesperada por ID o ruta.
SELECT o.id AS operation_id, o.report_id AS reporte_del_intento, o.actor_id,
       o.state, o.attempts, o.created_at, o.created_at AT TIME ZONE 'America/Lima'
         AS intento_creado_hora_peru,
       o.updated_at, o.next_attempt_at,
       CASE WHEN o.last_error IS NULL THEN NULL
         WHEN o.last_error IN ('commit_unknown','not_uploaded','persistence_failed',
           'upload_unknown','object_preexisting','cleanup_failed','late_upload_watch',
           'ownership_mismatch','reference_mismatch') THEN o.last_error
         ELSE 'unrecognized_error' END AS codigo_error,
       o.bucket, o.storage_path, p.id AS photo_id,
       p.report_id AS reporte_de_la_foto,
       CASE WHEN p.id IS NOT NULL THEN
         p.id = o.id AND p.report_id = o.report_id AND p.storage_path = o.storage_path
       END AS coincide_referencia_completa
FROM public.photo_upload_operations o
LEFT JOIN public.report_photos p ON p.id = o.id OR p.storage_path = o.storage_path
WHERE o.report_id IN (
  'd73343b5-ba92-4ba2-aeb1-f5df2f7ffc64'::uuid,
  '4a474173-d8be-4073-b5f7-08ea1c3bfa4a'::uuid)
  OR p.report_id IN (
  'd73343b5-ba92-4ba2-aeb1-f5df2f7ffc64'::uuid,
  '4a474173-d8be-4073-b5f7-08ea1c3bfa4a'::uuid)
ORDER BY o.created_at, o.id;

-- 4. Inventario de columnas Storage, sin asumir la estructura de sus objetos.
-- 001 define el bucket, pero no el catálogo completo del servicio Storage.
-- Comprobar en el panel el objeto exacto con bucket/storage_path de arriba.
SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'storage'
ORDER BY table_name, ordinal_position;

ROLLBACK;
