# Sprint 2 D2 · Revisión municipal de agrupaciones

Fecha: 30 de octubre de 2026, America/Lima. Alcance: API FastAPI, PostgreSQL, contratos, autorización y auditoría. **NO-GO para desplegar el backend actualizado en Supabase principal.** No se declara terminado el Sprint 2.

**Actualización de arranque:** el incremento posterior de [propuestas de rutas](API_RUTAS_SPRINT2_D2.md)
exige globalmente 001+002+003. Las operaciones de agrupación no cambian ni necesitan columnas
nuevas, pero el backend completo ya verifica también las tablas de 002.

## Arquitectura y decisiones

Se reutilizan reports, events, event_reports y grouping_decisions de 001, la guardia de esquema 003, autenticación JWKS ES256/RS256 y los endpoints municipales de eventos. No se modifica la estructura ni se necesita una migración nueva. 002 no es requisito de este incremento.

- `app/groupings.py`: comandos, lecturas y transacciones municipales.
- `app/grouping_contracts.py`: DTO administrativos y contrato provisional de entrada D3, separado de algoritmos.
- `app/events.py`: se reutilizan validación segura de HTTP, rollback, permisos y serialización de eventos. Su alta inicial impide ahora asociar reportes con historial por fuera del control de revisión.
- `event_reports.report_id`, PK existente, garantiza como máximo una asociación por reporte.
- `grouping_decisions` conserva las cuatro decisiones reales: agrupar, separar, mantener_separado y revisar. Una corrección se registra como agrupar, con operación reassign y evento anterior en JSONB.

Todas las escrituras nuevas pasan por **un solo endpoint de decisiones**. No hay cinco endpoints con lógica duplicada ni un endpoint que confirme automáticamente una sugerencia.

## Endpoints

Todos requieren JWT válido y perfil `encargado_municipal`. Ciudadano y chofer reciben 403; sin JWT o con JWT inválido, 401. El responsable siempre procede del perfil identificado mediante el JWT, nunca de React.

| Método / ruta | Entrada | Respuesta y efecto |
| --- | --- | --- |
| GET /municipal/groupings | limit 1..200 (50), offset >=0 (0); event_id, linked y pending_review opcionales | Lista de reportes con asociación actual, evento resumido y revisión |
| GET /municipal/groupings/reports/{report_id} | UUID | Detalle consistente de relación y reporte; 404 si falta |
| GET /municipal/groupings/candidates | report_id obligatorio, limit/offset | Candidatos manuales existentes; no resultados de IA |
| GET /municipal/groupings/decisions | report_id, event_id, decision, limit/offset | Historial append-only, más reciente primero |
| GET /municipal/groupings/decisions/{decision_id} | UUID de decisión/operación | Auditoría persistida; permite resolver commit incierto; 404 si falta |
| POST /municipal/groupings/decisions | Comando descrito abajo | 200 con decisión, relación actual y replayed |

Paginación por lista, sin campo de total. Relaciones: reports.created_at DESC, reports.id DESC. Historial: decided_at DESC, id DESC. Filtrar historial por event_id incluye candidato, resultado y evento anterior registrado.

## Relación reporte-evento y revisión esperada

Ejemplo de elemento de GET /municipal/groupings, inicialmente sin relación:

```json
{
  "report": {
    "id": "10000000-0000-4000-8000-000000000001",
    "citizen_id": "10000000-0000-4000-8000-000000000002",
    "description": "Reporte ficticio junto a un cruce",
    "latitude": -12.0528,
    "longitude": -75.226,
    "observed_at": "2026-10-30T18:00:00Z",
    "created_at": "2026-10-30T18:02:00Z",
    "waste_type": null,
    "status": "recibido"
  },
  "event_id": null,
  "event": null,
  "last_decision_id": null,
  "pending_review": false,
  "linked_at": null,
  "linked_by": null,
  "linkage_method": null,
  "config_version": null
}
```

El detalle por report_id devuelve el mismo objeto. Con relación, event contiene id, latitude,
longitude, state, intervention_type y closed_at. Fotos y detalle completo de eventos conservan
los contratos existentes. No se agregan datos personales de perfil.

La asociación y la última decisión se consultan en **una misma sentencia SQL**, evitando entregar
un evento y una revisión de snapshots distintos. El cliente debe conservar event_id y last_decision_id.

