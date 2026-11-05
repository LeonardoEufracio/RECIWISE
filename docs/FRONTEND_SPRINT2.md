# Frontend Sprint 2 · RECIWISE

Ampliación del 31 de octubre de 2026: [integración full-stack de recursos, eventos manuales, decisiones de rutas y chofer](INTEGRACION_FULLSTACK_SPRINT2.md). Ese documento describe los endpoints D2 nuevos, las comprobaciones posteriores y la aprobación operativa que permanece bloqueada. Los resultados de la revisión del 30 de octubre que siguen debajo se conservan como antecedente.

Revisión: 30 de octubre de 2026 (America/Lima). Integración de React/TypeScript/Leaflet con los endpoints existentes de FastAPI. No se implementan algoritmos, servicios de backend ni cambios de base de datos.

**NO-GO para desplegar el backend nuevo sobre Supabase principal.** Requiere 001+002+003, revisión y autorización del equipo. Esta entrega solo utiliza el ejecutor existente de PostgreSQL desechable local; nunca aplica migraciones ni modifica datos compartidos. No declara aceptado ningún sprint.

## Pantallas y separación de fuentes

“Conectada” significa que la pantalla llama a FastAPI mediante el cliente JWT; no afirma que utilice Supabase real durante las pruebas locales.

| Pantalla | Modo conectado | Demostración de desarrollo | Pendiente |
| --- | --- | --- | --- |
| Ciudadano | Auth, rol de /me, GPS/mapa, confirmación, POST de reporte, mis reportes y fotos | No se sustituye por ejemplos municipales | Auth/Storage remotos, GPS físico/HTTPS |
| Dashboard municipal | Reportes paginados, conteos y accesos rápidos | Cuatro reportes ficticios identificados | Estadísticas agregadas oficiales |
| Reportes ciudadanos | Filtro de estado, búsqueda en página, Leaflet y fotografías | Adaptador GET local independiente | Búsqueda global si se acuerda |
| Eventos o puntos | Listado, filtro, detalle, reportes asociados, fechas, prioridad disponible y Leaflet | Lista y mapa de ejemplos conservados | Restricciones verificadas y prioridad D3 |
| Revisión de agrupaciones | Relaciones, candidatos manuales, cinco acciones, confirmación, concurrencia e historial persistido | Tres recomendaciones e historial en memoria | Sugerencias verificadas de D3 |
| Priorización | Aviso de integración pendiente | Ejemplos con puntuaciones desconocidas | Contrato/resultados/factores de D3 |
| Planificación de rutas | Consulta de propuestas, paradas, exclusiones, métricas, procedencia y GeoJSON recibido | Generación y aprobación exclusivamente locales | Proveedor D3 verificado y flujo operativo |
| Recursos operativos | Vehículos, sitios, turnos y disponibilidad mediante endpoints existentes | Recursos ficticios independientes | Directorio de choferes autorizado |
| Chofer | Identidad y aviso de Sprint 3 | Sin ejecución ficticia de rutas | Asignación/atención/incidencias |

La demostración sigue disponible **solo en Vite de desarrollo**, con `VITE_ENABLE_DEMO=true` y un perfil municipal confirmado por `/me`. Entrar/salir exige confirmación y muestra **DATOS SIMULADOS — DEMOSTRACIÓN**. No mezcla respuestas reales ni envía decisiones/propuestas de ejemplo. La compilación de producción la deshabilita incluso con el flag activado. Los ejemplos viven en memoria y se descartan al salir/recargar.

## Contratos y endpoints conectados

Se contrastaron los contratos documentados con `app/schemas.py`, `app/grouping_contracts.py`, `app/route_contracts.py` y sus endpoints. Referencias: [eventos](API_EVENTOS_SPRINT2_D2.md), [agrupaciones](API_AGRUPACIONES_SPRINT2_D2.md), [rutas](API_RUTAS_SPRINT2_D2.md).

