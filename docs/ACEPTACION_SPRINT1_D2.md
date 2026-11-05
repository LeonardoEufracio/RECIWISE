# RECIWISE — Acta para revisión de aceptación funcional local, Sprint 1 D2

**Fecha:** 29 de octubre de 2026, America/Lima. **Estado:** preparada para revisión; pendiente de decisión del equipo. **Alcance:** backend, persistencia, autenticación/permisos e integración ciudadana/municipal de Sprint 1, en el entorno local aislado compatible con 003.

**Dictamen técnico propuesto:** la implementación está lista para revisión de aceptación funcional local. Este documento **no aprueba ni cierra el Sprint en nombre del equipo**, ni autoriza desplegar la rama nueva o aplicar migraciones en el Supabase principal. Se mantiene **NO-GO para ese despliegue** y GO para preparar el desarrollo local de Sprint 2.

Fuentes: [API y evidencia D2](API_SPRINT1.md), especialmente 6.8–6.13; [plan hasta la hackatón](PLAN_D2_HACKATON.md); [contratos D2↔D3 propuestos](CONTRATOS_D3.md); código, runners y artefactos locales enlazados abajo.

## 1. Base de la revisión y alcance real

Se acepta revisar una versión de trabajo local con cambios pendientes, identificada por los hashes de producción guardados en la evidencia. No se presume que un nombre de rama o un commit anterior contenga todos esos cambios. Antes de firmar, el revisor debe identificar la versión revisada y conservar su manifiesto/evidencia.

| Componente | Ejecutado en la prueba integrada | Límite |
| --- | --- | --- |
| React, Leaflet, SDK Supabase y Chrome | Código real, login por SDK, selección/arrastre/confirmación, fotos, listado y mapa | Navegador automatizado de escritorio, no teléfono físico |
| FastAPI | Uvicorn y HTTP reales; autenticación, permisos y guardia originales | Sin bypass de JWT/perfil ni de compatibilidad |
| PostgreSQL | Servidor local real 17.11, migraciones 001+003 en contenedor propio | No es PostgreSQL de Supabase; la base es desechable |
| Auth | Simulador HTTP local emite ES256 con clave efímera y publica JWKS; FastAPI verifica firma y claims | No demuestra disponibilidad/rotación de Supabase Auth remoto |
| Storage | Simulador HTTP local recibe bytes, firma enlaces de prueba, permite descargar y compensar | No demuestra privacidad, permisos o semántica del servicio Supabase real |
| Teselas | PNG ficticio y bloqueo de solicitudes externas | Leaflet y sus puntos son reales; las calles/cartografía base no se validaron |

La clave privada, contraseñas y sesiones ficticias se generan en memoria. La evidencia saneada excluye JWT, cabeceras privadas y URLs firmadas. El launcher y los controles de fallos/reinicio son infraestructura de pruebas ligada a loopback, no endpoints de producción.

**Actividad de esta tarea documental:** lectura de guías, código y artefactos; comprobación de resultados y hashes. **No se reejecutaron las suites** para redactar el acta ni se contactó el proyecto compartido. Los resultados siguientes pertenecen a las ejecuciones previas del 29/10/2026 y siguen siendo evidencia de esa versión; no se anuncian como ejecuciones nuevas.

## 2. Funcionalidades completadas y probadas

El inventario previsto está implementado. Contando `/health` como la operación auxiliar incluida en ese inventario, son 15 operaciones HTTP; `/ready` es una sonda interna adicional. No son 15 endpoints nuevos de negocio más las sondas.

| Grupo | Contratos implementados | Verificación disponible |
| --- | --- | --- |
| Proceso e identidad | GET `/health`, GET `/me`; GET `/ready` interno | Liveness/preparación separadas, JWT ES256/RS256 y rol desde perfil |
| Reportes | POST `/reports`; GET `/reports/mine` y `/reports/{id}` | Validación, autoría, persistencia y lectura; descripción de 3–2000 tras recorte |
| Fotografías | POST/GET `/reports/{id}/photos` | Autor, formato/tamaño, máximo tres, metadatos, URLs y compensación con Storage simulado |
| Lectura municipal | GET `/municipal/reports` | Permiso de encargado, filtros, coordenadas y mapa |
| Vehículos | GET/POST `/municipal/vehicles`; PATCH `/municipal/vehicles/{id}/availability` | Permisos, disponibilidad y conflictos de identificador |
| Sitios | GET/POST `/municipal/sites` | Coordenadas/tipos; validación de uso como salida/descarga al reservar |
| Turnos | GET/POST `/municipal/shifts` | Disponibilidad, rol del chofer, intervalo, exclusión de reservas y HTTP 409 |