`pending_review` significa estrictamente que **la última decisión de ese reporte es revisar**.
Una decisión municipal posterior cambia esa señal; los casos anteriores siguen consultables
por historial. No es una cola independiente de múltiples tickets por candidato ni elimina revisiones previas.

## Candidatos manuales y ausencia de IA

Ejemplo de envoltura:

```json
{
  "report_id": "10000000-0000-4000-8000-000000000001",
  "event_id": null,
  "last_decision_id": null,
  "source": "manual",
  "d3_available": false,
  "candidates": [
    {
      "id": "30000000-0000-4000-8000-000000000040",
      "latitude": -12.0528,
      "longitude": -75.226,
      "state": "en_revision",
      "intervention_type": "Recolección manual",
      "priority": null,
      "restrictions": null,
      "report_ids": [],
      "report_count": 0,
      "created_at": "2026-10-30T18:05:00Z",
      "closed_at": null
    }
  ]
}
```

Cada candidato utiliza EventOut de [API_EVENTOS_SPRINT2_D2.md](API_EVENTOS_SPRINT2_D2.md).
Se incluyen eventos en_revision o abierto, sin closed_at, excluyendo el evento actual.
El orden es created_at DESC/id DESC, **sin ranking semántico, métricas inventadas ni agrupación por proximidad**.
No se afirma que dos observaciones correspondan al mismo evento. El encargado selecciona y revisa.
No se llama a D3 ni se sustituye una caída del servicio por fixtures.

## Comando único y ejemplos para D1

Campos:

| Campo | Regla |
| --- | --- |
| operation_id | UUID nuevo por intención municipal; se conserva en reintentos idénticos |
| report_id | UUID de reporte existente |
| decision | agrupar, separar, mantener_separado o revisar |
| candidate_event_id | UUID obligatorio salvo separar, que requiere null/omisión |
| expected_event_id | Obligatorio, nullable; copia del event_id observado |
| expected_decision_id | Obligatorio, nullable; copia del last_decision_id observado |
| notes | Opcional/null, se recorta; máximo 2 000 caracteres |
| factors | Objeto JSON opcional, por defecto {}; números finitos; máximo 32 KiB |
| config_version | Opcional/null; texto recortado de 1..120 caracteres |
| suggestion | Snapshot D3 provisional opcional; no autoriza ni ejecuta decisiones |

No se admiten decided_by, fechas de auditoría, coordenadas, prioridad ni campos desconocidos.
No omitir las revisiones: enviar null explícito cuando el reporte todavía no tiene relación/historial.
El UUID de operación es una clave de idempotencia, no una credencial.

Confirmar manualmente:

```json
{
  "operation_id": "20000000-0000-4000-8000-000000000070",
  "report_id": "10000000-0000-4000-8000-000000000001",
  "decision": "agrupar",
  "candidate_event_id": "30000000-0000-4000-8000-000000000040",
  "expected_event_id": null,
  "expected_decision_id": null,
  "notes": "Lugar y observación revisados por el encargado",
  "factors": {"verificacion": "Revisión municipal"},
  "config_version": null
}
```

Corregir la confirmación anterior, manteniendo el reporte y moviendo la relación:

```json
{
  "operation_id": "20000000-0000-4000-8000-000000000071",
  "report_id": "10000000-0000-4000-8000-000000000001",
  "decision": "agrupar",
  "candidate_event_id": "30000000-0000-4000-8000-000000000041",
  "expected_event_id": "30000000-0000-4000-8000-000000000040",
  "expected_decision_id": "20000000-0000-4000-8000-000000000070",
  "notes": "La asociación anterior correspondía a otro lugar"
}
```

Separar después de esa corrección:

```json
{
  "operation_id": "20000000-0000-4000-8000-000000000072",
  "report_id": "10000000-0000-4000-8000-000000000001",
  "decision": "separar",
  "candidate_event_id": null,
  "expected_event_id": "30000000-0000-4000-8000-000000000041",
  "expected_decision_id": "20000000-0000-4000-8000-000000000071",
  "notes": "El reporte describe una acumulación distinta"
}
```