| Método/ruta | Uso en interfaz |
| --- | --- |
| GET /municipal/events | Lista paginada de 50 y filtro exacto por state |
| GET /municipal/events/{id} | Detalle, coordenadas y prioridad nullable |
| GET /municipal/events/{id}/reports | Reportes asociados paginados y fotografías por endpoint existente |
| GET /municipal/groupings | Relaciones, linked y pending_review |
| GET /municipal/groupings/reports/{report_id} | Estado actual del vínculo y última decisión |
| GET /municipal/groupings/candidates | Candidatos manuales paginados; sin sugerencias de IA |
| GET /municipal/groupings/decisions | Historial paginado del reporte seleccionado |
| GET /municipal/groupings/decisions/{decision_id} | Detalle auditado y resolución de respuesta incierta |
| POST /municipal/groupings/decisions | Única escritura nueva en esta integración |
| GET /municipal/route-proposals | Lista por turno, calculation_status y result_origin |
| GET /municipal/route-proposals/{id} | Detalle e instantánea persistida |
| GET /municipal/route-proposals/{id}/stops | Paradas ordenadas paginadas |
| GET /municipal/route-proposals/{id}/excluded-events | Exclusiones paginadas con motivo |

Se conservan Supabase Auth, GET /me, POST /reports, GET /reports/mine, GET /municipal/reports, GET/POST /reports/{id}/photos y los endpoints de recursos. No se añade selección pública de roles ni mecanismos de bypass.

Las listas de Sprint 2 son arrays sin total global. Cada página contiene hasta 50 resultados; Siguiente queda habilitado si se recibió una página completa, por lo que la última página siguiente puede estar vacía. Cambiar filtros reinicia el offset. Las lecturas se cancelan al cambiar de vista; no se sustituyen errores por datos ficticios.

### Eventos

Los seis estados del filtro son exactamente `en_revision, abierto, programado, atendido, cerrado, descartado`. Se muestran fechas reales, report_count y report_ids del backend. Los rombos de Leaflet representan eventos; los círculos representan observaciones ciudadanas. Compartir coordenadas no crea una relación de negocio.

`priority` puede ser null y sus factores pueden ser cualquier JSON almacenado. Se presentan sin generar un score ni transformar factores en un formato inventado. `restrictions=null` significa información desconocida, no ausencia de restricciones. El detalle permite abrir las fotos de cada reporte, sin habilitar subida municipal.

### Agrupaciones y concurrencia

Acciones municipales disponibles:

| Acción | decision enviado | candidate_event_id |
| --- | --- | --- |
| Confirmar agrupación sin vínculo | agrupar | Evento elegido |
| Corregir asociación existente | agrupar | Nuevo evento |
| Separar reporte | separar | null |
| Mantener separados | mantener_separado | Evento elegido |
| Registrar revisión | revisar | Evento elegido, incluido el actual |

Antes del POST, un diálogo muestra reporte, asociación anterior, candidato, observaciones e identificador de operación. El cuerpo confirmado queda congelado:

```json
{
  "operation_id": "60000000-0000-4000-8000-000000000001",
  "report_id": "60000000-0000-4000-8000-000000000002",
  "decision": "agrupar",
  "candidate_event_id": "60000000-0000-4000-8000-000000000003",
  "expected_event_id": null,
  "expected_decision_id": null,
  "notes": "Revisión manual municipal"
}
```

Ambos campos expected son obligatorios y se envían explícitamente, incluidos sus null. No se envían autor, estado del reporte, factores de IA ni metadatos privilegiados. El backend decide permisos, validez del vínculo, idempotencia y concurrencia.

