# Integración full-stack del Sprint 2 — RECIWISE

Fecha: 31 de octubre de 2026. Alcance: frontend React y backend D2. **NO-GO para Supabase compartido**. No constituye cierre del sprint ni autorización de despliegue.

> Actualización de publicación, 4 de noviembre de 2026: el usuario confirmó que aplicó manualmente las migraciones 002 y 003 en Supabase SQL Editor. Las secciones siguientes conservan la evidencia histórica de las pruebas aisladas; no implican que dichas migraciones sigan pendientes de aplicación. El historial de Supabase CLI puede requerir reconciliación y no se consultó ni modificó en esta publicación. Véase [PUBLICACION_FULLSTACK_20261104.md](PUBLICACION_FULLSTACK_20261104.md) para el alcance, verificaciones y bloqueos actuales. Se conserva NO-GO para un nuevo despliegue sin revisión; respaldar la rama no autoriza desplegar.

## Entorno y límites

Se reutiliza PostgreSQL 17 local con 001+002+003 y la guardia de esquema activa. FastAPI y React son reales. Auth/JWKS y Storage son simuladores HTTP locales; las firmas ES256 y la consulta de perfiles en PostgreSQL sí se verifican. Las teselas se simulan durante las pruebas de navegador. Ninguna prueba equivale a validación de Supabase Storage real.

No se modifican ni ejecutan módulos `d3/`, sus contratos, algoritmos, dependencias o datos. No se generan recorridos, distancias, prioridades ni sugerencias. El adaptador D2 existente todavía no autentica un proveedor operativo. Una etiqueta de origen `d3` no acredita procedencia.

No se modifican migraciones, credenciales ni archivos `.env`. No se aplican migraciones en Supabase compartido. No se hace push, merge ni despliegue.

## Incremento A: recursos y turnos

Se conservan GET/POST de vehículos, sitios y turnos y PATCH de disponibilidad. Se incorporan:

| Método y ruta | Permiso | Comportamiento |
| --- | --- | --- |
| GET /municipal/drivers?limit=200&offset=0 | Encargado | Directorio paginado de IDs con rol chofer. No devuelve correos ni consulta Auth administrativo. |
| PATCH /municipal/sites/{id} | Encargado | Edita nombre, uso, coordenadas juntas y/o disponibilidad. Campos extra y nulos se rechazan. |

Ejemplo de edición:

```json
{"name":"Punto operativo corregido","site_type":"salida","active":true,"latitude":-12.05,"longitude":-75.22}
```

No se permite alterar uso, ubicación o disponibilidad de un sitio referido por un turno programado que todavía no termina: HTTP 409. El nombre sí puede corregirse. No se eliminan sitios, vehículos ni turnos.

Crear un turno obtiene bloqueos SHARE de vehículo, perfil y sitios en orden estable. Los cambios de recursos obtienen bloqueos exclusivos. Así, la reserva ve el estado confirmado y no utiliza una disponibilidad leída antes de un cambio concurrente. Cada reintento de una transacción abortada reaccede a recursos y vuelve a validar. Las exclusiones EXCLUDE de 003 siguen siendo la garantía PostgreSQL contra superposición; se permiten intervalos contiguos. Un commit de resultado desconocido no se repite automáticamente.

React utiliza el directorio de choferes, recorre sus páginas y permite altas confirmadas, disponibilidad, edición de sitios y creación de turnos. No inventa capacidad, placa, nombres de choferes ni datos municipales. Las horas del dispositivo se envían con zona horaria y se presentan en hora de Perú.

## Incremento B: eventos manuales

El formulario nuevo reutiliza `POST /municipal/events`, GET de eventos/reportes y agrupaciones existentes. No se duplican endpoints:

```json
{"latitude":-12.05,"longitude":-75.22,"intervention_type":"Recolección manual","report_ids":["00000000-0000-4000-8000-000000000001"]}
```

La ubicación se elige o corrige en Leaflet o mediante GPS solicitado solo al pulsar el botón. Se confirma el punto y después el evento completo. El formulario permite seleccionar reportes sin asociación y sin historial; los casos con historial se resuelven mediante la revisión de agrupaciones existente. Se conservan sus comprobaciones de estado esperado y auditoría.

HTTP 409 devuelve a revisión; HTTP 503 o pérdida de comunicación exige consultar eventos antes de crear otro. Este POST no tiene UUID idempotente y la interfaz no lo reenvía automáticamente. Los reportes conservan su estado; asociar no equivale a atender.

## Incremento C: decisiones municipales seguras

Se mantienen intactos los contratos de `/municipal/route-proposals` y los contratos D2↔D3. Las propuestas siguen siendo no operativas. La revisión de decisiones usa endpoints D2 separados:

| Método y ruta | Función |
| --- | --- |
| GET /municipal/routes?status=propuesta&limit=50&offset=0 | Lista todos los estados, con recursos asignados, revisión y elegibilidad. |
| GET /municipal/routes/{id} | Detalle, recursos actuales, instantánea de paradas, exclusiones, métricas recibidas e historial. |
| GET /municipal/routes/{id}/history | Historial paginado, más reciente primero. |
| POST /municipal/routes/{id}/decisions | Rechazo o cancelación autorizados; aprobación bloqueada. |
| GET /municipal/routes/{id}/operations/{operation_id} | Resuelve el resultado de un commit incierto. |

Ejemplo:

```json
{"operation_id":"00000000-0000-4000-8000-000000000002","decision":"cancel","expected_status":"propuesta","expected_revision":null,"notes":"Alternativa descartada durante la revisión municipal"}
```

- `reject` admite propuesta → cancelada; `cancel` admite propuesta/aprobada → cancelada.
- No se cancelan rutas en ejecución ni finalizadas mediante estos endpoints.
- `approve` devuelve HTTP 409. La interfaz lo presenta deshabilitado y explica la dependencia.
- El UUID es idempotente **dentro de una ruta**. El mismo UUID con otro actor o cuerpo devuelve 409.
- Estado y última revisión son obligatorios, incluyendo `null` explícito. Un estado obsoleto devuelve 409.
- El resultado contiene `operation`, `route` y `replayed`.
- Los endpoints municipales rechazan ciudadanos y choferes con 403.