Mantener separado, o registrar revisión, usa ese mismo cuerpo con un **nuevo operation_id**,
decision=mantener_separado o revisar, candidato existente y las revisiones recién consultadas.
Ninguna de ambas decisiones crea, mueve o elimina una relación. Mantener separado respecto
del evento al que ya pertenece devuelve 409: primero se requiere una separación explícita.
Revisar puede registrar duda sobre el evento actual sin modificarlo.

## Respuesta, auditoría y compatibilidad histórica

POST devuelve:

```json
{
  "decision": {
    "id": "20000000-0000-4000-8000-000000000071",
    "report_id": "10000000-0000-4000-8000-000000000001",
    "candidate_event_id": "30000000-0000-4000-8000-000000000041",
    "resulting_event_id": "30000000-0000-4000-8000-000000000041",
    "previous_event_id": "30000000-0000-4000-8000-000000000040",
    "previous_event_known": true,
    "operation": "reassign",
    "decision": "agrupar",
    "factors": {
      "municipal": {},
      "suggestion": null,
      "_d2": {
        "version": 1,
        "operation": "reassign",
        "suggestion_source": null,
        "previous_event_id": "30000000-0000-4000-8000-000000000040",
        "expected_decision_id": "20000000-0000-4000-8000-000000000070",
        "request_hash": "<sha256-calculado-por-el-servidor>"
      }
    },
    "config_version": null,
    "decided_by": "40000000-0000-4000-8000-000000000099",
    "decided_at": "2026-10-30T19:00:00Z",
    "notes": "La asociación anterior correspondía a otro lugar"
  },
  "relation": {
    "report": {
      "id": "10000000-0000-4000-8000-000000000001",
      "citizen_id": "10000000-0000-4000-8000-000000000002",
      "description": "Reporte ficticio junto a un cruce",
      "latitude": -12.0528,
      "longitude": -75.226,
      "observed_at": "2026-10-30T18:00:00Z",
      "created_at": "2026-10-30T18:02:00Z",
      "waste_type": null,
      "status": "recibido"
    },
    "event_id": "30000000-0000-4000-8000-000000000041",
    "event": {
      "id": "30000000-0000-4000-8000-000000000041",
      "latitude": -12.053,
      "longitude": -75.226,
      "state": "en_revision",
      "intervention_type": null,
      "closed_at": null
    },
    "last_decision_id": "20000000-0000-4000-8000-000000000071",
    "pending_review": false,
    "linked_at": "2026-10-30T19:00:00Z",
    "linked_by": "40000000-0000-4000-8000-000000000099",
    "linkage_method": "manual",
    "config_version": null
  },
  "replayed": false
}
```

El historial devuelve una lista de objetos decision; la consulta por ID devuelve uno.
operation distingue confirm, reassign, separate, keep_separate y review sin agregar enumeraciones SQL.

El JSONB existente conserva datos municipales y sugerencia por separado. `_d2` lo construye
exclusivamente el servidor; un cliente no puede sobrescribirlo enviándolo en factors.
El evento anterior se almacena allí porque 001 no tiene previous_event_id. El responsable
se guarda en decided_by/linked_by; las fechas proceden de PostgreSQL.

Los registros anteriores no se reescriben: conservan factors, autor, fecha y demás campos.
Si no tienen esos metadatos, previous_event_known=false, previous_event_id=null y operation=null.
No se inventa una asociación anterior ni se retrocompleta la historia.

Separar elimina **solo event_reports**, nunca reports/events ni sus decisiones históricas.
La reasignación actualiza el vínculo y su procedencia, agregando otra decisión.
Ninguna operación modifica reports.status ni la descripción, ubicación o fechas originales.

## Transacciones, concurrencia e idempotencia

1. Se bloquea el reporte con FOR UPDATE.
2. Se comprueba primero si operation_id ya existe. La misma petición y el mismo actor
   devuelven su decisión sin otra escritura; reutilizar el UUID con otro cuerpo/actor da 409.
3. Se comparan la asociación y la última decisión con los valores esperados. Esto detecta
   incluso volver a “sin asociación” después de una corrección/separación (problema ABA).
4. Se bloquean evento actual y candidato en orden ascendente de UUID.
5. Se verifican compatibilidad y permisos de negocio, se modifica el vínculo y se agrega auditoría.
6. Se construye la respuesta antes de confirmar una sola transacción.