Los recursos tienen API; **sus pantallas municipales no están implementadas en el frontend actual**. El flujo del chofer, agrupación operativa y rutas no forman parte de estas funcionalidades aceptables de Sprint 1.

### Criterios y evidencia de aceptación local

`Comprobado` describe una prueba ejecutada; no equivale a `aprobado por el equipo`. E1–E6 remiten al inventario de evidencia de la sección 3.

| Criterio | Estado técnico | Resultado verificable | Evidencia |
| --- | --- | --- | --- |
| C01 · Identidad y autorización | Comprobado | Login de pruebas ES256/JWKS local; `/me` 200 y rol PostgreSQL. Metadata privilegiado no eleva al ciudadano. JWT ausente/malformado → 401 | E1, E2, código original `app/security.py` |
| C02 · Registro ciudadano desde React | Comprobado | Clic, arrastre y confirmación en Leaflet; sin POST antes del envío; POST 201 con coordenadas numéricas y UUID generado | E2, E3 |
| C03 · Persistencia y consulta propia | Comprobado | SELECT independiente READ ONLY confirma autor, descripción y coordenadas; `/reports/mine` incluye el UUID; otro ciudadano no lo recibe | E2, E3 |
| C04 · Consulta y mapa municipales | Comprobado | Encargado obtiene el mismo objeto/UUID/coordenadas; marcador, popup y fotos en Leaflet. Ciudadano → municipal 403 | E2, E3, E6 |
| C05 · Fotografía de prueba | Comprobado con simulación declarada | Upload 201, slot/metadatos en PostgreSQL, consulta 200 y bytes descargados idénticos al PNG ficticio; control intacto | E3, E4, E6 |
| C06 · Recuperación tras reinicio | Comprobado | Proceso FastAPI nuevo, guardia 003 y `/ready` 200; lecturas SQL/metadatos iguales antes/después; recarga de React conserva reporte | E2, E3 |
| C07 · Errores y reintentos | Comprobado en los casos ejecutados | 422 inválido; 403/404 por permisos; error de transporte sin alta duplicada; Storage 502 y persistencia de foto 503 con recuperación | E1, E2, E4 |
| C08 · Concurrencia y durabilidad | Comprobado en PostgreSQL local real | Exclusiones vehículo/chofer y horarios contiguos; slots limitan a tres; reclamación segura, reintentos, commit incierto y controles conservados | E1 y pruebas D2 de turnos/fotos/recuperación |
| C09 · Recursos municipales | Comprobado por API/suite D2 | Vehículos, sitios y turnos autorizados; disponibilidad/roles/relaciones y denegación a otros roles | E1; no se afirma una UI de recursos |
| C10 · Compatibilidad y aislamiento | Comprobado | Arranque/conciliador rechazan esquemas anteriores, parciales o incompatibles; sin migración automática; pruebas solo sobre base local propia | E1, E5 y manifiesto 003 |

La suite criptográfica de 69 casos forma parte de los 273 de D2: no se suma otra vez. SQLite/sustituciones verifican parte de la lógica de API/permisos; exclusiones, restricciones, carreras y recuperaciones se comprueban en PostgreSQL real local. No se presenta SQLite como prueba de esas garantías.

## 3. Resultados y evidencias verificables

| Ejecución registrada | Aprobadas | Fallidas/errores finales | Omitidas | Observación |
| --- | --- | --- | --- | --- |
| D2 backend | 273 | 0 | 12 | 285 casos, 77,40 s |
| Frontend Vitest | 39 | 0 | 0 | Contador independiente del backend |
| Integración Chrome/React/FastAPI/PostgreSQL | 4 | 0 | 0 | JUnit global 26,89 s; `testsuite` 25,76 s |
| TypeScript y build Vite | Correctos | 0 | No aplica | `tsc --noEmit` y `vite build --outDir`, códigos 0 |

**Doce omisiones D2, no aprobadas:** dos requieren recursos piloto existentes ausentes del aislado; nueve requieren PostgREST anónimo real; una requiere JWT ciudadano del servicio real. La matriz de fallos de Storage remoto es trabajo adicional pendiente, no otros tests aprobados ni skips producidos por esta suite.