Se utiliza el bloqueo transaccional de la propuesta ya existente en D2, además de FOR UPDATE sobre la ruta. Es el mismo espacio de bloqueo usado por el registro de resultados existente: una cancelación no pierde su historial frente a ese escritor.

## Auditoría y autorización operativa reservada

No se necesita una migración nueva: 002 ya contiene `route_plans.configuration` JSONB, `route_stops` y `stop_incidents`. El mapeo ORM de incidencias refleja la tabla existente.

El espacio raíz privado `configuration._municipal_execution_v1` conserva versión, operaciones y un recibo reservado de aprobación. Las operaciones contienen UUID, huella del comando normalizado, actor, acción, instante del servidor, estados anterior/resultante, parada y motivo. El reemplazo del documento y los cambios de ruta/parada/incidencia se confirman en la misma transacción.

Los parámetros públicos de propuestas se almacenan bajo `configuration.parameters`; no pueden escribir este espacio raíz. Los nuevos comandos rechazan campos extra. Las tablas mantienen RLS y revocación de permisos de roles de cliente. No hay acceso de edición genérica del JSON.

**Ningún endpoint ni proceso de desarrollo de esta entrega emite recibos de aprobación verificada.** La integración futura debe autenticar al proveedor y acordar/revisar la emisión del recibo del lado servidor. Los metadatos históricos, un `origin=d3` o un `approved_by` aislado no habilitan ejecución.

El lector del recibo exige correspondencia con responsable/fecha de aprobación, turno, chofer, vehículo, huellas de entrada/resultado y manifiesto de paradas. Es una frontera reservada para una integración futura; no implementa ni demuestra autenticación del proveedor D3.

El historial es append-only desde estos endpoints, con límite de 205 operaciones por ruta, suficiente para hasta 200 paradas más transiciones. No es un registro resistente a modificaciones por un administrador PostgreSQL. Una exigencia posterior de auditoría SQL inmutable necesita revisión y posible migración independiente. No se ofrece reparación automática de historiales incompatibles: HTTP 503 y revisión administrativa.

## Incremento D: chofer

| Método y ruta | Función |
| --- | --- |
| GET /driver/routes?limit=50&offset=0 | Solo rutas del chofer del JWT, con aprobación verificada y estado aprobada/en_ejecucion/finalizada. |
| GET /driver/routes/{id} | Detalle de su asignación. Otra asignación devuelve 404; propuesta o aprobación no verificada, 409. |
| POST /driver/routes/{id}/actions | `start` o `finish` con confirmación de estado/revisión. |
| POST /driver/routes/{id}/stops/{stop_id}/actions | `attend`, `incident` o `not_attended`. |
| GET /driver/routes/{id}/operations/{operation_id} | Solo sus operaciones sobre una ruta que le pertenece. |

Ejemplos:

```json
{"operation_id":"00000000-0000-4000-8000-000000000003","action":"start","expected_status":"aprobada","expected_revision":null,"notes":null}
```

```json
{"operation_id":"00000000-0000-4000-8000-000000000004","action":"incident","expected_status":"en_ejecucion","expected_revision":"00000000-0000-4000-8000-000000000003","incident_type":"acceso_bloqueado","notes":"No fue posible ingresar al punto asignado"}
```

El inicio requiere horario vigente, turno programado, vehículo disponible, perfil chofer y sitios activos del tipo correcto. Los bloqueos de vehículo y chofer también evitan iniciar si otro recorrido sigue en ejecución, aunque su turno haya terminado.

Solo se registra la siguiente parada pendiente de una ruta en ejecución. Se conserva `visited_at` y `recorded_by`. Incidencias y no atención requieren motivo; las incidencias requieren tipo. La fila `stop_incidents` y la auditoría se guardan atómicamente. Finalizar requiere todas las paradas registradas. Repetir el mismo comando no crea otra incidencia.

No se cambian automáticamente estados de reportes/eventos, disponibilidad del vehículo ni estado del turno. Esas reglas de cierre se deben acordar separadamente. No hay GPS continuo, evidencia fotográfica de incidencias ni navegación giro a giro.

React presenta una vista de celular con asignaciones propias, paradas ordenadas, mapa, inicio/fin, resultados e historial. Las propuestas no se muestran como recorridos del chofer. Si aún no existen aprobaciones verificadas, muestra un estado vacío explicativo.

## Confirmaciones y errores

Se reutilizan JWT, `/me`, permisos, cliente HTTP y trazas sin secretos. Se manejan 401, 403, 404, 409, 422 y 503. No se confía en el rol enviado por React.

Para decisiones y ejecución, React conserva el comando congelado durante la confirmación, bloquea doble envío y evita navegación/cambio de modo mientras la decisión municipal está pendiente. Tras 409 descarta y actualiza antes de una nueva confirmación. Tras errores 5xx, incluido 503, o fallo de red consulta el UUID: si existe recupera el resultado; solo tras 404 ofrece repetir **exactamente** el mismo comando. No hay reenvíos automáticos. En altas de recursos y eventos, un resultado incierto exige consultar el listado antes de crear otro.

No se cierra el diálogo con resultado incierto. Se muestra el UUID y se advierte al cerrar la pestaña. Una salida forzada, cierre de sesión o pérdida de almacenamiento de la pestaña puede requerir recuperar manualmente el UUID; el historial durable del servidor se conserva.

Las operaciones SQL de los endpoints nuevos son síncronas y FastAPI las ejecuta en su threadpool; no bloquean un endpoint async mediante consultas síncronas.

## Archivos del incremento

Backend:

- `app/municipal_resources.py`: directorio y edición de sitios.
- `app/main.py`: inclusión de routers y bloqueos/revalidación de turnos.
- `app/models.py`: mapeo de la tabla existente de incidencias.
- `app/execution_contracts.py` y `app/route_execution.py`: contratos D2, decisiones, auditoría y ejecución.

Frontend:

- `municipal/Resources.tsx`, `services.ts`, `model.ts`: gestión y selector.
- `municipal/CreateEvent.tsx`, `LiveEvents.tsx`, `backendService.ts`, `backendTypes.ts`: alta manual.
- `operations/{types,service,OperationConfirm,RouteDetails,RouteManagement,DriverWorkspace}` y `driver.css`.
- `App.tsx`, `MunicipalWorkspace.tsx`, `format.ts`, `LocationPicker.tsx` y `RouteMap.tsx`: integración por rol y componentes compartidos.
- Pruebas frontend de recursos, eventos y operaciones; adaptación del navegador existente al selector de choferes.

Pruebas/ejecutores:

- `tests/test_resource_management.py`, `tests/test_route_execution.py`.
- `tests/test_shift_concurrency.py`: sincronización solo en la primera lectura; un reintento abortado no espera a un participante que terminó.
- `tests/run_isolated_postgres.py`: fases resources/execution y regresión ampliada.
- `tests/execution_browser_fixture.py`: autorización **ficticia**, solo en DB desechable con nombre/marcador verificados.
- `tests/run_integrated_sprint1.py`: fixture y diagnóstico seguro del arnés.
- `frontend/e2e/integrated/sprint2_fullstack.spec.ts`: A/B, decisiones/conflicto y ejecución móvil con reinicio.

## Pruebas y evidencias

Regresión D2 final: **680 aprobadas, 0 fallidas, 12 omitidas** en 237.91 s. Evidencia: `.test-artifacts/reciwise-d2-test-c8755141b9a545d2bbc525614923fd31/pytest.xml` y `environment.json`.

| Verificación final | Resultado | Evidencia |
| --- | --- | --- |
| TypeScript + Vitest | 138 aprobadas, 0 fallidas | `.test-artifacts/reciwise-d2-test-7523f9915d2f4009be75a818025327ac/vitest.json` y `typescript.log` |
| Chrome + React + FastAPI + PostgreSQL | 10 aprobadas, 0 fallidas, 0 omitidas | Mismo directorio: `browser-junit.xml`, `browser.log`, `integrated-environment.json` y trazas HTTP por caso |
| Build integrado y `npm.cmd run build` | Correctos | `vite_build.log` y salida de compilación de la versión final |
| Navegador con API/Auth interceptados | 16 aprobadas | Comando de regresión controlada; no acredita comunicación real con backend |
| Preview del build de producción | 1 aprobada | Demostración deshabilitada incluso con flag público true; API/Auth interceptados |
| Volumen persistente tras reinicio | 28 controles HTTP + 1 recorrido React aprobados | `.test-artifacts/local-dev/04da38bc468844e1a027d896b0fffbd9/` |
| Endpoints nuevos en volumen persistente | 12 comprobaciones aprobadas; 0 escrituras de negocio | `.test-artifacts/fullstack-sprint2/local-http.json` |
| Archivos protegidos y alcance | 25 archivos protegidos sin cambios | `.test-artifacts/fullstack-sprint2/scope-verification.json` |

El integrado cubre los cuatro recorridos de Sprint 1, los tres de Sprint 2 anteriores y tres incrementos nuevos: recursos/evento manual, conflicto y cancelación municipal, y ejecución móvil del chofer. Comprueba paradas atendidas, incidencia, no atención, acceso de otro chofer denegado, reinicio real de FastAPI y recuperación exacta del detalle. Usa firmas ES256 verificables con JWKS servido por el simulador HTTP.

El entorno persistente se dejó iniciado en React `127.0.0.1:5173` y FastAPI `127.0.0.1:8001`. `/ready` devuelve 200 con schema 003. Los registros de aceptación y las fotografías/control conservan sus IDs, campos y hashes. **No se insertaron autorizaciones ficticias ejecutables en ese volumen**; el chofer muestra el estado vacío hasta disponer de una aprobación legítima.

Capturas locales de la ejecución final, todas con datos ficticios:

- [Evento manual y reportes asociados](../.test-artifacts/reciwise-d2-test-7523f9915d2f4009be75a818025327ac/fullstack-manual-event.png).
- [Cancelación e historial](../.test-artifacts/reciwise-d2-test-7523f9915d2f4009be75a818025327ac/fullstack-route-cancelled.png).
- [Chofer en móvil de 390 px, sin desborde](../.test-artifacts/reciwise-d2-test-7523f9915d2f4009be75a818025327ac/fullstack-driver-mobile.png).

Los artefactos están ignorados por Git y no deben publicarse sin revisión. La aprobación positiva del chofer en esas capturas procede de la fixture de autorización; no de un proveedor real.


Incluye **23** casos nuevos de recursos, **62** de decisiones/ejecución y los **11** de concurrencia de turnos. Esos casos utilizan PostgreSQL real aislado. Las 12 omisiones siguen pendientes: 2 requieren registros piloto existentes no proporcionados al ejecutor, 9 requieren REST anónimo de Supabase real y 1 requiere JWT ciudadano real para la comprobación remota.

El build avisa de un chunk principal de aproximadamente 726 kB (208 kB gzip). No impide compilar; la división del bundle queda como mejora de rendimiento, sin incorporar dependencias D3.

Incidencias resueltas durante la verificación: barrera de una prueba que no contemplaba revalidación en un reintento, directorio de más de 200 choferes, importación del arnés desde su carpeta, selectores de formularios y cabecera pública del Auth simulado. Un recorrido se interrumpió por HMR al editar durante la prueba; la ejecución estable posterior pasó sus diez casos. El primer intento de preview utilizó una URL distinta de la interceptada por su arnés; se repitió con la configuración ficticia documentada. Estos intentos fallidos no se contabilizan como pruebas aprobadas.

