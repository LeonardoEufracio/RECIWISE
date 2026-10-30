# RECIWISE — Prioridades D2 hasta el 19 de noviembre de 2026

Revisión: **29 de octubre de 2026, America/Lima**. Alcance: backend, datos y contratos de integración. Este plan aplica la decisión más reciente del responsable: continuar con el proyecto principal para la aplicación, sin crear RECIWISE-TEST por ahora, sin aplicar 003 al compartido y sin pruebas destructivas allí. Las comprobaciones de desarrollo usan el PostgreSQL local aislado y los servicios simulados existentes.

**Decisión operativa: GO para desarrollo y verificaciones locales; NO-GO para desplegar el backend nuevo/migrar 003 en el principal.** No se declara cerrado Sprint 1. Las pruebas pendientes con Storage real no detienen el desarrollo de adaptadores, API o interfaz que pueda verificarse localmente.

**Actualización de aceptación integrada:** ya se ejecutó React → FastAPI → PostgreSQL → consulta/mapa municipal con JWT ES256 verificable y servicios Auth/Storage de pruebas. **4 escenarios Chrome aprobados, 39 pruebas frontend/tipos/build correctos y 273 D2 aprobadas con 12 omitidas.** Está listo para revisión de aceptación funcional **local aislada**; quedan la aceptación del responsable y las condiciones del despliegue. Evidencia en [API_SPRINT1.md, 6.13](API_SPRINT1.md#613-prueba-integrada-ciudadano--postgresql--encargado--leaflet).

## 1. Lo que ya está implementado

La revisión de `app/main.py`, modelos, esquemas y pruebas no encontró operaciones ausentes dentro de las **15 operaciones de negocio de Sprint 1** inventariadas en [API_SPRINT1.md](API_SPRINT1.md). No hace falta reescribir autenticación, reportes, fotos ni recursos para completar ese inventario.

| Capacidad | Evidencia disponible | Límite de esa evidencia |
| --- | --- | --- |
| JWT ES256/RS256, `/me`, roles y permisos | 69 casos criptográficos/de autorización con claves ficticias y JWKS local; resultados manuales previos M01–M03/M13 | No demuestra rotación/JWKS remoto ni una sesión actual de móvil |
| Reportes ciudadanos, autoría, consulta propia y municipal | Pruebas de API y PostgreSQL, M04–M06 previos, más recorrido React/Chrome integrado ejecutado en 6.13 | Queda ensayar/aceptar la versión y entorno de presentación; la integración automática usa Auth local de pruebas |
| Fotos, límite de tres, compensación y conciliación | PostgreSQL real local, Storage simulado, concurrencia/fallos/reinicios; foto subida/recuperada desde React con bytes iguales y compensación visible | La semántica y permisos efectivos de Supabase Storage real siguen pendientes |
| Vehículos, sitios y turnos | GET/POST/PATCH existentes, exclusiones PostgreSQL de vehículo/chofer, horarios contiguos y HTTP 409 | La interfaz municipal actual muestra reportes/mapa/fotos; no incorpora pantallas de gestión de estos recursos |
| Guardia 003 y preparación | Arranque y `/ready` de FastAPI; guardia del CLI, READ ONLY y recuperación | No autoriza iniciar esta versión contra un esquema anterior |
| GPS y mapa | Evidencia histórica de GPS simulado más clic/arrastre/confirmación y mapa municipal en la nueva prueba integrada | GPS físico, permiso del sistema y HTTPS en móvil pendientes; la fase nueva no reejecuta GPS ni usa un teléfono físico |

La regresión D2 más reciente dio **273 aprobadas, cero fallos/errores y 12 omitidas**, 77,40 s. La nueva integración dio **4/4**, 26,89 s, y Vitest **39/39**, con tipos/build correctos; los contadores se conservan separados. Ver **API_SPRINT1.md, 6.13**. No se cuentan omisiones como aprobadas; los resultados manuales conservan su origen histórico.

## 2. Pendientes estrictos para aceptar el alcance funcional de Sprint 1

| Prioridad / tarea | Qué falta realmente | Criterio de aceptación | Dependencia |
| --- | --- | --- | --- |
| P0 · Entorno de presentación | El entorno automático local con 003 está comprobado; elegir/ensayar el entorno persistente que se usará el 19 | Registrar versión, `/ready` y modo Auth/Storage; respetar compatibilidad/autorización del principal | La rama nueva exige 003; ver sección 3 |
| P0 · Revisión del recorrido integrado | **Ejecutado en 6.13** en una misma versión React/FastAPI con PostgreSQL real local; el responsable revisa evidencia y límites | `/me`, mapa/confirmación, POST 201, `/reports/mine`, mismo UUID en mapa municipal, 403, foto y reinicio comprobados; no sustituye el móvil físico | Auth/Storage/teselas simulados declarados; aprobación del equipo pendiente |
| P0 · Alcance final de fotos/recursos | Foto de prueba, fallo y recuperación ya ejecutados; fijar qué recursos se presentarán | Foto opcional sin duplicar reporte; recursos pueden mostrarse por la API existente si no se incluyen sus pantallas | No requiere CRUD adicional, IA ni rutas |
| P1 · Acta de revisión y entrega | [Acta preparada](ACEPTACION_SPRINT1_D2.md); revisar y aprobar alcance, límites y evidencia | Resultado de regresión, guion de demo, pendientes explícitos y decisión de otro integrante/responsable registrada | Revisión del equipo pendiente; no implica push ni autorización de migración |

No se identificó una nueva corrección de lógica imprescindible en esta revisión. Existen casos de borde sin aserción específica enumerados en la guía API; se priorizarán si afectan el recorrido acordado, sin tratarlos como funcionalidades ausentes ni cambiar contratos que ya funcionan.

La aceptación funcional y la aprobación del despliegue son decisiones distintas. Se puede revisar la implementación y seguir con Sprint 2 en local mientras la migración remota permanezca pendiente. Esta revisión no marca automáticamente aceptada la demo ni cerrado Sprint 1.

## 3. Compatibilidad con el proyecto principal

La última inspección compartida documentada encontró 001; es evidencia histórica, **no una inspección nueva**. En esta revisión no se consulta el principal. El backend actual y el conciliador requieren el contrato 003 y rechazan 001, esquemas parciales o incompatibles antes de aceptar negocio/procesar trabajos.

Mientras no se autorice 003:

- Conservar el proyecto y la configuración actuales; no sustituir un servicio por el backend nuevo suponiendo que será compatible. No se ha verificado qué versión está desplegada hoy.
- No quitar la guardia, usar `create_all`, editar el manifiesto para aceptar el esquema anterior ni mezclar tablas locales con Storage real del principal.
- Usar la base local propia del runner para regresión y desarrollo. Aplica 001+003 únicamente en su contenedor desechable. Auth y Storage externos se sustituyen explícitamente en las pruebas.
- El runner destruye su contenedor al terminar. La nueva fase `integrated` **ya ensaya React/API/PostgreSQL** de forma automática, pero no deja un servidor persistente para presentar el 19. Su elección/ensayo sigue pendiente.
- Si la presentación requiere la versión nueva funcionando contra el principal, será imprescindible una revisión/autorización posterior de la migración y del despliegue coordinado. Este plan no la concede ni promete esa integración antes de resolver la compatibilidad.

No se crea un segundo proyecto Supabase. Una eventual validación de fallos en servicios reales necesitará un destino y datos de prueba autorizados por separado; no se traslada al principal por no disponer ahora de ese destino.

## 4. Verificaciones locales que se reutilizan

Desde la raíz, con las dependencias Python ya instaladas y Docker Desktop disponible:

```powershell
# Regresión D2 completa; no lee credenciales del principal para los servicios de prueba.
.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase all

# Ensayo automático nuevo: UI + API real + PostgreSQL 003 + JWT/Storage locales.
.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase integrated

# Fases existentes para cambios futuros: ejecutar solo la relacionada y luego regresión.
.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase shifts
.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase photos
.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase recovery
.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase schema
.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase reconciler
```

Las fases de backend específicas forman parte de `all`; no hace falta repetirlas después de esa suite. **`integrated` es independiente de `all`** y necesita además Node/dependencias frontend y Chrome. Arranca y cierra sus procesos locales, ejecuta tipos/Vitest/build y cuatro casos UI; solo simula Auth/Storage/teselas, conservando JWT/perfiles/guardia originales. El runner exige base/nonce propios y puerto ligado a localhost, registra evidencia en `.test-artifacts/` y retira su contenedor. No usar `scripts/d2_preflight.py --from-project-env`, el conciliador con `.env` principal ni runners remotos para estas verificaciones.

Las pruebas SQLite de API/permisos y los transportes simulados tienen su alcance explícito. Las garantías de exclusión, slots, reclamación y recuperación se demuestran con PostgreSQL real local; no se reemplazan por SQLite.

## 5. Pendientes de Supabase real, sin bloquear funciones independientes

Estos casos están **diseñados/pendientes**, no ejecutados ni omitidos automáticamente por la suite actual. Los 12 skips de D2 corresponden a otros requisitos históricos: dos de recursos piloto, nueve de PostgREST anónimo real y uno con JWT ciudadano real.

| Prueba real pendiente | Ya comprobado localmente | Qué falta y a qué afecta |
| --- | --- | --- |
| Subida y recuperación privada con JWT de ciudadano/encargado | Contratos, bytes simulados, autoría, límite y URLs temporales | Privacidad efectiva del bucket, descarga sin autorización y expiración real; afecta aceptación de fotos en el entorno de demo/despliegue |
| Subidas simultáneas en Supabase Storage | Seis peticiones concurrentes contra PostgreSQL real, slots 1–3 | Contar filas y objetos del servicio real y demostrar ausencia de objetos publicados excedentes; afecta validación del despliegue de fotos |
| Fallo de persistencia después de upload real | Abortos PostgreSQL y compensación con Storage simulado | Confirmar retirada de la ruta propia y conservación de controles reales; no inducir el fallo en el principal |
| Commit incierto y resolución no disponible | Cero DELETE mientras queda duda; ambos desenlaces y cuarentena probados | Pérdida real/controlada de respuesta y relectura contra servicios reales; mantiene pendiente la garantía operacional remota |
| Fallos DELETE/403/404/5xx, reintentos y acuses | Clasificación, backoff, recuperación y no considerar errores como ausencia | Semántica exacta de ausencia/borrado del servicio real y permisos efectivos |
| Upload tardío, caída/reinicio y objetos de control | Procesos reales locales, Storage HTTP simulado y vigilancia de cuarentena | Repetir con bytes de Storage real sin borrar referencias ni rutas vecinas; requiere entorno autorizado |
| Supervisor y parada en el alojamiento final | CLI, reclamación entre procesos y parada cooperativa por archivo | Timeouts, señales, alertas y drenaje del supervisor real; no se programan tareas ahora |

Se mantiene la limitación: caída tras DELETE y antes del commit puede exigir repetir ese DELETE idempotente sobre la misma ruta; no existe atomicidad PostgreSQL–Storage ni garantía de una única llamada externa. Cuarentenas y `review` conservan seguimiento, sin borrado manual para vaciar la cola.

No se requiere completar estas pruebas remotas para desarrollar/adaptar contratos, pantallas, revisión municipal o persistencia sobre PostgreSQL local. Su ausencia sí debe permanecer visible al aprobar fotos reales y el despliegue.

## 6. Preparación mínima D2 para Sprint 2

Son tareas **propuestas y pendientes**, no endpoints existentes ni autorización para aplicar 002 en el principal. Orden recomendado para entregar un recorrido demostrable:

| Orden | Trabajo D2 | Dependencia y entrega verificable |
| --- | --- | --- |
| 1 | Cerrar el contrato D2↔D3 de comparación | Acordar campos/nulos, UUID reporte/evento, tiempo/distancia, motivos, versión y error según [CONTRATOS_D3.md](CONTRATOS_D3.md). El contrato actual sigue siendo propuesta |
| 2 | Adaptador de datos operativos | Mapear `reports`/`events`/`event_reports` al DTO acordado con fixtures. No enviar etiquetas de evaluación ni inventar evento/mediciones/capacidad. Puede avanzar sin modelo real |
| 3 | Revisión municipal de agrupación y auditoría | Modelos/servicio/endpoints por acordar para `events`, `event_reports`, `grouping_decisions`, ya definidos en 001. Encargado decide; cambiar un vínculo y guardar decisión en una transacción. La IA propone, agrupar no marca `atendido` |
| 4 | Recursos para el flujo de planificación | Reutilizar vehículos, sitios, disponibilidad y turnos existentes. Si la interfaz necesita elegir chofer, acordar lectura municipal mínima de choferes: hoy no hay endpoint para enumerarlos. No exponer perfiles públicos ni construir CRUD completo por anticipación |
| 5 | Propuesta de ruta y aprobación, tras acordar entradas D3 | Solo si forma parte del recorrido de hackatón: DTO, persistencia/auditoría y aprobación municipal. 002 depende de 001 y prepara `route_plans`/`route_stops`/`stop_incidents`; probarla y revisar compatibilidad/guardia en aislamiento antes de un despliegue. 003 también depende de 001; ninguna de ambas se aplica al principal en esta tarea |

D2 no necesita implementar ni entrenar el comparador, ajustar sus umbrales ni integrar un optimizador para cerrar su API de Sprint 1. La agrupación operativa empieza en Sprint 2; ejecución del chofer, incidencias y evidencia de cierre corresponden a Sprint 3. No añadir eliminación general, PostGIS, colas distribuidas o moderación completa como condiciones nuevas del piloto.

## 7. Secuencia propuesta para la hackatón

Fechas de coordinación propuestas, no tareas programadas ni compromisos ya aceptados:

| Fecha, America/Lima | Prioridad | Salida esperada |
| --- | --- | --- |
| 29 oct.–1 nov. | Revisión/aceptación funcional Sprint 1 | Regresión aislada, guion ciudadano/encargado, alcance de fotos/recursos y entorno de demo identificado |
| 2–8 nov. | Primera integración Sprint 2 | Contrato acordado, adaptador D2 y revisión municipal/persistencia auditada en local; resultados simulados rotulados hasta disponer de D3 real |
| 9–13 nov. | Recorrido conjunto útil | Integrar D1/D2/D3; propuesta de ruta solo si ya hay contrato/datos y modelo disponible; mantener alternativa de revisión manual explícita |
| 14–16 nov. | Estabilizar la demo | Ensayo integrado, permisos, errores, persistencia/reinicio, móvil/GPS en el entorno elegido; resolver compatibilidad del despliegue si se pretende usar el principal |
| 17–18 nov. | Congelar y ensayar | Congelar alcance, revisar datos ficticios, evidencias y contingencia de conectividad; ningún cambio remoto sin aprobación |
| **19 nov.** | **Hackatón** | **Demostrar lo realmente integrado y declarar simulaciones/limitaciones** |

El siguiente trabajo útil es revisar/aceptar la evidencia local y acordar el contrato para construir el adaptador/revisión municipal de Sprint 2. El ensayo integrado automático de Sprint 1 ya está ejecutado. Storage real, respaldo/restauración, autorización de 003 y tareas del alojamiento siguen pendientes del despliegue, sin congelar desarrollo independiente.

## 8. Checklist de aceptación funcional local

- [x] Login por SDK con JWT ES256 firmado y JWKS HTTP local; validación original FastAPI y rol desde PostgreSQL.
- [x] Reporte creado desde React con clic/arrastre/confirmación de ubicación, POST 201 y coordenadas numéricas.
- [x] Persistencia comprobada mediante SELECT independiente READ ONLY y consulta `/reports/mine`.
- [x] Encargado obtiene el mismo UUID/coordenadas en consulta municipal y lo ve en marcador/popup Leaflet.
- [x] Ciudadano rechazado con HTTP 403 en municipal; acceso de otro ciudadano al reporte/foto rechazado.
- [x] Foto ficticia subida/consultada desde React, bytes recuperados iguales y archivo de control intacto en Storage simulado.
- [x] Reinicio real del proceso FastAPI y recarga React sin perder reporte/metadatos; guardia vuelve a comprobar 003.
- [x] Errores 401/422/403/404, Storage 502, persistencia de foto 503 y desconexión/reintento comprobados con su alcance explícito.
- [x] Regresión D2 273/0/12, frontend 39/0, cuatro casos integrados 4/0; tipos/build correctos.
- [ ] Aceptación del responsable y ensayo de presentación persistente; dispositivo físico/HTTPS si se exige en la demo.
- [ ] Validación remota, autorización de 003 y preparación operativa del despliegue en el principal.

**Dictamen:** listo para revisión de aceptación funcional local de Sprint 1 D2, sin declarar el Sprint cerrado ni autorizar el despliegue. El [acta de aceptación propuesta](ACEPTACION_SPRINT1_D2.md) contiene el guion reproducible, tareas priorizadas de Sprint 2 y el registro pendiente de otro integrante. Las capturas y JSON/JUnit están en `.test-artifacts/reciwise-d2-test-5096c791ea64401e8242848ecaae6118/`; regresión D2 en `.test-artifacts/reciwise-d2-test-7dbf1ec79fc94f20ac9db710c0da51ae/`. El checklist no presenta Auth/Storage/teselas simulados como Supabase o cartografía reales.