- Doble clic: bloqueo inmediato mediante ref y estado de envío. Se deshabilita navegación durante la escritura.
- HTTP 409: el comando queda bloqueado. El encargado debe **Descartar y actualizar relación**, leer el estado vigente y confirmar una intención nueva. No se cambian los expected ni se reenvía automáticamente.
- HTTP 503, fallo de red o error de servidor: resultado incierto. Se conserva **el mismo UUID y cuerpo**. **Comprobar operación** consulta GET /decisions/{operation_id}. Si existe, recupera el detalle sin otro POST.
- Un 404 al consultar no demuestra que una petición anterior no pueda terminar. Se permite comprobar otra vez o reintentar explícitamente **el mismo comando**, aprovechando la idempotencia del servidor. Nunca se genera un UUID nuevo para ese reintento.
- Otros errores de validación/permisos se presentan dentro del diálogo. El usuario puede cancelar y corregir.
- El historial consulta datos de FastAPI; muestra autor, fecha, operación, asociaciones, observaciones y factores recibidos. Los registros antiguos con previous_event_known=false no se presentan como si su asociación anterior fuera conocida.
- Cambiar una asociación no marca el reporte como atendido. Los eventos no editables bloquean cambios de vínculo; una revisión documental sigue sujeta a FastAPI.

La intención pendiente se conserva en el espacio municipal al navegar entre secciones y bloquea cambiar a demostración. Un aviso permite volver a ella. Se advierte al cerrar/recargar si ya se intentó la escritura. **No se almacena durablemente en el navegador**: cerrar sesión/pestaña pierde ese estado temporal. Ante una respuesta incierta, copiar el UUID mostrado y consultar el historial antes de iniciar otra intención. No se guardan tokens ni notas en almacenamiento adicional.

### Propuestas de rutas: solo lectura

No hay llamada de producto a POST /municipal/route-proposals, generación de rutas, aprobación ni asignación. El botón Solicitar propuesta permanece deshabilitado hasta verificar contrato y proveedor D3.

Se distinguen `pending/completed/unknown` y `pending/test_fixture/municipal_unverified/d3/legacy_unknown`. **Todas las propuestas actuales tienen operational=false y se rotulan NO OPERATIVA**, incluso si el resultado procede de D3. “Calculada” solo indica un resultado estructurado almacenado.

Se muestran estado, turno, orden de paradas, exclusiones y motivos, distancia en metros, duración convertida de segundos a minutos, algorithm_version, matrix_source, limitations y unknowns. Null se presenta como No disponible, sin convertirlo en cero.

El mapa dibuja únicamente `geometry_geojson` recibida y válida. Las posiciones de las paradas provienen de `input_snapshot.operational.events`, no de coordenadas actuales que puedan diferir de la instantánea. Si faltan coordenadas verificables, se conserva la parada en el listado y se avisa; no se inventa su posición ni se unen marcadores para fabricar una ruta vial. Una propuesta pendiente no muestra geometría ni paradas inventadas.

## Arquitectura y archivos de esta integración

Se reutilizan el cliente Supabase, `api.ts`, `ReportForm`, `Reports`, `Photos`, recursos y componentes comunes. No se añadieron dependencias.

- `frontend/src/municipal/backendTypes.ts`: DTO wire de eventos, decisiones, relaciones y propuestas.
- `backendService.ts`: adaptador REST tipado, filtros y señales de cancelación; solo decide realiza POST.
- `backendUi.tsx`: paginación, JSON recibido y extracción validada de coordenadas de la instantánea.
- `LiveEvents.tsx`: listado/detalle/reportes asociados/mapa/fotos.
- `LiveGroupings.tsx`: acciones, confirmación, UUID, estado esperado, conflictos y recuperación.
- `LiveProposals.tsx`: filtros, procedencia, detalle, paradas, exclusiones, métricas y mapa.
- `MunicipalWorkspace.tsx`: selección explícita entre componentes conectados y demostración; intención pendiente compartida entre secciones.
- `RouteMap.tsx` y `MapView.tsx`: tipos mínimos compartidos con DTO reales y rótulo del mapa recibido.
- `municipal.css`: presentación de métricas, identificadores largos y factores JSON.
- `backendService.test.ts` y `live.test.tsx`: 28 casos nuevos con servicios/mapas simulados.
- `frontend/e2e/integrated/sprint2.spec.ts`: tres recorridos con API/PostgreSQL reales.
- `frontend/e2e/integrated/sprint1.spec.ts`: conserva regresión; la aserción de transporte se limita al POST fallido, sin contar GET cancelados por StrictMode, y la espera de descarga contempla el reemplazo de la imagen en desarrollo.
- `frontend/e2e/sprint2.spec.ts` y `frontend/e2e/production/mode.spec.ts`: fixtures ajustados a consultas ahora disponibles.