La prueba positiva del chofer asume una aprobación confiable mediante una fixture insertada directamente por el arnés **solo en PostgreSQL desechable**. No es un bypass del JWT ni un endpoint de producción, no modifica el volumen de desarrollo y no acredita un proveedor real. Esa limitación debe mantenerse visible al presentar resultados.

Las pruebas D2 combinan casos antiguos con SQLite y comprobaciones directas en PostgreSQL. Los casos nuevos de recursos/concurrencia/ejecución usan PostgreSQL real, sin fallback a SQLite. Las pruebas de navegador integradas continúan las peticiones de negocio a FastAPI real; no las interceptan con respuestas ficticias.

## Respuestas y errores de los contratos D2

El directorio devuelve un array de `{"id":"UUID","role":"chofer"}`. Las listas de rutas también son arrays, con `limit` 1–200 y `offset` no negativo; el valor por defecto de `limit` es 50.

`ExecutionSummary` contiene `id`, `shift_id`, `driver_id`, `vehicle_id`, `vehicle_label`, `starts_at`, `ends_at`, `status`, `created_at`, `revision` (UUID o null), `approved_by`, `approved_at`, `approval_verified`, `can_approve` (siempre false en esta entrega) y `approval_blockers`.

El detalle añade `shift_status`, `vehicle_available`, `departure` y `disposal` (id, nombre, uso, disponibilidad y coordenadas), `stops`, `history`, `distance_m`, `estimated_duration_seconds`, `geometry_geojson`, `limitations` y `excluded_events`. Los recursos son los actuales; las coordenadas de cada parada proceden de la instantánea, nunca se deducen desde descripciones.

Ejemplo de formato de una parada; no es un registro real:

```json
{
  "id":"00000000-0000-4000-8000-000000000005",
  "event_id":"00000000-0000-4000-8000-000000000006",
  "order":1,
  "latitude":-12.05,
  "longitude":-75.22,
  "status":"pendiente",
  "estimated_service_minutes":null,
  "visited_at":null,
  "recorded_by":null,
  "incidents":[]
}
```

Cada entrada de historial contiene `operation_id`, `actor_id`, `action`, `at`, `previous_status`, `resulting_status`, `stop_id`, `notes` y `request_hash`. Una incidencia contiene `id`, `stop_id`, `reported_by`, `incident_type`, `description` y `created_at`. Las fechas se serializan como ISO 8601. Las definiciones exactas están en `app/execution_contracts.py` y el OpenAPI local.

| HTTP | Interpretación |
| --- | --- |
| 401 | Falta JWT o no es verificable. |
| 403 | Rol o perfil no autorizado. |
| 404 | Recurso inexistente/no visible, parada de otra ruta u operación no encontrada. |
| 409 | Revisión/estado en conflicto, recurso no disponible, horario inválido, aprobación sin verificar o transición prohibida. |
| 422 | Contrato inválido, campos extra, valores fuera de rango o falta de motivo. |
| 503 | Fallo de persistencia/consulta, bloqueo agotado o historial/instantánea incompatibles; comprobar resultado antes de repetir. |

## Iniciar y detener en VS Code (Windows)

Desde la raíz, con Docker Desktop activo:

```powershell
Set-Location 'C:\Users\DELL INSPIRON\Documents\RECIWISE'
.\.venv\Scripts\python.exe scripts\local_dev.py up
```

En otra terminal:

```powershell
.\.venv\Scripts\python.exe scripts\local_dev.py status
Invoke-RestMethod http://127.0.0.1:8001/ready
.\.venv\Scripts\python.exe scripts\check_local_dev.py
.\.venv\Scripts\python.exe scripts\local_dev.py down
```

React: `http://127.0.0.1:5173`. API: `http://127.0.0.1:8001`. El volumen y las identidades locales se conservan al detener. Los cambios Python requieren down/up; Vite recarga React. No usar Uvicorn directo heredando el `.env` principal: apuntaría a Supabase sin 003 y la guardia rechazaría el arranque.

Cuentas ficticias y gestión de su contraseña local: [ENTORNO_LOCAL.md](ENTORNO_LOCAL.md). No publicar `.localdev` ni copiar sus secretos al frontend.

Pruebas desechables independientes del volumen de desarrollo:

```powershell
.\.venv\Scripts\python.exe tests\run_isolated_postgres.py --phase resources
.\.venv\Scripts\python.exe tests\run_isolated_postgres.py --phase execution
.\.venv\Scripts\python.exe tests\run_isolated_postgres.py --phase all
.\.venv\Scripts\python.exe tests\run_isolated_postgres.py --phase integrated
```

El integrado ejecuta TypeScript, Vitest, build Vite y Chrome con puertos propios; guarda evidencia bajo `.test-artifacts/reciwise-d2-test-*/` y elimina únicamente su contenedor desechable. No invocar la fixture de aprobación sobre la base persistente.

Desde `frontend`:

```powershell
npm.cmd run check
npm.cmd run build
```

Para builds de prueba, utilizar variables públicas ficticias de proceso como documenta [FRONTEND_SPRINT2.md](FRONTEND_SPRINT2.md), sin cambiar archivos `.env`. Las pruebas de navegador controladas en el puerto 5173 requieren detener antes el Vite local; después se puede volver a ejecutar `local_dev.py up`.

## Pendientes y revisión del equipo

1. **D3 / operación real:** autenticación y verificación del proveedor, política de elegibilidad y emisión auditada del recibo; revisión de seguridad antes de habilitar `approve`. No se implementa en esta entrega.
2. Aceptación de reglas de operación: tratamiento de incidentes, cierre de eventos/reportes, turnos y evidencia de campo. No inferir que una parada atendida cierra reportes.
3. Supabase Auth/Storage reales: JWT y políticas de usuario, bucket privado, descarga temporal, fallos remotos, conciliación y recuperación. Continúan pendientes; los simuladores no las sustituyen.
4. Compartido: respaldo, diagnóstico de datos, revisión/aplicación autorizada de 003 y controles posteriores. **NO-GO** mientras el backend requiera 003 y el proyecto compartido no la tenga.
5. Revisión D1/D2 de formularios, permisos, conflictos y experiencia móvil; D3 revisa independientemente su futura frontera de confianza. No declarar aprobadas rutas ficticias ni el Sprint en nombre del equipo.

