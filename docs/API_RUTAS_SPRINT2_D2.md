# Sprint 2 D2 · Persistencia de propuestas de rutas

Fecha: 30 de octubre de 2026, America/Lima. Alcance: API administrativa y persistencia,
sin optimización, aprobación, asignación ni ejecución. **NO-GO para el despliegue compartido.**
El Sprint 2 permanece abierto.

## Inspección y esquema necesario

El código anterior del entorno aislado aplicaba 001+003. No incorporaba 002 ni route_plans,
route_stops o stop_incidents a la guardia. La migración **002 existente ya define las tablas,
FK, checks, unicidad de evento/orden por propuesta y el índice parcial de rutas ejecutables**.

Se reutiliza 002 sin cambiarla: **no se necesita una migración nueva**. Solo el runner
de pruebas desechables aplica ahora 001→002→003. No se ejecuta ninguna en Supabase compartido.
La guardia exige las trece tablas, sus restricciones, índices, RLS y permisos, incluidos los
requisitos anteriores de fotografías/reservas. Verifica catálogo en READ ONLY con ROLLBACK;
no aplica migraciones ni aprende del esquema remoto.

Se conserva REQUIRED_SCHEMA=003 como identificador de la migración más alta y el formato
de /ready. El manifiesto declara required_migrations=[001,002,003]. Un /ready válido comprueba
el catálogo completo; /health no prueba compatibilidad. El nuevo backend rechaza 001+003 sin 002.

El catálogo se generó exclusivamente desde Docker propio. Se comprobó, normalizando finales
de línea, que las secciones de las diez tablas anteriores permanecen iguales.
El archivo sigue llamándose app/schema_003.json por compatibilidad del verificador.
stop_incidents solo se comprueba como parte de 002: no se implementan funciones de Sprint 3.

## Endpoints y permisos

Todos requieren JWT válido ES256/RS256 y perfil encargado_municipal de PostgreSQL.
Identidad/rol conservan los mecanismos JWKS existentes. No se admiten responsables
arbitrarios enviados por React.

| Método / ruta | Función |
| --- | --- |
| POST /municipal/route-proposals | Crear propuesta pendiente o registrar resultado explícitamente no verificado/de prueba |
| GET /municipal/route-proposals | Resúmenes con filtros y paginación |
| GET /municipal/route-proposals/{id} | Detalle, snapshot, configuración, paradas, exclusiones y geometría recibida |
| GET /municipal/route-proposals/{id}/stops | Paradas ordenadas, con paginación |
| GET /municipal/route-proposals/{id}/excluded-events | Exclusiones y motivos, con paginación |

limit 1..200 (50 por defecto), offset >=0 (0 por defecto). El listado admite shift_id,
calculation_status y result_origin. status solo admite propuesta; consultar otros estados
es un flujo posterior. El detalle de un plan con otro estado devuelve 404 por esta API.
Se devuelve una lista, sin total global; orden created_at DESC/id DESC.

No existen endpoints /approval, /assign ni /execute. POST crea siempre status=propuesta,
approved_by/approved_at nulos y paradas pendiente, sin asignar trabajo al chofer ni cambiar
turnos, estados de eventos o reportes.

## Procedencia: campos que D1 debe mostrar

| result_origin | calculation_status | Significado |
| --- | --- | --- |
| pending | pending | Entrada registrada; ningún cálculo/recorrido disponible |
| test_fixture | completed | Resultado explícito de prueba; no optimización real |
| municipal_unverified | completed | Datos aportados por encargado; motor/procedencia no verificados |
| d3 | completed | Reservado al adaptador interno tras verificar un proveedor; integración real pendiente |
| legacy_unknown | unknown | Registro histórico sin metadatos suficientes; no se inventa procedencia |

**operational=false en todos los casos**. completed significa “resultado estructurado almacenado”,
no que este backend ejecutó ni certificó un optimizador. El origen se asigna en el servidor:
el cliente no puede enviar result_origin=d3, provider_reference, created_by ni status.
configuration del cliente queda dentro de parameters; no puede sobrescribir configuration._d2.

test_data=true solo clasifica datos como prueba y requiere result. Si el cliente envía un
resultado sin esa marca, igualmente queda municipal_unverified, nunca D3 u operativo.
La etiqueta de procedencia/limitaciones no debe ocultarse al representar métricas o geometría.