Los archivos anteriores de demostración, priorización y recursos se reutilizan. El backend, pruebas Python, IA, migraciones y archivos .env no forman parte de los cambios de esta entrega.

## Pruebas ejecutadas y evidencia

| Comprobación actual | Resultado | Qué demuestra |
| --- | --- | --- |
| npm run check | **114 aprobadas, 0 fallidas**, 9 archivos; TypeScript correcto | 86 anteriores + 28 nuevas. UI/servicios/mapas simulados en Vitest |
| npm run build | **Correcto**, 131 módulos | JS 701.52 kB / 202.30 kB gzip; advertencia de tamaño sin error |
| Playwright de desarrollo con interceptación | **16 aprobadas, 0 fallidas** | Regresión ciudadano/GPS/mapa/fotos, fuentes, recursos, errores y móvil simulado |
| Playwright del build de producción | **1 aprobada, 0 fallidas** | VITE_ENABLE_DEMO=true no habilita demostración ni decisiones ficticias en producción |
| Playwright integrado | **7 aprobadas, 0 fallidas, 0 omitidas**, 4 de Sprint 1 + 3 nuevas | FastAPI HTTP, PostgreSQL 17.11, React y Leaflet reales; Auth/Storage/teselas simulados |
| Suite D2 Python completa | No reejecutada en esta tarea de frontend | **595 aprobadas y 12 omitidas son evidencia previa**, no un resultado nuevo |
| Supabase Auth/Storage remotos y D3 real | **Pendientes** | No existen resultados nuevos con esos proveedores |

La primera ejecución integrada obtuvo 4 aprobadas y 3 fallidas: selector SVG incorrecto en un caso nuevo, coincidencia ambigua del mensaje 409 y una aserción anterior que contaba cualquier Sin HTTP, incluido un GET cancelado por StrictMode. La segunda obtuvo 6 aprobadas y 1 fallida al reemplazarse una imagen durante scrollIntoView bajo StrictMode. Se corrigieron las aserciones y la espera conservando los controles de descarga real, escritura, persistencia y permisos. **La tercera ejecución completa obtuvo 7/7 aprobadas**. No se detectó una incompatibilidad funcional de backend que requiriera modificarlo. Los fallos anteriores no se contabilizan como aprobaciones.

Los 16 casos interceptados usan sesiones JWT ficticias de interfaz: no prueban firmas, PostgreSQL ni Supabase. Los casos integrados usan el SDK de Auth con un simulador HTTP que emite **JWT ES256 verificables contra JWKS efímero**; FastAPI usa sus dependencias reales, perfil PostgreSQL y guardia activa. Auth y Storage siguen simulados; las teselas también. No hay interceptación del API de negocio salvo el fallo de transporte deliberado de Sprint 1.

La integración conserva los cuatro casos de Sprint 1: reporte/mapa/fotografía, validación y autoría, fallos Storage/persistencia con compensación y reintento, CORS y recuperación tras reinicio. Añade:
1. Reporte creado desde React/Leaflet, consulta de evento y asociados, cinco acciones municipales, historial persistido y estado ciudadano conservado.
2. Otra revisión que cambia PostgreSQL antes de confirmar: HTTP 409 real, descarte, nueva lectura y consentimiento.
3. Consulta de propuestas pendiente y de prueba, orden, exclusiones, métricas y geometría persistida; ninguna escritura de rutas desde el navegador.