## Validación municipal en el entorno persistente — 31 de octubre de 2026

Se comprobó el aplicativo en Chrome contra React `http://127.0.0.1:5173`, FastAPI `http://127.0.0.1:8001` y PostgreSQL 17 local persistente, identificado por etiquetas Docker y marcador interno. `/ready` respondió 200 con esquema 003. Se mantuvieron la guardia y la verificación JWT ES256/JWKS de producción, con identidades ficticias del Auth local. **Los datos son de prueba; «Modo real» significa conexión a FastAPI, no recursos municipales oficiales.** No se abrió el modo de demostración.

| Módulo | Resultado comprobado |
| --- | --- |
| Reportes | Listado coincide con FastAPI; descripción, estado, coordenadas, residuo y fechas de Perú contrastados. Filtro HTTP por estado, búsqueda local, resultados vacíos y recuperación tras recargar. |
| Leaflet y fotografías | Marcador, popup y selección del reporte correctos; descarga privada visible y renovación de enlaces. Fotografía accesible también desde el evento original. Se reutilizó la imagen existente, sin nuevas subidas. |
| Eventos | Creación manual desde React, ubicación elegida y confirmada en el mapa, selección de reporte y confirmación antes del POST. Un doble clic produjo un único POST 201. Detalle, coordenadas, relación manual y actor recuperados mediante API y SQL independiente. Reporte conserva `recibido`; evento queda `en_revision`, sin prioridad inventada ni agrupación automática. |
| Vehículos | Listado y disponibilidad coinciden con API. Capacidad desconocida se mantiene como tal. Alta confirmada de una unidad expresamente NO OPERATIVA; aparece «No disponible» y su opción nativa está deshabilitada para turnos. |
| Sitios y turnos | Nombres, usos, coordenadas, vehículo, chofer, salida, descarga y horarios contrastados. Fin igual al inicio se rechaza en React sin POST. Intentar reservar el turno existente devuelve 409 y muestra «Vehículo o chofer ya reservado en ese horario», también registrado en el historial HTTP. No se creó ni alteró ningún turno ni sitio. |
| Permisos y validación | Solicitudes desde el navegador a FastAPI real: 401 sin JWT; 403 para ciudadano en las seis consultas municipales verificadas y creación de evento; 422 para coordenadas/UUID/capacidad inválidos; 404 para evento inexistente; 409 al intentar volver a asociar el reporte original. Las escrituras rechazadas no dejaron filas. |
| Interfaz y comunicación | Carga visible, confirmación antes de altas, error de lectura 503 **inyectado solo en la prueba** y recuperación posterior con GET real 200. Navegación por las siete secciones, mapa, fotos y diálogo en 390×844, sin desbordamiento horizontal. Sesión y registros recuperados tras recargar. Cero excepciones JavaScript, cero solicitudes externas y cero solicitudes GPS automáticas. |

Los GET cancelados por desmontaje/navegación y StrictMode aparecen como «Sin HTTP» en el historial de desarrollo: se identificaron como `net::ERR_ABORTED`, seguidos por respuestas 200. No indican por sí solos caída del backend. Los mensajes de consola por los HTTP negativos intencionales se conservan en la evidencia; no se observaron otros errores de consola ni fallos de comunicación inesperados. El 503 inyectado verifica la interfaz, **no acredita un fallo real de PostgreSQL/Storage**.

Endpoints utilizados (contratos existentes, sin cambios):

| Métodos | Ruta y uso |
| --- | --- |
| GET | `/health`, `/ready`, `/me`: proceso, esquema y perfil. |
| GET, POST | `/reports/mine` (GET), `/reports` (POST): consulta ciudadana y única alta necesaria. |
| GET | `/municipal/reports?limit=50&offset=0&status=…`: listado/filtro y datos del detalle de cada tarjeta. No se inventa un endpoint de detalle municipal de reportes. |
| GET | `/reports/{id}/photos`: fotografías y renovación de enlaces. La imagen se descarga por HTTP desde el Storage local. |
| GET, POST | `/municipal/events`: listado y alta manual. |
| GET | `/municipal/events/{id}`, `/municipal/events/{id}/reports`: detalle y asociados. |
| GET | `/municipal/groupings?linked=false`, `/municipal/groupings/reports/{id}`: selector y comprobación de asociación; consultas de historial/candidatos al navegar la sección. |
| GET, POST | `/municipal/vehicles`: lectura y única alta NO OPERATIVA necesaria. |
| GET | `/municipal/sites`, `/municipal/drivers`: puntos y choferes habilitados. |
| GET, POST | `/municipal/shifts`: consulta y POST rechazado 409, sin alta. |
| GET | `/municipal/route-proposals` y sus detalles/paradas/exclusiones: regresión de navegación y fixture original, sin aprobar propuestas. |

### Datos conservados y nuevas fixtures mínimas

El único reporte inicial ya tenía asociación e historial, y no había vehículos no disponibles. Para verificar las altas sin cambiar esos registros se crearon, mediante React, exactamente:

- `PRUEBA MUNICIPAL LOCAL S2: reporte para asociación manual`.
- `PRUEBA MUNICIPAL LOCAL S2: revisión manual`, con su vínculo y decisión de auditoría `agrupar` generados por el backend.
- `PRUEBA MUNICIPAL LOCAL S2: unidad NO OPERATIVA`, no disponible, sin inventar placa ni capacidad.

