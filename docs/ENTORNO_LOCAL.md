# RECIWISE: entorno local persistente para Sprint 2

Verificado el 30 de octubre de 2026 en Windows/PowerShell. PostgreSQL y FastAPI reales, guardia de esquema activa y JWT ES256 verificados por JWKS. No requiere otro proyecto Supabase.

**Recuperación del 31 de octubre:** Docker Desktop estaba apagado y solo seguía activo un Vite habitual con Auth remoto. Además, otro Uvicorn con `--reload` retenía 8000 sin escuchar HTTP; su origen no se confirmó y no se detuvo. Se recuperó el volumen existente y se cambió únicamente `ports.api` a **8001** en `.localdev/config.json`. React recibió automáticamente la nueva URL. No se editaron .env ni se aplicaron migraciones. Las direcciones de abajo reflejan esa configuración local actual.

## Causa de schema_incompatible

La configuración habitual apunta al Supabase principal, que todavía no tiene el contrato completo 001+002+003. La guardia compara tablas, columnas, restricciones, índices, permisos y políticas con el manifiesto aprobado. Rechazar ese esquema es el comportamiento esperado; `/health` no sustituye `/ready`.

**No se cambió esa configuración, no se desactivó la guardia y no se migró Supabase.** El nuevo lanzador utiliza exclusivamente PostgreSQL local con identidad y volumen propios. Ejecutar `uvicorn app.main:app` por separado seguirá leyendo la configuración principal: para este entorno hay que usar los comandos siguientes.

## Iniciar desde VS Code en Windows

Abrir la carpeta del repositorio y una terminal PowerShell. Docker Desktop debe estar iniciado. Se reutilizan `.venv`, `requirements.txt`, Node y las dependencias existentes del frontend.

Después de reiniciar Windows, abrir Docker Desktop y ejecutar `up` otra vez. Los datos se conservan en el volumen; los procesos de desarrollo deben iniciarse en cada sesión.

```powershell
Set-Location 'C:\Users\DELL INSPIRON\Documents\RECIWISE'

# Una sola vez: crea recursos exclusivamente locales y las identidades ficticias.
.\.venv\Scripts\python.exe scripts\local_dev.py init --api-port 8001

# Cada sesión: mantiene esta terminal abierta. No vuelve a ejecutar migraciones.
.\.venv\Scripts\python.exe scripts\local_dev.py up
```

Si ya está iniciado, no abrir una segunda instancia: consultar `status`. Otro `up` se rechaza mediante un bloqueo exclusivo. Los errores de puerto no detienen ni reemplazan procesos ajenos.

| Servicio | Dirección configurada en este equipo | Naturaleza |
| --- | --- | --- |
| React/Vite | http://127.0.0.1:5173 | Aplicación real, HMR de frontend |
| FastAPI | http://127.0.0.1:8001 | `app.main:app` real; sin overrides ni lifespan desactivado |
| Preparación | http://127.0.0.1:8001/ready | `{"status":"ready","schema":"003"}` |
| OpenAPI | http://127.0.0.1:8001/docs | Documentación de la API local |
| Auth/JWKS/Storage local | http://127.0.0.1:54321 | Simuladores persistentes de desarrollo |
| PostgreSQL | 127.0.0.1:54329 | PostgreSQL 17, volumen Docker persistente y contraseña local aleatoria |

La contraseña de PostgreSQL no se pasa en la línea de comandos. El puerto inicialmente considerado, 55432, fue rechazado por Windows con 10013; se verificó disponible 54329. Para otra máquina con puertos ocupados, **antes de inicializar** se pueden elegir puertos distintos:

```powershell
.\.venv\Scripts\python.exe scripts\local_dev.py init --db-port 55300 --api-port 8001 --auth-port 54322 --ui-port 5175
```

Después de `init`, los puertos quedan en la configuración local. No editar nombres/identificadores del contenedor para reutilizar un recurso ajeno. La URL anunciada por `up` es la que debe abrirse.

## Cuentas de pruebas

El formulario de React utiliza su SDK normal de Supabase Auth contra el simulador HTTP local:

| Correo ficticio | Rol en los perfiles PostgreSQL locales |
| --- | --- |
| citizen@example.test | ciudadano |
| manager@example.test | encargado_municipal |
| driver@example.test | chofer |
| driver2@example.test | chofer |