Para confirmar, mover o separar, origen y destino modificados deben estar en_revision o abierto
y no tener closed_at. Eventos programado, atendido, cerrado o descartado quedan protegidos.
Revisar/mantener separado pueden documentar un candidato histórico porque no alteran vínculos.
No se infieren incompatibilidades por distancia, texto, capacidad o intervención no normalizada.

La PK de event_reports continúa siendo la garantía PostgreSQL de exclusividad.
Las fechas nuevas de decisión usan clock_timestamp(), avanzando al menos un microsegundo
respecto de la última decisión del reporte bajo ese mismo bloqueo. La revisión no depende
de UUID aleatorio ni del instante en que comenzó una transacción que pudo estar esperando.
lock_timeout=3 s y statement_timeout=15 s son locales a la transacción de escritura.

La creación existente POST /municipal/events conserva su formato, pero rechaza con 409
reportes que ya tienen historial, aunque estén separados. D1 puede crear el evento vacío
y luego usar la decisión con revisión esperada. Esto evita omitir una revisión previa por otra ruta.
Los escritores futuros, incluido el adaptador D3, deben reutilizar este protocolo.

Con un mismo UUID y cuerpo, dos peticiones simultáneas generan una auditoría y respuestas 200,
una con replayed=false y otra true. Dos correcciones distintas sobre una revisión generan 200/409.
En un replay posterior a otras decisiones, decision es la original y relation muestra el estado
actual; el replay nunca restablece una asociación histórica.

Si la persistencia falla, se revierten vínculo y decisión. Un commit con confirmación perdida
devuelve 503, **sin reintento automático, borrado ni compensación**. Consultar GET decisions/{operation_id};
si hay que reenviar, conservar exactamente UUID y cuerpo. No crear otro UUID para el mismo reintento.
El historial/idempotencia queda en PostgreSQL y sobrevive a nuevas conexiones/procesos.

La auditoría es append-only mediante esta API; no constituye un registro criptográfico
contra un administrador con acceso SQL. No se cambian RLS ni permisos ni se agregan triggers.

## Errores

| HTTP | Significado |
| --- | --- |
| 401 | Falta JWT o es inválido |
| 403 | Perfil sin permiso municipal |
| 404 | Reporte, candidato o decisión inexistente al consultar/decidir |
| 409 | Revisión obsoleta, asociación duplicada/incompatible o UUID reutilizado |
| 422 | Contrato inválido, UUID, campos reservados, puntuación no finita o límites |
| 503 | Bloqueo agotado, fallo de PostgreSQL o resultado de commit no confirmado |

Ejemplos:

```json
{"detail": "La relación o su revisión cambiaron; actualiza antes de decidir"}
```

```json
{"detail": [{"type": "missing", "loc": ["body", "expected_decision_id"], "msg": "Field required"}]}
```

Se reutiliza el manejador seguro del router de eventos para no convertir NaN/infinito en
un 500 al serializar errores. SQL, DSN, contraseñas, JWT y claves no se devuelven ni registran.
Las consultas de perfil que fallen antes del endpoint también reciben el 503 saneado existente.

## Contrato D3 provisional

No se ejecutan modelos de IA, Sentence Transformers ni módulos D3. Una sugerencia opcional
se valida y conserva como snapshot **aportado por el encargado, no verificado como salida D3**:
`_d2.suggestion_source=municipal_input_unverified`. No se presenta como una predicción ejecutada.

```json
{
  "reporte_nuevo_id": "10000000-0000-4000-8000-000000000001",
  "evento_candidato_id": "30000000-0000-4000-8000-000000000040",
  "similitud_texto": 0.84,
  "distancia_metros": 35,
  "diferencia_horas": 2.5,
  "sugerencia": "requiere_revision",
  "motivos": ["Ejemplo de formato pendiente de validación con D3"],
  "version_configuracion": "propuesta-v1"
}
```

Los UUID deben coincidir con el comando. Métricas obligatorias pero nullable para datos no
disponibles; siempre finitas si existen. La escala provisional del coseno es [-1,1], tomando
como referencia el prototipo existente; no es probabilidad calibrada. Distancia/horas >=0.
motivos exige 1..20 textos no vacíos de hasta 1000 caracteres; versión de 1..120.
La versión del comando se toma de la sugerencia si falta; una discrepancia devuelve 422.
Los ejemplos numéricos describen formato, **no resultados reales ni umbrales**.