No se añadieron fotografías, sitios ni turnos. Los IDs se guardan en `.localdev/municipal-acceptance.json` ignorado; el arnés también busca las etiquetas únicas en API antes de crear para recuperar una ejecución interrumpida sin duplicar. No repite automáticamente POST inciertos. Un candado local impide dos ejecuciones del arnés simultáneas.

Las instantáneas SQL se realizan en transacciones `READ ONLY`, con conexión local protegida. Se comparan todas las filas anteriores de ocho tablas, sus relaciones y los SHA-256 de la fotografía y el archivo de control. **Ninguna fila anterior se eliminó o modificó.** También se comprueban el vínculo manual, el encargado que lo creó y su decisión de auditoría. La ejecución final reutilizó todo y añadió **cero filas**.

### Pruebas ejecutadas y evidencia

| Comprobación de esta revisión | Resultado | Evidencia local ignorada |
| --- | --- | --- |
| `npm.cmd run check` | TypeScript correcto; **140 pruebas aprobadas**, 0 fallidas | Salida de la ejecución; incluye los dos nuevos casos de paginación |
| `npm.cmd run build` | Correcto; aviso conocido de bundle de 725.67 kB, 207.64 kB gzip | Salida del build; no impide compilar |
| Nuevo recorrido municipal persistente | **6 aprobadas**, 0 fallidas, 0 omitidas | `.test-artifacts/municipal-local/9f32c7bb3d02456e89219a7619732fae/browser.xml`, `browser.log`, trazas JSON por caso, `before.json`, `after.json`, `results.json` |
| Regresión de la fixture persistente original | **28 controles HTTP + 1 recorrido Chrome aprobados**; instantánea original intacta | `.test-artifacts/local-dev/31021c5d00794433ac2ff3db55a363b7/` |
| Regresión integrada anterior en PostgreSQL desechable separado | **10 recorridos Chrome aprobados**, 0 fallidos, 0 omitidos; TypeScript, **140 Vitest** y build correctos | `.test-artifacts/reciwise-d2-test-f8064d1666c742faa0bf56856722feed/`: `browser-junit.xml`, `vitest.json`, `integrated-environment.json`, `vite_build.log` |

Las altas positivas están registradas en los casos 02 y 03 de los primeros recorridos: `.test-artifacts/municipal-local/637da3340dfd4096b807d643b8d1f5dc/` y `bf02b4879a294414812106aa3223b9da/`. Esos intentos tuvieron respectivamente 2 y 1 fallos del arnés; otro intento (`acca2f98587648d5a5b5e7d6b4bb6556`) tuvo 1. Eran selectores de mapa/etiquetas y el matcher de una opción HTML deshabilitada, corregidos en la infraestructura de pruebas. **No se presentan esos intentos completos como aprobados.** La ejecución final usa selectores adecuados y comprueba la propiedad nativa `option.disabled`.

Capturas revisadas:

- [Reporte, mapa y fotografía en escritorio](../.test-artifacts/municipal-local/9f32c7bb3d02456e89219a7619732fae/municipal-reportes-desktop.png).
- [Evento manual con relación persistida](../.test-artifacts/municipal-local/9f32c7bb3d02456e89219a7619732fae/municipal-evento-manual.png).
- [Conflicto de turno 409 y mensaje](../.test-artifacts/municipal-local/9f32c7bb3d02456e89219a7619732fae/municipal-turno-conflicto.png).
- [Evento y mapa en móvil simulado](../.test-artifacts/municipal-local/9f32c7bb3d02456e89219a7619732fae/municipal-evento-mobile.png).

React, Leaflet, FastAPI y PostgreSQL son reales. **Auth, Storage y teselas son simuladores locales**; las respuestas de negocio de los casos positivos no se simulan. Solo el caso 05 inyecta un error GET para comprobar la interfaz. Esta revisión móvil utiliza viewport de navegador, no un celular físico. Los resultados D2 históricos (680 aprobadas y 12 omitidas) no se contabilizan como una nueva ejecución de la suite backend completa.

La regresión integrada anterior cubre Sprint 1, eventos/agrupaciones/propuestas de Sprint 2 y los incrementos de recursos/ejecución. Su prueba positiva de chofer emplea un recibo ficticio **solo en el contenedor desechable**, eliminado por el ejecutor tras las pruebas. No se trasladó esa autorización a la base persistente ni se acreditó un proveedor D3. El objeto de control se conservó.

### Corrección limitada y archivos de esta revisión

Se reprodujo que los botones de `Pager`, al estar dentro del formulario de creación de evento, disparaban `submit` por su tipo HTML predeterminado. La corrección añade únicamente `type="button"` a Anterior/Siguiente en `frontend/src/municipal/backendUi.tsx`. Los dos casos de `backendUi.test.tsx` fallaron antes y pasan después, sin enviar el formulario. No fue necesario modificar el backend.

Infraestructura nueva: `scripts/validate_municipal_local.py`, `scripts/municipal_validation.config.cjs` y `scripts/municipal_validation.spec.cjs`. Este documento recoge la integración. Se conservan los cambios locales anteriores del equipo.

La comparación SHA-256 con los 172 archivos del estado inicial identifica únicamente este documento y `backendUi.tsx` como archivos anteriores modificados; los otros cuatro archivos son nuevos. **44 archivos protegidos sin cambios**, incluidos backend, D3/contratos, migraciones, `.env` y credenciales locales verificadas. Evidencia: `.test-artifacts/municipal-local/scope-verification.json`.

### Repetir desde VS Code en Windows

Con Docker Desktop y el entorno local compatible ya preparado, mantener en una terminal:

```powershell
.\.venv\Scripts\python.exe scripts\local_dev.py up
```

En otra terminal, desde la raíz:

```powershell
.\.venv\Scripts\python.exe scripts\local_dev.py status
Invoke-RestMethod http://127.0.0.1:8001/ready
.\.venv\Scripts\python.exe scripts\check_local_dev.py
.\.venv\Scripts\python.exe scripts\validate_municipal_local.py
```

