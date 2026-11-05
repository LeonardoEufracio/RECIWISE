# Sprint 2 D2 · Primer incremento de eventos

Fecha: 30 de octubre de 2026, America/Lima. Se implementa API y persistencia municipal sobre tablas existentes. **NO-GO para desplegar el backend en Supabase compartido.** No se aplica allí 003, no se modifican credenciales, frontend ni algoritmos D3 y no se hace push/merge.

**Actualización de arranque:** el incremento posterior de [propuestas de rutas](API_RUTAS_SPRINT2_D2.md)
amplía la guardia global a 001+002+003. Las operaciones de eventos siguen usando 001,
pero el nuevo backend completo también exige las estructuras de 002. La evidencia histórica
de este documento se conserva; no se migra el compartido.

## Decisión de contrato y correspondencia con PostgreSQL

Se revisaron `docs/FRONTEND_SPRINT2.md`, `docs/CONTRATOS_D3.md`, la pantalla/adaptadores municipales, modelos, esquemas, guardia, migraciones y pruebas.

| Dato requerido | Estructura existente en 001 | Contrato inicial |
| --- | --- | --- |
| ID, ubicación | events.id/latitude/longitude | UUID y números; nombres latitude/longitude conservados |
| Estado | events.state | en_revision, abierto, programado, atendido, cerrado, descartado |
| Intervención | events.intervention_type, text nullable | Texto opcional, sin inventar catálogo D3 |
| Fechas | events.created_at/closed_at | ISO con zona; cierre nullable |
| Reportes vinculados | event_reports, PK report_id y FK event_id | report_ids y report_count; consulta paginada de reportes |
| Procedencia del vínculo | linked_by/linked_at/linkage_method | Asociación inicial manual, autor municipal y fecha |
| Auditoría | grouping_decisions | Decisión agrupar por cada vínculo inicial, autor/fecha/notas |
| Prioridad disponible | priority_score/priority_factors/priority_config_version | Objeto priority o null; valores almacenados, sin calcular |
| Restricciones operativas | No hay columna | restrictions: null, información no disponible |
| Factores tipados, umbrales y similitud | No hay contrato definitivo D3 | Fuera del incremento; no se simulan en la API |

La migración 002 solo prepara rutas/ejecución y **no es requisito** de estos endpoints. 003 sigue siendo obligatoria para el backend. Se reutilizan las tablas de 001 sin agregar migraciones ni crear tablas al arrancar.

El formato anidado `priority` sigue la intención del frontend, pero `factors` conserva el JSONB almacenado, cuya forma no está acordada con D3. No se transforma un objeto en factores ficticios label/value. `restrictions: null` tampoco significa “sin restricciones”. Estas dos diferencias requieren un DTO/adaptador de D1.

## Autorización

Los cuatro endpoints requieren JWT y perfil `encargado_municipal`. Se reutilizan `get_current_actor` y `require_roles`: JWKS, firma ES256/RS256, issuer, audience, expiración y perfil de PostgreSQL.

- Sin token o con token inválido: 401.
- Ciudadano, chofer o identidad firmada sin perfil: 403.
- El frontend no concede permisos y no hay selección pública de roles.
- No hay acceso nuevo directo desde React a las tablas ni cambios de RLS/permisos.

Las conexiones administrativas del backend no demuestran RLS por sí solas; la guardia comprueba catálogo, RLS y ausencia de permisos directos a anon/authenticated. La suite conserva las verificaciones SQL aisladas existentes. Auth/Storage de Supabase reales siguen pendientes.

## Endpoints y JSON

### GET /municipal/events

Parámetros: `limit` de 1 a 200 (50 por defecto), `offset` >= 0 (0 por defecto), `state` opcional de la enumeración existente. Orden estable: created_at DESC, id DESC. Devuelve una **lista**, no un objeto con total. Sin coincidencias o al superar el final devuelve [].

Ejemplo ficticio:

```json
[
  {
    "id": "d0000000-0000-4000-8000-000000000040",
    "latitude": -12.0528,
    "longitude": -75.226,
    "state": "en_revision",
    "intervention_type": "Recolección manual",
    "priority": null,
    "restrictions": null,
    "report_ids": ["d0000000-0000-4000-8000-000000000001"],
    "report_count": 1,
    "created_at": "2026-10-30T19:00:00Z",
    "closed_at": null
  }
]
```

`report_ids` se ordena por UUID. Su cantidad coincide con report_count; no se hace una consulta por cada evento, sino una consulta de eventos y otra de vínculos de la página. Los reportes asociados se recuperan mediante el endpoint paginado siguiente.

### GET /municipal/events/{event_id}

Devuelve un objeto del mismo contrato anterior. ID desconocido: 404; ID mal formado: 422. Permite consultar estados/cierres/prioridades ya almacenados, aunque su modificación no se implementa aquí.