## Crear una propuesta pendiente

Ejemplo ficticio:

```json
{
  "proposal_id": "50000000-0000-4000-8000-000000000001",
  "shift_id": "50000000-0000-4000-8000-000000000010",
  "event_ids": [
    "50000000-0000-4000-8000-000000000020",
    "50000000-0000-4000-8000-000000000021",
    "50000000-0000-4000-8000-000000000022"
  ],
  "configuration": {"scenario": "revision-municipal"},
  "result": null,
  "test_data": false
}
```

proposal_id es un UUID nuevo por intención y se conserva en reintentos idénticos.
shift_id y 1..200 event_ids distintos son obligatorios. El turno determina vehículo,
chofer, salida y descarga: no se reciben recursos discordantes por otros campos.
configuration es JSON finito de hasta 32 KiB, sin secretos.

La respuesta es 201 con ProposalDetail. Una propuesta pendiente devuelve algorithm_version=null,
sin paradas, geometría, distancia ni duración inventadas. Internamente la columna NOT NULL
algorithm_version almacena el marcador pending, que **no es una versión de algoritmo ejecutado**.

## Resultado estructurado de prueba o no verificado

Para registrar una propuesta con resultado, añadir result al cuerpo anterior y un UUID nuevo.
Este es un ejemplo de formato ficticio, no resultados de optimización:

```json
{
  "algorithm_version": "controlled-fixture-v1",
  "matrix_source": null,
  "stops": [
    {"event_id": "50000000-0000-4000-8000-000000000021", "order": 1, "estimated_service_minutes": null},
    {"event_id": "50000000-0000-4000-8000-000000000020", "order": 2, "estimated_service_minutes": null}
  ],
  "excluded_events": [
    {"event_id": "50000000-0000-4000-8000-000000000022", "reason": "Excluido en la fixture de integración"}
  ],
  "distance_m": null,
  "estimated_duration_seconds": null,
  "geometry_geojson": null,
  "limitations": ["Datos de prueba; no se ejecutó un optimizador"],
  "requirements": {"vehicle_types": null, "required_capacity_kg": null},
  "input_hash": null
}
```

Usar test_data=true para ese ejemplo de prueba. Las paradas/exclusiones deben cubrir exactamente
event_ids; no se aceptan duplicados, eventos omitidos ni un evento incluido y excluido a la vez.
order es entero estricto 1..N, consecutivo y en el mismo orden que la lista.
Una respuesta sin paradas es válida si todos los eventos están excluidos con motivo;
no puede incluir geometría de recorrido.

algorithm_version es obligatorio, recortado y de 1..120 caracteres. matrix_source es nullable,
de 1..120 si se aporta. distance_m y estimated_duration_seconds son números finitos >=0 o null.
estimated_service_minutes es finito >0 o null. No se convierten null en cero.
Cada exclusión requiere motivo no vacío de hasta 1000 caracteres.

Se admite GeoJSON **LineString WGS84 2D**, de 2 a 5000 posiciones [longitude,latitude],
con coordenadas finitas y rangos [-180,180]/[-90,90]. No se aceptan Point, coordenadas 3D ni
GeoJSON arbitrario. La geometría se almacena exactamente validada; no se generan segmentos
uniendo eventos ni se calcula red vial. Validez geométrica no demuestra viabilidad/topología vial.

## Consulta: resumen, paradas y exclusiones

Ejemplo de resumen de propuesta pendiente (el detalle agrega los campos indicados abajo):

```json
{
  "id": "50000000-0000-4000-8000-000000000001",
  "shift_id": "50000000-0000-4000-8000-000000000010",
  "status": "propuesta",
  "created_by": "50000000-0000-4000-8000-000000000099",
  "created_at": "2026-10-30T15:00:00Z",
  "calculation_status": "pending",
  "result_origin": "pending",
  "operational": false,
  "input_hash": "0000000000000000000000000000000000000000000000000000000000000000",
  "algorithm_version": null,
  "matrix_source": null,
  "distance_m": null,
  "estimated_duration_seconds": null,
  "stop_count": 0,
  "excluded_count": 0,
  "limitations": ["Propuesta pendiente de cálculo; no contiene un recorrido calculado."],
  "unknowns": ["calculation_pending"]
}
```

