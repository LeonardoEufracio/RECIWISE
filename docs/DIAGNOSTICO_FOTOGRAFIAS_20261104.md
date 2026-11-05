# Fotografías y asociación a reportes — 4 de noviembre de 2026

## Conclusión y alcance

**No está confirmada una asociación equivocada en Supabase.** Codex no se conectó al proyecto principal ni consultó/modificó datos persistentes. El usuario compartió el resultado SQL ejecutado manualmente: 0 fotografías para `d73343b5-ba92-4ba2-aeb1-f5df2f7ffc64` y 2 para `4a474173-d8be-4073-b5f7-08ea1c3bfa4a`. Son resultados proporcionados por el usuario, no consultas remotas ejecutadas por Codex.

Se confirmó y corrigió un error **de visualización local**: tras POST de foto 201, si falla el GET posterior (por ejemplo al firmar una URL), `Photos` conservaba el array vacío anterior. Podía mostrar simultáneamente «Fotografía guardada», «Fotografías (0/3)», «Este reporte no tiene fotografías» y un error de lectura. **Ese escenario no demuestra que la fotografía se haya guardado en otro reporte.**

También se reprodujeron respuestas tardías que sobrescribían un resultado más reciente o el de otro `reportId` al reutilizar directamente el componente. Los padres actuales ya usan tarjetas con `key={report.id}`, lo que reduce la exposición a esa reutilización; no se atribuye por ello ese escenario al incidente real. El aislamiento y la cancelación se incorporaron al propio componente.

El detalle manual confirma consistencia entre fotografía, operación y ruta del reporte anterior. La consulta de operaciones compartida contiene una sola fila, correspondiente al anterior; no hay un intento durable del nuevo en ese resultado. El `0/3` del nuevo refleja la ausencia de fotografías persistidas, sin evidencia de reasociación. No puede determinarse si hubo una petición rechazada antes del diario sin evidencia HTTP. No se reasoció, movió o eliminó ninguna fotografía.

## Evidencia real compartida por el usuario

Resultado de la consulta de conteos del diagnóstico, recibido el 4 de noviembre de 2026. Ambos reportes existen, están en estado `recibido` y pertenecen al mismo ciudadano. Se omite aquí su identificador.

| Registro | Fecha almacenada UTC | Hora de Perú (UTC−05:00) | Evidencia |
| --- | --- | --- | --- |
| Creación del reporte anterior | 2026-10-28 14:51:04.694873+00 | 2026-10-28 09:51:04.694873 | Reporte existente antes del incidente |
| Primera foto del anterior | 2026-10-28 15:46:41.473010+00 | 2026-10-28 10:46:41.473010 | Una de sus dos fotos tiene fecha del 28 de octubre |
| Última foto del anterior | 2026-11-04 23:52:39.198371+00 | 2026-11-04 18:52:39.198371 | La otra foto tiene fecha del 4 de noviembre |
| Creación del reporte nuevo | 2026-11-04 23:54:20.461205+00 | 2026-11-04 18:54:20.461205 | Tiene 0 filas de fotografías; fechas primera/última NULL |

La fecha registrada de la última foto del anterior precede la creación del nuevo por **101,262834 segundos**. Según estas fechas, no hay evidencia de que esa foto se enviara después de crear el nuevo y terminara en el anterior. Es compatible con una subida dirigida al reporte anterior antes de crear el nuevo, pero el conteo no demuestra la secuencia de clics ni qué archivo quiso adjuntar el usuario. Las fechas de las filas tampoco sustituyen la evidencia de inicio/final de la petición HTTP.

### Detalle de fotografías recibido posteriormente

El usuario compartió también el resultado de la consulta 2:

| Fotografía | Reporte asociado | Posición | Operación durable | Comprobaciones |
| --- | --- | ---: | --- | --- |
| `c61aa36c-3de3-4dc0-8a4c-2b89352a7048`, del 28 de octubre | `4a474173-d8be-4073-b5f7-08ea1c3bfa4a` | 1 | NULL | `coincide_*` NULL; compatible con una foto heredada sin diario |
| `b8fafbeb-2c24-4451-aefb-8f604490b806`, del 4 de noviembre | `4a474173-d8be-4073-b5f7-08ea1c3bfa4a` | 2 | Mismo UUID de la foto, estado `complete` | Reporte, ruta y ruta propietaria: las tres `true` |

La foto del 4 de noviembre es JPEG, de 4190 bytes, con fecha local `2026-11-04 18:52:39.198371`. Su clave incluye el UUID del reporte anterior y termina con su propio UUID `.jpg`; el diario identifica el bucket `reciwise-reportes`. Se omite la ruta completa que contiene el identificador del ciudadano.

**Conclusión comprobada en los resultados compartidos:** no hay discrepancia entre `report_photos`, la operación durable y la ruta registrada para esa foto. El sistema la registró consistentemente para el reporte anterior, con una fecha previa a la creación del nuevo. Esto no demuestra qué reporte pretendía seleccionar el usuario ni verifica por sí solo la existencia/descarga actual del objeto físico. La hipótesis de que el backend desvió al anterior una foto enviada después de crear el nuevo no está respaldada por esta evidencia.

La foto del 28 de octubre sin operación durable no constituye por sí sola una anomalía: 003 no crea diarios retroactivos para fotografías heredadas.

### Operaciones durables: resultado de la consulta 3

El resultado compartido contiene una sola operación, `b8fafbeb-2c24-4451-aefb-8f604490b806`, para el reporte anterior. Su `photo_id` es el mismo UUID, `reporte_del_intento` coincide con `reporte_de_la_foto` y `coincide_referencia_completa` es `true`.

| Campo | Resultado compartido |
| --- | --- |
| Estado | `complete` |
| Reintentos registrados, `attempts` | 0 |
| Código de error | NULL |
| Creación de la operación, hora de Perú | 2026-11-04 18:52:38.618255 |
| Última actualización, hora de Perú | 2026-11-04 18:52:41.656744 |

La última actualización de esta operación actualmente completada es **98,804461 segundos anterior** a la creación del reporte nuevo. Es consistente con la cronología de la foto; `updated_at` no es un registro HTTP ni una marca independiente del instante exacto del commit. Un `next_attempt_at` almacenado no convierte una operación `complete` en una pendiente.

**No aparecen operaciones para el reporte nuevo en el resultado recibido.** Por tanto, no hay evidencia en ese resultado de una subida pendiente, compensación o commit incierto para el nuevo. No equivale a demostrar que nunca se intentó una petición: una petición puede fallar antes de crear el diario, no llegar a FastAPI o dirigirse a otro destino. Tampoco este resultado comprueba por sí solo todos los objetos físicos del bucket.

En el momento del SQL, el `0/3` del nuevo coincide con PostgreSQL: **no se explica únicamente por el contador obsoleto corregido**. La hipótesis compatible con las fechas es una subida al anterior seguida de la creación del nuevo sin una fotografía persistida para este último; la intención y secuencia de clics no quedan probadas. Crear el reporte y adjuntar el archivo son operaciones separadas en el frontend actual.

El diagnóstico de asociación queda documentado **sin fallo de reasociación demostrado y sin reparación de datos justificada**. La corrección preventiva de visualización y respuestas tardías sigue respaldada por las pruebas locales, pero no se presenta como causa del caso real. Solo si se necesita reconstruir un intento adicional faltaría su pathname/código HTTP original, si se conservó, sin cabeceras, tokens o URLs firmadas. No hace falta solicitar más conteos ni repetir estos tres resultados SQL.

No se requiere repetir ninguna subida ni crear reportes para obtener esta evidencia. No hay autorización para mover la foto del anterior al nuevo.

## Seguimiento del ID en el código

