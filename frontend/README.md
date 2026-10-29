# RECIWISE: frontend local de pruebas

Interfaz React + Vite + TypeScript que inicia sesión con Supabase Auth y consume FastAPI. Las tablas de negocio y Storage se acceden exclusivamente a través de FastAPI. No hay registro público, selector de roles ni asignación de permisos desde React.

## Iniciar backend y frontend

Requisitos: Python con las dependencias de `../requirements.txt`, Node.js 22.12 o superior (preferible una versión LTS) y npm. Las dependencias del frontend ya fueron instaladas y están fijadas en `package-lock.json`. En otra copia del proyecto, ejecutar `npm ci` dentro de `frontend/`.

1. Desde la raíz de RECIWISE, conservar el `.env` del backend existente. Si se prepara una instalación nueva, crear el entorno Python e instalar `requirements.txt`, copiar `.env.example` a `.env` y configurar Supabase y PostgreSQL. La migración `migrations/001_sprint1.sql` debe estar aplicada; no se ejecuta automáticamente. El proyecto Auth debe usar firma RS256/ES256, que es lo que valida `app/security.py`.

   En una terminal PowerShell, desde la raíz:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

   En Linux/macOS, con el entorno activado: `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`. Documentación de la API: <http://127.0.0.1:8000/docs>.

2. En otra terminal, crear la configuración del frontend solo si aún no existe:

   ```powershell
   cd frontend
   Copy-Item .env.example .env.local
   ```

   Completar **únicamente** estas variables públicas en `frontend/.env.local`:

   ```dotenv
   VITE_SUPABASE_URL=https://<PROJECT_REF>.supabase.co
   VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_<PUBLIC_KEY>
   VITE_API_URL=http://127.0.0.1:8000
   ```

   La URL y la clave pública deben corresponder al mismo proyecto que usa el backend. Copiar la clave **publishable** desde la configuración del proyecto Supabase. Esta interfaz acepta el formato `sb_publishable_…`; rechaza `sb_secret_…`, claves JWT heredadas y `service_role`. No copiar el `.env` del backend al frontend. Nunca agregar contraseñas, conexión PostgreSQL ni credenciales de servidor con prefijo `VITE_`: Vite incorpora esas variables al JavaScript público.

   No se creó un `.env.local` con valores inventados. Falta completar la clave pública para iniciar sesión en el proyecto real. `.env.local` está excluido del repositorio.

3. Iniciar Vite:

   ```powershell
   npm run dev
   ```

   Abrir **<http://localhost:5173>**. Vite fija este host y puerto y falla si el puerto está ocupado, para evitar cambiar el origen autorizado silenciosamente. Reiniciar Vite después de editar sus variables.

   `npm run build` genera `dist/`; `npm run preview` sirve esa compilación en el mismo origen, con el servidor de desarrollo detenido. Las variables se incorporan al compilar; cambiarlas exige recompilar.

## CORS

El backend ya utiliza `CORSMiddleware` con el valor de `CORS_ORIGINS`, leído en el arranque. La configuración existente permite:

```dotenv
CORS_ORIGINS=http://localhost:5173
```

Autoriza `Authorization`, `Content-Type` y los métodos GET, POST y PATCH, sin cookies. El frontend envía `Authorization: Bearer <access_token>` y `credentials: omit`, sin proxy de Vite. Los preflights OPTIONS son atendidos por el middleware existente.

`http://127.0.0.1:5173` es un origen distinto de `http://localhost:5173`. Si se necesita usarlo, agregarlo explícitamente en el `.env` **del backend** y reiniciar FastAPI:

```dotenv
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

No se modificaron los endpoints ni el middleware para esta integración.

## Uso con las cuentas existentes

1. Pulsar **Comprobar /health**. Un 200 confirma que FastAPI responde, pero no verifica PostgreSQL, Auth ni Storage.
2. Iniciar sesión con el correo y contraseña de una cuenta existente. La contraseña se envía a Supabase Auth; se vacía el campo después del intento. El SDK conserva y renueva la sesión en el navegador.
3. La interfaz consulta `GET /me` antes de mostrar operaciones. El rol efectivo viene de `profiles` a través de FastAPI. Un 401/403 deja las operaciones bloqueadas y muestra el error. **Consultar /me** permite reintentar o recoger un cambio de rol administrativo.
4. Con rol `ciudadano`, registrar descripción, ubicación y fecha/hora de observación. **Usar mi ubicación** solicita GPS únicamente al pulsar el botón; **Elegir en el mapa** permite tocar, hacer clic o arrastrar el marcador con React Leaflet. Revisar el punto y pulsar **Confirmar ubicación** antes de registrar. El centro inicial del mapa es una referencia sin punto seleccionado. La fecha usa la hora local del dispositivo y se convierte a ISO 8601 con zona horaria UTC. Tipo de residuo es opcional.
5. En **Mis reportes**, abrir las fotografías o añadir una foto. El reporte se guarda antes de subir imágenes: un error de Storage no obliga a volver a crear el reporte. Hay paginación de 50 registros.
6. Con rol `encargado_municipal`, consultar el listado y los puntos de la página actual en el mapa. Se puede filtrar por estado; los estados de la migración son `recibido`, `en_revision`, `programado`, `atendido` y `descartado`. Se pueden ver las fotos. La cuenta municipal no tiene formulario ciudadano ni subida de fotos.
7. Los enlaces de las fotos vencen a los 300 segundos. Usar **Renovar enlaces** para volver a consultar la API. Se admite JPG/PNG/WebP, máximo 5 MiB por archivo y 3 fotos por reporte. Estos límites también son comprobados por el backend.
8. Revisar **Comunicación con FastAPI**: últimas 50 peticiones, hora, método, ruta, HTTP y duración. El historial solo vive en memoria; no almacena cuerpos, cabeceras de autenticación, contraseñas ni URLs firmadas. «Sin HTTP» indica que no hubo respuesta legible (p. ej. desconexión, timeout, CORS o sesión ausente); no equivale a un código HTTP del servidor.

El rol `chofer` se reconoce pero no tiene operaciones en esta interfaz. Los permisos de todos los endpoints siguen siendo responsabilidad de FastAPI.

## Selector de ubicación ciudadano

El formulario ya no presenta entradas obligatorias de latitud y longitud. Esos datos se obtienen del selector y se mantienen como números en el JSON de `POST /reports`; no cambian el backend, las migraciones ni `ReportCreate`.

**Probar «Usar mi ubicación»:**

1. Iniciar sesión como ciudadano. No debe aparecer ninguna solicitud de GPS al iniciar sesión ni al montar el formulario.
2. Pulsar **Usar mi ubicación** y aceptar el permiso del navegador. Mientras se resuelve, se muestra el estado de búsqueda. El mapa centra el marcador y muestra la precisión estimada en metros si el dispositivo la ofrece; el círculo representa esa precisión, no una garantía de exactitud.
3. Revisar el punto. Si hace falta, tocar otro lugar o arrastrar el marcador; al moverlo se descarta la precisión original del GPS. Pulsar **Confirmar ubicación**. Todavía no se envía un reporte.
4. Completar los demás datos y pulsar **Registrar reporte**. Solo en este momento se envían las coordenadas a FastAPI. Se conserva la autorización Bearer de Supabase y el flujo posterior de fotografías.
5. Para comprobar errores, denegar el permiso en la configuración del navegador y volver a pulsar el botón. Se muestra una explicación y sigue disponible la selección manual. También se manejan ubicación no disponible, tiempo de espera agotado, ausencia de geolocalización y contexto inseguro.

**Probar «Elegir en el mapa»:**

1. Pulsar **Elegir en el mapa**. Esta opción no solicita GPS.
2. Tocar o hacer clic en el lugar de la acumulación. Aparece un marcador que se puede arrastrar para ajustar el punto. Las coordenadas se muestran como texto de referencia, sin entradas técnicas que completar.
3. Sin una selección confirmada, **Registrar reporte** permanece desactivado. La validación del envío también rechaza una selección ausente o sin confirmar; no se hace `POST /reports`.
4. Pulsar **Confirmar ubicación**. Para cambiar el lugar después, pulsar **Corregir ubicación**, mover el marcador y confirmar de nuevo.
5. Pulsar **Registrar reporte**. El selector se limpia al guardar correctamente; si falla el envío, la selección permanece para poder reintentar.

La geolocalización requiere **HTTPS en un móvil** o **localhost en desarrollo**. Abrir desde el teléfono una dirección como `http://192.168.x.x:5173` no equivale a localhost y normalmente bloquea GPS; usar HTTPS con el origen correspondiente permitido en CORS. La selección por mapa puede seguir utilizándose sin GPS.