Los datos de propuestas se preparan **solo en el código de pruebas**, por APIRequestContext contra el API local, con test_data=true y sin optimizador. No representan resultados reales de D3 ni generación en la aplicación.

Evidencia local ignorada por Git:
- `.test-artifacts/frontend-api-sprint2/baseline.json`: SHA-256 inicial de 134 archivos, incluidos los protegidos.
- `.test-artifacts/frontend-api-sprint2/scope-verification.json`: **8 archivos existentes modificados y 9 nuevos**, todos de frontend o este documento; 0 cambios protegidos y 0 eliminaciones. Los cambios previos de otros integrantes, incluido frontend/.env.example, se conservan. git diff --check pasó y los 17 archivos están libres de espacios finales.
- `.test-artifacts/frontend-sprint2/`: capturas de la demostración e interfaz con servicios interceptados.
- El ejecutor imprime un directorio `.test-artifacts/reciwise-d2-test-<id>/` por ejecución: `environment.json`, `vitest.json`, `browser-junit.xml`, `browser.log`, capturas y `sprint2-*.json` con métodos/rutas/códigos sin cabeceras ni cuerpos sensibles.
- Ejecución integrada final: [browser.log](../.test-artifacts/reciwise-d2-test-31640ee48c524f3fbe55bcd2d034f6a2/browser.log), [JUnit](../.test-artifacts/reciwise-d2-test-31640ee48c524f3fbe55bcd2d034f6a2/browser-junit.xml), [entorno](../.test-artifacts/reciwise-d2-test-31640ee48c524f3fbe55bcd2d034f6a2/environment.json) y [Vitest](../.test-artifacts/reciwise-d2-test-31640ee48c524f3fbe55bcd2d034f6a2/vitest.json). Solo existen localmente; no se publican.
- `environment.json` acredita 001+002+003, PostgreSQL local e identificadores de migración. El rótulo estático antiguo “001+003” de `integrated-environment.json` omite 002; no describe el catálogo completo. Se contrasta con environment.json, la guardia activa y la evidencia Sprint 2, sin modificar el ejecutor del backend.
- La evidencia de ejecuciones fallidas se conserva por separado; no cuenta como aprobación.

El caso antiguo que espera FastAPI fijo en :8000 se excluye explícitamente de las 16 pruebas interceptadas. La comunicación real y CORS se verifican con puertos locales dinámicos mediante el ejecutor integrado. No se sustituye PostgreSQL por SQLite para afirmar persistencia o concurrencia.

## Reproducción segura

Para desarrollar de manera continua en Windows, usar el [entorno PostgreSQL local persistente](ENTORNO_LOCAL.md): `scripts/local_dev.py init` una vez y `scripts/local_dev.py up` por sesión. Prepara las dependencias mínimas de Auth/Storage, conserva los datos y utiliza configuración privada separada sin sobrescribir los .env. React y FastAPI reales usan Auth/Storage simulados persistentes; la guardia y la validación ES256/JWKS permanecen activas. `scripts/check_local_dev.py` verifica consultas desde React y persistencia tras reiniciar. El ejecutor desechable descrito abajo sigue reservado para la aceptación automatizada.

Requisitos: dependencias existentes, Node >=22.12, npm, Chrome, Python del .venv y Docker Desktop para PostgreSQL aislado. No se editaron .env ni credenciales.

```powershell
cd frontend
npm.cmd run check
$env:PLAYWRIGHT_CHANNEL = 'chrome'
npm.cmd run test:browser -- --grep-invert 'el navegador se comunica con FastAPI real'
```

Para build y prueba de producción, usar una **terminal temporal** y configuración pública ficticia solo del proceso:

```powershell
$env:VITE_SUPABASE_URL = 'https://frontend-test.supabase.co'
$env:VITE_SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_browser_test'
$env:VITE_API_URL = 'http://127.0.0.1:8000'
$env:VITE_ENABLE_DEMO = 'true'
npm.cmd run build
$env:PLAYWRIGHT_CHANNEL = 'chrome'
npm.cmd run test:browser -- --config playwright.production.config.ts
```