El hash de ceros es un marcador del ejemplo; la respuesta real contiene SHA-256 calculado por
el servidor. Las respuestas reales incluyen todas las limitaciones derivadas que correspondan.

Una parada del endpoint paginado tiene este formato:

```json
{
  "id": "50000000-0000-4000-8000-000000000030",
  "route_plan_id": "50000000-0000-4000-8000-000000000001",
  "event_id": "50000000-0000-4000-8000-000000000021",
  "order": 1,
  "estimated_service_minutes": null,
  "status": "pendiente"
}
```

El detalle agrega input_snapshot, configuration, geometry_geojson, stops y excluded_events.
El listado no descarga todos los snapshots/geometrías: cuenta paradas por lote, sin una consulta
por propuesta. Las listas de hijos admiten paginación y preservan order.

## Snapshot y limitaciones: no inventar datos operativos

input_snapshot contiene schema=route-input-v1, captured_at y operational:
solicitante, IDs candidatos, parámetros, turno/fechas/chofer, vehículo/capacidad,
sitios/tipos/coordenadas y eventos/estado/intervención/vínculos.
Las relaciones incluyen report_id y last_decision_id para detectar cambios de agrupación,
incluido un cambio que luego vuelve al evento original.

El snapshot se construye desde PostgreSQL; no se admite uno arbitrario en HTTP.
La huella cubre operational, no la hora de captura. Un resultado con input_hash debe coincidir.
No calcular ese hash en React: utilizar el que entrega la API.

Se validan turno programado no finalizado, intervalo válido, vehículo disponible, chofer con rol
adecuado y sitios activos de tipo salida/descarga/ambos. Los eventos incluidos deben estar
en_revision o abierto, sin closed_at. Eventos históricos solo pueden figurar como exclusiones explícitas.
Una propuesta pendiente exige candidatos activos; un resultado interno posterior se rechaza
si los datos del snapshot cambiaron.

requirements.vehicle_types y required_capacity_kg son requisitos declarados del resultado.
Si se conocen tipo/capacidad y son incompatibles, se devuelve 409. Si falta capacidad o carga
no se inventan y se registran limitaciones. No se deduce carga, acceso ni compatibilidad de intervención
desde texto libre. Los requisitos recibidos no están certificados cuando la fuente no está verificada.

El servidor combina las limitaciones recibidas con códigos/textos explícitos para capacidad/carga,
compatibilidad, matriz, geometría, estimaciones y tiempos de servicio desconocidos, eventos
en revisión, ausencia de paradas y origen de prueba/no verificado.
configuration._d2 guarda procedencia, registered_by, hashes, estado del cálculo y unknowns;
configuration.parameters conserva la configuración aportada y requirements los requisitos.

La propuesta terminada conserva su snapshot aunque los datos cambien después.
Esta API no declara vigencia para aprobación: el flujo posterior deberá revalidar recursos,
agrupaciones y estados antes de aprobar/asignar. D1 debe mostrar fecha y procedencia,
sin sustituir silenciosamente las coordenadas del snapshot por datos actuales.

## Adaptador interno preparado para D3

`app/planner_adapter.py:register_planner_result` recibe sesión SQLAlchemy, contexto municipal
validado, proposal_id, resultado estructurado, origin y provider_reference.
Valida DTO/identificador, perfil, input_hash y correspondencia con la propuesta pendiente.
Vuelve a leer los recursos reales y compara su huella antes de guardar.

Ejemplo de prueba controlada (no ejecutar contra Supabase compartido):

```python
result["input_hash"] = pending_proposal.input_hash
stored = register_planner_result(
    db, authenticated_actor, pending_proposal.id, result,
    origin="test_fixture", provider_reference="controlled-fixture"
)
```

origin=d3 está reservado al código servidor después de autenticar un proveedor real.
**No existe una ruta HTTP que deje al cliente elegirlo ni se ha activado una conexión D3.**
La futura integración debe verificar origen y contexto municipal antes de invocar el adaptador;
provider_reference es un identificador no secreto, no una URL con credenciales.
Los tests del adaptador usan origin=test_fixture, no certifican que D3 haya producido un resultado real.
Estas funciones SQL síncronas deben ejecutarse en un hilo/job síncrono, no bloquear un bucle async.