Si hay información de prioridad:

```json
{
  "score": 2.5,
  "factors": {"factor_existente": "ejemplo de JSON almacenado"},
  "version": "version-almacenada-de-ejemplo"
}
```

Ese ejemplo describe formato, no una puntuación calculada por esta entrega. Si los tres campos están ausentes se devuelve priority: null. Si el score no es representable como un número finito se devuelve un error controlado 503, sin inventar un reemplazo ni modificar el registro.

### GET /municipal/events/{event_id}/reports

Devuelve `list[ReportOut]` con el mismo contrato de reportes existente: id, citizen_id, description, latitude, longitude, observed_at, created_at, waste_type y status. No agrega contactos ni datos personales de perfiles. Paginación `limit` 1..200 y `offset` >=0; orden created_at DESC, id DESC. Un evento sin reportes devuelve []; uno inexistente, 404.

Las fotografías mantienen `GET /reports/{report_id}/photos` y los enlaces privados existentes; no se duplican archivos ni contratos.

### POST /municipal/events

Cuerpo:

```json
{
  "latitude": -12.0528,
  "longitude": -75.226,
  "intervention_type": "Recolección manual",
  "report_ids": ["d0000000-0000-4000-8000-000000000001"]
}
```

- Coordenadas obligatorias, finitas, latitude entre -90 y 90, longitude entre -180 y 180.
- intervention_type opcional/null; si se proporciona texto, se recortan espacios y se validan 1..120 caracteres. Es un límite de API, no un catálogo de IA.
- report_ids opcional (por defecto []), UUID distintos, máximo 100 por creación.
- Estado inicial **en_revision**, con fechas del servidor. No se aceptan state, closed_at, prioridad, autor ni campos desconocidos. No se implementa transición/cierre en este incremento.
- Se permite crear un evento manual sin reportes; no se inventan observaciones para completarlo.

Los errores de validación de estos endpoints mantienen HTTP 422 y detail con type/loc/msg.
No incluyen input ni ctx: así tampoco se reflejan cuerpos del usuario o valores NaN/infinito
que no pueden serializarse en JSON. Se reprodujo el fallo del manejador estándar de FastAPI
(422 convertido en 500 al intentar representar input=NaN) y se corrigió solo en el router de eventos.

Éxito: 201 con `EventOut`. Todos los reportes deben existir; si falta alguno devuelve 404 y no crea parte del evento. Si uno ya pertenece a un evento devuelve 409 y no lo reasigna, incluso si el evento anterior está cerrado. Moverlo requiere un futuro flujo explícito de revisión.

Evento, vínculos y decisiones se guardan en **una transacción**. Los reportes se bloquean en orden de UUID con FOR UPDATE y la PK report_id mantiene la exclusividad en PostgreSQL. Dos creaciones simultáneas sobre el mismo reporte producen 201/409, no dos relaciones ni un evento huérfano.

Por cada vínculo se registra linkage_method=manual, linked_by y una decisión agrupar con decided_by, timestamp y nota de procedencia. Los factores quedan vacíos y config_version nulo: no se atribuye un cálculo a D3. **No se modifica reports.status**.

El resultado se materializa antes del commit. Ante error de persistencia se revierte la transacción y se devuelve 503; ante conflicto de integridad, 409. Si el commit se realizó pero se perdió su confirmación se devuelve 503 **sin repetir, borrar ni compensar** ese evento. Hay que consultar antes de reintentar.

POST no es idempotente: puede haber eventos legítimos en las mismas coordenadas. Para registros sin reportes no existe todavía una clave de operación que permita identificar inequívocamente un commit incierto. Una futura idempotencia debe acordarse con D1/D2; no se resuelve deduplicando por proximidad.

La tabla events no tiene created_by: se audita el autor de los vínculos/decisiones, pero no se agrega una autoría ficticia a eventos sin reportes. Si el equipo la exige para cada alta vacía, deberá acordarse una ampliación de persistencia.

## Guardia y aislamiento

La guardia se amplía a events, event_reports y grouping_decisions, incluidas columnas, PK/FK, checks, índices, RLS y permisos. Se conserva la verificación de las siete tablas anteriores, las exclusiones de reservas, posiciones de fotos y registro durable.

`app/schema_003.json` se regeneró **solo desde un PostgreSQL desechable propio con 001+003 sin modificar**. La comparación de las secciones de las siete tablas anteriores no encontró cambios. Es una referencia de catálogo del backend, no una migración ni una política nueva.

En ejecución, la verificación sigue siendo READ ONLY, con ROLLBACK, sin aprendizaje del esquema remoto ni interruptor para omitirla. Arranque y readiness rechazan estructuras parciales; /health no prueba preparación. La suite añade casos que quitan checks, unicidad o FK y alteran RLS/permisos, únicamente en bases desechables.