1. `ReportForm.tsx`: espera el objeto retornado por POST `/reports`; llama `onCreated(report)` con ese mismo objeto. Crear un reporte **no sube una fotografía**: son dos operaciones distintas.
2. `App.tsx`: `created(report)` conserva `report.id` en `createdReportId` e incrementa la revisión del listado.
3. `Reports.tsx`: consulta `/reports/mine`, vuelve a la primera página y abre las fotografías del ID creado. Cada tarjeta tiene `key={report.id}` y pasa **su propio ID** a `Photos`. No hay un «último ID» global utilizado para las subidas.
4. `Photos.tsx`: el archivo viaja como campo multipart `file`; el destino está en **POST `/reports/{reportId}/photos`**, capturado al iniciar esa subida. El archivo no contiene un campo alternativo `report_id` que pueda cambiar el destino.
5. FastAPI `upload_photo`: autoriza al ciudadano propietario del ID de la ruta, valida tamaño/formato y pasa ese mismo ID a `PhotoUploads.create`.
6. `PhotoUploads.create`: usa el mismo `report_id` para el registro durable, el bloqueo, la reserva de posición, `report_photos.report_id` y la ruta `reports/{actor_id}/{report_id}/{operation_id}.{extension}`. No busca el reporte más reciente ni depende del orden de inserción.
7. GET `/reports/{report_id}/photos`: autoriza ese reporte y filtra **`ReportPhoto.report_id == report_id`**. Firma la ruta almacenada de cada fila; no obtiene fotografías desde un listado global del bucket.

**Conteo y objeto no son lo mismo:** un GET exitoso con `[]` significa ausencia de filas visibles para ese reporte en esa consulta. Un archivo ausente, una URL vencida o un fallo de firma no convierten por sí solos una lista de metadatos en una lista vacía; pueden impedir la descarga o hacer fallar el GET. Antes de esta corrección, ese fallo podía dejar visible un cero antiguo.

`/ready` con `schema: 003` comprueba la preparación del esquema PostgreSQL; no demuestra que Storage pueda subir objetos o firmar sus URLs.

## Corrección limitada

Solo se modificó lógica funcional en `frontend/src/Photos.tsx`:

- Estado, formulario de archivo y bloqueo de subida aislados por `reportId` mediante una clave interna.
- Lecturas con `AbortController` y versión; se ignoran respuestas obsoletas o de componentes desmontados, incluso si el cliente simulado no respeta la cancelación.
- Al consultar/renovar, el conteo pasa a **desconocido**, no a cero. Solo un GET exitoso con `[]` muestra «Este reporte no tiene fotografías». Una lectura fallida permite renovar, pero no habilita otra subida sobre un conteo no confirmado.
- Una subida iniciada para A conserva su destino A. Si se abre B o se desmonta A, su finalización no altera B ni lanza una lectura tardía desde el componente descartado. No se cancela el POST en curso, para no confundir cancelación del navegador con resultado de commit.
- Se muestra el UUID del reporte dentro del panel de fotografías para comprobar el destino antes de enviar.

No se cambiaron `ReportCreate`, `PhotoOut`, endpoints, JWT, roles, permisos, Storage, conciliación ni migraciones.

## Consultas SQL de solo lectura

Archivo: [scripts/sql/diagnostico_fotos_20261104.sql](../scripts/sql/diagnostico_fotos_20261104.sql).

Ejecutarlo **manualmente** en el proyecto que el usuario está verificando. Está envuelto en `BEGIN TRANSACTION READ ONLY` / `ROLLBACK`. Su sintaxis y los nombres de tablas/columnas se comprobaron sobre PostgreSQL aislado con 001+002+003. Los UUID reales no existían en esa base de pruebas; ese ensayo **no aporta sus conteos reales**.

Una consulta breve equivalente para el conteo, sin acceso a Storage:

```sql
BEGIN TRANSACTION READ ONLY;
SELECT r.id, r.description, count(p.id) AS fotos,
       max(p.created_at) AT TIME ZONE 'America/Lima' AS ultima_foto_hora_peru
FROM public.reports r
LEFT JOIN public.report_photos p ON p.report_id = r.id
WHERE r.id IN (
  'd73343b5-ba92-4ba2-aeb1-f5df2f7ffc64'::uuid,
  '4a474173-d8be-4073-b5f7-08ea1c3bfa4a'::uuid)
GROUP BY r.id
ORDER BY r.id;
ROLLBACK;
```