No se detectó un fallo funcional que requiriera modificar producción en la integración. El primer intento tuvo 2 aprobados/2 errores del lector de evidencia nuevo (`dict_row` antes de la comprobación READ ONLY por tupla); se corrigió solo la infraestructura de pruebas. El siguiente pase obtuvo 4/4 y el final también 4/4. Permanecen las advertencias preexistentes de Starlette/httpx y chunk Vite >500 kB; no son pruebas fallidas.

Los artefactos siguientes existen localmente, están fuera de Git y contienen únicamente datos ficticios/saneados. En otra máquina se regeneran con la demo de la sección 4. No se deben subir automáticamente ni sustituir por secretos del proyecto principal.

| ID | Artefactos | Cómo contrastarlos |
| --- | --- | --- |
| E1 | [JUnit D2](../.test-artifacts/reciwise-d2-test-7dbf1ec79fc94f20ac9db710c0da51ae/pytest.xml) y [entorno D2](../.test-artifacts/reciwise-d2-test-7dbf1ec79fc94f20ac9db710c0da51ae/environment.json) | 285 casos, 0 fallos/errores, 12 omitidos; PostgreSQL/identidad local y hashes |
| E2 | [JUnit navegador](../.test-artifacts/reciwise-d2-test-5096c791ea64401e8242848ecaae6118/browser-junit.xml), [Vitest](../.test-artifacts/reciwise-d2-test-5096c791ea64401e8242848ecaae6118/vitest.json), [entorno integrado](../.test-artifacts/reciwise-d2-test-5096c791ea64401e8242848ecaae6118/integrated-environment.json) | 4 y 39 aprobados, códigos 0 de tipos/build, 2 lecturas JWKS, 6 logins de pruebas; origen real/simulado |
| E3 | [Recorrido del reporte](../.test-artifacts/reciwise-d2-test-5096c791ea64401e8242848ecaae6118/report-flow.json) y [reinicio](../.test-artifacts/reciwise-d2-test-5096c791ea64401e8242848ecaae6118/restart.json) | Payload, respuesta y SQL coinciden; PIDs distintos y `before == after` |
| E4 | [Fallos de fotos](../.test-artifacts/reciwise-d2-test-5096c791ea64401e8242848ecaae6118/photo-failures.json) | Una foto al recuperar; estados `quarantined`, `cleaned` y `complete`; una ruta propia compensada. E2 confirma control intacto |
| E5 | [Entorno/migraciones](../.test-artifacts/reciwise-d2-test-5096c791ea64401e8242848ecaae6118/environment.json) y [alcance/hashes](../.test-artifacts/reciwise-d2-test-5096c791ea64401e8242848ecaae6118/scope-verification.json) | Localhost/nonce, 001+003; hashes de producción contra archivos revisados. Documentación posterior no es un cambio funcional |
| E6 | [Vista ciudadana](../.test-artifacts/reciwise-d2-test-5096c791ea64401e8242848ecaae6118/citizen.png) y [mapa municipal](../.test-artifacts/reciwise-d2-test-5096c791ea64401e8242848ecaae6118/municipal-map.png) | Mismo reporte y foto ficticios; mapa base simulado, sin afirmar cartografía real |

Ejemplo del pase conservado: reporte ficticio `91669045-35dd-4836-9418-2c3f6d16ff0f`, coordenadas `-12.053758333689268, -75.3006362915039`; PIDs FastAPI 26628 → 16952. SHA-256 del PNG descargado: `6b1048f8a6d40bac0b2954c18fefa40c4ea7a96120fc2e54b7317c0e43c2bbec`.

Los historiales `http-*.json` y `browser.log` del mismo directorio permiten seguir método/ruta/código sin cuerpos ni cabeceras. Los hashes de producción de E2 coinciden con los archivos actuales al redactar el acta. La nueva ejecución generará otros UUID, PIDs y puertos; deben compararse dentro de esa ejecución, no exigirse los del ejemplo.

## 4. Demostración reproducible en aislamiento

**Modalidad preparada:** ensayo automatizado en Chrome headless, con capturas y datos verificables al terminar. No es una sesión interactiva persistente ni tiene una opción documentada para dejar el entorno abierto.

Requisitos: raíz del repositorio, entorno Python con `requirements.txt`, Node conforme a `frontend/package.json` y dependencias del frontend ya instaladas, Docker Desktop disponible y Google Chrome instalado. En una máquina nueva, preparar esas dependencias previamente; no copiar ni reemplazar los `.env` existentes.