## Pruebas reproducibles

Requisitos: Python/venv del proyecto, Docker disponible, imagen local postgres:17-alpine y dependencias existentes.

```powershell
.\.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase events
.\.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase all
```

El ejecutor crea un contenedor propio etiquetado, publica PostgreSQL únicamente en 127.0.0.1 con puerto libre, usa nombre aleatorio y marcador dentro de la base. Verifica identidad antes de modificar, no lee .env y establece servicios/credenciales ficticios solo en el proceso. Aplica 001+003 exclusivamente al contenedor desechable y lo elimina al finalizar, sin reutilizar ni eliminar otros contenedores. No se debe cambiar la URL a Supabase ni ejecutar estos casos contra una base compartida.

Ese ejecutor no deja un backend/base encendido para una demo manual. Para la integración interactiva
de D1 hay que proporcionar PostgreSQL local aislado compatible y una configuración Auth/JWKS de pruebas
verificable mediante variables del proceso; no iniciar FastAPI usando por defecto el .env del principal.

`--phase events` también queda incluido en `--phase all`. Sin el entorno aislado las pruebas nuevas se omiten: **no usan SQLite como sustituto**.

Resultados finales comprobados:

| Ejecución | Resultado | Evidencia local |
| --- | --- | --- |
| Fase events final | **73 aprobadas, 0 fallidas, 0 omitidas**, 13.17 s | .test-artifacts/reciwise-d2-test-088a0821e04849f6ae836a8afb4a0c05/pytest.xml |
| Suite D2 completa final, incluyendo events y guardia ampliada | **353 aprobadas, 0 fallidas, 12 omitidas**, 97.11 s | .test-artifacts/reciwise-d2-test-34504b8066194a688ec77d56da50e517/pytest.xml |
| Incremento sobre la suite anterior de 273 | **80 casos nuevos** | 73 de eventos + 7 de guardia |
| Catálogo anterior | **Sin cambios en las siete tablas ya verificadas** | Comparación del manifiesto previo con las mismas secciones del nuevo |

Cada ejecución usa PostgreSQL 17.11 aislado. environment.json registra versión/imagen, identidad
del contenedor/base y hashes de 001/003. events-persistence.json y events-concurrency.json
registran la recuperación por conexión nueva y los estados 201/409 de la carrera.
Los contenedores propios fueron eliminados al finalizar.

Los logs de la tarea se guardan en .test-artifacts/events-sprint2/ (ignorados por Git):
events-final.log, full-d2-final.log y scope-verification.json.
Se conserva también el log del caso límite inicial que reprodujo cuatro fallos de serialización,
corregidos antes de las ejecuciones finales. No se declaran aprobadas esas ejecuciones fallidas.

Las 12 omisiones finales siguen siendo: dos comprobaciones sobre registros piloto preexistentes
ausentes en la base desechable, nueve accesos REST anónimos que requieren URL/clave pública
Supabase y una comprobación con JWT ciudadano real. Ninguna se sustituye por SQLite ni se
promueve a aprobada. La persistencia de eventos nuevos sí se prueba con registros ficticios
propios en PostgreSQL, pero no equivale a comprobar aquellos registros piloto.

Un aviso de deprecación Starlette/httpx no impidió las pruebas. No se cambiaron dependencias.
No se reejecutaron navegador/compilación React en esta tarea D2; los archivos frontend se
compararon con sus hashes iniciales y permanecen intactos.

Pruebas de esta entrega:

- Los cuatro endpoints, con JWT ES256 y RS256 firmados usando claves efímeras y JWKS servido en memoria; autorización municipal, 401 y 403. No es Supabase Auth real.
- Creación/consulta y campos compatibles con la pantalla, estados/cierre almacenados, prioridad nullable o JSON existente.
- Validación, UUID, paginación, límites de coordenadas y campos reservados.
- Persistencia PostgreSQL tras abrir una nueva conexión, FKs, autoría de vínculos y auditoría; reporte conserva recibido.
- Asociación simultánea de un reporte y protección PostgreSQL.
- Error SQL real durante la auditoría, comprobando rollback de evento y relaciones.
- Pérdida simulada de confirmación tras commit PostgreSQL real; una única escritura, recuperación por consulta y ninguna eliminación.
- Fallos de lectura saneados, incluida la consulta del perfil durante la autenticación antes de
  entrar al endpoint: 503 sin SQL ni detalles de conexión.

Los casos funcionales reutilizan un actor ficticio en la fixture; los casos JWT retiran ese reemplazo y verifican firma/claims/perfil de verdad. La guardia PostgreSQL no se sustituye en los casos nuevos. La suite D2 histórica incluye pruebas unitarias SQLite, que se distinguen de los casos PostgreSQL reales.

