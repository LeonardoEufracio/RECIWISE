# Publicación para revisión de la integración D1/D2 — 4 de noviembre de 2026

## Alcance y decisión

Rama de integración: `integration/d1-d2-fullstack`, con destino `main` mediante Pull Request para revisión, sin merge ni despliegue. Parte del commit `48b4081`, ya publicado en `feature/d2-sprint1-estabilizacion` y pendiente en el PR #1; por ello el PR de integración también contiene aquella estabilización. No se modifica ni cierra automáticamente el PR anterior. El equipo debe coordinar ambas revisiones antes de fusionar.

Se respaldan los avances fullstack ya existentes: panel municipal y chofer, reportes y fotografías, eventos manuales, decisiones de agrupación, propuestas de rutas, recursos/turnos, guardia de esquema y pruebas/documentación de integración. Esta preparación no añade funcionalidades de negocio. La aprobación de rutas de origen no verificado permanece bloqueada con HTTP 409; no se integra ni ejecuta un proveedor D3.

**GO para respaldo de código revisable; NO-GO para un nuevo despliegue sin revisión.** Publicar una rama no aprueba el Sprint ni autoriza operaciones remotas.

## Diagnóstico de fotografías

El [diagnóstico del 4 de noviembre](DIAGNOSTICO_FOTOGRAFIAS_20261104.md) incorpora los tres resultados SQL proporcionados manualmente por el usuario. No se demostró una asociación incorrecta: fotografía, operación completada y ruta coinciden con el reporte anterior, antes de la creación del nuevo. El nuevo tiene cero fotografías persistidas y no aparece un intento durable para él en el resultado compartido. No se puede reconstruir la intención del usuario ni descartar una petición rechazada antes del diario sin evidencia HTTP.

Se conserva la corrección local comprobada de `Photos.tsx`: un GET fallido después de una subida exitosa no presenta un cero obsoleto como ausencia confirmada; estado y respuestas tardías quedan aislados por reporte. No se atribuye ese fallo de visualización a la asociación histórica. No se movió, borró ni reasoció ninguna fotografía.

## Auditoría de contenido y automatizaciones

- Se revisaron el estado local, referencias actualizadas de `origin`, commits, cambios y archivos nuevos. Sin conflictos en el índice ni divergencia entre el punto de partida y su rama remota. `origin/main` es antecesor del commit base.
- Se excluyen íntegramente los cambios locales de `docs/CONTRATOS_D3.md` y `frontend/.env.example`. Permanecen en el árbol de trabajo, sin sobrescribirlos ni publicarlos en este incremento. No cambia `d3/` ni se alteran migraciones existentes.
- `.gitignore` protege `.env`, `.env.*`, configuración frontend privada, `.localdev/`, claves, credenciales, entornos virtuales, temporales, respaldos y resultados de pruebas. Se comprobó el comportamiento con trece rutas representativas y se añade la exclusión de `.localdev/` ya usada en desarrollo.
- La revisión combina patrones de secretos, comparación interna con valores sensibles de configuración local y revisión de los literales detectados. El hallazgo de URL con contraseña pertenece a una prueba unitaria explícitamente ficticia, de localhost y con conexión sustituida. Los otros literales son fixtures ficticios o referencias a generación/configuración dinámica. No se encontraron secretos reales, binarios, fotografías privadas ni archivos de configuración privada entre los candidatos. Las credenciales no se muestran ni se incluyen en informes.
- No hay workflows bajo `.github` ni configuraciones de despliegue versionadas en el árbol local, `origin/main` o la rama de estabilización actualizada. El commit previo no presenta estados ni ejecuciones de workflow de PR en las respuestas consultadas. No se añade ninguna automatización. Las integraciones externas configuradas fuera del repositorio no son auditables con los permisos disponibles; no se declara verificada su configuración administrativa.
- Los artefactos, capturas, bases, claves efímeras y resultados locales permanecen bajo rutas ignoradas. El inventario exacto de archivos del incremento se adjunta al PR; las evidencias locales no forman parte del commit.

## Estado de migraciones 002 y 003

**Información comunicada por el usuario:** ambas migraciones ya fueron aplicadas manualmente en **Supabase SQL Editor**. Codex no volvió a aplicarlas, no se conectó al proyecto principal y no consultó su historial CLI durante esta publicación. Los archivos 001, 002, 003 y el rollback existente se conservan sin cambios.

La ejecución en SQL Editor y el historial gestionado por **Supabase CLI son evidencias distintas**. El esquema puede estar aplicado mientras la CLI no tenga registradas las versiones correspondientes. El estado remoto de ese historial no está comprobado; podría requerir reconciliación.

Antes de autorizar una operación remota futura:

1. Confirmar destino y respaldo/restauración y obtener autorización para la intervención específica.
2. Comparar mediante diagnóstico de lectura el esquema actual, restricciones, extensiones y dependencias con los archivos revisados; verificar compatibilidad completa 001+002+003, no solo el estado de `/health`.
3. Contrastar el historial CLI y los identificadores de versión contra las migraciones efectivamente aplicadas. No asumir que la numeración corta de estos archivos se corresponde automáticamente con un historial administrado por otra herramienta.
4. Presentar y revisar el procedimiento de reconciliación de metadatos que corresponda. No ejecutar automáticamente `db push`, `db reset`, una reparación del historial o una reaplicación de 002/003 como parte de este respaldo.