El archivo completo añade detección de IDs inexistentes, detalle de `photo_id`, posición, tamaño, tipo, fechas en Perú, ruta y relación con `photo_upload_operations`. También muestra intentos sin fotografía persistida, estado/reintentos y coincidencia de referencia. El 4 de noviembre se evalúa en `America/Lima`, no por la fecha UTC sin convertir.

Las fotografías heredadas pueden no tener operación durable: migrar 003 añade posiciones, pero **no reescribe sus rutas ni crea un diario retroactivo**. Una operación NULL no demuestra error. Las comparaciones estrictas de ruta se aplican solo si existe esa operación.

001 crea/configura el bucket pero no define todo el catálogo interno de Storage. Por eso el script inspecciona `information_schema.columns` en vez de inventar columnas o hacer un JOIN supuesto con objetos de Storage. Para comprobar existencia física, revisar manualmente el **bucket y la clave exacta** que aparecen en el diario/fila; no buscar por el nombre original del archivo, que `report_photos` no almacena. No generar enlaces, mover ni borrar archivos durante esta comprobación.

SQL Editor suele tener una conexión administrativa: estos resultados comprueban filas, **no prueban RLS ni el acceso de una sesión ciudadana**.

## Evidencia para distinguir las causas

| Evidencia | Interpretación y siguiente paso |
| --- | --- |
| No hubo POST de fotografía después del POST de reporte 201 | El reporte se creó sin adjuntar una foto. Revisar la tarjeta/destino seleccionado, no reasociar nada. |
| POST `/reports/NUEVO/photos` devuelve 4xx/5xx y GET devuelve `[]` | Subida no confirmada o rechazada. Revisar el diario y volver a consultar antes de reintentar; no asumir que llegó al anterior. |
| Diario `pending`/`quarantined`, sin `report_photos` | Intento durable con desenlace pendiente/incierto; puede haber un objeto sin metadatos. No ejecutar conciliación remota o borrados como parte de este diagnóstico. |
| POST de foto 201 con `report_id=NUEVO`; GET falla; SQL muestra foto de NUEVO | Fallo de consulta/firma/visualización. Corregido el contador obsoleto; renovar enlaces, sin repetir POST. |
| GET `/reports/NUEVO/photos` devuelve fotos de NUEVO, pero la tarjeta muestra 0 u otra imagen | Investigar estado/frontend y versión cargada. Guardar únicamente IDs, ruta HTTP y código; no URLs firmadas. |
| POST `/reports/ANTERIOR/photos` 201 y SQL identifica esa misma `photo_id` en ANTERIOR | La petición se dirigió al anterior. Investigar la selección y orden de acciones. El backend sigue la ruta recibida; no trasladar la foto sin autorización. |
| SQL de NUEVO tiene filas, pero GET del mismo ID responde 200 `[]` | Contrastar API/proyecto/esquema/versión y actor. No inferir que un objeto del bucket determina la asociación de PostgreSQL. |
| IDs/rutas entre foto y operación no coinciden, o `complete` sin fila correspondiente | Inconsistencia que requiere evidencia y revisión; no resolver automáticamente mediante SQL ni conciliación. |
| Foto del anterior tiene fecha del 4 de noviembre | Indicio temporal, no prueba de que sea el archivo en cuestión. Identificar `photo_id` y petición; las dos imágenes previas no demuestran una subida nueva. |

Si no se conservó Network de la subida original, SQL/fechas no reconstruyen la intención del usuario ni el orden de clics. No se declara una causa histórica sin esa evidencia.

## Límite de tres y conciliación, revisados sin modificarlos

003 exige `slot NOT NULL`, `CHECK slot BETWEEN 1 AND 3` y `UNIQUE(report_id, slot)`; la subida bloquea el reporte y asigna una posición libre. La operación durable y la fotografía comparten UUID/ruta y completan su transacción antes de responder. Las restricciones y los permisos se conservan.