## Entrega para D1

No se modificó el frontend. `Events.tsx` sigue dependiendo de su adaptador de demostración y **todavía no está conectado** automáticamente a esta API.

1. Añadir funciones de servicio para GET de eventos/detalle/reportes, con el Api existente y Bearer de Supabase. No cambiar latitude/longitude ni inferir el rol.
2. Definir un DTO wire diferente del modelo interno `EventRecord`. Mapear state, coordenadas, fechas, report_ids y priority.score directamente.
3. Tratar restrictions=null como desconocido. Si el componente necesita un arreglo vacío, acompañarlo de “Sin información; no implica ausencia de restricciones”.
4. No asumir que priority.factors es label/value[]. Conservar el JSON o mostrar solo score/version y un aviso hasta acordar el adaptador con D3. No recalcular ni descartar silenciosamente factores.
5. Recuperar los reportes asociados del endpoint paginado del evento, sin depender de los reportes municipales de una sola página global. Renderizar descripción, fechas/estado y fotos por sus contratos existentes.
6. Sustituir la fuente real de Eventos, manteniendo independientes fixtures y transiciones locales de demo. Un GET fallido no debe activar datos simulados silenciosamente.
7. Para el alta municipal, enviar exclusivamente los campos del POST, confirmar la ubicación y la asociación manual. 409 exige revisión; 503 exige consultar el resultado antes de reintentar.
8. Validar juntos navegador → FastAPI → PostgreSQL local compatible antes de afirmar que la pantalla está conectada. Las pruebas actuales de frontend con mocks siguen siendo evidencia separada.

El filtro UI Todos corresponde a no enviar state; Cerrados a state=cerrado. No cerrados no equivale
a state=abierto: también puede incluir en_revision/programado y otros estados existentes.
Este incremento admite un estado exacto; D1 debe conservar una paginación/búsqueda coherente
al filtrar esa categoría o acordar un filtro adicional. No enviar valores UI como state=cerrados.

## Fuera del incremento y condiciones pendientes

- Sin agrupación automática, similitud, umbrales, cálculo de prioridad, rutas, ejecución de chofer ni llamada a algoritmos D3.
- Pendientes D3: formato/escala/procedencia de prioridad y factores, versión, explicación/datos faltantes y sugerencias de comparación según CONTRATOS_D3.
- Pendientes D2 posteriores: consultas/decisiones generales de agrupación, reasignación auditada, transiciones de eventos, idempotencia y cualquier nueva columna acordada.
- Pendientes de aceptación: conexión D1 y recorrido de navegador con estos endpoints, aceptación del equipo y validación de servicios remotos en un destino autorizado.
- Se mantienen las 12 omisiones históricas de D2; no se convierten en aprobaciones. No se usa el principal para cubrirlas.
- No se ejecutan 002/003 en Supabase compartido, no se configura conciliación real y no se declara cerrado ningún sprint.

## Archivos del incremento

- app/events.py: router municipal, consulta, transacción, asociación manual y errores.
- app/models.py: mapeos de las tres tablas ya existentes.
- app/schemas.py: contratos de creación, consulta y prioridad disponible.
- app/main.py: registro del router, sin cambiar los endpoints anteriores.
- app/schema_guard.py y app/schema_003.json: catálogo requerido ampliado.
- tests/test_events.py: pruebas nuevas PostgreSQL/JWT.
- tests/test_schema_guard.py: casos adicionales de incompatibilidad de eventos.
- tests/run_isolated_postgres.py: fase events y su inclusión en all.
- docs/API_EVENTOS_SPRINT2_D2.md, docs/CONTRATOS_D3.md y docs/API_SPRINT1.md: contratos, evidencia y seguimiento, conservando la evidencia histórica.

## Actualización posterior: revisión municipal de agrupaciones

El incremento [API_AGRUPACIONES_SPRINT2_D2.md](API_AGRUPACIONES_SPRINT2_D2.md) añade consultas
de relaciones/candidatos/historial y decisiones transaccionales con revisión esperada.
Resuelve las operaciones generales de confirmar, separar, mantener separado, revisar y corregir;
no implementa transiciones de eventos, IA ni prioridades.

POST /municipal/events conserva su contrato inicial, pero ahora rechaza con 409 cualquier
report_id con historial previo, aunque esté desvinculado. Para ese caso se crea el evento
sin report_ids y luego se usa la decisión con expected_event_id/expected_decision_id.
Así la ruta de alta no omite decisiones municipales ni el control de concurrencia.
Se mantienen los bloqueos sobre reports y la guardia 003, sin migraciones adicionales.