El último comando exige el entorno local listo y la fixture original de `check_local_dev.py`; no migra ni arranca contra una conexión alternativa. Conserva los registros marcados para repetir sin duplicados. Los errores y artefactos se redactan para no conservar contraseñas, JWT ni tokens de enlaces. Para detener los servicios, ejecutar `scripts\local_dev.py down` con el mismo Python; el volumen permanece.

### Pendientes del MVP y límites

El encargado puede trabajar localmente con **reportes, eventos manuales y recursos mediante FastAPI/PostgreSQL**, sin la demostración en memoria. No se aprueba el Sprint en nombre del equipo ni se habilita la operación en el proyecto compartido.

1. D3 verificado, prioridades reales y aprobación operativa confiable: siguen pendientes; no se modificaron algoritmos ni contratos D3 y no se aprobaron rutas en el volumen persistente.
2. Supabase Auth/Storage reales y sus políticas, fallos remotos y conciliación: pendientes; los resultados locales no los sustituyen.
3. Prueba en celular físico, GPS/permisos y HTTPS: pendiente; la adaptación de escritorio a 390 px está comprobada.
4. Revisión de equipo y despliegue seguro de 003 con respaldo y autorización: pendiente. **Se mantiene NO-GO para desplegar el backend nuevo sobre Supabase compartido sin 003.**
5. Mejoras posteriores: distinguir cancelaciones de GET en el historial y dividir el bundle. No bloquean el recorrido local validado.

No se modificaron credenciales, `.env`, migraciones, backend funcional ni IA. No se ejecutaron migraciones sobre Supabase ni sobre el volumen persistente durante esta revisión. No hubo push, merge ni despliegue.

## Demostración reproducible de tres perfiles — 31 de octubre de 2026

Guion y comandos completos: [DEMO_RECIWISE.md](DEMO_RECIWISE.md). Se conservan las pantallas y los contratos de negocio existentes. **La demostración está preparada y ensayada técnicamente; su aceptación por otro integrante del equipo sigue pendiente. NO-GO de despliegue compartido.**

### Estado comprobado por perfil

| Perfil | Resultado real y alcance |
| --- | --- |
| Ciudadano | Registro desde React a 390×844 con selección y arrastre en Leaflet, confirmación, fecha válida y coordenadas numéricas; POST 201, consulta propia, fotografía privada, etiqueta de estado y recuperación tras recarga/reinicio. Sin desbordamiento ni excepciones JavaScript. |
| Encargado | Consulta del mismo reporte/fotografía/mapa, evento manual, asociaciones e historial con estado esperado, recursos y turnos. Propuestas consultables; rechazo **y** cancelación desde React auditados; conflicto concurrente 409 recuperado. Aprobación sin proveedor bloqueada en React y FastAPI. |
| Chofer | JWT verificado y acceso exclusivo al recorrido asignado; otro chofer recibe 404 y no accede a funciones municipales. Tres paradas, inicio, atención, incidencia, no atención y finalización, con motivos e historial; detalle idéntico después de reiniciar FastAPI. Comprobado en viewport móvil, **solo con autorización ficticia en PostgreSQL desechable**. |

La parte positiva del chofer es un escenario independiente, no la continuación calculada/aprobada del reporte ciudadano mostrado en vivo. Sus tres eventos y su recibo proceden de la fixture de ejecución ya existente. No se implementó ni se acreditó verificación D3; no se copiaron autorizaciones a la base persistente. Las reglas de cierre de reportes/eventos continúan sujetas a revisión: asociar o finalizar un recorrido no convierte automáticamente un reporte en atendido.

### Lanzador de demostración

```powershell
.\.venv\Scripts\python.exe tests\run_isolated_postgres.py --phase demo
```

Abre tres sesiones separadas con el formulario de autenticación normal y perfiles ficticios. Anuncia URLs en puertos propios y `DEMO READY`, sin mostrar contraseñas ni tokens. No requiere detener React 5173/FastAPI 8001. Las identidades, reportes, foto técnica, recursos y propuestas se preparan exclusivamente en su contenedor desechable. Las dos propuestas están pendientes y no operativas; el recorrido autorizado ficticiamente del chofer está separado de ellas.

El nuevo modo reutiliza bootstrap 001+002+003, `LocalServices`, `execution_browser_fixture.seed`, funciones del ejecutor integrado y el lanzador Vite local. Antes de la fixture exige Docker local, contenedor exacto en ejecución, etiqueta/ID/nombre aleatorios, puerto loopback, ausencia de montajes persistentes y marcador de la base. Rechaza el contenedor de desarrollo persistente. No cambia migraciones ni permite regenerar el manifiesto desde este modo. FastAPI arranca normalmente con su guardia de esquema y JWT, sin hooks de fallos ni overrides de seguridad.

Ctrl+C solicita `demo.stop`; el hijo cierra únicamente sus sesiones y procesos, y el padre elimina su contenedor/volumen anónimo identificados. También puede solicitarse la parada desde otra terminal creando ese archivo dentro de la carpeta de evidencia de la demo. Se ensayó esta segunda vía en Chrome visible. Al iniciar otra demo se crean datos nuevos; no hay reinicialización ni eliminación de registros persistentes.

Para comprobar preparación y recuperación sin dejar procesos abiertos:

```powershell
.\.venv\Scripts\python.exe tests\run_isolated_postgres.py --phase demo --demo-check
```

### Regresión final ejecutada