Pendiente de aprobar con D3: escala final, nulos/causas de ausencia, motivos, procedencia confiable,
IDs/versión/vigencia de sugerencias y futura ingesta/consulta persistente. Este contrato todavía
es provisional según [CONTRATOS_D3.md](CONTRATOS_D3.md).
La recomendación no determina el comando municipal ni crea asociaciones por sí sola.

## Pruebas y evidencia

Resultados finales ejecutados:

| Comprobación | Resultado | Evidencia |
| --- | --- | --- |
| Incremento A/B | 52 aprobadas, 0 fallidas, 5.04 s | .test-artifacts/reciwise-d2-test-077fb62243be4e60b5725b9748a80464/ |
| Incremento C inicial | 110 aprobadas, 0 fallidas, 20.82 s | .test-artifacts/reciwise-d2-test-2209acb4099242569fe14eb6a55d1f18/ |
| Módulo final | **111 aprobadas, 0 fallidas/omitidas**, 21.25 s | .test-artifacts/reciwise-d2-test-b4a1710f76974554a1a5fbe38943d50a/pytest.xml |
| Regresión D2 final | **464 aprobadas, 0 fallidas/errores, 12 omitidas**, 112.35 s | .test-artifacts/reciwise-d2-test-ab221a578c66456aa4ed57b3ab350f7a/pytest.xml |
| Ejemplos de documentación | 9 JSON parseados; 7 ejemplos validados con DTO | .test-artifacts/groupings-sprint2/documentation-check.json |

Las 111 nuevas pruebas son **31 unitarias de contrato sin BD** y **80 de integración PostgreSQL**.
Se agregan a las 353 anteriores, sin duplicar ni promover las doce omisiones históricas.
Estas siguen siendo dos casos con registros piloto ausentes, nueve verificaciones REST
anónimas que requieren configuración Supabase y un caso con JWT ciudadano real.
La suite histórica conserva sus pruebas unitarias SQLite; las garantías nuevas de concurrencia
no se obtienen de ellas.

El entorno final utiliza PostgreSQL **17.11**, Docker local con publicación solo en localhost,
001+003 sin modificar y marcadores de aislamiento. environment.json registra versión, imagen,
identidad y hashes; groupings-race-*.json registra cuatro carreras con encargados distintos;
groupings-flow.json y groupings-api-e2e.json registran persistencia y el recorrido integrado.
Todos los contenedores propios se eliminaron al finalizar; no se contactó Supabase compartido.

Los logs se conservan en .test-artifacts/groupings-sprint2/ (ignorados por Git).
Persiste únicamente la advertencia de deprecación Starlette/httpx preexistente; no se
modificaron dependencias para ocultarla. git diff --check y la revisión de espacios pasan.
La comparación SHA-256 con la captura inicial confirma que frontend, D3, .env, credenciales,
modelos, guardia/manifiesto y migraciones quedaron intactos.

```powershell
.\.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase groupings
.\.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase all
```

El runner verifica Docker, crea un contenedor propio con etiqueta aleatoria, puerto solo 127.0.0.1,
nombre de base y marcador internos verificables. Aplica 001+003 únicamente a esa base desechable;
no lee .env, establece servicios ficticios solo en el proceso y elimina únicamente su contenedor.
No hay fallback SQLite para estas integraciones. Sin aislamiento disponible deben omitirse,
no apuntar el runner al principal. No se necesitan dependencias nuevas.

Las pruebas de contrato son unitarias sin BD/red. Las de flujo, concurrencia y fallos usan
PostgreSQL real; en los casos de permisos/dos encargados se verifican firmas ES256/RS256 y
perfiles reales de esa base con claves efímeras/JWKS en memoria. Otros casos funcionales
reutilizan el actor ficticio de la fixture existente. La guardia PostgreSQL permanece activa.

El recorrido integrado de API crea el reporte mediante POST /reports con JWT ciudadano,
consulta candidatos como encargado, revisa/mantiene separado/confirma/corrige/separa,
recupera el historial y comprueba /reports/mine sin cambios. Es FastAPI TestClient + PostgreSQL
y criptografía reales; **no navegador ni Supabase Auth real**.

## Matriz de alcance