El conciliador bloquea/reclama trabajo, comprueba referencias por ID/ruta y no reasocia `report_photos.report_id`. Conserva archivos referenciados y marca referencias incompatibles para revisión; ante commit incierto no borra en la petición y resuelve el estado antes de una limpieza. Las pruebas de esta revisión se ejecutan con PostgreSQL desechable y Storage simulado, no con Supabase real.

## Regresiones y verificación

- Cuatro casos de `Photos.test.tsx` fallaron **antes** de corregir el componente y pasan después: GET fallido tras POST 201, respuesta de otro ID tardía, lectura obsoleta del mismo ID y subida A terminando mientras se muestra B.
- `App.test.tsx`: dos reportes consecutivos, archivos con nombres/contenido diferentes, fallo del segundo y reintento manual al mismo ID; se comprueban las rutas exactas y que solo se crean dos reportes.
- Recorrido nuevo en `sprint1.spec.ts`: dos PNG válidos de colores distintos, HTTP real a FastAPI, filas en PostgreSQL y descarga desde Storage simulado con SHA-256 distintos. Verifica fallo de Storage, ausencia de reintento automático, POST al ID correcto, diario, rutas, recarga e imágenes visibles. Reutiliza los helpers existentes.
- `test_photo_concurrency.py`: una prueba adicional ejecuta el script SQL en transacción de solo lectura y comprueba ausencia de cambios. Las pruebas existentes cubren independencia de reportes, cuota, autorización, fallos y recuperación.

Comandos locales (Docker Desktop local activo; no usar un Uvicorn conectado al principal):

```powershell
Set-Location 'C:\Users\DELL INSPIRON\Documents\RECIWISE\frontend'
npm.cmd run check
Set-Location ..
.\.venv\Scripts\python.exe tests\run_isolated_postgres.py --phase photos
.\.venv\Scripts\python.exe tests\run_isolated_postgres.py --phase recovery
.\.venv\Scripts\python.exe tests\run_isolated_postgres.py --phase reconciler
.\.venv\Scripts\python.exe tests\run_isolated_postgres.py --phase integrated
```

El integrado comprueba TypeScript, Vitest y build con configuración pública ficticia y puertos propios. Auth, Storage y teselas están simulados; React, Leaflet, FastAPI y PostgreSQL son reales. No se usan las credenciales de `.env`.

### Resultados ejecutados el 4 de noviembre de 2026

| Comprobación | Aprobadas | Fallidas | Omitidas | Evidencia local |
| --- | ---: | ---: | ---: | --- |
| Frontend completo, `npm.cmd run check` y repetición dentro del integrado | 145 | 0 | 0 | `vitest.json`; TypeScript sin errores |
| PostgreSQL aislado, fase `photos` | 13 | 0 | 0 | JUnit `pytest.xml` |
| PostgreSQL aislado, fase `recovery` | 19 | 0 | 0 | JUnit `pytest.xml` |
| PostgreSQL aislado, fase `reconciler` | 15 | 0 | 0 | JUnit `pytest.xml` |
| Navegador con React + FastAPI + PostgreSQL aislado | 11 | 0 | 0 | `browser-junit.xml` |
| Compilación TypeScript y Vite dentro del integrado | Correcta | — | — | `typescript.log`, `vite_build.log` y `frontend-build/` |

Los dos pases de Vitest corresponden a los mismos 145 casos, no a 290 pruebas distintas. Se ejecutaron 47 casos backend relevantes; **no se repitió la suite completa del backend**. Los casos históricos pendientes con servicios reales no se consideran aprobados ni incluidos en estos conteos. Docker Desktop estaba detenido al comenzar; esos intentos terminaron antes de ejecutar casos. Después de iniciarlo se completaron las cuatro fases y se eliminaron sus contenedores desechables.

Directorios de evidencia, ignorados por Git:

- `.test-artifacts/reciwise-d2-test-830b2d73d53c4464950f5f2812fa4bbe/`: fotografías y comprobación SQL de solo lectura.
- `.test-artifacts/reciwise-d2-test-29f8141d16fc4691b3cb3a8bd8a6bcce/`: recuperación.
- `.test-artifacts/reciwise-d2-test-c3596f1c0f754bde8df76b41f47890c4/`: conciliador.
- `.test-artifacts/reciwise-d2-test-30e89a53a82f45858207ae3b60c7b478/`: frontend, compilación y navegador; incluye `photo-association.json` y `photo-association-two-reports.png`.

En el recorrido nuevo, el primer reporte ficticio recibió POST de foto 201; el segundo recibió 502 por un fallo de Storage simulado y 201 tras el reintento manual. Las dos fotos quedaron en sus respectivos reportes, con claves de objetos y SHA-256 distintos y coincidentes con los archivos enviados. La recarga conservó esa asociación. Estos UUID y objetos son exclusivos del entorno desechable; **no son los dos reportes del incidente real**.

### Archivos de esta corrección

- `frontend/src/Photos.tsx`: única modificación funcional.
- `frontend/src/Photos.test.tsx`: cuatro regresiones del componente.
- `frontend/src/App.test.tsx`: regresión de dos reportes consecutivos y reintento.
- `frontend/e2e/integrated/sprint1.spec.ts`: recorrido real local con dos imágenes distintas.
- `tests/test_photo_concurrency.py`: comprobación reproducible del SQL de lectura.
- `scripts/sql/diagnostico_fotos_20261104.sql`: diagnóstico manual, sin modificaciones.
- `docs/DIAGNOSTICO_FOTOGRAFIAS_20261104.md`: análisis, evidencia e instrucciones.

No hubo cambios funcionales en FastAPI, Storage, conciliador o base de datos. No se modificaron credenciales, `.env`, D3 ni migraciones; tampoco se accedió al Supabase principal, se modificaron registros persistentes o se hizo push/despliegue. El usuario compartió conteos y fechas de la consulta 1, detalle de fotografías de la consulta 2 y el resultado de operaciones de la consulta 3: quedan incorporados arriba. La intención/secuencia histórica de clics y el estado físico actual de los objetos de Storage no se comprobaron. La actualización por estos resultados fue exclusivamente documental; no se repitieron pruebas funcionales ni se añadieron cambios al código.

## Repetir la comprobación real sin crear reportes innecesarios

1. Ejecutar primero el SQL de lectura para los dos IDs existentes y conservar los resultados. Compartir solo conteos y `photo_id`, `report_id`, fecha local y estado; no JWT, contraseñas, enlaces firmados ni imágenes personales.
2. En la versión corregida de React, localizar **el UUID completo** del reporte nuevo y pulsar «Ver fotografías» / «Renovar enlaces». Esta comprobación no sube un archivo ni crea un reporte. En Network, verificar el pathname GET, estado HTTP y `report_id` de los resultados; omitir cabeceras y tokens al compartir evidencia.
3. Repetir la consulta del anterior, sin subir nada. Distinguir sus dos filas por ID y fecha; comprobar sus objetos por la clave exacta si es necesario.
4. Si SQL o GET ya muestran la fotografía del nuevo, **no repetir la subida**: corregir la lectura/firmado/visualización. Ante error o commit incierto, volver a consultar y revisar el diario antes de enviar.
5. Solo si el usuario decide realizar una nueva subida real, usar el **reporte nuevo ya existente**, confirmar el UUID visible en el panel y comprobar antes que no haya un intento incierto pendiente ni una foto ya guardada. Enviar una sola vez un archivo de prueba identificable. Verificar POST 201 y `report_id`, luego GET y SQL con la misma `photo_id`. Esta revisión de Codex no ejecutó ni necesita esa escritura remota.

No se propone trasladar la foto del anterior, borrar objetos, alterar diario, ejecutar el conciliador remoto ni tocar políticas/migraciones. La prueba automatizada de dos reportes se hace exclusivamente en un entorno desechable.