El adaptador completa una propuesta pendiente una sola vez. Un resultado idéntico del mismo
actor/proveedor se recupera sin duplicar paradas; otro resultado para el mismo ID devuelve 409:
debe registrarse una alternativa con otro ID. No se sobrescribe un resultado ya registrado.
Si cambia una agrupación, recurso o configuración de entrada, se exige una propuesta nueva.

Pendiente de acordar con D3: DTO/versionado final, unidades/nulos/tiempos de servicio,
requisitos operativos, matriz y vigencia, fidelidad vial de GeoJSON, procedencia autenticada,
tratamiento de infeasibilidad y entrega correlacionada al input_hash. No se implementan OR-Tools,
OSRM, Sentence Transformers ni llamadas a algoritmos existentes.

## Transacciones, concurrencia y recuperación

POST utiliza proposal_id como clave de intención. Una petición idéntica y mismo actor recupera
la misma propuesta (201); otro cuerpo/actor reutilizando ese ID devuelve 409. No se repite la escritura.

Un bloqueo transaccional advisory por UUID serializa ese identificador. Se bloquean turno,
vehículo, chofer, sitios y eventos antes de capturar datos. Los eventos/sitios se adquieren en
orden UUID; no se toman bloqueos de reportes después de eventos, conservando compatibilidad
con las agrupaciones que bloquean reporte→evento. lock_timeout=3 s y statement_timeout=15 s
son locales a la escritura.

Propuesta y paradas se confirman en una transacción. El fallo de una parada revierte el padre
y todos los hijos; al completar una pendiente, el rollback conserva la pendiente original.
No se eliminan ni alteran eventos, reportes, turnos o decisiones.

Se permiten propuestas alternativas del mismo turno: el índice de 002 solo restringe estados
ejecutables, no propuesta. El índice se conserva y se prueba directamente con ROLLBACK,
sin crear un endpoint de aprobación.

Ante resultado incierto del commit se devuelve 503, sin reintento automático ni borrado:
consultar GET por proposal_id antes de reenviar exactamente la misma intención.
La respuesta se materializa antes del commit para evitar lecturas posteriores ambiguas.
La persistencia de ID, configuración y paradas permite recuperar tras reinicio.

## Errores

401 sin JWT/inválido; 403 perfil sin permiso; 404 turno/evento/propuesta inexistente;
409 incompatibilidad, entrada obsoleta o ID reutilizado; 422 contrato inválido;
503 fallo temporal de BD, bloqueo o commit no confirmado.

```json
{"detail": "Los datos operativos cambiaron; solicita una propuesta nueva"}
```

```json
{"detail": [{"type": "finite_number", "loc": ["body", "result", "distance_m"], "msg": "Input should be a finite number"}]}
```

Los errores no exponen SQL, DSN, claves o JWT. Se reutiliza el manejo de validación seguro
para que NaN/infinito no conviertan un rechazo 422 en 500. Los logs no guardan cuerpos ni geometrías.

## Pruebas y evidencia

Resultados ejecutados:

| Comprobación | Resultado | Evidencia local |
| --- | --- | --- |
| Primer incremento de persistencia/DTO | 43 aprobadas, 0 fallidas, 3.74 s | .test-artifacts/reciwise-d2-test-6ceb0522212041ab8f7a60b262b9c958/ |
| Módulo final routes | **123 aprobadas, 0 fallidas/omitidas**, 59.97 s | .test-artifacts/reciwise-d2-test-9118c8b763f44181ad51944bd6d25176/pytest.xml |
| Regresión D2 final | **595 aprobadas, 0 fallidas/errores, 12 omitidas**, 318.00 s | .test-artifacts/reciwise-d2-test-a9ce3f810a634286a98e6b9e261d66e8/pytest.xml |
| Ejemplos JSON | 6 parseados, 4 validados con DTO | .test-artifacts/routes-sprint2/documentation-check.json |

Las nuevas pruebas suman **38 unitarias de contratos**, **85 de integración PostgreSQL**
y **8 de guardia** adicionales: 464 previas + 131 nuevas = 595 aprobadas.
Se conservaron las doce omisiones: dos casos con registros piloto preexistentes ausentes,
nueve accesos REST anónimos Supabase sin configuración y un JWT ciudadano real no disponible.
No se declaran aprobadas ni se sustituyen por SQLite.