La contraseña ficticia compartida de estas cuentas está en el campo `auth_password` de **`.localdev/credentials.json`**. Abrir ese archivo en el editor de VS Code; no copiarlo al chat, capturas, Git o documentación. No usar contraseñas reales. No existe selección pública de rol: las asignaciones se crean solo durante la preparación aislada; `/me` consulta los perfiles de esa base.

Tras recuperar el entorno, abrir `http://127.0.0.1:5173` en una pestaña nueva o recargar completamente para usar la configuración del lanzador. Las cuentas de Supabase principal pertenecen a otro entorno; para estas pruebas se usan las identidades ficticias de la tabla.

La clave privada ES256 se conserva en `.localdev/auth-signing.key`. JWKS publica solo la clave pública. FastAPI verifica firma, issuer local, audience y perfil con su código habitual; no se agregaron mecanismos de bypass. Se mantienen los algoritmos ES256/RS256 del backend.

## Consultar y detener

Desde otra terminal de VS Code:

```powershell
Set-Location 'C:\Users\DELL INSPIRON\Documents\RECIWISE'
.\.venv\Scripts\python.exe scripts\local_dev.py status

# Comprobación sin credenciales en la consola:
Invoke-RestMethod http://127.0.0.1:8001/ready

# Detiene Vite, FastAPI, simuladores y el contenedor propio. Conserva los datos.
.\.venv\Scripts\python.exe scripts\local_dev.py down
```

También se puede usar Ctrl+C en la terminal que ejecuta `up`. Esperar a que finalicen las peticiones antes de detenerlo. Para reiniciar, ejecutar de nuevo `up`; no ejecutar `init` ni migraciones manualmente. Los cambios Python requieren reiniciar; Vite conserva la recarga del frontend.

El cierre solicita al supervisor su propia instancia y comprueba propiedad de Docker. No mata procesos arbitrarios por número de puerto o PID. Si el supervisor no responde, se informa `supervisor_not_responding_no_process_was_force_killed`: revisar la terminal de origen y los procesos propios antes de continuar; no usar un kill masivo. Un cierre abrupto puede requerir esa revisión.

**No usar `docker compose down -v`, `docker volume rm` ni borrar `.localdev` como método de detener.** No hay comando de borrado/reset automático. El volumen y el directorio local son parte del estado persistente.

## Aislamiento y preparación de migraciones

`init` crea un contenedor y volumen con nombres derivados del workspace y una etiqueta aleatoria de propiedad. Comprueba ambos objetos y el enlace exacto a loopback. Rechaza objetos preexistentes sin esa identidad. Solo admite Docker local por named pipe de Windows o socket Unix; rechaza contextos/overrides TCP y SSH. No ofrece un parámetro de URL remota.

Sobre una base **nueva y vacía**, reutiliza `tests/isolated_postgres.py` para preparar primero:

1. Roles `anon` y `authenticated` sin LOGIN ni BYPASSRLS.
2. `auth.users` mínimo, necesario para la FK y el trigger de perfiles.
3. `storage.buckets` mínimo, necesario para la sentencia de bucket de 001.
4. Marcador aleatorio dentro de la base local.
5. Migraciones 001, 002 y 003 sin alterar sus archivos. 003 incorpora `btree_gist`, exclusiones y estructuras durables.
6. Identidades ficticias y perfiles correspondientes.
7. Verificación de catálogo con `app.schema_guard.verify_schema` y el manifiesto existente, sin regenerarlo.

Esto **no instala Supabase completo**. `auth.users` y `storage.buckets` son soportes locales mínimos, no servicios reales de Auth/Storage. La conexión administrativa local permite a FastAPI trabajar como servicio; las pruebas de roles pasan por JWT y `/me`, no demuestran políticas Supabase con credenciales de usuario.

Cada `up` comprueba etiquetas, volumen, puerto, marcador, versión PostgreSQL, hashes de las migraciones y catálogo. **No aplica ni repara migraciones.** Un esquema parcial/incompatible o una inicialización incompleta se rechazan, sin eliminar o modificar datos para resolverlos automáticamente. Si cambia el contrato del backend, preparar y revisar la evolución local antes de arrancar.

## Archivos y configuración privada

No se sobrescriben `.env`, `.env.local` ni `.env.example` existentes. El proceso FastAPI recibe explícitamente `DATABASE_URL`, `SUPABASE_URL`, la credencial **ficticia** de Storage, bucket y CORS locales. Las variables originales de la terminal no se modifican.