Desde PowerShell en la raíz:

```powershell
# UI real + API real + PostgreSQL 003, Auth/Storage/teselas locales de pruebas.
.\.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase integrated

# Regresión backend independiente; no contiene la fase de navegador.
.\.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase all
```

El runner existente verifica base/nonce propios y puerto Docker ligado a localhost, aplica 001+003 solo allí y reemplaza configuración en sus procesos hijos, sin editar archivos de entorno. El backend exige el mismo destino aislado y una URL local de servicios. No iniciar `uvicorn` desde el `.env` principal, ni ejecutar el worker o Playwright integrado por separado eludiendo ese runner.

### Guion de presentación y revisión

| Paso | Acción automatizada que se puede narrar | Resultado que el revisor debe observar |
| --- | --- | --- |
| 1 | Preparar base compatible, servicios locales y FastAPI | Guardia real y `/ready` preparados; ningún destino Supabase compartido |
| 2 | Login ciudadano con SDK y JWT ES256 de pruebas | `/me` 200, rol ciudadano desde PostgreSQL; metadata no eleva privilegios |
| 3 | Elegir mapa, arrastrar y confirmar el punto; registrar | Ningún POST anticipado; POST 201 con UUID y coordenadas numéricas |
| 4 | Leer SQL y `/reports/mine` | Mismo autor, UUID, descripción y coordenadas; fila realmente persistida |
| 5 | Subir foto ficticia, consultarla y descargarla | Metadatos/slot en SQL; bytes recuperados iguales, foto visible |
| 6 | Reiniciar FastAPI y recargar React | PID cambia, guardia vuelve a pasar, SQL idéntico y reporte recuperado |
| 7 | Cerrar sesión e iniciar como encargado | Consulta municipal 200 del mismo reporte; círculo/popup y foto en Leaflet |
| 8 | Revisar escenarios negativos | Ciudadano municipal 403; autor ajeno 404; inválido 422; fallos de foto 502/503; desconexión y reintento sin duplicados |

La fase integrada ejecuta tipos, 39 tests frontend, build y cuatro escenarios. Sale con código 0 si pasan; códigos distintos de 0 requieren revisar el log/JUnit, sin dar por aceptada una parte no terminada. La regresión D2 devuelve éxito con 12 omisiones explícitas; eso no las convierte en éxitos.

Al terminar, abrir el directorio `.test-artifacts/reciwise-d2-test-<identificador>` que imprime **cada** runner y contrastar E1–E6 en los nuevos archivos. Revisar las capturas como apoyo visual; el SELECT y los JUnit son los que sustentan persistencia/resultados. Conservar evidencia saneada y versión para revisión del equipo, sin enviar contraseñas, tokens o claves.

Los procesos y el contenedor propios se retiran al terminar. Los datos ficticios no sobreviven a esa retirada; **lo probado es la persistencia al reiniciar FastAPI mientras PostgreSQL sigue activo**. El entorno persistente y el dispositivo para presentar el 19/11 se deciden aparte.

## 5. Funcionalidades pendientes de aceptación humana

No se identificó una operación prevista de Sprint 1 ausente. Los pendientes de esta sección son de revisión/aceptación, no nuevas implementaciones atribuidas a D2.

| Pendiente | Decisión necesaria |
| --- | --- |
| Aceptación independiente del recorrido local | Otro integrante debe revisar/reproducir la demo y decidir sobre C01–C10 |
| Alcance de la presentación | Confirmar qué se mostrará, con fotos opcionales y recursos por API; las pantallas municipales de recursos no se prometen |
| Modalidad real/simulada | Aceptar expresamente que Auth, Storage y teselas son simulados y GPS físico no se probó en esta fase |
| Entorno de presentación | Elegir y ensayar una versión/esquema compatibles que permanezcan disponibles; no confundir el runner efímero con un despliegue |
| Firma del cierre funcional | Registrar versión, revisor, resultados/observaciones y decisión del responsable; no inferir aprobación por tener un acta |

Un ensayo físico de móvil/GPS/HTTPS queda pendiente si se exige en la demo. Las pruebas previas con GPS simulado y los resultados manuales históricos de Supabase conservan su alcance, sin presentarse como nueva aceptación del entorno remoto.

## 6. Validaciones de servicios reales pendientes

Ninguna de estas filas está aprobada por el simulador. No se crea un segundo Supabase por ahora y no se trasladan las pruebas destructivas al principal.