| Función | Implementada | Verificación | Pendiente |
| --- | --- | --- | --- |
| Relaciones/detalle y candidatos manuales | Sí | API y PostgreSQL | Conexión D1 |
| Confirmar, corregir, separar | Sí, transacción con auditoría | Flujo y fallos SQL | Aceptación del equipo |
| Mantener separado / revisión | Sí, sin tocar vínculos | Flujo e historial | Cola múltiple por candidato si se requiere |
| Control de revisión / ABA | Sí | Conflicto después de cambios | Adoptar protocolo en futuros escritores |
| Dos encargados concurrentes | Sí | Conexiones PostgreSQL, JWT distintos | Validación de carga fuera del MVP |
| Replay y commit incierto | Sí | Una auditoría, consulta por UUID | Integración de reintentos explícitos D1 |
| Reporte original conservado | Sí | Comparación en cada paso y consulta ciudadana | Ninguna corrección identificada |
| Sugerencia D3 | DTO provisional y snapshot no verificado | Validación, sin algoritmos | Aprobación del contrato e ingesta confiable |
| Pantalla React | No modificada | Evidencia anterior separada | D1 debe consumir estos endpoints |
| Supabase/Storage real | No probado aquí | No se contactó el compartido | Entorno/autorización y validaciones anteriores |
| Migración/despliegue compartido | No realizado | Restricciones conservadas | Autorización 003 y revisión NO-GO |

## Entrega concreta para D1

1. Consultar relaciones y mantener event_id/last_decision_id para cada intención.
2. Mostrar candidatos como selección manual, sin etiqueta de “sugerencia de IA”.
3. Mapear acciones actuales agrupar/mantener_separado/revisar a decision con los mismos nombres.
   Para corregir usar agrupar con candidato diferente y revisión vigente; para separar, decision=separar.
4. Generar operation_id una vez; conservar cuerpo/UUID durante una petición o reintento.
5. Confirmar cambios importantes; ante 409 recargar y pedir una nueva decisión, sin reemplazar
   automáticamente la revisión esperada ni reenviar como si fuera consentimiento nuevo.
6. Ante 503 comprobar el UUID antes de reintentar. Nunca registrar responsable desde un campo público.
7. Mostrar historial con actor, fecha, candidato, resultado y anterior cuando previous_event_known=true.
   Las decisiones antiguas no tienen suggestion_id ni un anterior deducible: adaptar el DTO de demo.
8. Consumir EventOut/ReportOut existentes para mapas, detalle y fotos; fechas con zona/hora de Perú.
9. Mantener las demostraciones separadas. No enviar fixtures al backend ni ofrecer un bypass de login.
10. Preparar entorno PostgreSQL local ya compatible + Auth/JWKS de pruebas para navegador;
    el runner elimina su base y no deja un servidor de demo. No arrancar el backend actualizado
    usando por defecto .env del Supabase principal.

## Riesgos y siguiente incremento D2

- Un evento programado/cerrado no puede corregirse por esta API: requiere un flujo de ciclo
  de vida y revisión operativa posterior, no modificar historia a escondidas.
- pending_review es la decisión más reciente por reporte, no tickets independientes por candidato.
- La búsqueda de candidatos es manual y paginada. Rendimiento/índices adicionales requieren
  medición y justificación antes de cualquier migración.
- La evidencia HTTP no certifica Supabase Auth/JWKS remoto, RLS vía JWT real ni Storage.
  Las doce omisiones históricas siguen pendientes; no se declaran aprobadas.
- El frontend no está conectado por esta tarea. D3 sigue pendiente; no se declaran reales sus métricas.
- Siguiente incremento recomendado: validar estos contratos con D1/D3, conectar la revisión municipal
  en entorno aislado y, después, acordar ingesta confiable/versionada de sugerencias y
  persistencia de resultados de prioridad. No comenzar rutas antes de cerrar esos contratos.

## Archivos

Nuevos: app/groupings.py, app/grouping_contracts.py, tests/test_groupings.py,
tests/test_grouping_contracts.py y este documento.
Modificados: app/main.py (registro del router), app/events.py (protección de historial),
tests/run_isolated_postgres.py (fase groupings), docs/CONTRATOS_D3.md,
docs/API_SPRINT1.md y docs/API_EVENTOS_SPRINT2_D2.md (seguimiento del incremento).
Modelos, guardia/manifiesto, migraciones, frontend, D3 y credenciales se conservan sin cambios
respecto de la captura inicial de esta tarea.