Vite recibe las tres variables públicas locales, `VITE_ENABLE_DEMO=false` y **`envDir:false`**: no carga archivos `.env` del frontend. Por ello el entorno de pruebas no hereda la conexión Supabase habitual. Sus consultas HTTP se dirigen al API local.

`.localdev/` está excluido por `.gitignore`; antes de generar credenciales, `init` comprueba esa exclusión. Contiene:

- `config.json`: identidad Docker, puertos, perfiles y hashes de migración.
- `credentials.json`, `postgres.env`, `auth-signing.key`: credenciales/clave exclusivamente ficticias y locales.
- `storage/`: fotografías simuladas y archivo de control persistentes.
- `refresh-tokens.json`, `read-tokens.json`: tokens locales persistentes; las URLs de lectura expiran a los 300 segundos.
- `runtime.json`, `local.lock`, `stop.json`: coordinación de procesos propios.
- `check-data.json` y `acceptance-baseline.json`: IDs y referencia de aceptación de los datos ficticios.

No copiar estos archivos a `frontend/src`, documentación, commits ni PR. No configurar aquí cuentas o datos personales. No exportar sus variables privadas para ejecutar pruebas destructivas contra este volumen de desarrollo; las pruebas D2 utilizan su ejecutor desechable separado.

## Verificación reproducible

Con `up` activo, ejecutar:

```powershell
.\.venv\Scripts\python.exe scripts\check_local_dev.py
```

La primera ejecución crea una sola colección de fixtures locales: reporte, foto, evento asociado, revisión auditada, vehículo, salida/descarga, turno y propuesta **pendiente, no operativa**, sin resultado de planificador. Las siguientes reutilizan los IDs registrados. Los recursos se preparan desde el script de pruebas; React no genera ni registra propuestas de rutas.

La comprobación hace HTTP real a Auth local y FastAPI; valida ES256 mediante JWKS, perfiles, 401/403, CORS y consultas de Sprint 2. Chrome inicia sesión mediante el formulario existente, descarga la fotografía, abre evento/mapa y reportes asociados, consulta relación/historial/detalle de decisión y propuesta/paradas/exclusiones. No intercepta el API de negocio. Intercepta solo teselas y bloquea orígenes externos.

Se compara una instantánea SQL **READ ONLY** de IDs/campos y hashes de fotografías/control con la referencia inicial. Si alguien modifica deliberadamente esos fixtures, la comparación debe fallar: no se sobreescribe la referencia para ocultar cambios. No se borran fixtures al terminar.

Para verificar persistencia:

```powershell
.\.venv\Scripts\python.exe scripts\check_local_dev.py
.\.venv\Scripts\python.exe scripts\local_dev.py down
# En la primera terminal:
.\.venv\Scripts\python.exe scripts\local_dev.py up
# En la segunda:
.\.venv\Scripts\python.exe scripts\check_local_dev.py
```

Las pruebas de herramientas se ejecutan separadas de la base:

```powershell
$localDevTmp = '.test-artifacts/local-dev/unit-tmp-' + [guid]::NewGuid().ToString('N')
.\.venv\Scripts\python.exe -m pytest tests/test_local_dev.py -q -p no:cacheprovider --basetemp $localDevTmp
```

## Resultados comprobados

| Verificación | Resultado actual |
| --- | --- |
| Inicialización en PostgreSQL local real | Correcta; dependencias + 001+002+003 y guardia compatibles |
| Arranque `/ready` | HTTP 200, status ready, schema 003 |
| Pruebas unitarias de herramientas | 29 aprobadas, 0 fallidas |
| HTTP antes del reinicio | 28 comprobaciones aprobadas |
| Navegador antes del reinicio | 1 recorrido aprobado, 0 fallos |
| HTTP y navegador después del reinicio | 28 comprobaciones y 1 recorrido aprobados, 0 fallos |
| Persistencia tras detener/iniciar PostgreSQL y procesos | Mismos IDs, campos, relaciones, decisión, turno, propuesta y hashes de fotografía/control; sin duplicados |
| Repetir init sobre el volumen existente | Solo verificación; no se repitieron migraciones ni perfiles |
| Regresión D2 en contenedor desechable separado | 595 aprobadas, 0 fallidas, 12 omitidas; 215.44 s |