Una reparación del historial puede modificar metadatos remotos: tampoco queda autorizada por esta publicación. Aplicar manualmente 003 no demuestra por sí solo recuperación con Storage real, restauración de respaldo o preparación operativa del conciliador.

## Verificaciones de esta publicación

Todas las pruebas con escrituras usan PostgreSQL local desechable, con identidad por ejecución y migraciones 001+002+003. Las pruebas unitarias existentes que usan SQLite/sustituciones no equivalen a PostgreSQL; las garantías de concurrencia se ejercitan en PostgreSQL real. Auth, Storage y teselas de la integración son simuladores locales; JWT ES256, React, Leaflet, FastAPI y PostgreSQL sí se verifican realmente.

| Verificación | Resultado |
| --- | --- |
| Suite D2, `tests/run_isolated_postgres.py --phase all` | 681 aprobadas, 0 fallidas/errores, 12 omitidas; 242,32 s |
| Herramientas locales, `tests/test_local_dev.py` y `tests/test_demo_support.py` | 43 aprobadas, 0 fallidas, 0 omitidas |
| Frontend y TypeScript dentro del integrado | 145 aprobadas, 0 fallidas, 0 omitidas; tipos correctos |
| Navegador integrado, `--phase integrated` | 11 aprobadas, 0 fallidas, 0 omitidas |
| `npm run build` con variables públicas ficticias | Código de salida 0 |
| Compilación Vite del runner integrado | Código de salida 0 |
| Revisión del índice y `git diff --cached --check` | 112 archivos del incremento; sin errores tras normalizar finales CRLF del manifiesto JSON y retirar una línea vacía final de documentación |

Los dos builds se corresponden con la misma fuente; no se suman como casos de prueba. El navegador incluye el caso de dos reportes consecutivos, fotografías diferentes, fallo de Storage y reintento al mismo ID; las descargas y rutas se comparan con las filas reales de PostgreSQL aislado. Los contenedores desechables de ambas fases terminaron y fueron retirados por sus runners.

Las **12 omisiones** proceden de `test_postgres_persistence.py`, y no son doce pruebas aprobadas ni doce casos de Storage:

- 2 casos requieren el reporte con fotos y el turno de `Compactadora Piloto 01` preexistentes; la base desechable no los contiene y estas pruebas no crean sustitutos automáticamente.
- 9 comprobaciones REST anónimas requieren URL/clave pública de Supabase real.
- 1 comprobación de sesión ciudadana requiere un JWT real. Las comprobaciones SQL `SET ROLE` no la sustituyen.

La integración local sí verifica persistencia/reinicio con sus propios registros ficticios y JWT ES256 verificables. No reemplaza la validación de los registros piloto omitida ni las sesiones de Supabase reales.

Se encontraron incidencias del entorno al lanzar herramientas locales: acceso denegado de Windows a temporales de pytest dentro del sandbox y un error de impresión Unicode de un wrapper del build. Se repitieron las verificaciones afectadas con temporales nuevos, permisos adecuados y salida segura, sin modificar código funcional. Los resultados finales sustituyen esos intentos de infraestructura, que no se presentan como aprobados. La normalización CRLF→LF de `app/schema_003.json` conserva exactamente el mismo contenido JSON probado; no regenera el manifiesto ni cambia sus hashes de migraciones. Permanece una advertencia de deprecación de Starlette/httpx y una advertencia de Vite por un chunk superior a 500 kB; no impiden la compilación ni se corrigen añadiendo alcance a este respaldo.

Evidencias locales, excluidas de Git:

- `.test-artifacts/publicacion-fullstack-20261104/`: auditoría, referencias de integridad, inventario, resultados de herramientas y log/resultado de `npm run build`.
- `.test-artifacts/reciwise-d2-test-b69a42953add44359b56039790d14f9e/`: suite D2 y manifiesto del entorno.
- `.test-artifacts/reciwise-d2-test-081b10327bdc4af29364fdd969683c5e/`: JUnit del navegador, Vitest, build y evidencias de la integración con servicios simulados.

## Bloqueos y revisión del equipo

- Revisión del PR, coordinación con el PR #1 y aprobación independiente antes de fusionar.
- Historial CLI de migraciones por contrastar/reconciliar con autorización posterior; no reaplicar SQL a ciegas.
- Pruebas de fallos/recuperación con Supabase Auth/Storage reales no demostradas por las pruebas locales ni por el diagnóstico SQL de fotografías. No se crean proyectos ni se ejecutan pruebas remotas en este trabajo.
- Proveedor D3 operativo verificado pendiente; aprobación real de rutas bloqueada. El recorrido positivo del chofer usa autorizaciones ficticias solo en entornos desechables.
- Confirmación administrativa de integraciones de despliegue externas, configuración operativa, respaldo/restauración y supervisión del conciliador antes de autorizar un nuevo despliegue.

No se configura despliegue, no se fusiona a `main`, no se modifican datos persistentes y no se ejecuta ninguna migración en Supabase en esta publicación.