No hay seguimiento continuo, guardado de la ubicación en localStorage/sessionStorage ni envío anticipado a la API. La selección temporal se descarta al salir del formulario/cerrar sesión o después de registrar correctamente. Se ignoran respuestas de GPS que llegan después de cambiar a selección manual o desmontar el formulario. El mapa base sigue descargando teselas de OpenStreetMap según el área visible; no se añadió ningún servicio de geocodificación.

Archivos de esta mejora:

- `src/LocationPicker.tsx`: solicitud explícita de GPS, carga, errores, precisión y confirmación/corrección.
- `src/LocationMap.tsx`: React Leaflet, selección por clic/toque, marcador arrastrable y círculo de precisión. Los iconos se empaquetan con Vite.
- `src/ReportForm.tsx`, `src/reportPayload.ts`, `src/types.ts`: estado temporal y validación de una ubicación confirmada; envío del contrato existente sin datos internos del selector.
- `src/styles.css`, `package.json`, `package-lock.json`: estilos y dependencia `react-leaflet`.
- `src/ReportForm.test.tsx`, `src/App.test.tsx`, `src/reportPayload.test.ts`, `e2e/integration.spec.ts`: pruebas de consentimiento, errores, corrección, envío, autenticación, fotos, mapa municipal y selección táctil.

El mapa municipal de `src/MapView.tsx`, el cliente JWT, las fotografías y todo `app/` permanecen sin cambios.

## Inspección del backend y contratos usados

Antes de implementar se revisaron `app/main.py`, `schemas.py`, `security.py`, `config.py`, `db.py`, `models.py`, `storage.py`, las migraciones y las pruebas. No existía otro frontend. `app/` permanece sin cambios.

| Archivo/carpeta | Responsabilidad existente |
| --- | --- |
| `app/main.py` | Endpoints y CORS |
| `app/schemas.py` | Validación y esquemas Pydantic |
| `app/security.py` | JWT Supabase vía JWKS, emisor, audiencia, vencimiento y rol leído en `profiles` |
| `app/config.py`, `app/db.py`, `app/models.py` | Entorno, sesiones SQLAlchemy y modelos |
| `app/storage.py` | Subida privada y firma de URLs mediante una credencial exclusiva del servidor |
| `migrations/` | Tablas, perfiles y bucket privado; estructura futura de rutas |
| `tests/`, `d3/`, `docs/` | Pruebas de API, trabajo de D3 y documentación previa |

| Petición | Contrato real consumido |
| --- | --- |
| `GET /health` | Público; `{status, version}` |
| `GET /me` | Bearer; `{id, role}` |
| `POST /reports` | Ciudadano; JSON con `description`, `latitude`, `longitude`, **`observed_at` obligatorio**, `waste_type` opcional; devuelve reporte y HTTP 201 |
| `GET /reports/mine?limit=50&offset=0` | Ciudadano; array directo de reportes, sin envoltorio de paginación |
| `POST /reports/{id}/photos` | Ciudadano propietario; multipart con campo **`file`**; HTTP 201, metadatos con `signed_url: null` |
| `GET /reports/{id}/photos` | Propietario o encargado; array de fotos con `signed_url` temporal; se consulta también después de subir |
| `GET /municipal/reports?limit=50&offset=0&status=…` | Encargado; array directo con latitud/longitud, estado, descripción, IDs y fechas |

La descripción requiere entre 3 y 2000 caracteres, latitud −90 a 90, longitud −180 a 180, fecha con zona horaria y no más de cinco minutos en el futuro. `waste_type` admite hasta 80 caracteres. React no envía rol, `citizen_id`, estado ni fecha de creación al registrar un reporte.

También existen `GET /reports/{id}`, filtros geográficos `north/south/west/east` del listado municipal y operaciones sobre `/municipal/vehicles`, `/municipal/sites` y `/municipal/shifts`. Se conservaron; esta interfaz no amplía su alcance.

## Comprobaciones y límites de la verificación

Resultados del **28 de octubre de 2026**:

| Comprobación | Resultado y alcance |
| --- | --- |
| Instalación npm | Dependencias instaladas y lockfile generado. El registro principal falló desde este entorno; se utilizó el espejo HTTPS `registry.npmmirror.com`, reflejado en las URLs del lockfile. |
| Backend original | Los 9 tests existentes pasaban antes de los cambios. |
| Backend con pruebas de integración añadidas | **11 tests pasan**: conserva los originales y añade preflight CORS, respuesta CORS real, origen rechazado, contrato multipart, lectura de fotos, límite de 3 y permisos. Usan SQLite y sustituyen Auth/Storage. |
| Frontend | **39 tests pasan**: mantiene cobertura de login, rol, JWT, fotos y API; añade ubicación confirmada, ausencia de GPS al montar/iniciar sesión, carga y precisión, errores GPS, contexto inseguro, corrección, respuestas tardías y ausencia de persistencia/envío anticipado. Auth y API simulados; mapas sustituidos en las pruebas de componentes. |
| TypeScript y build | Comprobación de tipos y compilación de producción correctas. Vite advierte sobre un chunk mayor de 500 kB; es una advertencia de tamaño, no un fallo de compilación. |
| HTTP contra Uvicorn real | `/health` → **200**, `/me` sin token → **401**, preflight de POST con Authorization/Content-Type → **200**, todos con CORS para localhost:5173. No se escribieron datos en Supabase. |
| Chrome/Playwright | **6 pruebas pasan**. Una verifica desde el navegador `/health` 200 y `/me` 401 contra FastAPI real. Las otras verifican arrastre real del marcador en React Leaflet, bloqueo hasta confirmar, foto visible, logout, GPS con coordenadas simuladas del navegador, permiso denegado, selección táctil móvil y la vista municipal. **Auth, API de negocio, imágenes y teselas están simulados**. |

Pendiente de prueba con el proyecto real:

- Completar `frontend/.env.local` con la clave publishable del proyecto y entrar con ambas cuentas existentes. No se usaron ni crearon contraseñas.
- Verificar JWT firmado por Supabase, `/me` con ambos perfiles y persistencia real de un reporte a través de PostgreSQL. Las pruebas con dependencias sustituidas no comprueban JWKS ni las migraciones aplicadas.
- Subir fotos al bucket privado real, leerlas desde la cuenta municipal y renovar una URL tras su vencimiento. Las pruebas de Storage no se conectan al bucket.
- Comprobar teselas de OpenStreetMap con conexión a Internet. Se probó el render y la interacción de Leaflet con teselas locales de prueba.
- Probar el GPS físico y el permiso real del sistema en un teléfono servido mediante HTTPS. Chrome se probó con geolocalización simulada y pantalla táctil emulada; no sustituye esa comprobación en el dispositivo.

### Repetir las comprobaciones

Desde la raíz, con el entorno Python disponible:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Desde `frontend/`:

```powershell
npm run check
npm run build
```

Para las pruebas de navegador, iniciar primero el backend en el puerto 8000 y dejar libre el puerto 5173. Playwright inicia/detiene su propio Vite con configuración pública ficticia; no modifica `.env.local` ni manda reportes a Supabase. En esta máquina se utilizó el Chrome instalado:

```powershell
$env:PLAYWRIGHT_CHANNEL = 'chrome'
npm run test:browser
```

En Linux/macOS: `PLAYWRIGHT_CHANNEL=chrome npm run test:browser`. Alternativamente, instalar el Chromium de Playwright con `npx playwright install chromium` y ejecutar sin `PLAYWRIGHT_CHANNEL`.

El backend emite una advertencia de deprecación de Starlette/httpx que ya existía. El entorno restringido también bloqueó los subprocesos de Vite con `spawn EPERM`; las comprobaciones se ejecutaron con permiso para iniciar esos procesos, sin cambiar la aplicación para eludirlo.

Referencias usadas: [inicio de sesión con contraseña](https://supabase.com/docs/reference/javascript/auth-signinwithpassword), [eventos de sesión](https://supabase.com/docs/reference/javascript/auth-onauthstatechange), [variables de Vite](https://vite.dev/guide/env-and-mode) y [API de Leaflet](https://leafletjs.com/reference.html).

Para el selector: [marcadores arrastrables de React Leaflet](https://react-leaflet.js.org/docs/example-draggable-marker/), [eventos y acceso al mapa](https://react-leaflet.js.org/docs/api-map/) y [especificación de geolocalización W3C](https://www.w3.org/TR/geolocation/).