Evidencia local ignorada:

- Antes del reinicio: `.test-artifacts/local-dev/7b8d1f880b3345e8bc051f8402b02af8/`.
- Después: `.test-artifacts/local-dev/c740cb4bee1f483188002ce2755deb07/`.
- Verificación de la versión final, tras repetir init y arrancar de nuevo: `.test-artifacts/local-dev/2e9022370783498990984b2612e6e204/` (28 comprobaciones y 1 recorrido aprobados, misma instantánea persistente).
- Recuperación del 31 de octubre en API 8001: `.test-artifacts/local-dev/143a384e7a5345348bf88920ddecc990/` (28 comprobaciones HTTP y el recorrido React aprobados, mismos datos persistentes). `/ready` 200, `/me` sin JWT 401 y autenticación/perfiles verificados; no se reejecutó la suite D2 completa para esta recuperación.
- Cada carpeta contiene `results.json`, `persistence.json`, `browser.xml`, `browser.log`, `browser-http.json` y captura `react-local.png`; no se publican credenciales ni tokens.
- `.test-artifacts/local-dev/unit.xml`: 29 pruebas.
- Regresión D2: `.test-artifacts/reciwise-d2-test-251cb6ca0c5a4438ad4d6199984d032d/pytest.xml` y `environment.json`. Su contenedor se eliminó; no comparte el volumen de desarrollo.

Incidencias del entorno: puerto 55432 no disponible y permisos de directorios temporales de pytest dentro del sandbox Windows. Se usó 54329 y las pruebas se ejecutaron con permisos locales adecuados; no se relajaron permisos de la aplicación ni de PostgreSQL. Las aserciones de negocio pasaron.

## Qué sigue simulado o pendiente

- Auth/JWKS: simulador HTTP local con firmas ES256 reales, sin GoTrue ni usuarios del proyecto principal. No demuestra MFA, confirmación de correo, revocación o políticas remotas.
- Storage: servicio HTTP y archivos persistentes locales, con URLs temporales; no es Supabase Storage real ni demuestra sus políticas, disponibilidad o fallos remotos.
- Teselas: simuladas en la prueba de navegador. Durante uso manual, Leaflet conserva el proveedor OpenStreetMap existente y requiere conexión si se desea mapa base.
- D3/IA/matriz vial: no se ejecutan. La propuesta fixture permanece pendiente y no operativa.
- Las 12 omisiones D2 conservan ese estado: 2 requieren registros piloto existentes no proporcionados al ejecutor desechable; 9 requieren REST anónimo de Supabase real; 1 requiere una sesión JWT ciudadana real para la comprobación remota. La nueva prueba de persistencia local no se contabiliza como ejecución de esos casos omitidos. El proyecto compartido sigue sin 003 aplicada y mantiene **NO-GO para desplegar el backend nuevo**.

El entorno permite continuar desarrollo funcional local de Sprint 2. No constituye aprobación del despliegue ni cierre formal del sprint. No se hizo push, merge ni despliegue.

## Cambios del repositorio

- `scripts/local_dev.py`: preparación, propiedad/puertos, ciclo de vida, estado y comprobación de esquema.
- `scripts/local_dev_services.py`: reutiliza el simulador existente con clave ES256, sesiones y objetos persistentes.
- `scripts/local_dev_vite.mjs`: arranca Vite existente con carga de .env deshabilitada.
- `scripts/check_local_dev.py`, `scripts/local_dev_playwright.config.cjs`, `scripts/local_dev.spec.cjs`: verificación HTTP, navegador y persistencia con fixtures reutilizables.
- `tests/test_local_dev.py`: 29 pruebas de seguridad/configuración, almacenamiento, exclusión de procesos y diagnóstico.
- `tests/isolated_postgres.py`: admite la contraseña de la URL local; mantiene las comprobaciones de host/nombre/marcador.
- `tests/integrated_services.py`: permite puerto fijo y lista explícita de orígenes; sus valores por defecto conservan el ejecutor desechable.
- `.gitignore`: excluye `.localdev/`.
- Este documento y el enlace de `docs/FRONTEND_SPRINT2.md`.

La comparación SHA-256 con 143 archivos del estado inicial verifica **0 cambios en app/, IA, migraciones y archivos .env**. Se conservan los cambios anteriores de otros integrantes. Evidencia: `.test-artifacts/local-dev/scope-verification.json`.