PostgreSQL **17.11**, imágenes/contenedores propios y publicación solo localhost.
environment.json registra identidad, versión, hashes de 001/002/003 y del catálogo.
routes-persistence.json y routes-process-restart.json registran recuperación con conexión nueva
y dos PID FastAPI diferentes. Las identidades JWT son ficticias con criptografía/JWKS local;
los resultados del planificador son fixtures, no datos calculados por D3.
Todos los contenedores propios se eliminaron al finalizar.

Se conservaron los logs en .test-artifacts/routes-sprint2/ y un comprobante SHA-256 de alcance.
schema-comparison.json confirma las diez tablas previas sin cambios de catálogo.
git diff --check y revisión de espacios pasan. Persiste la deprecación Starlette/httpx anterior;
no se modificaron dependencias para ocultarla. No se reejecutaron compilación ni navegador
React en esta tarea backend; sus archivos se verificaron íntegros por hash.

```powershell
.\.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase routes
.\.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase all
```

El runner crea Docker/PostgreSQL propios, con puerto solo 127.0.0.1 y marcador de identidad;
no lee .env ni toca proyectos remotos. Aplica 001+002+003 sin modificaciones solo allí y elimina
su contenedor al terminar. No reemplazar la URL por Supabase. Sin entorno seguro, las pruebas
de integración se omiten; no hay sustitución SQLite para concurrencia o restricciones.

Se comprueban DTO, JWT ES256/RS256 con JWKS local y perfiles de prueba, permisos,
snapshot/orden/exclusiones, alternativas, límites operativos, rollback, idempotencia concurrente,
commit incierto, restricciones PostgreSQL, denegación SQL anon/authenticated y reinicio de procesos.
Las pruebas SQL de roles no equivalen a autenticación real vía Supabase/PostgREST.
El worker de reinicio reutilizado tiene un encabezado de identidad exclusivamente de pruebas,
protegido por marcador local; no se añade ese mecanismo al código de producción.

## Estado de integración y entrega

| Función | Estado comprobable | Pendiente |
| --- | --- | --- |
| Crear/listar/detalle/paradas/exclusiones | Implementado en FastAPI/SQLAlchemy | D1 debe conectar pantallas |
| Propuesta pendiente y resultado de prueba/no verificado | Implementado, marcado no operativo | Aceptación de UX/contrato |
| Snapshot, huellas, rollback y recuperación | Implementado | Revalidación al aprobar en incremento posterior |
| Adaptador interno de resultado estructurado | Preparado y probado con fixtures | Autenticar/conectar proveedor D3 real |
| Distancias/tiempos/GeoJSON | Solo se conservan datos recibidos y validan | D3 debe producirlos con procedencia/limitaciones |
| Aprobación, asignación y ejecución | No implementadas | Flujo posterior |
| Supabase compartido | No contactado ni migrado | Revisión/autorización 002+003, respaldo y demás NO-GO |

D1 debe utilizar result_origin/calculation_status/operational/limitations, adaptar
estimated_duration_seconds a su duration_seconds y geometry_geojson a geometry,
y conservar order de paradas. No debe generar líneas ni tiempos faltantes.
Las fotografías/eventos/recursos conservan sus endpoints. El frontend sigue intacto,
con sus simulaciones previas; esta tarea no afirma que la pantalla ya esté conectada.

El siguiente incremento debe acordar y probar el contrato real D2↔D3/D1 en el entorno aislado.
La aprobación y asignación requerirán validaciones y autorización específicas posteriores.
Se mantienen las doce omisiones históricas de D2 y el NO-GO de despliegue; no se declara
terminado el Sprint 2 ni se configuran servicios programados.

## Archivos

Nuevos: app/route_contracts.py, app/route_proposals.py, app/planner_adapter.py,
tests/test_route_contracts.py, tests/test_route_proposals.py y este documento.
Modificados: app/main.py, app/models.py, app/schema_guard.py, app/schema_003.json,
tests/isolated_postgres.py, tests/run_isolated_postgres.py, tests/test_schema_guard.py,
docs/CONTRATOS_D3.md, docs/API_SPRINT1.md, docs/API_EVENTOS_SPRINT2_D2.md
y docs/API_AGRUPACIONES_SPRINT2_D2.md.
No se modifican migraciones, frontend, módulos D3, .env, credenciales ni dependencias.