| Validación real pendiente | Evidencia que se necesitará en un destino autorizado |
| --- | --- |
| Auth/JWKS remoto y sesión de usuario | Login/renovación, firma/issuer/audience, perfil y permisos efectivos; rotación/fallos de JWKS si se incluyen en la compatibilidad |
| Acceso directo y RLS con usuario real | Denegación mediante credenciales de usuario/anon, distinta de una conexión administrativa; los skips remotos permanecen visibles |
| Storage privado y enlaces | Subida/descarga real, rechazo de acceso ajeno/no autorizado y expiración/renovación efectiva; bucket no público |
| Concurrencia de fotos | Conteo de filas y objetos reales, máximo tres y ausencia de objetos publicados excedentes |
| Persistencia/commit incierto y compensación | Ambos resultados de commit, indisponibilidad al resolver, ningún DELETE prematuro y controles reales conservados |
| Fallos, uploads tardíos y recuperación | 403/404/5xx/acuses DELETE, backoff, caída/reinicio y objeto tardío; ausencia idempotente inequívoca |
| Alojamiento y operación | Readiness, señales/timeouts, parada, conciliador, heartbeat y alertas en el supervisor final |

Estos pendientes afectan la aceptación del entorno real y su despliegue. No congelan los contratos, adaptadores, modelos o persistencia de Sprint 2 que puedan desarrollarse y probarse en PostgreSQL local.

## 7. Riesgos de despliegue y migración 003