Para la integración real local, desde la raíz, sin arrancar el backend con su .env:

```powershell
.\.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase integrated
```

Ese comando crea un contenedor de propiedad verificada y nombre aleatorio enlazado solo a 127.0.0.1, aplica 001+002+003 **únicamente allí**, inicia FastAPI/Vite y simuladores, ejecuta TypeScript/Vitest/build y los siete casos de navegador, y elimina su contenedor al terminar. Nunca usar --refresh-schema-manifest para estas pruebas. La aplicación conserva su guardia; no hay bypass en código de producción. Las credenciales ficticias del entorno no se imprimen ni se escriben en .env.

Guion de demostración reproducible:
1. Ejecutar el comando integrado y comprobar cero fallos en browser-junit.xml.
2. Revisar ciudadano/reporte/fotografía y reinicio en las capturas/evidencia de Sprint 1.
3. Revisar `sprint2-groupings.png` y los GET/POST registrados: las cinco acciones pertenecen al mismo reporte y su historial persiste.
4. Revisar `sprint2-conflict-recovered.png` y el HTTP 409 seguido de nueva decisión explícita.
5. Revisar `sprint2-route-readonly.png`: procedencia de prueba, algoritmo, limitaciones y NO OPERATIVA. Dentro del diálogo se puede desplazar hasta mapa, paradas y exclusiones; sus contratos/orden/geometría también se verifican en las aserciones. No existe POST de rutas del navegador.
6. Para explorar la demostración con inspector, ejecutar `npm.cmd run test:browser -- --grep 'Sprint 2: turno' --debug` desde frontend. Sus datos son simulados, no la base anterior.

El dashboard consulta hasta 1000 reportes y avisa si la muestra está limitada; no ofrece totales oficiales ni una instantánea transaccional entre páginas. La búsqueda de reportes sigue siendo local a la página. Fechas en America/Lima; fechas enviadas con zona. GPS se solicita solo al pulsar su botón; en móvil físico requiere HTTPS y confirmación antes del POST.

## Seguridad, pendientes y dependencias D3

- El token vigente del SDK se envía a FastAPI; /me determina el rol. Un 401 retira funciones y solicita sesión nueva; 403/404/409/422/503 conservan su código y detalle. No se reenvían escrituras automáticamente.
- El historial técnico no guarda tokens, cuerpos ni URLs firmadas. El frontend no incluye service_role, contraseñas ni claves privadas.
- Pendientes D3: proveedor autenticado/verificado, sugerencias de agrupación y sus factores/versiones, prioridad y restricciones operativas, matrices viales y resultados/limitaciones de planificación. No se calculan en React.
- Pendientes de endpoints/flujo operativo: generación de propuestas con proveedor verificado, aprobación/asignación/ejecución, directorio autorizado de choferes, priorización y estadísticas oficiales. Los trece endpoints solicitados para consulta/decisión sí se integran.
- Validaciones remotas pendientes: Supabase Auth ES256/JWKS del proyecto autorizado, bucket privado, URLs firmadas, fallos/compensación/reintentos y recuperación con Storage real. Las **12 omisiones D2 permanecen pendientes** y no se contabilizan como aprobadas.
- Pendientes de producto: revisión del equipo, Safari/iOS y Android físicos, GPS real/HTTPS, accesibilidad completa, volúmenes grandes y rendimiento. Vite avisa de bundle >500 kB; se puede dividir después sin condicionar este contrato.
- El identificador de una decisión incierta vive en memoria; copiarlo antes de abandonar sesión y consultar historial. Una mejora durable de UX requeriría acordar retención/privacidad, sin almacenar secretos.
- No hay cambios en backend/IA/migraciones/credenciales, datos compartidos, RLS o tareas programadas. No se realizó push, merge ni despliegue. **Se mantiene NO-GO compartido y no se declara cerrado el sprint.**