| Comprobación | Resultado | Evidencia local ignorada |
| --- | --- | --- |
| Suite D2 completa | **680 aprobadas, 0 fallidas, 12 omitidas**, 461.70 s | `.test-artifacts/reciwise-d2-test-2fa57679e0bd4b4983113ce1518efdf3/pytest.xml`, `environment.json` |
| Frontera del lanzador de demo | **14 unitarias aprobadas**, 0 fallidas; rechaza destino compartido/remoto, contenedor persistente, montaje/puerto/ID/etiqueta incompatibles | `.test-artifacts/demo-tres-perfiles/launcher-unit.xml` |
| Frontend final | TypeScript correcto, **140 Vitest aprobadas**, build Vite correcto | `.test-artifacts/reciwise-d2-test-58585f098e9d4de295573a17f65b1531/vitest.json`, `typescript.log`, `vite_build.log` |
| Regresión integrada desechable | **10 recorridos Chrome aprobados**, 0 fallidos/omitidos | Mismo directorio: `browser-junit.xml`, `browser.log`, trazas JSON, `integrated-environment.json` |
| Demo final automática | **20 controles aprobados** y tres sesiones React preparadas; incluye reinicio real de FastAPI y recuperación exacta de reporte/foto/recorrido | `.test-artifacts/reciwise-d2-test-c5158a7644f548568e776efcb0e1466e/demo-results.json`, `demo-browser.json`, `demo-ready.json` |
| Demo visible y parada | **18 controles aprobados**, tres sesiones Chrome visibles, parada por `demo.stop` y eliminación del contenedor propio | `.test-artifacts/reciwise-d2-test-5dd7ec08bd2340d397c79897450db931/demo-results.json` |
| Municipal persistente | **6 recorridos aprobados**, cero nuevas filas; originales y hashes de fotografía/control intactos | `.test-artifacts/municipal-local/2d138ecd448a4b31a2ef0f16bacc26bc/` |
| Fixture persistente original | **28 controles HTTP + 1 recorrido Chrome aprobados**, instantánea original conservada | `.test-artifacts/local-dev/fb39fd535eae4590a9ba223b9ada7e97/` |

Son **17 recorridos de negocio en navegador** (10 + 6 + 1). Las tres sesiones y los controles de preparación de demo se informan aparte; no se suman como casos nuevos de negocio. Los 140 Vitest y los 14 casos del lanzador son pruebas unitarias, no integraciones remotas. La suite D2 combina casos unitarios/SQLite existentes con PostgreSQL real aislado donde corresponde; las verificaciones de concurrencia/ejecución usan PostgreSQL, sin sustituirlo por SQLite.

Se reutilizaron los diez recorridos integrados y se ampliaron únicamente dos: ciudadano con registro/foto/recarga a 390 px y decisión municipal con rechazo exitoso y auditoría, además de la cancelación/conflicto ya cubiertos. Se añadió observación de `pageerror` al recorrido Sprint 1; los tres perfiles completaron la regresión sin excepciones críticas. No hubo reconstrucción de pantallas ni nuevas funcionalidades de negocio.

Las **12 omisiones** mantienen sus causas: 2 requieren registros piloto existentes no proporcionados al ejecutor; 9 requieren REST anónimo de Supabase real; 1 requiere sesión JWT ciudadana real. Las nuevas comprobaciones locales no acreditan esos casos. Auth, Storage y teselas continúan simulados. El 503 de interfaz municipal es una inyección de prueba explícita; los fallos de Storage/persistencia de la regresión usan servicios simulados y PostgreSQL de pruebas.

Incidencia de la preparación de demo: el primer ensayo visible (`1e74abb5d298444f9d408a49f3e4222c`) autenticó los perfiles, pero falló el hilo que mostraba estado por diferencias de codificación Windows. No se presenta como ensayo final correcto. Se corrigió la salida del proceso hijo/terminal y se repitieron apertura, parada y chequeo automático satisfactoriamente. No fue necesario corregir código funcional de frontend/backend. Permanecen los avisos conocidos, no bloqueantes, de tamaño del bundle y deprecación de TestClient.

Capturas verificables de datos ficticios:

- [Ciudadano móvil: reporte y fotografía](../.test-artifacts/reciwise-d2-test-58585f098e9d4de295573a17f65b1531/citizen.png).
- [Rechazo municipal e historial](../.test-artifacts/reciwise-d2-test-58585f098e9d4de295573a17f65b1531/fullstack-route-rejected.png).
- [Chofer móvil: ejecución finalizada](../.test-artifacts/reciwise-d2-test-58585f098e9d4de295573a17f65b1531/fullstack-driver-mobile.png).
- [Demo: advertencia de autorización ficticia](../.test-artifacts/reciwise-d2-test-c5158a7644f548568e776efcb0e1466e/demo-driver-mobile-ready.png).

### Archivos y límites de esta preparación

Nuevos: `tests/demo_support.py`, `tests/run_demo_sprint2.py`, `tests/test_demo_support.py`, `scripts/demo_profiles.cjs` y `docs/DEMO_RECIWISE.md`.

Actualizados: `tests/run_isolated_postgres.py`, `frontend/e2e/integrated/sprint1.spec.ts`, `frontend/e2e/integrated/sprint2_fullstack.spec.ts` y este documento. Se conservaron los cambios locales anteriores del equipo. No se modificaron módulos funcionales de `app/` ni `frontend/src/`, D3/contratos, migraciones, `.env` o credenciales. No hubo push, merge ni despliegue.

La comparación con 176 archivos iniciales confirma esos cuatro archivos anteriores modificados y cinco nuevos; **97 archivos protegidos sin cambios**. Evidencia: `.test-artifacts/demo-tres-perfiles/scope-verification.json`. Se verificó la eliminación de los seis contenedores desechables de esta revisión y, mediante SQL local `READ ONLY`, **cero rutas aprobadas/en ejecución/finalizadas en el volumen persistente**: `lifecycle-verification.json` en esa misma carpeta. Los 62 casos de `test_route_execution.py` están incluidos en las 680 pruebas D2, sin contabilizarlos dos veces.

La demostración local está técnicamente lista. Faltan ensayo y aprobación de otro integrante, verificación del proveedor D3 y cadena de aprobación real, servicios Supabase reales y celular físico/HTTPS. El despliegue del backend nuevo sobre el proyecto compartido sigue **NO-GO**; no se aplicó allí ninguna migración ni se modificaron datos.