**Estado comunicado:** 003 no está aplicada al principal. No se consultó ni alteró ese proyecto para esta acta. La guía de [auditoría y checklist](API_SPRINT1.md#69-auditoría-de-preparación-del-despliegue-no-go) conserva las condiciones de revisión; no es una orden de ejecución.

| Riesgo | Condición necesaria antes de un despliegue autorizado |
| --- | --- |
| Backend/BD incompatibles | Esta rama exige 003 y debe rechazar esquema anterior/parcial. No retirar la guardia ni usar `/health` 200 como prueba de compatibilidad; verificar `/ready` |
| Extensión y bloqueos | Revisar disponibilidad/esquema/permisos de `btree_gist` y ventana de mantenimiento; 003 toma ACCESS EXCLUSIVE en turnos/fotos con espera de lock de 5 s |
| Datos en conflicto | Diagnóstico previo READ ONLY: solapamientos de vehículo/chofer y más de tres fotos bloquean 003. No corregirlos borrando/modificando registros automáticamente |
| Aplicación coordinada | Respaldo/restauración ensayados, escritores y conciliador drenados, migración/versión identificadas, comprobaciones posteriores y autorización explícita del destino/ventana |
| Reversión condicionada | El rollback archiva el registro y se niega ante operaciones sin resolver. No forzar `cleaned` ni vaciar la cola; volver a backend compatible tras revertir y conservar las evidencias |
| Consistencia eventual | PostgreSQL y Storage no son atómicos; una caída tras DELETE y antes del commit puede exigir repetir el DELETE idempotente de la misma ruta. Cuarentena y `review` requieren supervisión |
| Diferencias del servicio remoto | El catálogo/versión/permisos y la semántica de Storage remoto deben verificarse; no adaptar el manifiesto para ocultar drift ni considerar el stub local equivalente a Supabase |

No hay tareas reales de conciliación programadas por esta entrega. Su funcionamiento local no demuestra operación continua, alertas ni capacidad del alojamiento. Tampoco se declara cobertura exhaustiva de todo fallo de infraestructura: la API no tiene un manejador general de errores de BD, y un fallo no controlado fuera de los casos 503 documentados puede terminar en 500.

**Decisión de despliegue: NO-GO.** Requiere una revisión y autorización posteriores independientes de la eventual aceptación funcional local.

## 8. Revisión y decisión de otro integrante

El equipo debe designar **al menos a otro integrante distinto de quien preparó la implementación/evidencia**. Esta acta no asigna nombres ni registra una aprobación automática.

Checklist del revisor:

- [ ] Identificar la versión de trabajo y comprobar hashes de producción/manifiesto frente a la evidencia; preservar cambios locales pendientes.
- [ ] Reproducir o presenciar el ensayo aislado y contrastar E1–E6, incluidos UUID/coordenadas/bytes y lecturas antes/después del reinicio.
- [ ] Revisar firma ES256/perfil, permisos y rechazo 403/404, aislamiento/guardia y ausencia de bypasses de producción.
- [ ] Confirmar 273/0/12, 39/0 y 4/0; reconocer las 12 omisiones, las simulaciones y las advertencias sin declararlas resueltas.
- [ ] Revisar fallos de foto, compensación y conservación del control; reconocer cuarentena pendiente y consistencia eventual.
- [ ] Acordar alcance de fotos/recursos, pendientes de móvil/presentación y servicios reales; mantener NO-GO del despliegue.
- [ ] Registrar decisión y observaciones. Si corresponde cerrar formalmente, hacerlo mediante el procedimiento del equipo y su responsable, no por esta propuesta técnica.

| Registro a completar por el equipo | Valor |
| --- | --- |
| Revisor/a independiente | Pendiente de designación |
| Responsable que confirma el cierre | Pendiente |
| Fecha y versión/hash revisados | Pendiente |
| Directorios de la reproducción y resultados | Pendiente |
| Criterios aceptados y observaciones/condiciones | Pendiente |
| Decisión: aceptar localmente / aceptar con observaciones / solicitar corrección | **Pendiente, sin opción seleccionada** |
| Aprobación de despliegue o migración | **No concedida por esta acta** |

## 9. Tareas iniciales priorizadas D2 para Sprint 2

**Backlog propuesto; nada de esta sección se implementa en esta tarea.** Los contratos existentes siguen por validar con D3. P0/P1 ordenan trabajo local; no autorizan migraciones ni operaciones en el principal.

| Orden / prioridad | Tarea | Dependencia | Criterio de terminado propuesto |
| --- | --- | --- | --- |
| 1 · P0 | Acordar contrato D2↔D3 y adaptador | Revisión conjunta de `CONTRATOS_D3.md` y necesidades D1 | Campos/tipos/unidades/nulos, UUID y tiempos, errores, motivos y versión acordados; mapeo API inglés ↔ DTO D3; fixtures sin etiquetas de evaluación ni medidas inventadas |
| 2 · P0 | Persistencia de eventos | Contrato y estados acordados; `events` ya existe en 001 | Modelos/servicio y operaciones mínimas por acordar, permisos municipales, ubicación/estado/cierre validados y recuperación tras reiniciar |
| 3 · P0 | Relación reporte–evento | Eventos y decisión de vinculación | `event_reports` mantiene como máximo una relación vigente por reporte; asociación/reasignación autorizada, FKs, conflictos concurrentes y auditoría en una transacción |
| 4 · P0 | Decisiones de agrupación auditadas | Contrato D3 y tareas 2–3 | `grouping_decisions` conserva actor, fecha, candidato/resultado, factores y configuración; mapeo de sugerencia D3 a decisión persistida acordado; encargado revisa, agrupar no marca `atendido` |
| 5 · P1 | Contrato e insumos de propuestas de rutas | Eventos revisados y recursos/turnos existentes | Entradas/salidas D2↔D3 de planificación acordadas; capacidades desconocidas conservadas, fuente de matriz/versión/limitaciones explícitas. Consulta mínima municipal de choferes solo si la UI la necesita |
| 6 · P1 | Persistencia y revisión municipal de propuestas | Tarea 5; revisar/probar 002 únicamente en aislamiento cuando se desarrolle | `route_plans`/`route_stops` guardan propuesta, snapshot, configuración, orden, geometría/estimaciones, excluidos y limitaciones; autorización y transición de aprobación auditadas, persistencia/reinicio y duplicidades probados |
| 7 · P1 | Regresión e integración del recorrido Sprint 2 | Incremental con cada tarea | Pruebas de permisos, validación, FK/atomicidad/concurrencia, historial/reinicio e integración D1/D2/D3, usando respuestas de D3 claramente simuladas hasta disponer del modelo real |

Orden de ejecución sugerido: 1 → 2 → 3 y 4 juntas en la operación transaccional → 5 → 6, con 7 en cada incremento. 001 ya define eventos/relaciones/decisiones; 002 depende de 001 y prepara rutas/paradas/incidencias. No se modifica ni se aplica ninguna migración por preparar este backlog; cualquier necesidad estructural nueva se justifica y versiona por separado.

D2 no asume entrenar IA, elegir umbrales ni implementar un optimizador en este cierre. La ejecución operativa del chofer y las incidencias de parada corresponden al alcance posterior acordado, no se anuncian como funcionalidades de Sprint 1.

**Estado final del acta: preparada, pendiente de revisión y aprobación del equipo.**
