# RECIWISE — API y base de datos del Sprint 1 (D2)

Fecha de documentación y comprobación automatizada: **29 de octubre de 2026**. Código base revisado: **`ef9b45a`**, con los cambios locales de descripción (6.4), JWT/permisos (6.5), PostgreSQL/persistencia (6.6), concurrencia/compensación (6.8), guardia de esquema (6.10) y operación del conciliador (6.11); estos tres últimos comprobados exclusivamente en PostgreSQL aislado. API **`0.1.0`**. Responsable funcional: D2, backend, autenticación, permisos, PostgreSQL, persistencia e integración con D1/D3.

Este documento describe lo implementado y la evidencia disponible. **No declara cerrado el Sprint 1.** Las pruebas manuales comunicadas por el responsable D2 se distinguen de las pruebas automatizadas ejecutadas para esta documentación.

**Preparación del despliegue: sigue NO-GO para aplicar 003 al Supabase compartido.** La guardia de **FastAPI está implementada en 6.10**, y la del ejecutor del conciliador, junto con su operación segura, en **6.11**. Continúan pendientes Storage real, respaldo/restauración y preparación operativa del despliegue. En estas dos implementaciones no se contactó Supabase compartido; solo se usó PostgreSQL aislado. La lectura compartida de 6.9 es evidencia histórica READ ONLY.

**Decisión vigente del responsable (29/10/2026):** no crear RECIWISE-TEST por ahora; conservar el proyecto principal para la aplicación, sin aplicar 003 ni ejecutar pruebas destructivas allí. Reutilizar PostgreSQL local aislado y servicios simulados. **GO para desarrollo local; NO-GO para desplegar el backend nuevo/003 en el principal.** Las pruebas de Storage real quedan pendientes, sin bloquear funciones independientes. Ver **6.12** y [prioridades D2 para la hackatón del 19 de noviembre](PLAN_D2_HACKATON.md); esta decisión reemplaza los pasos de crear otro proyecto como requisito inmediato de trabajo, no elimina los controles del despliegue.

**Prueba integrada posterior, 6.13:** recorrido React → FastAPI → PostgreSQL → mapa municipal comprobado con JWT ES256 y Storage de pruebas por HTTP local. **4 escenarios de navegador aprobados**, frontend **39 pruebas/tipos/build correctos** y regresión D2 **273 aprobadas, 12 omitidas, cero fallos/errores**. Listo para revisión de aceptación funcional **en entorno local aislado**, sin declarar aceptación del despliegue ni cierre del Sprint.

**Acta preparada:** [ACEPTACION_SPRINT1_D2.md](ACEPTACION_SPRINT1_D2.md) reúne criterios, artefactos, demo reproducible, revisión independiente y backlog D2 de Sprint 2. La decisión del equipo queda pendiente; preparar el documento no la sustituye.

## 1. Fuentes, alcance y convenciones

Se revisaron [endpoints](../app/main.py), [modelos ORM](../app/models.py), [esquemas Pydantic](../app/schemas.py), [autenticación](../app/security.py), [Storage](../app/storage.py), [configuración](../app/config.py), [sesiones de BD](../app/db.py), las migraciones [001](../migrations/001_sprint1.sql) y [002](../migrations/002_sprint2_3_estructura.sql), las pruebas y las guías existentes. Las 15 operaciones de negocio documentadas se contrastaron con el OpenAPI generado por la aplicación local.

- Las rutas son relativas a la URL configurada de FastAPI. `/docs`, `/redoc` y `/openapi.json` son recursos automáticos de documentación, no operaciones adicionales de negocio.
- JSON utiliza los nombres reales en inglés y `snake_case`. Los identificadores se serializan como UUID y las fechas como cadenas ISO 8601.
- Los ejemplos de UUID, textos, fechas, coordenadas y recursos de este documento son **ficticios**. No describen reportes reales ni puntos municipales oficiales.
- Ningún ejemplo contiene cuentas, contraseñas, JWT, claves, URLs firmadas reales ni valores extraídos de `.env`.
- Las respuestas de listados son arrays directos. No existe envoltorio `items`, contador `total` ni enlaces automáticos de paginación.
- No existen endpoints de eliminación ni CRUD completo de todos los recursos. Solo se documentan las operaciones presentes en `app/main.py`.

La revisión empezó con un cambio local pendiente en `frontend/.env.example`, que se conserva sin sobrescribirlo. La documentación inicial añadió este archivo; la corrección de descripción se limitó a `app/schemas.py`, `tests/test_api.py` y este documento. La tarea de autenticación añadió `tests/test_security.py`. La verificación PostgreSQL/persistencia añade cinco archivos de pruebas y soporte, descritos en la sección 6.6, y actualiza este documento. Se preservan los cambios locales anteriores. Los artefactos locales de pruebas quedan fuera de Git.

La implementación autorizada de concurrencia modifica backend y pruebas, añade la migración 003 y su reversión, según la sección 6.8. **No se aplicó 003 en Supabase compartido. El backend nuevo requiere un despliegue coordinado con 003; no debe iniciarse contra la configuración compartida anterior mientras esa revisión esté pendiente.**

## 2. Autenticación, roles y acceso

### 2.1. Flujo React → Supabase Auth → FastAPI

1. React inicia sesión con una cuenta existente mediante `supabase.auth.signInWithPassword`. La autenticación y el registro de cuentas corresponden a Supabase Auth; FastAPI no implementa `/login`, `/register` ni un emisor de tokens propio.
2. El SDK obtiene la sesión y su `access_token`. El frontend actual conserva/renueva la sesión y recupera el token vigente antes de las peticiones protegidas.
3. React envía el token como **Bearer en la cabecera `Authorization`**. Las contraseñas no se envían a FastAPI. El cliente utiliza `credentials: 'omit'`; no depende de cookies para autenticar la API.
4. FastAPI valida el JWT y consulta el perfil en PostgreSQL. React obtiene la identidad y el rol efectivo mediante `GET /me` antes de habilitar las operaciones de la cuenta.
5. El backend decide los permisos en cada petición. Ocultar botones en React no sustituye esas comprobaciones.

El cliente de negocio usa FastAPI para reportes, recursos y fotos. No accede directamente a las tablas mediante la API pública de Supabase. La configuración pública del frontend contiene únicamente URL del proyecto, clave publishable y URL de FastAPI; la conexión PostgreSQL y las credenciales privadas de Storage permanecen en el servidor.

### 2.2. Validación real de JWT

`app/security.py` obtiene claves de la ruta pública de Supabase **`/auth/v1/.well-known/jwks.json`**, construida a partir de la URL del proyecto del servidor. `PyJWKClient` mantiene caché del conjunto de claves durante 300 segundos.

La decodificación permite exclusivamente **RS256 y ES256**, verifica la firma y exige las claims `sub`, `exp`, `iss` y `aud`. Comprueba:

- Emisor igual a la URL del proyecto más `/auth/v1`.
- Audiencia `authenticated`.
- Token no vencido.
- `sub` convertible a UUID.
- Existencia de `profiles.id` para ese UUID.

El rol de negocio se lee de **`profiles.role`**. No se toma de una selección enviada por React, de `user_metadata`, de una cabecera inventada ni del rol general `authenticated` del JWT. Los JWT HS256 heredados no están admitidos por esta implementación.

### 2.3. Roles y matriz de permisos

| Operación | `ciudadano` | `encargado_municipal` | `chofer` |
| --- | --- | --- | --- |
| `GET /health` | Público | Público | Público |
| `GET /me` | Su perfil | Su perfil | Su perfil |
| `POST /reports` | Sí | 403 | 403 |
| `GET /reports/mine` | Sus reportes | 403 | 403 |
| `GET /reports/{report_id}` | Solo sus reportes; otro autor → 404 | Cualquier reporte existente | 404 |
| `GET /reports/{report_id}/photos` | Solo sus reportes; otro autor → 404 | Cualquier reporte existente | 404 |
| `POST /reports/{report_id}/photos` | Solo sus reportes; otro autor → 404 | 403 | 403 |
| Todas las operaciones `/municipal/*` documentadas | 403 | Sí | 403 |

La ausencia del reporte también produce 404. Se usa 404 en detalle/fotos para no confirmar al ciudadano ajeno o al chofer que un reporte existe. En el Sprint 1 el chofer puede consultar `/me`, pero no tiene endpoints operativos propios de rutas o atención.

**Registro público:** el trigger de la migración 001 crea cada perfil nuevo como `ciudadano`, independientemente del metadata del registro. La migración también crea perfiles ciudadanos para usuarios previos que aún no tengan perfil, sin cambiar roles ya asignados.

**Roles privilegiados:** un administrador autorizado debe verificar la identidad y asignar `encargado_municipal` o `chofer` mediante el procedimiento administrativo controlado del proyecto, por ejemplo SQL Editor. No hay una API pública de promoción, selector público de privilegios ni actualización de roles desde este frontend. La creación de cuentas mediante Auth no implica privilegios municipales.

### 2.4. Errores comunes y CORS

| HTTP | Significado implementado |
| --- | --- |
| 401 | Falta el Bearer o el token es inválido/vencido según las comprobaciones de autenticación |
| 403 | No hay perfil habilitado o el rol no permite la operación |
| 404 | Recurso inexistente, o reporte fuera del alcance del solicitante |
| 409 | Conflicto de recurso/horario o máximo de fotos; se especifica por endpoint |
| 413 | Imagen superior a 5 MiB |
| 415 | Firma de archivo no admitida |
| 422 | Error de Pydantic, UUID/query/body inválido o una validación de negocio que lo devuelve explícitamente |
| 502 | El servidor no pudo guardar la imagen u obtener su URL temporal desde Storage |
| 503 | Falta configuración de Storage, falla preparar/persistir/confirmar una fotografía, o no se puede confirmar una reserva tras un fallo de BD/agotamiento de reintentos |

Las rutas de negocio devuelven también 503 si el proceso no completó su guardia de arranque o si una comprobación `/ready` detectó incompatibilidad/indisponibilidad. Un fallo de guardia durante el arranque normal aborta el lifespan: no se inicia un servicio disponible para negocio. `/health` sigue siendo liveness y conserva su contrato; `/ready` es una comprobación interna independiente, descrita en 6.10.

Los `HTTPException` de la aplicación devuelven `{"detail": "mensaje"}`. Los 422 de validación de FastAPI pueden devolver `detail` como array con `loc`, `msg` y `type`. Un 422 de negocio puede usar `detail` de texto. No todos los fallos de infraestructura tienen un contrato JSON propio: no hay un manejador general de errores de BD en `app/main.py`; una excepción no controlada puede terminar en 500.

CORS toma los orígenes de `CORS_ORIGINS` en el arranque. El valor predeterminado del **código** es `http://localhost:5173`. Se autorizan GET, POST y PATCH, cabeceras `Authorization` y `Content-Type`, con `allow_credentials=False`. El middleware atiende los preflights OPTIONS. `localhost` y `127.0.0.1` son orígenes distintos. Un origen no autorizado recibe preflight 400 sin `Access-Control-Allow-Origin`; CORS no sustituye la autenticación y los clientes fuera del navegador también requieren JWT.

## 3. Esquemas de entrada y salida

Los ejemplos de los endpoints siguientes utilizan estos modelos reales. Los campos de salida indicados no se deben enviar para intentar asignar autor, rol, estado o auditoría.

| Modelo de salida | Campos |
| --- | --- |
| `ActorOut` | `id: UUID`, `role: ciudadano / encargado_municipal / chofer` |
| `ReportOut` | `id: UUID`, `citizen_id: UUID`, `description: string`, `latitude: number`, `longitude: number`, `observed_at: datetime`, `created_at: datetime`, `waste_type: string o null`, `status: string` |
| `PhotoOut` | `id: UUID`, `report_id: UUID`, `content_type: string`, `size_bytes: integer`, `created_at: datetime`, `signed_url: string o null` |
| `VehicleOut` | `id: UUID`, `label: string`, `vehicle_type: string`, `plate: string o null`, `capacity_kg: number o null`, `available: boolean` |
| `SiteOut` | `id: UUID`, `name: string`, `site_type: string`, `latitude: number`, `longitude: number`, `active: boolean` |
| `ShiftOut` | `id: UUID`, `vehicle_id: UUID`, `driver_id: UUID`, `departure_site_id: UUID`, `disposal_site_id: UUID`, `starts_at: datetime`, `ends_at: datetime`, `status: string`, `created_by: UUID` |

`created_at` existe en BD para vehículos y turnos, pero no se incluye en sus respuestas Pydantic actuales. `storage_path` existe en BD para fotos y tampoco se expone en `PhotoOut`.

### Entradas y validaciones Pydantic

| Modelo | Campos obligatorios | Opcionales y reglas |
| --- | --- | --- |
| `ReportCreate` | `description`, `latitude`, `longitude`, `observed_at` | Descripción: primero se recortan los espacios exteriores y después se valida longitud de 3–2000 caracteres; no puede quedar vacía. Los espacios interiores se conservan. Latitud −90..90, longitud −180..180. Observación con zona horaria, como máximo cinco minutos en el futuro. `waste_type`: null por defecto, hasta 80 caracteres, sin enumeración de tipos impuesta por la API. |
| `VehicleCreate` | `label`, `vehicle_type` | `label`: 2–100 caracteres. Tipo: `compactadora`, `volquete`, `camion_baranda` u `otro`. `plate`: null por defecto, hasta 20 caracteres. `capacity_kg`: null por defecto o número mayor que cero. `available`: false por defecto. |
| `AvailabilityPatch` | `available` | Booleano; no permite actualizar los demás datos del vehículo. |
| `SiteCreate` | `name`, `site_type`, `latitude`, `longitude` | Nombre: 2–120 caracteres. Tipo: `salida`, `descarga` o `ambos`. Coordenadas en los mismos límites globales de los reportes. |
| `ShiftCreate` | `vehicle_id`, `driver_id`, `departure_site_id`, `disposal_site_id`, `starts_at`, `ends_at` | IDs UUID. Inicio y fin con zona horaria; fin estrictamente posterior al inicio. No hay restricción adicional de fecha futura/pasada en este esquema. |

**Validación corregida:** `ReportCreate.description` usa un `field_validator` con `mode="before"` para recortar antes de los límites `min_length=3` y `max_length=2000`. `" a "` y `" ab "` devuelven HTTP 422; una descripción de 2000 caracteres rodeada de espacios devuelve 201 y conserva solo el texto recortado. Los valores null o numéricos siguen rechazándose con 422. La estructura JSON, los nombres/tipos de campo y los límites publicados del contrato se mantienen; no se cambian las migraciones. La evidencia HTTP se registra en la sección 6.4.

## 4. Catálogo de los 15 endpoints implementados

Los errores comunes 401/403 se aplican a las rutas protegidas según la matriz anterior. Los códigos que se detallan aquí se obtienen de las dependencias y handlers; OpenAPI no enumera automáticamente todos los errores de negocio.

### GET /health

- **Finalidad y rol:** comprobar el proceso de API; público.
- **Parámetros/cuerpo:** ninguno.
- **Respuesta:** 200, `{"status": "ok", "version": "0.1.0"}`.
- **Errores y límite:** no define errores de negocio propios. No consulta PostgreSQL, Supabase Auth, JWKS ni Storage; un 200 no prueba esos servicios.

### GET /me

- **Finalidad y rol:** consultar identidad y rol efectivo; cualquier cuenta autenticada con perfil.
- **Parámetros/cuerpo:** ninguno; Bearer obligatorio.
- **Respuesta:** 200, `ActorOut`.
- **Errores:** 401 por autenticación; 403 `Usuario sin perfil habilitado`.

```json
{
  "id": "00000000-0000-4000-8000-000000000001",
  "role": "ciudadano"
}
```

### POST /reports

- **Finalidad y rol:** registrar una observación ciudadana; solo `ciudadano`.
- **Parámetros:** ninguno.
- **Cuerpo:** JSON `ReportCreate`. `observed_at` es obligatorio aunque la ubicación provenga de GPS/mapa.

```json
{
  "description": "Ejemplo ficticio: bolsas acumuladas cerca de una esquina",
  "latitude": -12.065,
  "longitude": -75.21,
  "observed_at": "2026-10-26T10:30:00-05:00",
  "waste_type": "mixto"
}
```

- **Respuesta:** 201, `ReportOut`. El autor se toma del JWT/perfil; el estado inicial es `recibido`. El servidor genera ID y fecha de recepción.

```json
{
  "id": "00000000-0000-4000-8000-000000000101",
  "citizen_id": "00000000-0000-4000-8000-000000000001",
  "description": "Ejemplo ficticio: bolsas acumuladas cerca de una esquina",
  "latitude": -12.065,
  "longitude": -75.21,
  "observed_at": "2026-10-26T15:30:00Z",
  "created_at": "2026-10-26T15:31:00Z",
  "waste_type": "mixto",
  "status": "recibido"
}
```

- **Errores:** 401; 403 si no es ciudadano; 422 por cuerpo, fecha, coordenadas o longitud de descripción inválidos. La longitud se valida después de recortar los espacios exteriores, antes de persistir el reporte.

### GET /reports/mine

- **Finalidad y rol:** consultar reportes del ciudadano autenticado; solo `ciudadano`.
- **Query:** `limit` entero, predeterminado 50, entre 1 y 100; `offset` entero, predeterminado 0, mínimo 0. No recibe `citizen_id` ni selecciona a otro autor.
- **Cuerpo:** ninguno.
- **Respuesta:** 200, array `ReportOut[]`, vacío si no hay coincidencias. Orden por `created_at DESC, id DESC`.
- **Ejemplo de ruta:** `/reports/mine?limit=50&offset=0`.
- **Errores:** 401, 403 por rol y 422 por paginación inválida.

### GET /reports/{report_id}

- **Finalidad y rol:** recuperar un reporte concreto; ciudadano autor o encargado municipal.
- **Path:** `report_id`, UUID obligatorio. Sin query ni cuerpo.
- **Respuesta:** 200, `ReportOut`, con la misma estructura del ejemplo de creación.
- **Errores:** 401/403 de autenticación/perfil; 404 si no existe, pertenece a otro ciudadano o el solicitante es chofer; 422 si el identificador no es UUID válido.

### POST /reports/{report_id}/photos

- **Finalidad y rol:** añadir una fotografía privada; ciudadano autor del reporte.
- **Path:** `report_id`, UUID obligatorio.
- **Cuerpo:** **`multipart/form-data`**, campo binario obligatorio **`file`**. No es un cuerpo JSON ni un envío base64. El navegador debe generar el boundary de FormData.
- **Reglas:** JPG, PNG o WebP detectados por firma básica de bytes, máximo **5 MiB = 5 242 880 bytes** y máximo **3 fotos por reporte**. No basta con declarar un MIME permitido en la petición.
- **Respuesta:** 201, `PhotoOut`. Después de subir, `signed_url` es null; se consulta el GET de fotos para obtener un enlace de lectura.

```json
{
  "id": "00000000-0000-4000-8000-000000000102",
  "report_id": "00000000-0000-4000-8000-000000000101",
  "content_type": "image/png",
  "size_bytes": 1024,
  "created_at": "2026-10-26T15:32:00Z",
  "signed_url": null
}
```

- **Errores:** 401; 403 para encargado/chofer; 404 si el reporte no existe o pertenece a otro ciudadano; 409 `Máximo 3 imágenes por reporte`; 413 `La imagen supera 5 MB`; 415 `Formato inválido: JPG, PNG o WebP`; 422 por UUID/archivo obligatorio; 502 al guardar en Storage; 503 por configuración ausente o persistencia/confirmación de BD. Si la confirmación es incierta, consultar las fotos antes de reintentar; no se promete que un 503 implique que el commit no ocurrió.
- **Alcance:** firmas básicas, sin decodificación completa. El máximo de tres se protege mediante posiciones únicas SQL y bloqueo por reporte con 003. Storage/BD siguen siendo servicios distintos; la compensación y recuperación son eventuales (6.8), sin fingir una transacción distribuida.

### GET /reports/{report_id}/photos

- **Finalidad y rol:** consultar fotos con acceso temporal; ciudadano autor o encargado municipal.
- **Path:** `report_id`, UUID obligatorio. Sin query ni cuerpo.
- **Respuesta:** 200, array `PhotoOut[]`. Para las fotos existentes se agrega `signed_url` firmado por **300 segundos**. Si no hay fotos, devuelve `[]`. El orden no está especificado.
- **Errores:** 401/403 de autenticación/perfil; 404 por reporte inexistente o fuera de alcance, incluido chofer; 422 por UUID inválido; 502 al obtener el enlace; 503 si se requiere Storage y falta configuración.
- **Uso:** React puede mostrar la URL temporal en una imagen y renovar los enlaces repitiendo este GET. La URL permite leer a quien la posea durante su vigencia; no debe publicarse ni registrarse como si fuera una dirección pública permanente.

### GET /municipal/reports

- **Finalidad y rol:** listado/mapa municipal; solo `encargado_municipal`.
- **Query opcional:**

| Parámetro | Tipo, valor predeterminado y regla |
| --- | --- |
| `status` | String, omitido por defecto; filtra por igualdad exacta. El parámetro no está restringido por `Literal`: un estado desconocido normalmente da 200 con lista vacía, no 422. Omitirlo para no filtrar. |
| `north`, `south` | Números entre −90 y 90 |
| `west`, `east` | Números entre −180 y 180 |
| `limit` | Entero, 100 por defecto, entre 1 y 200 |
| `offset` | Entero, 0 por defecto, mínimo 0 |

Si se incluye cualquier límite geográfico se requieren los cuatro: `north >= south` y `east >= west`. Los extremos son inclusivos. No admite una caja que cruce el antimeridiano con `east < west`. No hay un perímetro distrital adicional implementado.

- **Cuerpo:** ninguno.
- **Respuesta:** 200, array `ReportOut[]`; orden `created_at DESC, id DESC`. Incluye coordenadas numéricas para el mapa. Se devuelve la página solicitada, sin total.
- **Ejemplo:** `/municipal/reports?status=recibido&north=-12&south=-13&west=-76&east=-75&limit=50&offset=0`.
- **Errores:** 401; 403 por rol; 422 por tipo/rango/paginación o `Límites inválidos: north, south, west y east`.

### GET /municipal/vehicles

- **Finalidad y rol:** consultar recursos vehiculares; solo `encargado_municipal`.
- **Parámetros/cuerpo:** ninguno; no tiene filtros ni paginación.
- **Respuesta:** 200, array `VehicleOut[]`, ordenado por `label` ascendente. Incluye vehículos disponibles y no disponibles.
- **Errores:** 401 y 403. No define un 404 por lista vacía: devuelve `[]`.

### POST /municipal/vehicles

- **Finalidad y rol:** registrar un vehículo; solo `encargado_municipal`.
- **Parámetros:** ninguno.
- **Cuerpo:** JSON `VehicleCreate`.

```json
{
  "label": "Unidad ficticia de documentación",
  "vehicle_type": "compactadora",
  "plate": null,
  "capacity_kg": null,
  "available": false
}
```

- **Respuesta:** 201, `VehicleOut`.

```json
{
  "id": "00000000-0000-4000-8000-000000000201",
  "label": "Unidad ficticia de documentación",
  "vehicle_type": "compactadora",
  "plate": null,
  "capacity_kg": null,
  "available": false
}
```

- **Errores:** 401, 403, 422 por esquema y 409 `Identificador de vehículo duplicado` cuando se captura una infracción de integridad. La restricción única documentada es **`label`**, no `plate`; no se afirma que las placas sean únicas.
- **Uso:** capacidad desconocida permanece null. No se inventa capacidad para completar la ficha.

### PATCH /municipal/vehicles/{vehicle_id}/availability

- **Finalidad y rol:** cambiar disponibilidad; solo `encargado_municipal`.
- **Path:** `vehicle_id`, UUID obligatorio.
- **Cuerpo:** JSON `AvailabilityPatch`.

```json
{"available": true}
```

- **Respuesta:** 200, `VehicleOut` completo con la disponibilidad actualizada.
- **Errores:** 401, 403, 404 `Vehículo no encontrado` y 422 por UUID o cuerpo inválido.
- **Alcance:** cambia solo `available`; no cancela ni reprograma automáticamente turnos existentes.

### GET /municipal/sites

- **Finalidad y rol:** consultar puntos de salida/descarga; solo `encargado_municipal`.
- **Parámetros/cuerpo:** ninguno; no tiene filtros ni paginación.
- **Respuesta:** 200, array `SiteOut[]`, ordenado por `name` ascendente. No filtra por `active`.
- **Errores:** 401 y 403. Una lista sin registros devuelve `[]`.

### POST /municipal/sites

- **Finalidad y rol:** registrar un punto de salida, descarga o ambos; solo `encargado_municipal`.
- **Parámetros:** ninguno.
- **Cuerpo:** JSON `SiteCreate`.

```json
{
  "name": "Salida ficticia de documentación",
  "site_type": "salida",
  "latitude": -12.01,
  "longitude": -75.02
}
```

- **Respuesta:** 201, `SiteOut`. ID y `active: true` se asignan en el servidor.

```json
{
  "id": "00000000-0000-4000-8000-000000000301",
  "name": "Salida ficticia de documentación",
  "site_type": "salida",
  "latitude": -12.01,
  "longitude": -75.02,
  "active": true
}
```

- **Errores:** 401, 403 y 422 por nombre, tipo o coordenadas inválidas. No existe restricción única de nombre ni un 409 de duplicado definido para este endpoint.
- **Alcance:** no hay endpoint de edición, desactivación o eliminación de sitios en esta versión.

### GET /municipal/shifts

- **Finalidad y rol:** recuperar turnos; solo `encargado_municipal`.
- **Parámetros/cuerpo:** ninguno.
- **Respuesta:** 200, array `ShiftOut[]`, orden `starts_at DESC`, limitado a **100 registros**. No tiene query de paginación ni filtro de estado/chofer; puede incluir distintos estados existentes en BD.
- **Errores:** 401 y 403. Una lista vacía devuelve `[]`.

### POST /municipal/shifts

- **Finalidad y rol:** programar un turno; solo `encargado_municipal`.
- **Parámetros:** ninguno.
- **Cuerpo:** JSON `ShiftCreate`.

```json
{
  "vehicle_id": "00000000-0000-4000-8000-000000000201",
  "driver_id": "00000000-0000-4000-8000-000000000003",
  "departure_site_id": "00000000-0000-4000-8000-000000000301",
  "disposal_site_id": "00000000-0000-4000-8000-000000000302",
  "starts_at": "2026-11-02T08:00:00-05:00",
  "ends_at": "2026-11-02T12:00:00-05:00"
}
```

Para ejecutar una petición deben utilizarse UUID reales ya existentes y autorizados. Los del ejemplo no crean por sí mismos un chofer, un vehículo ni sitios.

- **Validación de negocio:** vehículo existente y `available=true`; perfil del chofer existente con rol `chofer`; salida activa con tipo `salida`/`ambos`; descarga activa con tipo `descarga`/`ambos`.
- **Solapamiento:** se busca otro turno `programado` con el mismo vehículo **o** chofer y condición `existing.starts_at < new.ends_at` y `existing.ends_at > new.starts_at`. Turnos contiguos cuyo fin coincide con el siguiente inicio no se solapan según esta regla. Turnos cancelados/finalizados no se incluyen en la búsqueda.
- **Respuesta:** 201, `ShiftOut`; estado inicial `programado`, `created_by` igual al encargado autenticado.

```json
{
  "id": "00000000-0000-4000-8000-000000000401",
  "vehicle_id": "00000000-0000-4000-8000-000000000201",
  "driver_id": "00000000-0000-4000-8000-000000000003",
  "departure_site_id": "00000000-0000-4000-8000-000000000301",
  "disposal_site_id": "00000000-0000-4000-8000-000000000302",
  "starts_at": "2026-11-02T13:00:00Z",
  "ends_at": "2026-11-02T17:00:00Z",
  "status": "programado",
  "created_by": "00000000-0000-4000-8000-000000000002"
}
```

- **Errores:** 401, 403, 422 por esquema o por `El vehículo no existe o no está disponible`, `Chofer no válido`, `Punto de salida no válido`, `Punto de descarga no válido`; 409 `Vehículo o chofer ya reservado en ese horario`; 503 si no se puede confirmar el turno tras un fallo transaccional. Ante 503 consultar turnos antes de reintentar.
- **Concurrencia:** con 003 aplicada, dos exclusiones PostgreSQL protegen vehículo y chofer. La consulta previa sigue dando errores tempranos; la garantía la aporta la BD. Se reintentan como máximo tres intentos ante abortos conocidos 40001/40P01, sin reintentar automáticamente un commit incierto. No hay endpoint de cancelación, edición o finalización de turnos en este Sprint.

## 5. PostgreSQL, relaciones y persistencia

### 5.1. Alcance de las migraciones y del ORM

La migración 001 define **nueve tablas de negocio**. El ORM representa seis de ellas: `profiles`, `reports`, `report_photos`, `vehicles`, `service_sites` y `shifts`. La migración 003 añade `photo_upload_operations`, séptimo modelo ORM y registro interno sin endpoint público. `events`, `event_reports` y `grouping_decisions` no tienen modelos operativos ni endpoints en este backend.

La migración 002 prepara tres tablas futuras; no se modificó ni ejecutó en esta tarea. El esquema compartido de 001 se inspeccionó anteriormente (6.6). En esta implementación se ejecutaron únicamente **001 y 003 en contenedores PostgreSQL desechables**, además de la reversión de 003 en bases aisladas. No se ejecutaron migraciones sobre Supabase compartido.

Las restricciones de 001 se contrastaron con `pg_constraint` en PostgreSQL 17.11 (6.6); las de 003 se probaron en PostgreSQL 17.11 aislado (6.8). `CREATE TABLE IF NOT EXISTS` no actualiza tablas preexistentes. El ORM incorpora CHECK/UNIQUE de posiciones de foto, pero no todas las restricciones PostgreSQL, exclusiones, RLS o permisos: crear tablas en SQLite no demuestra esas garantías.

### 5.2. Tablas de Sprint 1: migraciones 001 y 003

| Tabla | Relaciones y datos | Restricciones y valores relevantes |
| --- | --- | --- |
| `profiles` | `id` es PK y FK a `auth.users.id`. Guarda `role` y `created_at`. Un usuario tiene como máximo un perfil. | Rol no nulo, por defecto `ciudadano`; CHECK de los tres roles. Al borrar el usuario se solicita cascada al perfil; las demás referencias de negocio pueden impedir eliminar datos relacionados. |
| `reports` | PK UUID; `citizen_id` referencia `profiles`. Una cuenta ciudadana puede tener muchos reportes. Guarda descripción, ubicación, observación, recepción, tipo y estado. | Descripción recortada de 3–2000 caracteres en SQL; límites globales de coordenadas; observación/recepción `timestamptz`; recepción por defecto `now()`. Estado: `recibido`, `en_revision`, `programado`, `atendido`, `descartado`; inicial `recibido`. Tipo de residuo nullable, hasta 80 caracteres. |
| `report_photos` | PK UUID; FK `report_id` con cascada de **metadatos**; ruta, MIME, tamaño, fecha y posición interna `slot` de 003. | Ruta única, MIME JPG/PNG/WebP y tamaño 1–5 242 880 bytes. Con 003: slot NOT NULL, CHECK 1–3 y UNIQUE `(report_id,slot)` garantizan máximo tres. |
| `vehicles` | PK UUID; etiqueta, tipo, placa, capacidad y disponibilidad. Se referencia desde turnos. | `label` único; tipos permitidos según `VehicleCreate`; placa nullable sin UNIQUE; disponibilidad false por defecto; capacidad nullable o mayor que cero. |
| `service_sites` | PK UUID; nombre, tipo, coordenadas y actividad. Puede usarse como salida y/o descarga. | Tipo `salida`, `descarga`, `ambos`; límites globales de coordenadas; `active=true` por defecto. Nombre no único. |
| `shifts` | PK UUID; FKs a vehículo, chofer, sitios y creador; intervalo, estado y fecha. | `ends_at > starts_at`; estados `programado`, `cancelado`, `finalizado`. Con 003: exclusiones GiST independientes por vehículo/chofer y rango `[inicio,fin)` para estado `programado`. |
| `photo_upload_operations` | Nueva tabla interna de 003; PK UUID, FKs de autor/reporte, bucket/ruta, extensión, estado, intentos y fechas de reintento. | Ruta única y CHECK que la vincula exactamente a sus UUID/extensión; estados limitados, intentos ≥0; RLS habilitado y REVOKE a PUBLIC/anon/authenticated. No contiene credenciales ni bytes. |
| `events` | PK UUID; ubicación representativa, estado, intervención, prioridad/factores/versionado, creación y cierre. Puede reunir varios reportes. | Coordenadas globales; estado `en_revision`, `abierto`, `programado`, `atendido`, `cerrado`, `descartado`. Inicial `en_revision`; si el estado es `cerrado`, `closed_at` debe existir. Sin endpoints actuales. |
| `event_reports` | `report_id` es PK y FK a `reports`; `event_id` referencia `events`. Incluye actor, fecha, método y factores de vinculación. | Cada reporte tiene como máximo **una relación vigente** en esta tabla. Un evento puede tener varias. Método `automatica` o `manual`; actor opcional. Mover una relación requiere diseñar la auditoría correspondiente. Sin endpoints actuales. |
| `grouping_decisions` | PK UUID; reporte, evento candidato, evento resultante y actor referenciados; factores, configuración, fecha y notas. Guarda historial de decisiones de agrupación. | Decisión `agrupar`, `separar`, `revisar`, `mantener_separado`; factores JSONB no nulos con objeto vacío por defecto. No se escribe automáticamente desde el prototipo D3 ni tiene endpoints actuales. |

Las FKs a perfiles garantizan existencia, pero no expresan por sí solas que un perfil sea ciudadano, encargado o chofer. La autorización de autor y creador y la validación del rol del chofer se realizan en FastAPI. Del mismo modo, las FKs de sitios no garantizan que un sitio sea salida/descarga activa: ese control se hace al crear el turno.

Los índices definidos cubren consultas por autor/recepción, estado/recepción y coordenadas de reportes, fotos por reporte, turnos por vehículo/intervalo y chofer/intervalo, vínculos por evento y decisiones por reporte/fecha. No se utiliza PostGIS en esta estructura.

### 5.3. Fotografías y bucket privado

Los bytes se almacenan en **Supabase Storage**, no en una columna binaria de PostgreSQL. La tabla `report_photos` conserva metadatos y la ruta privada. La ruta generada sigue el patrón `reports/{autor_uuid}/{reporte_uuid}/{foto_uuid}.{extensión_detectada}`; no se utiliza el nombre enviado por el cliente para decidir la ruta.

La migración define el bucket privado `reciwise-reportes`, con límite de 5 MiB y MIME admitidos. La aplicación utiliza la variable de servidor `STORAGE_BUCKET`, cuyo valor predeterminado en código coincide con ese nombre. El bucket configurado y el creado deben coincidir; este documento no revela la configuración efectiva del entorno.

`app/storage.py` usa una credencial privada solo del servidor para subir el objeto y pedir URLs firmadas de 300 segundos. Contempla tanto el formato de credencial privada nuevo como el JWT de servicio heredado al construir las cabeceras de servidor. Esa credencial nunca reemplaza el JWT del ciudadano/encargado en las peticiones de React a FastAPI.

La autorización ocurre antes del acceso a Storage. El bucket no se hace público para mostrar una imagen. Una cascada SQL de metadatos no elimina automáticamente el objeto de Storage; no hay endpoint de borrado/limpieza de objetos en esta versión.

### 5.4. RLS y puerta de acceso a datos

Las migraciones habilitan RLS para las tablas de negocio y revocan permisos a `anon` y `authenticated`; no crean políticas de acceso directo para que React consulte esas tablas. El backend utiliza una conexión PostgreSQL de servidor con las facultades necesarias. La protección de sus rutas se aplica mediante validación JWT, consulta de perfil, filtros de autor y dependencias de rol.

Esto no convierte la credencial de servidor en una credencial de frontend ni demuestra por sí solo que un proyecto remoto conserve esas políticas. Verificar el despliegue efectivo y proteger esa conexión forman parte de la aceptación del entorno real.

### 5.5. Estructuras reservadas: migración 002

| Tabla | Relaciones y datos preparados | Restricciones existentes en SQL | Estado funcional |
| --- | --- | --- | --- |
| `route_plans` | FK a turno y perfiles creador/aprobador. Versiones de algoritmo, fuente de matriz, snapshot/configuración JSONB, distancias, duración, geometría, excluidos y limitaciones. | Estado `propuesta`, `aprobada`, `en_ejecucion`, `finalizada`, `cancelada`; distancias/duración no negativas cuando existen. Aprobador y fecha de aprobación deben ser ambos null o ambos no null. Índice único por turno cuando el estado está en `aprobada`, `en_ejecucion`, `finalizada`. | Estructura futura; no hay generación, aprobación ni consulta de rutas mediante endpoints. |
| `route_stops` | FK a plan con cascada y FK a evento. Orden de visita, servicio estimado, estado, visita y actor. | Orden mayor que cero; servicio estimado positivo si existe; unicidad de evento y orden dentro del plan. Estado `pendiente`, `atendida`, `incidencia`, `no_atendida`. | Estructura futura; no hay endpoints de ejecución o cierre de paradas. |
| `stop_incidents` | FK a parada y perfil informante; tipo, descripción, ruta de evidencia y fecha. | Identificadores y tipo obligatorios según SQL. | Estructura futura; no hay endpoints de incidencias operativas. |

También se habilita RLS y se revocan permisos directos a `anon`/`authenticated` para estas tres tablas. Estos campos y CHECK no equivalen a un flujo de aprobación y ejecución implementado.

### 5.6. Reporte, evento y parada son entidades distintas

- **Reporte:** observación enviada por un ciudadano, con autor, descripción, ubicación, fechas y fotos. Registrar un reporte no crea un evento ni una ruta automáticamente.
- **Evento:** acumulación o intervención candidata que puede reunir varios reportes tras una decisión revisada y auditable. Su ubicación/estado no tienen que ser una copia automática del último reporte.
- **Parada:** visita planificada a un evento dentro de una ruta y turno, con un orden y resultado operativo. No representa una observación ciudadana nueva.

Agrupar reportes no significa atenderlos. El estado de atención no se debe dar por resuelto al calcular similitud, proponer un grupo o crear una ruta.

## 6. Evidencia de pruebas

### 6.1. Pruebas manuales comunicadas por el responsable D2

Fuente: resultados confirmados por el usuario en el encargo de esta documentación, recibido el 29 de octubre de 2026. La fecha exacta de ejecución de cada prueba y los registros HTTP no fueron adjuntados. Se registran como **pruebas manuales comunicadas**, sin afirmar que Codex las haya vuelto a ejecutar ni publicar sus credenciales o datos.

| ID | Prueba manual comunicada | Resultado comunicado |
| --- | --- | --- |
| M01 | Registro y autenticación con Supabase | Correctos |
| M02 | Verificación de roles ciudadano, encargado municipal y chofer | Los tres roles verificados |
| M03 | Validación de JWT ES256 | Correcta |
| M04 | Creación de reportes mediante POST | Correcta |
| M05 | Consulta de reportes mediante GET | Correcta |
| M06 | Acceso municipal a reportes y coordenadas | Correcto |
| M07 | Subida y visualización de fotos privadas | Correctas |
| M08 | Consulta de vehículos | Correcta |
| M09 | Registro y consulta de puntos de salida/descarga | Correctos |
| M10 | Creación y recuperación de un turno programado | Correctas |
| M11 | Intentar programar con vehículo no disponible | HTTP 422 |
| M12 | Intentar reservar vehículo o chofer en horario ocupado | HTTP 409 |
| M13 | Ciudadano consultando vehículos, sitios y turnos municipales | HTTP 403 |

Estas evidencias actualizan los estados antiguos de guías que indicaban que toda integración con Supabase seguía sin probar. No se convierten en tests automatizados ni demuestran por sí solas concurrencia, recuperación tras reinicio o todos los casos negativos de JWT.

### 6.2. Pruebas automatizadas ejecutadas por Codex para D2

En la documentación inicial se ejecutaron las **ocho pruebas existentes del backend**, sin modificar entonces su código. La ejecución tras corregir la descripción se registra en la sección 6.4; la ejecución con pruebas JWT/autorización en la sección 6.5; la ejecución actual con PostgreSQL/persistencia en la sección 6.6.

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_api.py tests/test_frontend_contract.py
```

Resultado del 29 de octubre de 2026: **8 aprobadas, 0 fallidas, 0 errores y 0 omitidas**. Duración comunicada por pytest: **0,40 s**. Una advertencia preexistente de deprecación de Starlette/httpx; no es un fallo de prueba ni se actualizaron dependencias para ocultarla.

Se generó además un informe JUnit local mediante `--junitxml`: `.test-artifacts/api-docs-3aa7af1aad2541a1ba6a893145e0148d/pytest-d2.xml`, excluido de Git. Sus contadores coinciden con el resultado anterior.

| Archivo y prueba | Alcance comprobado |
| --- | --- |
| `tests/test_api.py::test_health_and_profile` | Respuesta de salud y rol del actor sustituido en `/me` |
| `tests/test_api.py::test_report_visibility_and_permissions` | Creación 201, estado `recibido`, listado propio, aislamiento entre ciudadanos, reporte ajeno 404, ciudadano rechazado en listado municipal, chofer rechazado en creación/detalle, lectura municipal y filtros geográficos |
| `tests/test_api.py::test_invalid_report_date_and_coordinates` | 422 por latitud fuera de rango, observación sin zona horaria y observación demasiado futura |
| `tests/test_api.py::test_vehicle_and_shifts` | Alta de vehículo, etiqueta duplicada 409, alta de sitios, turno con vehículo no disponible 422, PATCH de disponibilidad 200, turno válido 201, solapamiento 409 y consulta de vehículos por ciudadano 403 |
| `tests/test_api.py::test_photo_mime_validation_before_storage` | Archivo de firma no admitida rechazado con 415 antes de Storage |
| `tests/test_api.py::test_no_auth_without_token` | `/me` devuelve 401 sin token, usando la dependencia real de autenticación para este caso |
| `tests/test_frontend_contract.py::test_vite_cors_preflight_and_actual_response` | Preflight GET/POST y multipart para el origen local previsto, respuesta CORS y rechazo de origen ajeno |
| `tests/test_frontend_contract.py::test_photo_upload_listing_limits_and_roles` | Multipart `file`, tres altas 201, lectura de URLs sustituidas, cuarta foto 409, ciudadano ajeno 404 y encargado con lectura 200/subida 403 |

**Límites de estas pruebas, también aplicables a la corrección de la sección 6.4:** `tests/conftest.py` utiliza SQLite en memoria, crea perfiles sintéticos y sustituye `get_db` y normalmente `get_current_actor`. Las funciones de subida/firma de Storage se sustituyen en la prueba de fotos. No se conectan a PostgreSQL/Supabase reales ni validan una firma ES256/RS256 válida contra JWKS. La prueba sin token sí usa el código real de rechazo por ausencia de credencial.

El ORM usado por SQLite no reproduce todos los CHECK, triggers, RLS, tipos y restricciones de las migraciones PostgreSQL. El aislamiento y los commits entre peticiones de una prueba no sustituyen una prueba de persistencia entre reinicios del servidor.

No se ejecutaron nuevas pruebas de frontend ni módulos D3 en esta tarea de documentación. Las cifras de 39 tests React, 6 pruebas Chrome y 31 pruebas Python de la [integración anterior](INTEGRACION_SPRINT1.md) pertenecen a esa ejecución previa y a un alcance distinto: 23 de las 31 pruebas Python son de datos/D3, no estas ocho de API D2.

### 6.3. Comprobaciones adicionales sin crear registros

- Se generó el OpenAPI local y se contrastaron las 15 combinaciones método/ruta con este catálogo. Esta operación no ejecuta INSERT ni consulta el proyecto remoto.
- En la revisión inicial se instanció localmente `ReportCreate` para reproducir el comportamiento anterior de la descripción recortada. No se intentó guardarlo en PostgreSQL; posteriormente se corrigió y cubrió por HTTP en la sección 6.4.
- Las pruebas de D2 crean únicamente las filas sintéticas necesarias en SQLite en memoria; no se crearon cuentas ni recursos nuevos en Supabase.
- La documentación inicial conservó el cambio local previo de `frontend/.env.example` y no modificó código. La corrección posterior modifica únicamente el validador de descripción, sus pruebas y este documento; no cambia claves, migraciones, políticas, frontend ni módulos de IA.

### 6.4. Corrección de longitud tras el recorte

El 29 de octubre de 2026 se añadieron 19 casos de regresión HTTP en `tests/test_api.py`. Antes de corregir el esquema se ejecutaron tres casos representativos: las descripciones recortadas a uno/dos caracteres se aceptaban incorrectamente con 201 y la de 2000 caracteres con espacios exteriores se rechazaba con 422. Los tres casos fallaron como se esperaba, reproduciendo el defecto sin acceder a PostgreSQL real.

Después de mover el recorte a un validador `before`, se ejecutó nuevamente la suite de D2:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_api.py tests/test_frontend_contract.py
```

**Resultado de esta corrección: 27 aprobadas, 0 fallidas, 0 errores y 0 omitidas**, en **0,68 s**. Son las ocho pruebas previas y 19 casos nuevos. Permanece una advertencia preexistente de deprecación de Starlette/httpx.

| Prueba nueva | Casos y resultado |
| --- | --- |
| `test_report_description_invalid_returns_422_without_persisting` | **12 casos:** vacío, solo espacios, tabulaciones/saltos exteriores, uno/dos caracteres, uno/dos tras recortar, dos tras recorte mixto, 2001 caracteres, 2001 con espacios exteriores, null y número. Todos devuelven **422**, con error localizado en `body.description`, y dejan el listado propio vacío. |
| `test_report_description_valid_is_trimmed_and_persisted` | **7 casos:** mínimo de 3, mínimo con espacios, descripción normal con espacios exteriores, recorte mixto, conservación de espacios interiores, máximo de 2000 y máximo con espacios exteriores. Todos devuelven **201**, conservan el autor/coordenadas/estado del contrato y se recuperan por GET con la descripción normalizada. |

`TestClient` mantiene su comportamiento de propagar excepciones internas: un fallo no controlado no se oculta. Además se exige explícitamente HTTP 422 en cada entrada inválida. No se obtuvieron respuestas 500 en esos casos. La falta de CHECK equivalentes de SQLite ya no permite aceptar el texto inválido, porque Pydantic lo rechaza antes de persistirlo.

Evidencia JUnit local: `.test-artifacts/description-validation-da9d9c72ff5947558f445f40e6e5df7d/pytest-d2.xml`, generada con `--junitxml` y excluida de Git. En esa ejecución no se utilizaron datos existentes del proyecto Supabase. Las pruebas negativas de JWT se registran en la sección 6.5 y la verificación posterior de persistencia tras reinicio en la sección 6.6.

### 6.5. Autenticación JWT y autorización: ejecución actual de D2

Se añadió `tests/test_security.py` con **69 casos**. A diferencia de las pruebas anteriores basadas en un actor sustituido, esta fixture retira el override de `get_current_actor`: se ejecutan realmente la extracción Bearer, el cliente `PyJWKClient`, la selección de `kid`, `jwt.decode`, la verificación criptográfica, las claims, la búsqueda del perfil y las dependencias de rol.

**Aislamiento:** se generan claves privadas efímeras EC P-256 y RSA de 2048 bits, exclusivamente para la ejecución. Sus claves públicas forman un JWKS ficticio; las privadas y los JWT no se guardan en archivos ni se toman de Supabase. Se sustituye solo la configuración del emisor por un dominio `.test`, el transporte HTTP del JWKS por JSON en memoria y la BD por SQLite. El transporte se intercepta tanto para `urlopen` como para el opener utilizado por la versión instalada de PyJWT. Se bloquean resolución DNS y conexiones TCP en esta fixture; cualquier intento inesperado de acceder a la red hace fallar la prueba. La caché del cliente JWKS se limpia al comenzar y terminar cada caso.

No se sustituyen la función de autenticación, la decodificación de JWT ni las comprobaciones de firma/claims. Las pruebas positivas ES256/RS256 demuestran que la fixture no rechaza indiscriminadamente todos los tokens. Los JWT vencidos o con issuer/audience incorrectos están firmados con una clave confiable de prueba; el de firma incorrecta usa un `kid` publicado y otra clave privada. El HS256 también usa un `kid` publicado, de modo que su rechazo no depende de que falte la clave.

| Escenario comprobado | Resultado |
| --- | --- |
| Solicitud a `/me` sin JWT | **401**, sin consultar JWKS |
| Cabecera de autorización incorrecta/vacía o JWT malformado | **401** |
| JWT vencido, con firma incorrecta, issuer incorrecto o audience incorrecta | **401**, comprobado con ES256 y RS256 |
| HS256, pese a indicar un `kid` publicado | **401**; se conservan exclusivamente ES256/RS256 en el backend |
| Ausencia de `sub`, `exp`, `iss` o `aud`, `sub` no UUID o `kid` desconocido | **401**, con ambos algoritmos asimétricos |
| `/me` con ciudadano, encargado o chofer y JWT ES256/RS256 válido | **200**, con el rol leído del perfil |
| Ciudadano autenticado en los ocho endpoints municipales GET/POST/PATCH | **403** en todos |
| Chofer autenticado en los mismos ocho endpoints | **403** en todos |
| Encargado autenticado en los ocho endpoints municipales | **200/201** según el contrato, comprobado con ES256 y RS256 |
| JWT válido cuyo usuario no tiene fila en `profiles` | **403**, `Usuario sin perfil habilitado`, con ambos algoritmos |
| Ciudadano cuyo JWT/metadata declara un rol municipal | `/me` conserva `ciudadano` y la petición municipal recibe **403** |

La matriz municipal incluye `GET /municipal/reports`, GET/POST de vehículos, PATCH de disponibilidad, GET/POST de sitios y GET/POST de turnos. Los cuerpos y referencias usados para comprobar autorización son válidos y sintéticos; las respuestas 403 no se confunden con un error de validación 422. La creación de recursos y turnos del encargado ocurre solo en la BD en memoria de cada prueba.

Comandos ejecutados:

```powershell
# Pruebas nuevas, por separado:
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_security.py --tb=short

# Suite completa de D2, incluyendo la corrección previa de descripciones:
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_api.py tests/test_frontend_contract.py tests/test_security.py
```

| Ejecución | Aprobadas | Fallidas | Errores | Omitidas | Tiempo de pytest |
| --- | --- | --- | --- | --- | --- |
| Nuevas pruebas JWT/permisos | **69** | **0** | **0** | **0** | **1,48 s** |
| Suite completa D2 | **96** | **0** | **0** | **0** | **1,96 s** |

El total de 96 se distribuye en **25** casos de `test_api.py`, **2** de `test_frontend_contract.py` y **69** de `test_security.py`. No incluye los módulos D3 ni pruebas de frontend, fuera del alcance de esta tarea. Se utilizó PyJWT **2.15.1** y cryptography **50.0.2**. Persiste una advertencia preexistente de deprecación de Starlette/httpx.

Evidencia JUnit local: `.test-artifacts/jwt-authorization-7ed77555f3cb437eb337df2c4dfe71b5/pytest-d2.xml`, generada con `--junitxml` y excluida de Git. Los contadores del informe son 96 pruebas, cero fallos, cero errores y cero omisiones.

**Problemas encontrados:** no apareció un fallo funcional en los escenarios ejecutados. La carencia era la cobertura de la cadena JWT real, porque las pruebas anteriores normalmente sustituían el actor autenticado. No fue necesario modificar `app/security.py`, `app/main.py`, los algoritmos admitidos ni los esquemas. Los cambios locales previos de descripción permanecen intactos.

**Límites:** el JWKS se obtiene de un transporte local, no del servicio real de Supabase. Estos casos no prueban conectividad TLS, renovación/rotación de claves en el servicio, restricciones/RLS de PostgreSQL ni persistencia tras reinicios. El rechazo de un `kid` desconocido no equivale a una prueba de rotación. PostgreSQL y persistencia se verificaron posteriormente en la sección 6.6; la conectividad/rotación del servicio JWKS real sigue pendiente.

### 6.6. PostgreSQL, acceso directo y persistencia tras reiniciar FastAPI

**Evidencia histórica anterior a 003.** Los comandos `run_postgres_checks.py --from-project-env` de esta sección ya no están habilitados: el runner rechaza ese argumento y las conexiones de integración requieren ahora la marca de PostgreSQL aislado. Para comprobar la versión actual usar la sección 6.8, sin reutilizar la configuración compartida.

**Entorno y seguridad de ejecución.** Se utilizó PostgreSQL **17.11 del proyecto configurado**, con autorización explícita para transacciones terminadas en `ROLLBACK`. No había otra URL de pruebas configurada, ni PostgreSQL local activo; Docker estaba instalado con su servicio detenido. No se sustituyó PostgreSQL por SQLite ni se arrancaron servicios ajenos.

La conexión de servidor inspeccionada tiene `rolsuper=false` y **`rolbypassrls=true`**. Es una conexión administrativa a efectos de RLS. Sus lecturas de datos no se presentan como una prueba de permisos del ciudadano. La configuración se leyó en memoria; no se imprimieron ni modificaron valores de `.env`, contraseñas, claves o tokens.

Las pruebas SQL temporales emplean `BEGIN`, UUID nuevos, perfiles ya existentes y `ROLLBACK` incondicional en `finally`; no existe una ruta de `COMMIT`. Antes de escribir se comprueba la ausencia de reglas y triggers personalizados en las nueve tablas. No se ejecutan migraciones, `UPDATE`, `DELETE`, creación de usuarios, subida de imágenes, cambios de permisos ni políticas. Los metadatos de fotografía temporales no representan subidas a Storage y desaparecen con la transacción.

Todas las inspecciones y las consultas de persistencia usan transacciones **`READ ONLY` explícitas y verificadas con `SHOW transaction_read_only`**. No se confía en opciones de arranque de libpq: el pooler no las aplicó en el primer sondeo, que solo hizo consultas SELECT. Se fijan tiempos máximos de consulta y bloqueo. Los hashes de todas las filas y campos de las nueve tablas coinciden antes/después; no basta con comparar contadores.

**Archivos añadidos:**

| Archivo | Responsabilidad |
| --- | --- |
| [test_postgres.py](../tests/test_postgres.py) | Restricciones reales, relaciones, catálogo y permisos de roles SQL; transacciones con rollback |
| [test_postgres_persistence.py](../tests/test_postgres_persistence.py) | Lectura de registros piloto, reinicio real de procesos, fotografía existente y acceso REST directo |
| [postgres_support.py](../tests/postgres_support.py) | Conexión PostgreSQL explícita, transacciones, hashes y evidencia sin secretos |
| [_persistence_worker.py](../tests/_persistence_worker.py) | Proceso de pruebas FastAPI limitado a localhost/GET, BD de solo lectura e identidad de prueba |
| [run_postgres_checks.py](../tests/run_postgres_checks.py) | Ejecución voluntaria con configuración en memoria y directorio de evidencia único |

**Restricciones ejecutadas directamente en PostgreSQL:**

| Grupo | Casos | Evidencia exigida |
| --- | --- | --- |
| CHECK inválidos de reportes, vehículos y sitios | 18 | SQLSTATE **23514**: cuatro coordenadas de reporte, vacío/espacios/1 o 2 caracteres tras `btrim`/2001 caracteres, estado inválido; capacidad 0 o negativa, tipo de vehículo inválido; tipo de sitio inválido y cuatro coordenadas de sitio |
| Límites válidos de descripción | 4 | Se admiten 3 y 2000 caracteres, con/sin espacios exteriores. SQL comprueba `btrim` pero conserva el texto original; FastAPI recorta antes de insertarlo |
| Límites válidos de coordenadas | 2 | Se admiten −90/−180 y 90/180 en reportes y sitios |
| CHECK de turnos | 3 | SQLSTATE **23514**: estado inválido, fin igual al inicio y fin anterior |
| Vehículo duplicado | 2 | SQLSTATE **23505** para PK `id` y UNIQUE `label`. `plate` no es único en el contrato/migración y no se afirma que lo sea |
| Referencias inexistentes | 8 | SQLSTATE **23503**: perfil→`auth.users`, reporte→perfil, foto→reporte y las cinco FKs del turno |
| Relaciones | 2 | Grafo temporal coherente entre perfiles/reporte/foto/vehículo/sitios/turno; además, sin huérfanos ni roles/tipos incompatibles en los registros existentes |

Son **39 casos de restricciones y relaciones**. No se duplican los 19 casos HTTP de descripción para presentarlos como evidencia SQL. Las FKs solo garantizan existencia: el rol del chofer/creador y el uso salida/descarga se comprueban en FastAPI y se contrastan en los registros piloto, sin inventar un CHECK entre tablas. Los CHECK/FKs de las tres tablas reservadas para eventos/agrupación se inspeccionaron en catálogo; no se escribieron datos en ellas ni se ejecutaron módulos de IA. Tampoco se probó borrado en cascada, fuera de este alcance sin eliminaciones.

**RLS y permisos efectivos:**

- **18 pruebas** cambian únicamente el rol de la transacción con `SET LOCAL ROLE anon/authenticated`, comprueban `current_user`, ausencia de superusuario/`BYPASSRLS` y rechazo SELECT **42501** en las nueve tablas. La conexión original sigue siendo administrativa: es una simulación del rol SQL, no una conexión autenticada mediante JWT de Supabase.
- **2 pruebas** de catálogo comprueban RLS habilitado y ausencia de permisos SELECT/INSERT/UPDATE/DELETE para ambos roles en esas tablas. No hay políticas de acceso directo para las nueve tablas (`pg_policies` vacío), coincidiendo con la migración 001. La denegación observada ocurre por permisos SQL revocados; no demuestra la evaluación de filtros de filas de una política RLS.
- **9 pruebas REST anónimas reales**, con la clave pública existente y sin Bearer ni service role, obtienen 401/403 y código PostgreSQL **42501** al consultar las nueve tablas vía PostgREST. Esto comprueba acceso directo no autorizado fuera de SQL Editor.
- **1 prueba omitida:** acceso directo REST con un JWT real de ciudadano. No hay `RECIWISE_CITIZEN_ACCESS_TOKEN` disponible y no se creó ni renovó una sesión. `SET ROLE` y una consulta administrativa no sustituyen esa evidencia.

No se alteraron políticas ni permisos. La diferencia entre privilegios administrativos y acceso sujeto a RLS se apoya en la [documentación de PostgreSQL sobre RLS](https://www.postgresql.org/docs/current/ddl-rowsecurity.html); el alcance transaccional de la suplantación SQL está descrito en [SET ROLE](https://www.postgresql.org/docs/current/sql-set-role.html).

**Persistencia, dos pruebas con procesos nuevos:** se leen los recursos piloto existentes mediante los handlers reales de FastAPI, se detiene exclusivamente el proceso creado por la prueba y se arranca otro proceso con un pool de conexiones nuevo. El backend que pudiera estar abierto por el usuario no se detiene. Ambos procesos escuchan únicamente en `127.0.0.1`, rechazan métodos distintos de GET y abren PostgreSQL en modo de solo lectura.

Se comparan el reporte ciudadano de `/reports/mine` y `/reports/{id}`, su presencia en `/municipal/reports`, `Compactadora Piloto 01`, los dos sitios referenciados y el turno **programado existente**. Los campos de las respuestas e IDs coinciden tras el reinicio. La segunda prueba compara ID, relación, MIME, tamaño y fecha de la fotografía existente; solicita una URL firmada nueva y descarga el objeto antes y después. No se compara la URL temporal ni se guarda su token; se compara el SHA-256 de los bytes de la imagen.

**Límite de autenticación de estas dos pruebas:** solo `get_current_actor` se sustituye por perfiles existentes y `get_db` se adapta para imponer `READ ONLY` en el proceso de pruebas. Los endpoints, modelos, serialización, PostgreSQL y Storage son reales. Esto prueba persistencia a través de FastAPI tras reiniciar procesos, con autenticación simulada; no es una nueva prueba de login/JWT real del ciudadano o encargado. La aplicación desplegable y su autenticación permanecen intactas.

No se crean duplicados para persistencia ni se alteran disponibilidad, estados, fechas o turnos. Los registros al inicio/final son 3 perfiles, 1 reporte, 1 fotografía, 1 vehículo, 2 sitios, 1 turno y cero filas en las tres tablas reservadas. Los IDs reales se registran solo en los artefactos locales de evidencia; los ejemplos de API de este documento siguen siendo ficticios.

**Reproducción desde la raíz del repositorio, con las dependencias existentes:**

```powershell
# Autorización explícita de usar la BD configurada, solo con rollback/READ ONLY:
.\.venv\Scripts\python.exe tests/run_postgres_checks.py --from-project-env --suite new
.\.venv\Scripts\python.exe tests/run_postgres_checks.py --from-project-env --suite d2
```

El runner lee `.env` y la configuración pública existente del frontend sin modificarlos, comprueba que pertenecen al mismo proyecto y pasa la configuración al proceso hijo en memoria. No imprime valores de credenciales. Para una BD aislada se puede omitir `--from-project-env` y proporcionar `RECIWISE_TEST_DATABASE_URL` solo al proceso; debe contener el esquema ya provisionado y perfiles piloto para las pruebas que los necesitan. Nunca se provisiona automáticamente una BD ni se usa SQLite como alternativa. Las pruebas de Storage/REST se omiten si no se facilitan sus configuraciones; las de persistencia se omiten si faltan los recursos existentes. Un fallo de conexión con una URL explícita produce error, no una omisión silenciosa.

Un `pytest` ordinario sin variables `RECIWISE_TEST_*` omite explícitamente esta integración y conserva las pruebas locales. El runner genera JUnit y JSON en `.test-artifacts/postgres-<id>/`, directorio ya ignorado por Git. Los informes contienen IDs, metadatos no secretos y hashes; no contraseñas, claves, JWT, descripciones de reportes ni URLs firmadas.

**Resultado final comprobado:**

| Grupo de la ejecución final | Aprobadas | Fallidas | Errores | Omitidas |
| --- | --- | --- | --- | --- |
| Suite D2 previa: descripción/API/contrato/JWT | 96 | 0 | 0 | 0 |
| PostgreSQL: restricciones/relaciones y roles SQL | 59 | 0 | 0 | 0 |
| Persistencia mediante FastAPI y Storage reales, identidad de prueba | 2 | 0 | 0 | 0 |
| PostgREST anónimo real | 9 | 0 | 0 | 0 |
| PostgREST con JWT real de ciudadano no disponible | 0 | 0 | 0 | 1 |
| **Total D2** | **166** | **0** | **0** | **1** |

Duración de pytest: **155,71 s**. Se mantiene una advertencia preexistente de deprecación de Starlette/httpx. No se ejecutaron frontend, D3 ni pruebas de concurrencia. El primer pase de integración, antes de añadir la auditoría de relaciones existentes, había dado 69 aprobadas y 1 omitida en 135,83 s; la tabla anterior corresponde a la versión final con **71 casos nuevos** (70 aprobados y 1 omitido).

Evidencia final local: **`.test-artifacts/postgres-eac719156a8e4230a73d92c22edd9eca/`**:

- `pytest-d2.xml`: 167 casos, 166 aprobados, 1 omitido, cero fallos y errores.
- `postgres-catalog.json`: restricciones, validación de catálogo, ausencia de triggers/reglas personalizados y políticas directas.
- `postgres-unchanged.json`: conteos y hashes de todas las filas/campos de las nueve tablas antes/después, `unchanged=true`; rol administrativo con `BYPASSRLS` identificado.
- `persistence.json`: IDs existentes, hashes de los campos antes/después y `same_fields=true` para los cinco recursos; procesos **20348 → 13012**, `all_s1_data_unchanged=true`.
- `photo-persistence.json`: fotografía existente, metadatos iguales y hash de bytes idéntico; procesos **55388 → 41864**, `all_s1_data_unchanged=true`. Imagen JPEG de **99 899 bytes**, SHA-256 `a845fcb6bcf037539afa498932aec0a20da3644d6782cbcef32f5b8169f97e9c` en ambas lecturas.

**Problemas y pendientes:** no se detectó un incumplimiento funcional en las restricciones ejercitadas ni pérdida de datos tras el reinicio. La adaptación necesaria fue imponer `READ ONLY` mediante SQL dentro de cada transacción de prueba, en lugar de asumir que el pooler respetaba las opciones iniciales del cliente. No requiere cambiar el backend, permisos ni migraciones. Queda pendiente la prueba directa con un JWT real de ciudadano y la repetición del flujo de reinicio con sesiones reales de ciudadano/encargado. El trigger de alta de perfil, la privacidad/configuración del bucket y las propiedades de tablas futuras no se afirman como probadas por esta suite. Las comprobaciones de SQLite siguen siendo las 96 pruebas locales previas, separadas de la evidencia real PostgreSQL/Storage; las dos pruebas de reinicio simulan únicamente la identidad y fuerzan sesiones de solo lectura.

### 6.7. Diagnóstico previo y propuesta de concurrencia

**Estado cuando se redactó este análisis: sin implementar.** Se revisaron backend, esquemas, migraciones y pruebas, modificando entonces solo documentación. El responsable D2 autorizó posteriormente las tres correcciones; la implementación y sus resultados están en **6.8**. Se conserva aquí el diagnóstico original y el plan aprobado. Aplicar cambios al proyecto compartido sigue requiriendo otra autorización específica.

**Diagnóstico por inspección del código:**

| Riesgo | Secuencia que lo permite | Protección actual y evidencia |
| --- | --- | --- |
| Doble reserva de vehículo o chofer | A y B consultan solapamientos antes de que cualquiera confirme; ambas ven libre el recurso, insertan y hacen commit | `create_shift`, `app/main.py:199`: SELECT previo sin bloqueo; migración 001 solo tiene CHECK del intervalo e índices ordinarios. `test_vehicle_and_shifts` prueba dos solicitudes consecutivas, sin carrera |
| Más de tres fotos | Con dos fotos, A y B cuentan dos; ambas suben un objeto distinto y confirman una fila; quedan cuatro | `upload_photo`, `app/main.py:84`: COUNT separado de INSERT. El UNIQUE de `storage_path` evita repetir rutas, no limita fotos por reporte. La prueba de fotos actual realiza las subidas en serie |
| Objeto sin metadatos tras un fallo | Storage acepta el objeto; falla INSERT/commit o se interrumpe el proceso antes de persistir | `app/main.py:89–94` sube antes de guardar. `app/storage.py` no ofrece compensación ni registro durable de trabajo pendiente. Un rollback PostgreSQL no revierte Storage |
| Borrado incorrecto si la corrección fuera un `except` genérico | El commit llega a PostgreSQL pero se pierde su confirmación; o falla `refresh` después de un commit exitoso; una limpieza indiscriminada borraría una foto válida | Es un requisito de seguridad para la corrección propuesta. Una excepción al cliente no demuestra que la transacción no se confirmó |

Las carreras se deducen de la separación entre lectura y escritura; **todavía no se reprodujeron con solicitudes simultáneas ni se probaron soluciones**. Las 166 pruebas anteriores no incluyen esa evidencia. No se recomienda sustituir las restricciones por un mutex Python: no protege entre procesos, réplicas o escritores SQL.

**Cambio propuesto 1: exclusiones PostgreSQL de turnos.** Preparar, después de autorización, una nueva `migrations/003_sprint1_concurrencia.sql`, sin editar 001/002. Tendría dos restricciones `EXCLUDE USING gist` independientes, con `btree_gist` para igualdad de UUID e intervalos `tstzrange(starts_at, ends_at, '[)')`. El borrador central es:

```sql
-- PROPUESTA: no ejecutada; faltan comprobaciones previas y extensión.
ALTER TABLE public.shifts
  ADD CONSTRAINT shifts_vehicle_no_overlap
  EXCLUDE USING gist (
    vehicle_id WITH =,
    tstzrange(starts_at, ends_at, '[)') WITH &&
  ) WHERE (status = 'programado');

ALTER TABLE public.shifts
  ADD CONSTRAINT shifts_driver_no_overlap
  EXCLUDE USING gist (
    driver_id WITH =,
    tstzrange(starts_at, ends_at, '[)') WITH &&
  ) WHERE (status = 'programado');
```

Son dos restricciones porque una sola que incluyera ambos UUID rechazaría únicamente la coincidencia simultánea de vehículo **y** chofer. Se conserva la semántica actual: impedir coincidencia de cualquiera de los dos, permitir turnos contiguos y excluir cancelados/finalizados. La comprobación abarcaría INSERT y UPDATE, incluida una vuelta a estado `programado`. La consulta previa puede seguir dando un error temprano; la garantía sería de PostgreSQL. Referencias: [restricciones sobre rangos de PostgreSQL 17](https://www.postgresql.org/docs/17/rangetypes.html#RANGETYPES-CONSTRAINT) y [btree_gist y UUID](https://www.postgresql.org/docs/17/btree-gist.html).

En FastAPI, capturar exclusivamente SQLSTATE **23P01** de esas restricciones, ejecutar rollback y conservar HTTP **409**, `Vehículo o chofer ya reservado en ese horario`. No transformar todos los `IntegrityError` en solapamiento. Los errores se identificarían por SQLSTATE/nombre de restricción, según la [documentación de errores PostgreSQL](https://www.postgresql.org/docs/17/errcodes-appendix.html).

La migración comprobaría primero si existen turnos superpuestos y reportes con más de tres fotos; abortaría sin reparar ni eliminar registros automáticamente. Verificaría disponibilidad, esquema y permisos de `btree_gist`. Al agregar restricciones e inicializar la columna interna de fotos sería necesaria una ventana controlada sin escrituras, con despliegue coordinado de backend/migración para que una versión antigua no inserte fotos sin la nueva posición. Ninguna aplicación sobre Supabase compartido está autorizada en esta etapa.

**Cambio propuesto 2: máximo de tres fotos garantizado por la BD.** Añadir a `report_photos` una columna interna `slot smallint NOT NULL`, `CHECK (slot BETWEEN 1 AND 3)` y `UNIQUE (report_id, slot)`. Solo pueden existir tres posiciones por reporte, incluso si otro escritor omite el COUNT de FastAPI. No se usaría un CHECK que consulte COUNT de otras filas: PostgreSQL recomienda restricciones relacionales para reglas entre filas, no [CHECK dependientes de otras filas](https://www.postgresql.org/docs/17/ddl-constraints.html#DDL-CONSTRAINTS-CHECK-CONSTRAINTS).

Para filas existentes, asignar posiciones deterministas por `created_at,id` durante la migración, conservando sus IDs, rutas y archivos; abortar si alguna cuenta supera tres, sin borrar las sobrantes. En el backend, bloquear la fila padre del reporte (`SELECT ... FOR UPDATE`), revalidar propietario, elegir una posición libre e insertar/`flush` los metadatos antes de subir. Mantener ese bloqueo hasta el final de la transacción: serializa solo las subidas al mismo reporte. Con tres posiciones ocupadas, devolver **409** sin llamar a Storage. Los conflictos de posición se resolverían releyendo/reintentando de forma acotada; no se confundirían con errores de PK/ruta.

El bloqueo implica esperas durante la subida, un costo aceptable a validar para imágenes de hasta 5 MiB. La sección con llamadas síncronas y bloqueos PostgreSQL debe ejecutarse fuera del bucle async, con una sesión dedicada por operación. Añadir `FOR UPDATE` directamente al endpoint async actual con una `Session` síncrona puede bloquear el bucle mientras otra solicitud espera que termine su llamada a Storage. Se fijarían límites de espera y no se compartirían sesiones simultáneamente entre hilos/tareas.

`slot` no se añadiría a `PhotoOut`, `ReportCreate` ni al formulario. Se mantienen endpoints, JWT, roles, propiedad de reportes y el máximo de tres imágenes publicadas.

**Cambio propuesto 3: compensación segura y recuperación durable.** Un `try/except` con DELETE es insuficiente ante caída del proceso, fallo de la propia limpieza o confirmación de commit perdida. Se propone una tabla interna `photo_upload_operations`, creada por la misma migración, con UUID de operación/foto, reporte/autor, bucket/ruta únicos generados por el servidor, estado, fechas, intentos y próximo reintento. No guardaría credenciales ni enlaces firmados. Tendría RLS habilitado y permisos revocados a `anon`/`authenticated`; no se expondría un endpoint público ni se cambiarían políticas existentes.

Flujo propuesto, con orden de bloqueos fijo:

1. Autorizar y validar tamaño/firma; crear y confirmar la intención interna **antes** de cualquier subida. Si eso falla, no llamar a Storage.
2. En una transacción nueva, bloquear primero la operación y después el reporte, comprobar que la operación sigue pendiente y no fue reclamada/cancelada por el conciliador, validar nuevamente el acceso, asignar posición e insertar/`flush` los metadatos sin confirmar todavía. La fila de operación previamente confirmada permite recuperar el trabajo si esta transacción se pierde. Una operación abortada no reutiliza su ruta para otra subida.
3. Subir a una ruta UUID nueva manteniendo `x-upsert=false`. Confirmar en una sola transacción los metadatos y la marca de operación completada; preparar los datos de respuesta para no depender de un `refresh` posterior al commit.
4. Si la subida falla o el rollback es conocido, liberar la transacción y compensar únicamente el objeto de esta operación cuando su creación sea confirmada o indeterminada. Un conflicto que indique objeto preexistente no autoriza borrarlo. La compensación usaría la API Storage, nunca DELETE SQL sobre `storage.objects`, conforme a la [guía de eliminación de Supabase](https://supabase.com/docs/guides/storage/management/delete-objects).
5. Si el commit es incierto, una conexión nueva debe bloquear/releer la operación, esperar a que la transacción original se resuelva y consultar ID **y** ruta. Si los metadatos quedaron confirmados, conservar el archivo y recuperar el resultado; si no se puede resolver la duda, no borrar y dejar la tarea pendiente.
6. Un conciliador reintentable procesa solo operaciones propias incompletas, reclamadas mediante bloqueo transaccional. Omite las activas/bloqueadas, verifica otra vez que la foto no quedó publicada y limita la eliminación al bucket/ruta exactos de la operación. Nunca barre el bucket, acepta rutas del cliente ni elimina fotos antiguas/referenciadas. Los fallos de limpieza se conservan duraderamente y se registran sin secretos.

PostgreSQL y Storage no comparten una transacción. Ante un timeout, la petición de Storage puede haber sido aceptada o seguir en curso; el sistema debe conservar la operación, impedir finalizaciones tardías incompatibles y volver a comprobar/compensar hasta resolverla. No dar por terminada una operación indeterminada solo porque un DELETE temprano no encontró el objeto. La consistencia entre servicios sería **eventual, con seguimiento y reintentos**, no atomicidad instantánea. Sin el conciliador funcionando no se declararía resuelta la recuperación ante caídas.

**Contratos HTTP propuestos:** éxito 201 y cuerpos públicos sin cambios; 409 por reserva o límite de fotos; mantener 401/403/404, 413, 415, 422, 502 de Storage y 503 por configuración ausente. Para fallos transitorios de BD, esperas agotadas o commit aún incierto, proponer **503 controlado**, con mensaje genérico y sin SQL/credenciales, en lugar de un 500 accidental. Los fallos inesperados no transitorios seguirían siendo 500 genéricos registrados internamente. Una compensación fallida no debe ocultar el error original ni prometer que el archivo ya desapareció. Esta ampliación del significado de 503 quedaría documentada y probada.

**Archivos previstos tras autorización:** `app/main.py`, `app/models.py`, `app/storage.py`; un coordinador interno de subidas y un ejecutor del conciliador; nueva migración 003; pruebas de fallos HTTP/Storage y de carreras PostgreSQL; adaptación de fixtures/runners existentes para la nueva columna y tabla protegida. Sin frontend, IA, `.env`, credenciales ni cambios a migraciones aplicadas.

**Plan de pruebas de aceptación, aún no implementado:**

| Entorno | Casos necesarios | Resultado a exigir |
| --- | --- | --- |
| PostgreSQL aislado, dos conexiones/transacciones reales y sincronización por barreras/eventos | Mismo vehículo con choferes distintos; mismo chofer con vehículos distintos; ambos iguales; recursos diferentes; intervalos contiguos; estados excluidos; actualización/reactivación que solape | Una sola reserva conflictiva confirmada; la otra obtiene 23P01/409. Casos compatibles exitosos. Repetir tras rollback del primer competidor para comprobar que no quedan reservas fantasma |
| FastAPI con PostgreSQL aislado y Storage simulado explícitamente | Partir de dos fotos y lanzar varias subidas; partir de cero y lanzar al menos cuatro; reportes distintos | Nunca más de tres filas; 201 solo para las aceptadas, 409 para el exceso; no subir objetos para posiciones ya agotadas; ningún bloqueo global entre reportes |
| SQL directo PostgreSQL | Cuarta posición/fila, slot nulo/fuera de rango o duplicado; cambio de reporte/slot | Restricciones rechazan el estado inválido sin depender del COUNT de FastAPI |
| SQLite/simulaciones, sin afirmar garantías de bloqueo | Storage 502/timeout/503, imagen 413/415, fallo de `flush`, commit fallido, confirmación perdida, fallo después del commit, fallo y reintento de DELETE | Códigos controlados; sin metadatos publicados de una subida fallida; compensación exacta cuando corresponde; nunca borrar una foto confirmada o preexistente |
| PostgreSQL aislado + reinicio de proceso + Storage de prueba | Caída después de intención, después de subida y después de commit; dos conciliadores; respuesta tardía de subida; reintento del conciliador | Trabajo durable recuperable, sin borrar referencias válidas, sin marcar como resueltos trabajos indeterminados y sin exceder tres fotos |
| Regresión D2 | Pruebas existentes, con fixtures adaptados donde cambie el esquema interno | Mantener contratos, autenticación/permisos y evidencia de cada entorno; conservar la omisión de JWT real si sigue sin sesión |

Para demostrar el conflicto entre transacciones hace falta que una confirme y la otra observe el rechazo: **las pruebas anteriores de una sola conexión y rollback obligatorio no bastan**. Los nuevos tests usarían exclusivamente una BD PostgreSQL 17 desechable/aislada con el esquema y la migración propuesta; ninguna migración ni COMMIT de estos tests se ejecutaría sobre el proyecto compartido. Si no se dispone del entorno aislado, los casos se marcarían bloqueados/omitidos, sin sustituirlos por SQLite. Los fallos/compensaciones de Storage se ejecutarían con transporte simulado o almacenamiento aislado; la prueba del servicio real requeriría un bucket/proyecto de pruebas autorizado, no las fotografías del piloto.

**Resultados de esta etapa de análisis:** se volvió a ejecutar la suite D2 sin habilitar integración externa:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_api.py tests/test_frontend_contract.py tests/test_security.py tests/test_postgres.py tests/test_postgres_persistence.py --tb=short -rs --junitxml=.test-artifacts/concurrency-analysis-20261029/pytest-d2-local.xml
```

Resultado: **96 aprobadas, 0 fallidas, 0 errores, 71 omitidas**, en **4,81 s**, con la advertencia preexistente de Starlette/httpx. Las 71 omisiones corresponden a integración PostgreSQL/Storage sin activación explícita en esta etapa. La evidencia anterior de **166 aprobadas y 1 omitida** de la sección 6.6 permanece válida como ejecución previa, sin atribuirle pruebas de concurrencia. No hay todavía resultados de aceptación de las correcciones propuestas.

**Prioridad para el MVP:** críticos antes de uso simultáneo real: impedir dobles reservas a nivel BD, mantener el máximo de tres fotos y resolver la compensación sin pérdida de evidencia válida, incluyendo trabajo recuperable cuando falla la limpieza. El plan de conciliación básico y sus pruebas forman parte de esa solución; no se declara una garantía de recuperación solo con un `except`. Para una fase posterior pueden quedar claves de idempotencia de peticiones HTTP, optimización del tiempo de bloqueo/carga masiva, paneles/alertas avanzados y auditoría o limpieza de huérfanos históricos. Los objetos históricos no se eliminarían con este cambio. La espera por reporte y la consistencia eventual entre servicios deben documentarse como límites operativos del MVP.

### 6.8. Implementación autorizada de concurrencia y consistencia, solo en PostgreSQL aislado

**Resultado actual: 220 aprobadas, 0 fallidas, 0 errores y 12 omitidas**, en **57,74 s**. Las tres correcciones están implementadas y comprobadas en el entorno aislado descrito abajo. **No están desplegadas ni migradas en Supabase compartido y no se declara cerrado el Sprint.**

#### Aislamiento y archivos

Docker Desktop estaba detenido; se inició para ejecutar PostgreSQL **17.11**, imagen oficial `postgres:17-alpine`, ID/digest `sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b`. Cada ejecución creó su propio contenedor/base con UUID, puerto aleatorio publicado únicamente en `127.0.0.1`, etiqueta Docker comprobada y marca aleatoria dentro de la base. Antes de migrar/escribir se verifica host, nombre y marca. La autenticación `trust` se limita a este contenedor de pruebas local y efímero, sin usar contraseñas del proyecto. No es una receta de despliegue.

El runner no carga `.env`, pasa URL/clave de Storage ficticias a los procesos de prueba y elimina las variables de integración Supabase. `auth.users` y `storage.buckets` son esquemas mínimos locales que permiten ejecutar 001 literalmente; **no son Supabase Auth ni Storage reales**. Los datos son ficticios. Todos los contenedores propios se eliminaron después, verificando su etiqueta e ID; no se detuvieron procesos FastAPI ajenos ni se eliminaron recursos existentes. Si Docker/PostgreSQL/las marcas no están disponibles, el runner falla y no cambia a SQLite ni al proyecto compartido.

| Archivos de esta tarea | Cambio |
| --- | --- |
| `app/main.py`, `app/models.py`, `app/storage.py` | Exclusiones traducidas a 409, posiciones internas, flujo de fotos síncrono en hilo de trabajo, HTTP Storage seguro y errores controlados |
| `app/db_errors.py`, `app/photo_uploads.py`, `app/reconcile_photos.py` | Nuevos: diagnóstico SQLSTATE, coordinador transaccional y conciliador durable reintentable |
| `migrations/003_sprint1_concurrencia.sql`, `migrations/rollback/003_sprint1_concurrencia.sql` | Nuevos: aplicación y reversión con comprobaciones previas |
| `tests/test_shift_concurrency.py`, `test_photo_concurrency.py`, `test_photo_recovery.py`, `test_photo_restart.py`, `test_storage_failures.py`, `test_migration_003.py` | Nuevos: 65 casos de aceptación/regresión |
| `tests/isolated_postgres.py`, `run_isolated_postgres.py`, `concurrency_support.py`, `_concurrency_worker.py` | Nuevos: PostgreSQL desechable, fixtures independientes y procesos de caída/reinicio |
| `tests/test_frontend_contract.py`, `test_postgres.py`, `postgres_support.py`, `run_postgres_checks.py` | Adaptación de sustitutos síncronos/slot y rechazo explícito de integración no aislada; no son cambios al frontend |
| `docs/API_SPRINT1.md` | Estado actual, evidencia, contratos y procedimientos |

`app/security.py`, `app/schemas.py`, `app/db.py`, `app/config.py`, migraciones **001/002**, frontend, IA, `.env` y credenciales permanecen iguales respecto al inicio de esta tarea. El cambio local anterior de descripción y el cambio anterior de `frontend/.env.example` se conservaron. No hubo commits ni push.

#### Restricciones de 003 y comportamiento

1. **Reservas:** `shifts_vehicle_no_overlap` y `shifts_driver_no_overlap`, `EXCLUDE USING gist` con igualdad de UUID y solapamiento `tstzrange(...,'[)')`, filtradas a `programado`. Permiten horarios contiguos y protegen INSERT/UPDATE/reactivación. 23P01 de esos nombres devuelve **409**. Los abortos conocidos 40001/40P01 admiten hasta tres intentos totales; al agotarlos, **503**. Una confirmación perdida no se reintenta automáticamente. Los tests fuerzan que ambas solicitudes terminen su consulta previa antes de insertar, por lo que no atribuyen la exclusión al SELECT temprano.
2. **Fotos:** `slot smallint NOT NULL`, `report_photos_slot_valid` (1–3) y `report_photos_report_slot_key` (UNIQUE reporte/posición). Un escritor SQL tampoco puede guardar una cuarta posición. FastAPI bloquea el reporte y elige una posición libre; serializa las subidas de ese reporte, conservando paralelismo entre reportes. La posición no aparece en `PhotoOut` ni se exige al cliente. Metadatos insertados/`flush` antes de subir, commit después de Storage aceptado.
3. **Registro durable:** intención confirmada antes de cualquier subida en `photo_upload_operations`; CHECK de ruta exacta ligada a autor/reporte/operación/extensión, FKs, UNIQUE de ruta, estados limitados, intentos no negativos e índice de trabajos pendientes. RLS y REVOKE de la tabla nueva impiden acceso directo de anon/authenticated; no se alteran políticas anteriores. Operación `complete` y metadatos se confirman juntos.

Antes de cambiar estructura se bloquean las tablas afectadas con espera limitada y se comprueba si hay turnos superpuestos o reportes con más de tres fotos. **Si los hay, 003 aborta sin arreglar, borrar ni renumerar esas filas.** Solo para datos válidos se inicializa la columna nueva según `created_at,id`, manteniendo IDs, rutas y campos previos. La extensión `btree_gist` se instala o reutiliza en su esquema existente. Los tests verificaron que las migraciones conflictivas no cambian los hashes de las filas, que la asignación es determinista y que la reversión recupera los campos originales.

#### Compensación, caídas y límites

El flujo bloquea primero la operación y luego el reporte, con sesiones dedicadas a cada operación. Los endpoints de fotos y sus llamadas HTTP son síncronos, ejecutados por FastAPI fuera del bucle async. Los bloqueos SQL del flujo de fotos tienen espera máxima de 5 s y consultas de 15 s; el HTTP de subida/borrado usa timeout de 30 s. Un archivo inválido o superior a 5 MiB se rechaza antes de crear intención o llamar a Storage.

- Error conocido antes de subir: no se crea un objeto y se marca `rejected` cuando hay intención.
- Subida aceptada y rollback definitivo: se registra `cleanup_pending` y se intenta borrar **solo** la ruta generada por esa operación. Un error de DELETE conserva estado, intentos y siguiente reintento; no oculta el error original.
- Commit incierto: se consulta con una sesión nueva y bloqueo. Si se encuentra la foto confirmada, se recupera el 201. Si no se puede confirmar el resultado, se devuelve **503 sin DELETE en esa solicitud**, manteniendo la intención para revisión posterior. La ausencia de confirmación no se interpreta como ausencia de commit.
- El conciliador usa bloqueos con `SKIP LOCKED`: no toma operaciones activas ni las que otro conciliador procesa. Revisa ID/ruta y cualquier referencia existente; conserva siempre archivos referenciados y rechaza bucket/ruta que no correspondan a la operación.
- Timeout de red, HTTP 408/5xx o caída con subida incierta: conservar `quarantined` y repetir comprobación/compensación, con espera creciente hasta una hora. **Un DELETE que hoy no encuentra objeto no cierra el trabajo**, porque el POST anterior puede terminar tarde. Estas marcas no se retiran automáticamente.
- Un objeto declarado preexistente por Storage deja la operación en `review`, sin borrarlo. No hay barrido del bucket, borrado de fotos históricas, eliminación de filas reales ni DELETE SQL sobre `storage.objects`.

La eliminación usa la API Storage con un único path, siguiendo el [cliente oficial de Supabase](https://raw.githubusercontent.com/supabase/storage-js/master/src/packages/StorageFileApi.ts). Se acepta ausencia idempotente confirmada por 2xx/lista, sin confundir 403/404, respuestas inválidas o errores con éxito. Los tests usan claves ficticias; no probaron borrados contra el servicio Supabase real.

**Operación del conciliador:** es un ejecutor de una pasada, no un servicio ya instalado. `--execute` autoriza la compensación de esa pasada; `--limit` (1–1000) y `--operation-id UUID` acotan el trabajo. Su endurecimiento posterior está descrito en **6.11**: guardia 003 obligatoria, diagnóstico predeterminado READ ONLY, revalidación del próximo intento al reclamar y parada ordenada. El UUID explícito también respeta `next_attempt_at`; no fuerza reintentos anticipados. Ver allí los códigos de salida y la distinción entre una pasada exitosa y una cola resuelta.

Ejemplos **solo en un entorno aislado ya configurado**, nunca con el `.env` compartido actual:

```powershell
.\.venv\Scripts\python.exe -m app.reconcile_photos --limit 100
.\.venv\Scripts\python.exe -m app.reconcile_photos --execute --operation-id UUID_DE_PRUEBA
```

Antes de desplegar hay que programar la pasada periódica en el servidor y supervisar las operaciones en revisión/cuarentena. **Mientras no esté programada, los reintentos no se ejecutan solos.** No se creó una tarea del sistema ni un cron en esta sesión. La recuperación tras reiniciar el ejecutor sí se probó en procesos separados.

#### Evidencia y resultados

La ejecución final está en **`.test-artifacts/reciwise-d2-test-39218df8c4164bd18638c145f86cdb7d/`**, ignorada por Git. `environment.json` registra imagen, versión, base aislada, host local y hashes SHA-256 de 001/003/reversión; `pytest.xml` contiene **232 casos, 0 fallos, 0 errores y 12 omisiones**. `postgres-catalog.json` y `postgres-unchanged.json` corresponden al catálogo y transacciones rollback del subconjunto de restricciones previo; no significan que toda la suite de carreras carezca de commits. Las carreras y pruebas de migración **sí confirman/escriben datos ficticios** y solo dentro del contenedor propio desechable.

| Grupo final | Aprobadas | Entorno/evidencia |
| --- | --- | --- |
| API/contrato/JWT anteriores | 96 | SQLite, claves efímeras y JWKS local; sin login Supabase real |
| Restricciones/relaciones/roles SQL anteriores | 59 | PostgreSQL 17.11 aislado, transacciones rollback |
| Turnos concurrentes/abortos/commit incierto | 11 | PostgreSQL real; barreras, abortos SQL inyectados, commits independientes y respuesta HTTP |
| Fotos concurrentes/posiciones/validación/contratos | 12 | PostgreSQL real, Storage simulado; seis solicitudes simultáneas, SQL directo, reportes independientes y permisos |
| Persistencia/compensación/conciliadores | 16 | PostgreSQL real; Storage simulado, fallos controlados de comunicación/persistencia y limpieza |
| Caída/reinicio real de procesos | 3 | PostgreSQL real y servidor HTTP Storage simulado local; caída tras intención, subida o commit; conciliador nuevo y API nueva |
| HTTP Storage | 18 | `httpx.MockTransport`, sin PostgreSQL ni red externa; headers, 408/4xx/5xx, timeout, borrado inválido y URLs |
| Migración/reversión | 5 | Bases adicionales dentro del contenedor propio; rechazo sin reparar conflictos, backfill, reversión y archivo de registro |
| **Total aprobado** | **220** | **0 fallos/errores; 57,74 s** |

**Doce omisiones explícitas:** dos pruebas históricas requieren los recursos piloto del proyecto compartido, inexistentes en este contenedor; nueve requieren PostgREST/clave pública reales; una requiere JWT real de ciudadano. No se copiaron esos datos/credenciales ni se contactó Supabase para evitarlas. La evidencia anterior de 166 aprobadas/1 omitida (6.6) se conserva como ejecución previa. Las tres pruebas nuevas de caída/reinicio son independientes y sí pasaron con datos ficticios, PostgreSQL real y autenticación de prueba.

Se conserva una advertencia preexistente de deprecación Starlette/httpx. No se ejecutaron frontend ni IA. `compileall` de `app`/`tests` también pasó.

Tras la revisión final se ejecutaron los mismos once módulos D2 sin habilitar PostgreSQL: **114 aprobadas, 0 fallidas/errores y 118 omitidas**, en **5,71 s**. Las 114 son las 96 locales anteriores y los 18 casos HTTP Storage con transporte simulado; las 118 omisiones son explícitas por falta de activación del entorno aislado. Informe: `.test-artifacts/d2-local-final-003/pytest.xml`. Esta comprobación local no sustituye la ejecución PostgreSQL de 220 aprobadas. Se verificaron los hashes de **46 archivos protegidos** (incluidos frontend, IA, `.env`, configuración/autenticación/esquema previos y migraciones 001/002): todos coinciden con el inicio de la implementación. Los hashes de 001/003/reversión coinciden con el manifiesto de la ejecución aislada final; `git diff --check` y la revisión de espacios de archivos nuevos no mostraron errores. La consulta Docker por la etiqueta de pruebas no encontró contenedores restantes.

Secuencia de verificación incremental y ejecuciones intermedias:

| Ejecución | Aprobadas | Fallidas | Omitidas | Evidencia local / observación |
| --- | --- | --- | --- | --- |
| Turnos, primer prototipo de tests | 1 | 6 | 0 | `reciwise-d2-test-6f7936d6b1c846ad9421d27e3d3ddd93/pytest.xml` |
| Turnos, después de aislar identidades por caso | 7 | 0 | 0 | `reciwise-d2-test-dfa657e620594b289d1fe11b4cafa4a7/pytest.xml` |
| Regresión local previa | 96 | 0 | 0 | pytest local, 4,77 s |
| Fotos, primera aceptación | 9 | 0 | 0 | `reciwise-d2-test-a25dbcd6cdc441e0be65bc5c96763d18/pytest.xml` |
| Recuperación, primer inyector de fallo | 12 | 2 | 0 | `reciwise-d2-test-9ec378772ac64fcfb55f8bed2fe6120f/pytest.xml` |
| Recuperación, inyector corregido | 14 | 0 | 0 | `reciwise-d2-test-4aeaee3d399f4766a1c8d6c58354d795/pytest.xml` |
| HTTP Storage, ampliación de casos | 14 y después 18 | 0 | 0 | pytest local, 0,06 s por ejecución |
| Suite completa, primer pase | 207 | 0 | 12 | `reciwise-d2-test-3445cd10c48b48daaf81773faea6b754/pytest.xml`, 41,04 s |
| Suite completa, ampliación de fallos inciertos | 213 | 0 | 12 | `reciwise-d2-test-b162003fe8d1499b955fa6a80a26583a/pytest.xml`, 29,35 s |
| **Suite completa final** | **220** | **0** | **12** | Directorio final indicado arriba, **57,74 s** |
| Comprobación local final, PostgreSQL deshabilitado | 114 | 0 | 118 | `d2-local-final-003/pytest.xml`, **5,71 s**; no prueba concurrencia |

Todos los directorios de la tabla están bajo `.test-artifacts/`. Los fallos iniciales de los tests se debían a compartir choferes entre casos con el mismo horario y a un inyector cuya consulta no provocaba el aborto esperado después de un autoflush; se corrigieron sin limpiar datos compartidos. Se añadieron reintentos limitados para abortos transaccionales conocidos y pruebas de su agotamiento/no repetición ante commit incierto. Hubo además un arranque de contenedor que no alcanzó pytest porque `pg_isready` observó el servidor temporal de inicialización: el runner ahora espera al servidor TCP definitivo. Un error de sintaxis de un módulo de tests en desarrollo se corrigió antes de la ejecución completa. Ninguno de estos resultados intermedios se presenta como aceptación exitosa.

#### Aplicación y reversión, sin autorización para Supabase compartido

Requisitos: dependencias existentes de `requirements.txt`, Docker en ejecución e imagen oficial disponible. Desde la raíz, estos comandos **provisionan, migran, prueban y eliminan su propio entorno aislado**:

```powershell
.\.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase shifts
.\.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase photos
.\.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase recovery
.\.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase all
```

Para una revisión manual posterior en otra base **realmente aislada**, comprobar primero su identidad/host/base frente al contenedor propio, detener escritores y conciliadores, tener copia de seguridad y aplicar sobre 001 el archivo de subida con parada ante error. Usar una URI PostgreSQL del entorno aislado, no la URI de SQLAlchemy con `+psycopg`, ni valores del `.env` compartido:

```powershell
# Plantillas de revisión aislada; reemplazar el marcador por una URI local verificada.
psql -X -v ON_ERROR_STOP=1 --dbname 'URI_POSTGRESQL_AISLADA_VERIFICADA' -f migrations/003_sprint1_concurrencia.sql
psql -X -v ON_ERROR_STOP=1 --dbname 'URI_POSTGRESQL_AISLADA_VERIFICADA' -f migrations/rollback/003_sprint1_concurrencia.sql
```

El cliente `psql` no es necesario para el runner automático. No ejecutar las plantillas contra el proyecto compartido. La migración usa una transacción y aborta ante conflictos existentes; conservar el estado y solicitar revisión de esos conflictos, sin eliminarlos ni cancelarlos automáticamente. Reiniciar el backend con el esquema correspondiente, ejecutar los casos de aceptación y solo entonces habilitar escrituras. Código anterior y esquema nuevo no deben coexistir durante la asignación obligatoria de posiciones.

**Reversión:** detener escrituras y el conciliador; examinar/guardar el registro durable. El archivo de reversión **se niega a continuar si hay operaciones pendientes, en cuarentena o revisión**. No se deben cambiar sus estados artificialmente para sortear ese control: recuperar/comprobar primero cada operación. Cuando procede, archiva la tabla como `photo_upload_operations_archive_003` manteniendo sus filas, RLS y permisos, elimina la columna/constraints de posiciones y las exclusiones, conserva `btree_gist` por posibles dependencias y exige volver al backend anterior. No borra fotos, reportes, turnos ni archivos. Una segunda reversión con un archivo del mismo nombre ya existente debe revisarse, sin sobrescribirlo. Revertir retira las garantías de concurrencia; no equivale a mantenerlas.

**Pendiente de revisión/despliegue:** autorización y aplicación en Supabase compartido; pruebas de compensación contra un proyecto/bucket Supabase de pruebas real; programar/supervisar el conciliador; sesión JWT de usuario real. La consistencia Storage/BD es eventual y depende de disponibilidad/reintentos: puede haber objetos temporalmente sin metadatos durante una caída. La cuarentena y los objetos preexistentes requieren criterio operativo explícito. Siguen como fase posterior idempotencia de reintentos HTTP, optimización de conexiones/bloqueos, limpieza de huérfanos históricos y decodificación completa de imágenes. No se declara terminado el Sprint 1.

### 6.9. Auditoría de preparación del despliegue: NO-GO

**Dictamen:** no aplicar todavía 003 al Supabase compartido. Los datos observados no presentan los conflictos que impiden la migración, pero eso no sustituye las condiciones de liberación siguientes. Esta auditoría añade un diagnóstico de solo lectura y pruebas de auditoría; **no cambia el arranque ni las funcionalidades del backend, no modifica 003/rollback y no instala tareas**. El control de arranque se propone para una corrección posterior, no se presenta como implementado.

#### Evidencia actual de solo lectura

Se añadió [scripts/d2_preflight.py](../scripts/d2_preflight.py). Acepta una URL explícita en la variable de proceso `RECIWISE_AUDIT_DATABASE_URL`, o `--from-project-env` para leer el `.env` existente en memoria. Este último argumento pertenece **a este diagnóstico**, no al antiguo runner de integración, donde sigue deshabilitado. No acepta contraseñas por argumentos, no imprime URL/usuario/credenciales y solo permite guardar informes bajo `.test-artifacts/`.

Ejemplo ejecutado, exclusivamente diagnóstico:

```powershell
.\.venv\Scripts\python.exe scripts/d2_preflight.py --from-project-env --output .test-artifacts/readiness-audit-003/shared-readonly.json
```

El diagnóstico usa `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY`, comprueba `transaction_read_only=on`, limita consultas a 10 s y espera de bloqueos a 2 s, y termina en **ROLLBACK incondicional**. Las consultas son SELECT sobre catálogo/conteos, sin `FOR UPDATE`, locks explícitos, migraciones, reparaciones o llamadas de escritura a Storage. Los savepoints permiten informar una consulta no disponible como error, nunca como cero resultados. Un error de sección o conexión produce código 2; código 0 significa diagnóstico completado, **no GO**. Las consultas ordinarias pueden adquirir bloqueos de lectura y generar estadísticas del servidor; READ ONLY no equivale a cero actividad física. [Semántica PostgreSQL READ ONLY](https://www.postgresql.org/docs/17/sql-set-transaction.html).

Lectura del compartido: **29-10-2026, 22:45:22 UTC / 17:45:22 Lima**, PostgreSQL 17.11. Evidencia local: `.test-artifacts/readiness-audit-003/shared-readonly.json`, sin contraseñas, claves, JWT, descripciones ni coordenadas de reportes.

| Comprobación | Observado | Límite de la conclusión |
| --- | --- | --- |
| Modo transaccional | READ ONLY `on`, aislamiento `repeatable read`, ROLLBACK; cero errores de consulta | Fotografía del momento; no impide escrituras posteriores de otros clientes |
| Datos operativos | 3 perfiles, 1 reporte, 1 foto, 1 vehículo, 2 sitios y 1 turno | No se crearon ni modificaron registros |
| Solapamientos programados | 0 pares por vehículo y 0 por chofer | Repetir después de drenar escritores, antes de la aplicación |
| Fotos/intervalos | 0 reportes con más de 3 fotos; 0 intervalos inválidos | No significa que se haya aplicado una restricción nueva |
| Relaciones | 0 autores de reporte incompatibles, fotos huérfanas o relaciones de turno inválidas | Control de existencia/roles/tipos de los datos leídos |
| Estructura 003 | Sin `slot`, sin ambas exclusiones y sin `photo_upload_operations` | Estado esperado antes de migrar; peligroso si se inicia ahora el backend nuevo |
| Extensión | `btree_gist` 1.7 disponible, **no instalada**, declarada trusted | No se intentó instalar en el compartido |
| Permisos de operador | CREATE en BD/esquema público y privilegios de propietario de las seis tablas operativas | Comprobación de catálogo; no prueba ejecutar DDL en el proveedor |
| Rol de conexión | No superusuario, **BYPASSRLS=true** | Conexión administrativa: no es una prueba de JWT/RLS de ciudadano |
| Tablas operativas | Seis tablas ordinarias, RLS habilitado, sin permisos SELECT/INSERT/UPDATE/DELETE para anon/authenticated ni políticas directas | No reemplaza los nueve casos REST reales omitidos ni examina todas las tablas futuras |
| Actividad | 0 transacciones >1 min, 0 idle-in-transaction y 0 esperas Lock visibles | No demuestra que una ventana de mantenimiento esté coordinada |
| Bucket configurado | Privado; 5 MiB; MIME JPEG/PNG/WebP | Configuración de catálogo, sin prueba HTTP de acceso/bytes |
| Relación con `storage.objects` | 0 fotos sin entrada y 0 objetos candidatos sin referencia en el prefijo de reportes | Metadatos solamente; no acredita que los bytes estén presentes, respaldados o accesibles |
| Colisiones de nombres de subida/archivo | Ninguna detectada | El diagnóstico debe repetirse inmediatamente antes de intervenir |

La extensión trusted permite instalación por un rol con CREATE en la BD; no se debe interpretar el campo `superuser=true` de su versión como prohibición cuando `trusted=true`. Aun así, la instalación y permisos reales del proveedor deben ensayarse primero en el proyecto aislado. [btree_gist en PostgreSQL 17](https://www.postgresql.org/docs/17/btree-gist.html).

**Pruebas nuevas de auditoría:** `tests/test_deployment_readiness.py`; ejecución `tests/run_isolated_postgres.py --phase audit`: **11 aprobadas, 0 fallidas, 0 errores y 0 omitidas**, 4,01 s. Informe `.test-artifacts/reciwise-d2-test-627e8502d09041a6b794e6d75947f8bc/pytest.xml`. Comprueban que el servidor rechaza UPDATE/DELETE/CREATE y SELECT FOR UPDATE con SQLSTATE 25006 dentro del diagnóstico, preservación de filas, detección sin reparación de tres clases de conflictos, protección de `.env`, rechazo de SQLite y reproducción del backend sin guardia sobre esquema antiguo. Las bases de reproducción se crearon/migraron solo dentro del contenedor local marcado y se eliminaron con él.

**Importante:** el caso que reproduce comportamiento inseguro pasa porque demuestra el hallazgo; no es aceptación de ese comportamiento. Las **220 aprobadas y 12 omitidas** de 6.8 siguen siendo la evidencia funcional anterior; no se suman las 11 de auditoría para declarar resueltos esos bloqueos.

#### Riesgos de la migración y de su reversión

| Riesgo/precondición | Diagnóstico y condición necesaria |
| --- | --- |
| Extensión y propietario | `CREATE EXTENSION IF NOT EXISTS btree_gist` y reutilización de su esquema. Confirmar soporte UUID/GiST, permisos del ejecutor y estado real de las tablas; no instalarla desde la aplicación |
| Bloqueos de subida | ACCESS EXCLUSIVE sobre `shifts` y `report_photos`, en ese orden, hasta terminar la transacción; impide también lecturas incompatibles. No es una migración sin interrupción |
| Tiempo total | `lock_timeout=5s` limita cada espera, **no** la duración de índices, comprobaciones ni backfill. 003 no establece `statement_timeout`; elegir presupuesto probado y comprobarlo en una sesión directa/de sesión antes de operar |
| Trabajo y espacio | Dos índices GiST, asignación de slot a todas las fotos y creación de índices/registro; estimar duración, WAL y espacio en una copia representativa. No extrapolar los pocos registros actuales a crecimiento futuro |
| FKs y actividad externa | La creación del registro referencia perfiles/reportes y puede tomar bloqueos sobre esos padres. Drenar las escrituras relacionadas, procesos de carga y conciliadores; no basta pausar solo el POST de turnos |
| Conflictos de datos | La migración aborta antes de corregir si hay solapamientos o >3 fotos. No borrar/cancelar/renumerar conflictos automáticamente. El backfill de la columna nueva solo se hace tras aceptar los datos válidos |
| Artefacto no idempotente | ADD COLUMN/CONSTRAINT y CREATE TABLE no pueden repetirse ciegamente. Ante desconexión o resultado de COMMIT incierto, consultar catálogo y resolver el resultado antes de reintentar |
| Nombres/drift | Revisar tablas/índices/constraints nuevos, tipos, nulabilidad y objetos de archivo existentes; un nombre correcto no demuestra una definición correcta |
| Reversión bloqueada | DOWN rechaza estados distintos de complete/cleaned/rejected; las cuarentenas se retienen deliberadamente y pueden impedirlo. No falsificar estados para conseguir una reversión |
| Archivo y dependencias | DOWN mantiene filas, FKs, RLS y ACL del registro archivado y conserva la extensión. Comprobar colisiones del archivo/índices, exportación y dependencias nuevas antes de renombrar o retirar slot |
| Garantías tras DOWN | Retira las exclusiones y posiciones; exige backend anterior y vuelve a admitir los riesgos anteriores. No es un mecanismo de continuidad de la protección |

PostgreSQL mantiene los bloqueos hasta finalizar la transacción. `NOT VALID` no sirve para posponer exclusiones/UNIQUE y las FKs pueden bloquear también las tablas referenciadas. No sustituir el artefacto probado por una variante supuestamente concurrente sin revisión y nuevas pruebas. [LOCK](https://www.postgresql.org/docs/17/sql-lock.html), [ALTER TABLE](https://www.postgresql.org/docs/17/sql-altertable.html).

Los controles de conflictos dentro de 003 están protegidos por bloqueos exclusivos y forman parte de una transacción que **escribe**: no son el diagnóstico previo de solo lectura. Durante esta auditoría, el modo de inspección del conciliador (sin `--execute`) tomaba locks `FOR UPDATE`. **Corregido en 6.11:** el diagnóstico predeterminado ahora usa READ ONLY, sin reclamar filas ni llamar a Storage. No existe una opción CLI `--dry-run`; `dry_run` es el indicador JSON de la ejecución sin `--execute`.

#### Guardia de esquema: diagnóstico previo y actualización en 6.10

Al realizar la auditoría, la aplicación no tenía lifespan/startup de compatibilidad. `/health` devolvía 200 con versión **de API 0.1.0**, no de esquema. La prueba con solo 001 reprodujo fotos=500 y dos reservas concurrentes 201/201. **Ese comportamiento se corrigió para FastAPI en 6.10:** el test ahora exige rechazar el arranque y conservar las rutas de negocio bloqueadas. La misma comprobación se incorporó después al conciliador en **6.11**, antes de inspeccionar o procesar trabajos.

Propuesta a implementar y probar antes del GO:

1. Verificador único de compatibilidad **requerida 003**, usado por el arranque de FastAPI y por el conciliador antes de ejecutar compensaciones. Solo consultas de catálogo en READ ONLY; sin `create_all`, DDL ni migración automática.
2. En el lifespan de FastAPI, ejecutar ese verificador en un hilo de trabajo antes de aceptar tráfico. Si falta algo, el esquema es parcial/desconocido o la BD no responde, abortar el arranque con diagnóstico genérico sin URL/secretos. En el servicio desplegable no permitir fallback a SQLite ni un bypass silencioso por variable de entorno.
3. Verificar definiciones, no solo nombres: ambas exclusiones validadas y sus índices GiST válidos/listos, igualdad del UUID correcto, rango `[)` y predicado programado; slot smallint NOT NULL, CHECK 1–3 y UNIQUE con claves correctas; columnas/PK/UNIQUE/FKs/CHECK/ruta del registro, RLS y ACL. Normalizar catálogo de acuerdo con los esquemas de extensión admitidos.
4. Mientras no existe una tabla de versiones, la compatibilidad se puede comprobar estructuralmente con el catálogo aprobado. Un futuro registro versionado/checksum requiere una migración revisada propia; una fila “3” o `app.version` por sí sola no prueba integridad. Este diagnóstico no implementa un certificado de compatibilidad.
5. Mantener `/health` como liveness si se conserva su contrato; añadir una comprobación interna de readiness que indique 503 si se pierde compatibilidad/conectividad, y configurar el despliegue para no enviar tráfico sin readiness. Detener todos los escritores antes de UP/DOWN; la comprobación al arrancar no protege contra cambios manuales de esquema mientras el proceso sigue vivo.
6. Pruebas de aceptación: sin 003, esquema parcial, constraint con nombre correcto y definición incorrecta, índice inválido, conexión caída y reversión deben impedir disponibilidad/escrituras; con esquema correcto deben iniciar API/conciliador y pasar los contratos. Eran **pendientes al realizar esta auditoría**, no cubiertas por los 220 casos ni por su caso de reproducción. Las comprobaciones locales posteriores se documentan en 6.10 y 6.11; no sustituyen las pruebas remotas ni las sondas del despliegue.

#### Programación y supervisión del conciliador, sin tareas instaladas

Diseño propuesto: un único planificador responsable, cuenta de servicio del backend, ruta absoluta al intérprete del entorno y directorio de trabajo fijo. Usar la configuración segura existente del servidor; no colocar service role/DSN en argumentos, nombre de tarea, logs o cron. No se cambian `.env` ni credenciales en esta auditoría.

Tras validación en el Supabase aislado, proponer una pasada cada **minuto**, inicialmente `--limit 20`, y ajustar según latencia/volumen medidos. Ejecutable: `python -m app.reconcile_photos --execute --limit 20`. No se ejecutó ni programó sobre servicios reales. El runner tiene como máximo hasta 30 s por DELETE y procesa trabajos en serie: un lote de 20 podría durar unos diez minutos más consultas. No fijar un timeout global menor sin medir y verificar recuperación; una ejecución cortada tras un DELETE puede requerir repetición idempotente.

En Programador de tareas de Windows: directorio de trabajo del backend, identidad de servicio, repetición por minuto y opción **“No iniciar una nueva instancia”**. En Linux, un timer/servicio único con exclusión de proceso equivalente; en un orquestador usar política de una ejecución activa. Una exclusión de archivo local no coordina dos hosts. Evitar planificadores duplicados durante cambios de servidor.

La defensa entre procesos/hosts sigue siendo PostgreSQL: `FOR UPDATE SKIP LOCKED` por operación, orden operación→reporte y consulta final de referencias antes de DELETE. No se permite un lock global Python como garantía. Una operación ocupada se omite, no se declara terminada; el SELECT inicial por lote no es por sí mismo una reserva del trabajo. Los reintentos usan `next_attempt_at` y espera creciente hasta una hora. La programación por minuto no anula esa espera.

Supervisión mínima propuesta, con consultas SELECT:

- Timestamp/resultado/duración de cada pasada; códigos 0, 1 o 2 y último heartbeat del planificador, sin secretos ni URLs firmadas. Revisar código 2 inmediato; código 1 requiere revisar el estado, no reiniciar indefinidamente sin diagnóstico.
- Conteos por estado, número vencido, antigüedad del vencido más antiguo, intentos máximos y `last_error`; separar `pending`/`cleanup_pending`/`quarantined` de `review`. Este último no entra en el lote automático: consultarlo y revisarlo explícitamente.
- Umbrales iniciales a validar: alertar si faltan dos pasadas esperadas, crece cleanup_pending o el trabajo sigue vencido >5 min; revisión inmediata de review. Medir SLA distinto para quarantined, que se conserva aunque DELETE haya funcionado y no se retira automáticamente.
- Registrar solo UUID de operación y códigos internos; no imagen, token, cuerpo Storage, DSN ni clave. Probar cancelación/reinicio del ejecutor y failover sin dos eliminaciones conflictivas; nunca borrar filas para “vaciar la cola”.

Consulta de supervisión **de solo lectura después de 003**, para un operador autorizado (no ejecutar antes de existir la tabla):

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout='10s';
SELECT state, count(*) AS total,
       count(*) FILTER (WHERE state IN ('pending','cleanup_pending','quarantined')
                        AND next_attempt_at <= now()) AS due,
       min(next_attempt_at) FILTER (WHERE state IN ('pending','cleanup_pending','quarantined')
                                   AND next_attempt_at <= now()) AS oldest_due,
       max(attempts) AS max_attempts
FROM public.photo_upload_operations GROUP BY state ORDER BY state;
ROLLBACK;
```

No se instaló cron, timer ni tarea Windows; no se activó el conciliador en el compartido. La supervisión SQL no autoriza cambiar estados o borrar archivos. La inspección por UUID del ejecutor es READ ONLY desde **6.11**; informa una observación, sin reservar trabajo ni consultar bytes en Storage.

#### Plan pendiente: proyecto Supabase aislado y Storage real

**Todos los casos siguientes están diseñados, no ejecutados.** Requieren un proyecto Supabase de pruebas autorizado, distinto del compartido, con ref/host/BD/API comprobados contra una allowlist y rechazo explícito del compartido. Crear allí, con autorización específica, identidades ficticias ciudadano A/B, encargado y chofer; roles asignados por el operador, nunca por selección pública. Bucket privado exclusivo del ensayo y prefijo UUID por ejecución; claves solo en memoria/configuración segura del servidor, sin editar `.env` del repositorio. No clonar cuentas ni fotografías ciudadanas reales.

**Actualización de alcance (6.12):** no se crea ese proyecto ahora y no se ejecuta este plan contra el principal. Queda como diseño de validación remota futura, sujeto a un destino/permiso específicos. La falta de ese entorno no detiene el desarrollo local de Sprint 2.

El manifiesto debe registrar IDs/rutas propias, hashes/tamaños y operaciones del ensayo, sin secretos/URLs temporales. Los fallos se inyectan solo en el proceso/proxy de pruebas. El PostgreSQL y el Storage del objetivo son reales; no sustituir el servicio con un diccionario y presentarlo como evidencia remota. Antes/después comprobar metadatos y bytes de objetos con credenciales correctas; no interpretar 403 como ausencia. Conservar un objeto ajeno al trabajo y una foto publicada como controles contra borrados incorrectos.

| Caso diseñado | Inyección/ejecución en el proyecto de pruebas | Evidencia para aprobar |
| --- | --- | --- |
| Fallo tras upload | Storage real confirma el objeto; provocar un aborto SQL definitivo de la persistencia | Metadatos no confirmados, intención durable, DELETE de una única ruta propia, ausencia confirmada y controles intactos |
| Fallo de compensación | Interrumpir solo DELETE tras upload aceptado y rollback; volver a habilitarlo | cleanup_pending, intentos/fecha conservados, objeto aún presente; proceso nuevo reintenta y limpia solo ese objeto |
| Commit incierto confirmado | Confirmar realmente en PostgreSQL y perder la confirmación al cliente | 201 recuperado o 503 si falla la consulta; foto/objeto intactos y ninguna eliminación, incluso después de reiniciar |
| Commit incierto no confirmado | Simular pérdida de comunicación con transacción realmente abortada | 503 sin DELETE en la solicitud; relectura con bloqueo por proceso nuevo resuelve el resultado, sin borrar referencias válidas |
| Indisponibilidad al resolver | Tras pérdida de confirmación impedir también la consulta de resolución | Intención preservada y cero borrados mientras hay duda; recuperar conectividad y verificar ambos desenlaces anteriores |
| Caídas duras | Terminar solo el proceso propio tras intención, upload o commit | Recuperación por un ejecutor nuevo; ninguna foto publicada perdida, ningún trabajo pendiente olvidado |
| Respuesta/upload tardío | Proxy de prueba retrasa respuesta o reenvío al Storage real hasta después del timeout y un primer DELETE | Cuarentena no retirada; objeto tardío detectado y compensado en una pasada posterior |
| Colisión y ruta segura | Respuesta de objeto preexistente y controles con nombres semejantes/otra ruta, reporte y bucket | Estado review sin borrar el objeto preexistente; tampoco eliminar controles o rutas vecinas |
| Ausencia/error de DELETE | Repetir DELETE válido; inducir 403, bucket inexistente, 5xx y acuse inválido | Solo ausencia inequívoca es idempotente; errores conservan trabajo/reintentos y no se marcan cleaned |
| Subidas concurrentes reales | Dos fotos previas y seis solicitudes con JWT real; repetir con reportes distintos | Máximo tres filas y tres objetos publicados por reporte, 201/409 adecuados; sin objetos propios olvidados |
| Dos ejecutores/reinicio | Ejecutores independientes y cambio de host durante un lote | Operación activa omitida por el segundo, reintentos recuperables y sin borrados simultáneos conflictivos |
| Permisos reales | JWT A/B/encargado, /me y endpoints; REST anónimo y con JWT válido sobre nueve tablas originales **y el registro nuevo** | Identidad validada antes de comprobar 403/404/42501; nuevas cargas/lecturas siguen autorizadas, acceso directo denegado |
| Guardia y restauración | Ensayar esquema ausente/parcial/incorrecto, restauración y UP/DOWN revisados | Aplicación/ejecutor fallan cerrados cuando corresponde y arrancan solo con versión compatible; respaldo restaurable de BD **y bytes** |

Los borrados del ensayo deben limitarse al manifiesto del proyecto/prefijo de pruebas y a objetos no referenciados cuya propiedad se conozca; no utilizar una búsqueda de “huérfanos” como autorización para borrar. La limpieza final y la creación del proyecto/bucket son acciones futuras, no realizadas aquí. Salida de aprobación: JUnit, manifiesto de versiones/objetivo, consultas antes/después, hashes de bytes, trazas redacted de HTTP/SQLSTATE y prueba de ausencia de borrados de controles. Un fallo o una omisión mantienen el gate correspondiente abierto.

#### Diferencias con las doce pruebas omitidas

| Casos originales omitidos en 6.8 | Qué sí probó el entorno local | Qué continúa pendiente |
| --- | --- | --- |
| 1: `test_existing_records_survive_fastapi_restart` | Tres caídas nuevas con datos ficticios y PostgreSQL real | Los recursos piloto no existen en el contenedor; no se volvieron a consultar vía API ni reiniciar el backend compartido en esta auditoría. El test histórico además sustituye identidad |
| 1: `test_existing_photographs_survive_fastapi_restart` | Transporte HTTP local/simulado, metadatos transaccionales y preservación ante caídas | Descarga/firma/bytes y ciclo de compensación con Supabase real en el proyecto aislado; el catálogo compartido no prueba los bytes |
| 9: REST anónimo para cada tabla original | SET ROLE SQL y permisos de catálogo; dos controles SQL adicionales para el registro nuevo | Repetir por PostgREST real con clave pública y sin service role, incluidos proxy/configuración y nueva tabla. La evidencia remota anterior de 6.6 no es una ejecución actual con 003 |
| 1: REST con JWT ciudadano válido | 69 casos criptográficos/roles con claves ficticias y JWKS local | Sesión real aceptada por Auth antes de la denegación de tablas; no confundir JWT inválido con RLS correcto |

**Las doce siguen omitidas y no se convierten en aprobadas.** Para las pruebas futuras usar datos ficticios del nuevo proyecto y sesiones reales; no es necesario copiar los registros privados del compartido para obtener evidencia equivalente de integración. Los tests antiguos de persistencia con actor sustituido no bastan para declarar login/JWT real de extremo a extremo.

#### Secuencia de liberación y reversión, preparada pero no ejecutada

| Paso | Responsable/evidencia requerida | Punto de parada |
| --- | --- | --- |
| 1. Cerrar bloqueos | Implementar/probar guardia de esquema, completar proyecto Storage real, validar planificador y aprobar runbook con responsable y ventana | Sin estas evidencias, **NO-GO** aunque los conflictos actuales sean cero |
| 2. Congelar artefactos | Registrar revisión de código, SHA-256 de 003/DOWN, versiones de aplicación/PG/extensión, configuración referenciada sin copiar secretos y backend anterior disponible | Un cambio al SQL exige revisión y repetir el ensayo; no editarlo durante la intervención |
| 3. Ensayar recuperación | Restaurar un respaldo en un destino aislado autorizado, probar integridad, roles/permisos y lectura de archivos; medir tiempo y acordar RPO/RTO | Un respaldo existente sin restauración comprobada no cierra este gate |
| 4. Detener y drenar | Pausar todos los escritores/administradores y nuevas subidas, drenar solicitudes/HTTP a Storage, detener conciliadores y sus planificadores; registrar quién confirmó el drenaje | No usar solo ausencia de sesiones SQL largas como prueba de drenaje HTTP |
| 5. Respaldo final consistente | Registrar hora/ID/ubicación protegida de respaldo BD con esquema/datos/ACL/RLS/funciones y registro; copiar aparte bytes de Storage e inventario de hashes/tamaños; verificar coherencia con escrituras detenidas | Sin copia verificable de archivos, no basta el respaldo PostgreSQL |
| 6. Diagnóstico final READ ONLY | Repetir preflight en conexión administrativa identificada: conflictos cero, tipos/constraints esperados, nombres libres, permisos/extensión disponibles y sin interferencia; comparar con snapshot/copia | No corregir datos ni matar sesiones automáticamente. Ante cambios inesperados, detenerse |
| 7. Autorizar explícitamente | Aprobación del responsable para **ese proyecto/ventana/artefacto** y plan de reversión; verificar objetivo mediante comprobación independiente | La autorización de pruebas aisladas anterior no autoriza este paso en el compartido |
| 8. Aplicar UP | Sesión PostgreSQL directa/de sesión aprobada, ejecutor con permisos, presupuesto de tiempo probado; cliente con ON_ERROR_STOP y archivo 003 intacto | 003 ya incluye BEGIN/COMMIT: no envolver ciegamente en otro `--single-transaction`. Si falla, rollback; si se pierde confirmación, resolver catálogo antes de reintentar |
| 9. Comprobar sin reabrir | Preflight/catálogo y guardia: dos exclusiones y sus índices válidos, slot asignado, CHECK/UNIQUE/NOT NULL, registro/FKs/ruta/RLS/ACL correctos; IDs/campos previos iguales salvo slot nuevo; bytes/objetos conservados | Mantener bloqueo operativo si falta cualquier requisito o aparece drift |
| 10. Arranque controlado | Backend compatible inicia sin migrar; readiness validada en todas las réplicas, login/roles y lecturas; ensayos de escritura solo en el objetivo de pruebas o con autorización explícita para datos de humo | No introducir reportes/turnos duplicados en el compartido para comprobarlo |
| 11. Activar operación | Habilitar una sola programación del conciliador revisado, probar heartbeat/estados y alertas; reabrir gradualmente con seguimiento de 409/503, bloqueos y cola | Cuarentenas/review y fallos nuevos requieren evaluación; no ocultarlos ni vaciar el registro |
| 12. Aceptar o retroceder | Aceptación explícita; conservar evidencia, copia y revisión durante el periodo acordado | El Sprint sigue abierto hasta revisión posterior, no se cierra con esta auditoría |

Los respaldos de BD de Supabase guardan metadatos, **no los objetos binarios de Storage**, y restaurar la BD no recupera archivos borrados. Las contraseñas de roles personalizados tampoco están garantizadas en esos respaldos. Mantener referencias a los secretos en el almacén seguro existente y un respaldo separado de archivos; no copiarlos a Git o `.env` nuevos. No se consultó el plan de backups, no se generó/restauró una copia ni se activó PITR en esta sesión. [Documentación de respaldos Supabase](https://supabase.com/docs/guides/platform/backups).

**Si UP falla antes de confirmar:** comprobar rollback y esquema/IDs originales en la misma ventana; no ejecutar DOWN para una transacción ya revertida. Si el resultado es incierto, mantener escritores detenidos y verificar catálogo/estado de conexión; no repetir UP ni DOWN por suposición.

**Si UP confirmó y hay que revertir:** detener también backend nuevo, planificadores y procesos en curso; tomar evidencia/copia nueva; resolver honestamente todo trabajo pendiente o incierto y verificar referencias/objetos. Comprobar ausencia del nombre de archivo y sus índices/constraints de archivo. Solo entonces, con autorización del operador, aplicar el DOWN intacto, verificar archivo/RLS/filas/objetos y restaurar el backend anterior. Conservar `btree_gist`; revisar dependencias adicionales antes de quitar slot. No eliminar registros, objetos ni cuarentenas para desbloquearlo.

La reversión simple es más predecible **antes** de reabrir escrituras. Una vez que hay operaciones inciertas, DOWN puede negarse legítimamente: mantener mantenimiento y preferir una corrección hacia delante o evaluar restauración coordinada de BD/Storage con aceptación explícita de pérdida de datos/RPO. Restaurar solo la BD sobre Storage que ya cambió no es una reversión consistente. Un segundo DOWN con archivo existente tampoco se fuerza ni sobrescribe su historial.

#### Gates para cambiar el dictamen

- [x] Diagnóstico actual de datos/catálogo, READ ONLY verificado, sin conflictos observados.
- [x] Integridad del artefacto 003/DOWN y pruebas aisladas anteriores disponibles; prueba adicional del diagnóstico y reproducción del bloqueo de arranque.
- [ ] **G1 integral:** guardia/readiness de **FastAPI implementadas/probadas (6.10)** y guardia del **conciliador implementada/probada (6.11)**. Falta validar la configuración de sondas en el despliegue; no se marca completo el gate combinado.
- [ ] **G2:** proyecto Supabase aislado autorizado y matriz de Storage/Auth/PostgREST real aprobada; omisiones justificadas explícitamente, nunca reclasificadas como éxitos.
- [ ] **G3:** respaldo reciente de BD y archivos, restauración comprobada y RPO/RTO aceptados.
- [ ] **G4:** programación/supervisión del conciliador ensayada, responsables de cuarentena/review y failover sin planificadores duplicados.
- [ ] **G5:** ventana/drenaje/permisos y extensión ensayados con el proveedor; diagnóstico final repetido tras el drenaje y presupuesto de tiempo/espacio aceptado.
- [ ] **G6:** revisión de compatibilidad, reversión/dependencias y autorización específica para el proyecto compartido.

**Recomendación final de la auditoría: NO-GO.** Podrá pasar a GO técnico para una ventana concreta cuando G1–G6 tengan evidencia aprobada y siga limpio el diagnóstico final; ese GO no sustituye la autorización explícita para ejecutar. No hubo migraciones ni cambios de datos en el compartido, tareas reales, modificaciones de credenciales/`.env`, push ni cierre de Sprint.

### 6.10. Guardia de esquema de FastAPI implementada, sin migraciones automáticas

**Alcance:** exclusivamente guardia de FastAPI y sus pruebas. No se cambian migraciones, conciliador, Storage, autenticación, frontend, IA, `.env` ni credenciales. No se ejecutaron consultas ni migraciones en Supabase compartido en esta etapa. **El backend nuevo debe negarse a arrancar allí mientras no exista el esquema compatible autorizado.** Esta protección no autoriza aplicar 003 ni cierra Sprint 1.

#### Método y contrato de compatibilidad

Se añadió `app/schema_guard.py` y un contrato estático revisable, `app/schema_003.json`, generado una vez desde **001 + 003 intactas** en PostgreSQL 17.11 desechable. El contrato incluye hashes de ambas migraciones y metadatos, sin filas, UUID de usuarios, URLs ni credenciales. No se aprende ni actualiza desde la base conectada al servicio; no se consulta una versión de API para deducir la de BD.

La verificación abre una conexión del mismo engine configurado que usa FastAPI y ejecuta:

1. `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY`, con `SHOW transaction_read_only=on` obligatorio; timeout de consulta 10 s, espera de locks 2 s y search_path local `pg_catalog,public`.
2. SELECT del catálogo de las **siete tablas requeridas**: perfiles, reportes, fotos, vehículos, sitios, turnos y registro durable. No lee reportes, imágenes ni cuentas de Auth.
3. Comparación conservadora del catálogo con el contrato; **ROLLBACK siempre**, antes de devolver la conexión al pool.

| Requisito | Qué se comprueba |
| --- | --- |
| Tablas y columnas | Tabla/esquema, permanencia, tipos con tamaño, nulabilidad, defaults e identidad/generación de columnas |
| Reservas | Exclusiones de vehículo y chofer con definición completa, `[)` y predicado `programado`, validación y condiciones de diferimiento correctas |
| Índices | Método GiST/B-tree, claves/expresiones, predicados, unicidad, clases de operador, flags valid/ready/live y número de claves |
| Posiciones de fotos | `slot smallint NOT NULL`, CHECK efectivo 1–3 y UNIQUE exactamente de reporte/posición |
| Registro durable | Columnas, PK/UNIQUE/FKs/CHECK, ruta ligada a UUID/extensión, estados y estructura de reintentos, índice de pendientes |
| Ejecución de FKs | Triggers internos de integridad asociados a las FKs y su estado de habilitación, sin comparar sus nombres/OIDs variables |
| Protección y drift | RLS, permisos de tabla/columna efectivos de anon/authenticated, políticas y triggers/reglas adicionales sobre esas tablas |

No basta que exista una constraint con el nombre correcto: una definición que controle el recurso equivocado, permita slot arbitrario, use otro rango/predicado o altere una FK se rechaza. Se identifica la clase UUID GiST por pertenencia a `btree_gist`, independientemente de su esquema de instalación; la prueba con la extensión movida a `extensions` pasó. Los datos o roles concretos de los ciudadanos no intervienen en la comparación.

**Política conservadora:** el contrato es exacto para esos objetos, incluidos índices y columnas. Un cambio aditivo o una definición equivalente con otra representación puede exigir revisión; no se interpreta como una versión nueva compatible de forma automática. PostgreSQL 17.11 es el entorno comprobado; actualizaciones/versiones con cambios de representación del catálogo requieren ensayo. Esto prioriza rechazar drift desconocido frente a iniciar con garantías inciertas.

Regeneración excepcional del contrato, solo tras revisión de cambios aprobados:

```powershell
.\.venv\Scripts\python.exe tests/run_isolated_postgres.py --refresh-schema-manifest
```

Ese comando construye una base **nueva y local** desde migraciones del repositorio, escribe el artefacto y elimina su contenedor. No forma parte del arranque ni debe utilizarse para “aprobar” lo que casualmente exista en un servidor. Revisar el diff/hash resultante; los arranques normales nunca regeneran el archivo. Si falta o es inválido, el servicio falla cerrado. No se añadió ningún flag de entorno para omitir la guardia en producción ni fallback a SQLite.

#### Arranque, disponibilidad y preparación

`app/main.py` incorpora un lifespan obligatorio. Tanto la creación del engine como la lectura de catálogo/verificación se ejecutan mediante `run_in_threadpool`, fuera del bucle async. `app/db.py` limita conexión PostgreSQL y espera de pool a 5 s; los timeouts SQL anteriores son por sentencia, no una promesa de duración total de toda la secuencia.

Si falta 003, hay una migración parcial/drift, el motor no es PostgreSQL, la conexión falla o el contrato no puede comprobarse, se lanza `SchemaCheckError` con texto genérico y código interno estable. El lifespan no llega al estado preparado. Se suprime la excepción original del driver en mensajes/trazas de arranque para no divulgar DSN, usuario, contraseña o SQL. No se llama a `create_all`, a scripts SQL, al conciliador ni a Storage.

| Señal | Contrato y límite |
| --- | --- |
| `/health` | Mismo JSON `{"status":"ok","version":"0.1.0"}`; solo liveness del proceso que responde. No consulta ni certifica BD/Storage/JWT |
| `/ready` antes de un arranque verificado | HTTP 503, `{"status":"not_ready","schema":"unverified"}`. La sonda no puede reemplazar el arranque |
| `/ready` tras arranque válido | Repite la comprobación real en hilo de trabajo; 200 `{"status":"ready","schema":"003"}` solo si sigue compatible |
| `/ready` con error posterior | 503 genérico y marca no preparado; bloquea siguientes solicitudes de negocio. Una sonda posterior correcta puede recuperar la preparación |
| Rutas de negocio sin preparación | Middleware devuelve 503 antes de ejecutar autenticación o handlers. Aplica también si el servidor se configura deliberadamente sin lifespan |

La sonda es una ruta interna de operación, excluida de OpenAPI para conservar el catálogo anterior; los contratos de las operaciones existentes no cambian. CORS sigue envolviendo los errores 503 para el origen autorizado. Un preflight CORS puede responder correctamente sin que eso demuestre preparación de BD.

Si Uvicorn aborta su startup no habrá servicio HTTP normal para probar `/health`; el supervisor debe tratar ese arranque como fallido. En un transporte que omite lifespan puede haber liveness 200, pero `/ready` y negocio permanecen en 503: se probó que llamar a la sonda no habilita el proceso. En despliegue configurar sondas con `/ready`, no solo `/health`.

**Límite operacional:** no se relee todo el catálogo por cada petición de negocio. Una modificación manual del esquema tras el arranque se detecta al consultar `/ready`; después se cierran las rutas de negocio. Sigue siendo obligatorio detener escritores para UP/DOWN y configurar sondas periódicas. La guardia no convierte una alteración de esquema en caliente en una operación segura. Tampoco certifica conectividad con Storage/Auth: esas verificaciones siguen fuera de este alcance.

#### Archivos de esta corrección

| Archivo | Cambio |
| --- | --- |
| `app/schema_guard.py` | Nuevo: lectura READ ONLY, contrato, validación y errores sanitizados |
| `app/schema_003.json` | Nuevo: catálogo aprobado de referencia, no datos de aplicación |
| `app/main.py` | Lifespan, estado cerrado por defecto, middleware de negocio, `/ready` y orden CORS |
| `app/db.py` | Límites de conexión/pool PostgreSQL, sin cambiar URL ni configuración privada |
| `tests/test_schema_guard.py` | Nuevo: aceptación/rechazo, READ ONLY, fallo de conexión, privacidad, CORS y reinicio real |
| `tests/conftest.py` | Verificador sustituido explícitamente **solo en tests SQLite**, sin valor como evidencia de esquema PostgreSQL |
| `tests/concurrency_support.py` | Engine de fixture para startup, manteniendo el verificador PostgreSQL real |
| `tests/test_deployment_readiness.py` | El antiguo contraejemplo ahora exige rechazar el esquema 001; deja de aceptar 201/201 |
| `tests/run_isolated_postgres.py` | Fase `schema`, contrato reproducible, hash de contrato en evidencia y suite completa con auditoría/guardia |
| `docs/API_SPRINT1.md` | Evidencia, comportamiento y alcance de desbloqueo |

`app/config.py`, `app/security.py`, esquemas públicos, `app/reconcile_photos.py`, `app/photo_uploads.py`, Storage y **todas las migraciones, incluida 003 y su rollback**, se conservan respecto al inicio de esta corrección. Los cambios locales de tareas anteriores no se sobrescribieron.

#### Pruebas y evidencia

Ejecutadas únicamente con el runner que crea un PostgreSQL aislado, valida localhost/nombre/marca y elimina su contenedor al terminar. No se conectó al Supabase compartido.

```powershell
.\.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase schema
.\.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase all
```

Los casos de la guardia comprueban:

- 001 sin 003: startup rechazado, sin crear registro/slot ni modificar filas.
- 17 variantes de estructura incompleta/incompatible: exclusiones ausentes o incorrectas, rango/predicado erróneos, slot nullable/tipo incorrecto/CHECK inefectivo o sin validar/UNIQUE incorrecto, registro/columna de reintentos ausentes, FK/ruta/índice alterados, RLS deshabilitado, SELECT directo concedido o integridad FK deshabilitada.
- 003 completo aceptado y extensión en esquema `extensions` aceptada.
- Puerto PostgreSQL local inaccesible: fallo controlado; ni mensaje ni traceback/log incluyen las credenciales ficticias utilizadas para comprobar redacción.
- SQL de verificación limitado a SET/SHOW/SELECT, cero commits y rollback observado; catálogo y hashes de filas iguales antes/después. Una escritura de prueba inyectada dentro de la verificación es rechazada por PostgreSQL con 25006.
- Preparación/liveness separadas; drift detectado por `/ready` cierra negocio; transporte sin lifespan y SQLite no pueden habilitar el backend desplegable.
- Dos procesos FastAPI diferentes arrancan con el mismo esquema correcto y recuperan el mismo reporte ficticio tras reiniciar. El alta de ese reporte es una petición de prueba explícita, no un efecto de la guardia.

Primera fase específica: **26 aprobadas**, 35,47 s, antes de añadir el caso de FK deshabilitada. Primer pase integral ampliado: **258 aprobadas, 0 fallidas/errores y 12 omitidas**, 107,63 s, con 27 casos de guardia y los 11 de auditoría además de las 220 pruebas anteriores. Se volvió a ejecutar tras conservar CORS en los 503 de preparación. La ejecución local complementaria dio **99 aprobadas y 24 omitidas**, 7,48 s: 96 casos previos más tres controles sin PostgreSQL; los 24 escenarios PostgreSQL no se sustituyen por SQLite.

**Resultado integral final:** **258 aprobadas, 0 fallidas, 0 errores y 12 omitidas**, **96,26 s**. Directorio de evidencia: **`.test-artifacts/reciwise-d2-test-813825bcc96a4043a3093fe59ff10883/`**. `pytest.xml` registra 270 casos; `environment.json` identifica PostgreSQL 17.11, contenedor propio/localhost y hashes de migraciones y contrato. El contenedor se eliminó al terminar.

| Grupo de la ejecución final | Aprobadas | Omitidas | Evidencia |
| --- | --- | --- | --- |
| Suite D2 anterior | 220 | 12 | Regresión funcional sin cambios a los contratos existentes |
| Auditoría y regresión de arranque antiguo | 11 | 0 | El antiguo contraejemplo ahora exige rechazo seguro |
| Guardia nueva | 27 | 0 | 24 casos con PostgreSQL aislado y 3 controles de transporte sin lifespan, conexión TCP fallida y rechazo explícito de SQLite |
| **Total** | **258** | **12** | **Cero fallos/errores** |

El contrato contiene 7 tablas, 54 columnas, 43 restricciones, 40 entradas de triggers de FKs, 20 índices y 14 comprobaciones de acceso de clientes, además de políticas/reglas/triggers personalizados esperados. Su SHA-256 probado es `b31e1704e246b282448721b156b21706c71d67089ec22d078e3f1dec68bba7f7`. No contiene datos privados. Se mantiene una advertencia preexistente de Starlette/httpx; no se actualizaron dependencias para ocultarla. `compileall`, `git diff --check` y la revisión de espacios pasaron. Los **52 archivos protegidos** comprobados por hash siguen iguales, incluidas todas las migraciones, conciliador, frontend, IA, configuración y `.env`; el contrato y los SQL coinciden con los hashes de la ejecución final. Evidencia adicional: `scope-verification.json` en el directorio final. No quedan contenedores de pruebas.

Las doce omisiones históricas conservan su significado: dos casos de recursos piloto, nueve PostgREST anónimos y uno con JWT real. No se marcan aprobados. Los datos, Storage/Auth y las identidades de las pruebas locales son los mismos entornos explícitos descritos en 6.8; los 96 casos SQLite sustituyen el verificador mediante monkeypatch de tests, mientras todos los arranques de las fixtures PostgreSQL usan la guardia real.

**Estado al terminar esta etapa de guardia FastAPI:** quedaba pendiente proteger el ejecutor del conciliador. Esa protección y sus pruebas se completan en **6.11**. Continúan sin programarse tareas ni hacerse pruebas con Storage real. No se autoriza desplegar sobre el compartido ni se declara cerrado Sprint 1; los gates restantes de 6.9 siguen abiertos.

### 6.11. Conciliador independiente: reclamación, diagnóstico y recuperación

**Alcance:** se reutilizan el ejecutor existente, `PhotoUploads`, la tabla durable de 003, el verificador de 6.10 y las funciones de `app/storage.py`. No se añade otro conciliador, tabla, migración ni endpoint. Esta etapa usa exclusivamente PostgreSQL local desechable y Storage simulado; no consulta ni modifica Supabase compartido, ni configura tareas reales. El Sprint sigue abierto.

| Archivos de esta etapa | Cambio |
| --- | --- |
| `app/reconcile_photos.py` | Guardia 003 compartida, diagnóstico real, errores/códigos controlados y parada cooperativa |
| `app/photo_uploads.py` | Observación READ ONLY, próximo intento revalidado al reclamar, detección `busy`/`missing`, parada y saneamiento de errores |
| `tests/test_reconciler.py` (nuevo) | 15 casos sobre PostgreSQL aislado, incluidos procesos independientes |
| `tests/_reconciler_worker.py` (nuevo) | Puntos de caída exclusivamente de pruebas, tras comprobar el aislamiento |
| `tests/test_photo_recovery.py` | Adaptación de pruebas anteriores a la fecha durable de reintento, adelantando solo trabajos ficticios del ensayo |
| `tests/test_photo_restart.py` | Hook opcional del Storage HTTP simulado para sincronizar procesos sin cambiar su comportamiento habitual |
| `tests/run_isolated_postgres.py` | Fase `reconciler` y nuevos casos en la suite integral |
| `docs/API_SPRINT1.md` | Operación, evidencia, riesgos y pendientes |

No se modifican `app/storage.py`, `app/schema_guard.py`, configuración, modelos/esquemas públicos, autenticación, migraciones ni contratos HTTP. Se preservan los cambios locales previos del proyecto.

#### Cambios y garantías

- **Guardia antes de cualquier trabajo:** `python -m app.reconcile_photos` llama al mismo `verify_schema` de FastAPI, tanto en diagnóstico como en ejecución. 001 sin 003, un esquema parcial/incompatible o una conexión no verificable terminan con código 2, sin reclamaciones ni llamadas a Storage. No hay bypass ni migración automática. El contrato `schema_003.json` y los SQL permanecen iguales.
- **Reclamación transaccional por trabajo:** `FOR UPDATE SKIP LOCKED` sobre la operación, seguido del bloqueo del reporte, se conserva durante la comprobación de referencias y el DELETE. Otro proceso observa `busy` y omite esa fila. No depende de un mutex Python, archivo local, reloj de lease ni de que el planificador tenga una sola instancia. Al terminar/caer el proceso, PostgreSQL libera el bloqueo; no quedan reclamaciones permanentes que resetear.
- **Corrección de una carrera de reintento:** el SELECT inicial descubre candidatos; no los reserva. Ahora `state` y `next_attempt_at` se vuelven a comprobar bajo el bloqueo de reclamación. Si otro proceso ya reprogramó el trabajo, devuelve `not_due` sin llamar a Storage. Esto también se aplica a UUID explícitos; no hay opción de forzar la fecha.
- **Reintentos durables:** se conservan `attempts`, `updated_at`, `next_attempt_at` y un código estable en `last_error`. La espera es `min(3600, 30 * 2**min(attempts, 7))` segundos tras incrementar intentos: 60, 120, 240, 480, 960, 1920 y 3600 en adelante. No hay bucle de reintento inmediato. Un fallo de BD deja el trabajo recuperable y devuelve `deferred` o código 2 si falla la pasada/guardia.
- **Commit de upload incierto:** mientras la transacción original retenga el bloqueo de la operación, el conciliador la omite. Solo después de resolver ese bloqueo, en una conexión independiente, consulta las referencias confirmadas por ID o ruta. Una foto publicada se conserva; una discrepancia se envía a `review`. Una conexión fallida no se interpreta como ausencia ni autoriza DELETE.
- **Borrado acotado:** únicamente el bucket configurado y la ruta exacta derivada de actor/reporte/UUID/extensión. Nunca un barrido de bucket ni una ruta aportada libremente. `review`, `complete`, `cleaned` y `rejected` no se procesan automáticamente. No se eliminan filas del registro durable ni reportes/fotos existentes.
- **Cuarentena conservadora:** `pending` o `quarantined` sin referencias permanecen en `quarantined` incluso tras un DELETE exitoso, con `late_upload_watch`, porque un upload incierto puede llegar tarde. Solo una compensación de fallo definitivo (`cleanup_pending`) pasa a `cleaned`. No se inventa un plazo tras el cual una cuarentena quede resuelta.
- **Sin secretos en errores:** salida JSON y warnings con UUID/códigos controlados; sin cuerpos Storage, cabeceras, DSN, trazas del driver ni claves. El diagnóstico oculta un `last_error` ajeno a los códigos conocidos como `unrecognized_error`. Los errores de configuración/conexión se capturan también antes de crear el servicio.

**Idempotencia entre servicios:** una nueva pasada sobre `cleaned` no vuelve a enviar DELETE; una selección atrasada respeta la nueva fecha. Sin embargo, si Storage confirma DELETE y el proceso muere antes de confirmar PostgreSQL, la recuperación tiene que repetir la petición sobre **la misma ruta propia**, aceptando la ausencia idempotente. Se comprueba este caso con caída real de proceso: dos peticiones HTTP, un solo objeto retirado y un objeto de control intacto. No se promete exactamente una llamada externa. `attempts` cuenta intentos confirmados en BD; una caída anterior al commit puede dejar una llamada HTTP sin incremento confirmado. La consistencia sigue siendo eventual.

#### Uso manual controlado

Los ejemplos siguientes son para un **entorno de pruebas aislado previamente identificado y configurado por el operador**. Se usa la configuración segura existente del backend; no poner DSN/clave en argumentos ni editar `.env` del repositorio. No ejecutarlos con `--execute` contra el Supabase compartido. Allí, mientras no se autorice/aplique 003, la guardia debe rechazar la ejecución.

Desde la raíz del backend:

```powershell
# Diagnóstico predeterminado: sin escrituras, reclamaciones ni llamadas a Storage.
.venv\Scripts\python.exe -m app.reconcile_photos --limit 20

# Inspección de un UUID conocido; sustituir el marcador por un UUID del ensayo.
.venv\Scripts\python.exe -m app.reconcile_photos --operation-id <UUID_DEL_ENSAYO>

# Una pasada de compensación de trabajos vencidos; no es un daemon.
.venv\Scripts\python.exe -m app.reconcile_photos --execute --limit 20

# Mismo control por UUID, conservando next_attempt_at.
.venv\Scripts\python.exe -m app.reconcile_photos --execute --operation-id <UUID_DEL_ENSAYO>

# Preparar parada cooperativa con una ruta de marcador absoluta del operador.
.venv\Scripts\python.exe -m app.reconcile_photos --execute --limit 20 --stop-file C:\OPERACION\reconciler.stop
```

`--limit` acepta 1–1000, predeterminado 100. Los marcadores `<UUID_DEL_ENSAYO>` no son comandos listos para copiar. En Linux, usar el intérprete absoluto del entorno correspondiente y la misma invocación `-m app.reconcile_photos`.

El diagnóstico abre una transacción **REPEATABLE READ READ ONLY**, exige `SHOW transaction_read_only=on`, limita consultas a 15 s/locks de lectura a 2 s y finaliza con ROLLBACK. Produce `read_only=true`, `claims_work=false`, fecha de observación, `summary` con conteos de todos los estados y hasta `limit` detalles ordenados por fecha/UUID. Cada detalle incluye estado, inspección, intentos, próximo intento, `candidate_due` y error saneado. Con UUID, el resumen queda limitado a ese UUID. `referenced` indica una referencia existente, no una comprobación de bytes en Storage. La observación puede quedar desactualizada; no demuestra que un trabajo esté libre de bloqueos. No requiere clave Storage, pero sí configuración de conexión/URL del backend y compatibilidad 003. `--execute` exige configuración de Storage antes de reclamar filas.

| Código de salida | Interpretación operativa |
| --- | --- |
| 0 | Pasada sin resultados que requieran atención; puede incluir `busy` o `not_due`. No certifica que la cola esté vacía ni que no existan `review` fuera del lote |
| 1 | Resultado `deferred`, `cleanup_pending`, `quarantined`, `review` o UUID inexistente; en diagnóstico también `pending` y los estados pendientes del resumen completo |
| 2 | Esquema no verificable/incompatible, configuración ausente, conexión/consulta fallida o error controlado del ejecutor. No asumir que no hubo efectos si falla después de una llamada externa |
| 130 | Parada solicitada; el trabajo externo ya iniciado se drena y se conserva lo no procesado |

JSON en stdout; warnings saneados en stderr. Conservar ambos más código de salida, inicio/fin y duración en el supervisor. Un 0 no sustituye la consulta global de estados ni el heartbeat.

#### Programación posterior, supervisión y parada

**No se instaló ni habilitó ninguna tarea.** Después de validar Storage real y aprobar el despliegue, usar un único responsable/planificador, intérprete y directorio absolutos, identidad de servicio con configuración protegida y política de no iniciar otra instancia. Propuesta inicial: una pasada por minuto con `--limit 20`; medir duración y cola antes de fijar el timeout y volumen. Windows: “No iniciar una nueva instancia”; Linux: timer/servicio sin solapamiento; orquestador: prohibir ejecuciones paralelas del mismo job. Los bloqueos PostgreSQL son la defensa si aun así coinciden dos hosts. Coordinar failover y una misma ruta de parada en cada host; un archivo local no detiene otros servidores.

Monitorizar con el diagnóstico READ ONLY y la consulta de 6.9: totales por estado, pendientes vencidos/antigüedad, `attempts`, próximo intento y códigos de error. Para contar trabajos accionables, filtrar `state IN ('pending','cleanup_pending','quarantined')`; las fechas de estados terminales no son cola pendiente. Supervisar `review` por separado, porque nunca entra en el lote automático. Alertas iniciales a ensayar: código 2 inmediato, `review` nuevo, dos pasadas/heartbeats ausentes, crecimiento de limpieza pendiente o vencimiento >5 min. Las cuarentenas requieren otro SLA: pueden mantenerse por vigilancia aun cuando el objeto esté ausente. No reiniciar en bucle ni cambiar estados para silenciar alertas.

**Parada:** primero deshabilitar nuevas invocaciones en el planificador futuro; luego enviar SIGINT/Ctrl+C o SIGTERM (SIGBREAK cuando exista), o crear el archivo indicado por `--stop-file`. Se comprueba antes de reclamar, antes de DELETE y entre trabajos. Si ya hay una llamada Storage en curso, dejarla terminar y confirmar/registrar su resultado; el proceso devuelve 130 sin empezar el siguiente trabajo. El CLI nunca crea ni elimina el marcador: debe permanecer mientras la operación esté suspendida. Al reanudar, revisar diagnóstico, retirar deliberadamente el marcador y habilitar el planificador. En esta etapa se prueba la parada por archivo, no la integración con un supervisor real.

No usar terminación forzada como parada habitual. Ante una caída dura, PostgreSQL libera los bloqueos; iniciar otro proceso con la misma configuración/003 y respetar el próximo intento. Puede repetirse el DELETE exacto si el commit de la compensación quedó incierto. No hay que resetear un lease ni borrar registros. Los timeouts actuales por consulta y cliente HTTP no son un límite global del lote; ensayar el tiempo de drenaje con red real antes de configurar límites del supervisor.

**Errores de recuperación:**

1. `schema_not_ready`/código 2: detener ejecución y verificar despliegue, catálogo y conectividad; nunca saltar la guardia ni aplicar migraciones automáticamente.
2. `cleanup_failed`: verificar red, bucket, permisos y disponibilidad con el operador del entorno; respetar backoff y repetir la pasada cuando venza. 403, 404 y respuestas inválidas no demuestran ausencia y no concluyen limpieza.
3. `commit_unknown`, `upload_unknown` o `late_upload_watch`: recuperar primero conectividad y releer con bloqueo/referencias. Conservar cuarentena e historial; no borrar manualmente archivos ni forzar `cleaned`.
4. `review`, colisión, bucket/ruta o referencia discrepantes: suspender automatización de ese caso y revisar identidad, metadatos y objeto con acceso autorizado. Documentar una resolución explícita; el ejecutor no ofrece un comando para modificar estados/fechas ni retirar cuarentenas.
5. Acumulación/`busy` persistente: revisar transacciones activas, escritores y planificadores; no terminar transacciones ajenas ni resolverlo eliminando datos. Atender la causa y volver al diagnóstico.

#### Pruebas y evidencia de esta etapa

El runner existente incorpora `--phase reconciler`, con 15 casos nuevos. Usa PostgreSQL 17.11 en Docker propio, puerto aleatorio ligado a `127.0.0.1`, base/label/nonce únicos y guardia de aislamiento; aplica 001+003 solo allí. Storage es un diccionario de prueba o un servidor HTTP local con rutas/bytes ficticios. No se sustituye la concurrencia por SQLite ni se usan credenciales Supabase reales.

```powershell
.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase reconciler
.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase all
```

| Cobertura nueva | Casos | Resultado específico comprobado |
| --- | --- | --- |
| Recuperación, repetición y próxima fecha | 2 | Trabajo recuperado; terminal sin segundo DELETE; descubrimiento atrasado devuelve `not_due` |
| Fallo temporal de Storage y recuperación | 1 | Estado/fecha/intentos durables, espera respetada, siguiente pasada recupera; secreto ficticio ausente en logs/salida |
| Diagnóstico estricto | 1 | Funciona con fila bloqueada por otro escritor, cero commits/FOR UPDATE/Storage, filas idénticas y errores saneados |
| Esquema incompatible o solo 001 | 4 | Diagnóstico y ejecución rechazados antes de procesar; no crea estructuras ni toca objetos |
| Configuración Storage ausente | 1 | Ejecución rechazada; observación READ ONLY disponible sin clave |
| Dos procesos CLI independientes | 1 | Uno reclama, otro devuelve `busy`; repetición posterior no elimina de nuevo |
| Commit original incierto | 2 | Ningún DELETE durante transacción activa; commit confirmado preserva foto, rollback permite compensar |
| Caída del conciliador y reinicio | 2 | Después de DELETE/antes de commit y después de commit; recuperación conserva objeto ajeno y estados consistentes |
| Parada cooperativa | 1 | Drena una operación, devuelve 130, deja siguiente trabajo pendiente; proceso nuevo lo recupera |

Primera fase específica: **15 aprobadas, 0 fallidas/errores/omitidas**, 83,79 s. Evidencia: `.test-artifacts/reciwise-d2-test-59e66bba828349f49463668f820a2d60/pytest.xml`. Primera regresión integral: **273 aprobadas y 12 omitidas**, 222,65 s. Después se ajustó el diagnóstico para devolver código 1 también ante intenciones `pending`, y se comprobó en el caso de configuración Storage ausente.

**Resultado integral definitivo:** **273 aprobadas, 0 fallidas, 0 errores y 12 omitidas**, **201,58 s**. Evidencia: **`.test-artifacts/reciwise-d2-test-35250a3d14c14207ba2f29af41b78c95/`**, con `pytest.xml` (285 casos), `environment.json` (PostgreSQL 17.11, identidad de contenedor/base local y hashes) y `scope-verification.json` (alcance y hashes del código). El runner retiró su contenedor al terminar. No se ejecutaron pruebas remotas ni escrituras en el proyecto compartido.

| Grupo de la ejecución definitiva | Aprobadas | Omitidas |
| --- | --- | --- |
| Suite D2 previa, incluidas guardia FastAPI y auditoría | 258 | 12 |
| Nuevos casos del conciliador | 15 | 0 |
| **Total** | **273** | **12** |

Las 12 omisiones siguen siendo **2 de persistencia con recursos piloto ausentes en esta base, 9 de PostgREST anónimo real y 1 de JWT ciudadano real**. No se crean duplicados para satisfacer las primeras ni se sustituyen las otras por simulaciones. Los 96 casos previos de API/permisos usan SQLite y sustituciones explícitas; las carreras, reclamaciones y reinicios nuevos usan PostgreSQL real. Storage de esta etapa es simulado, no Supabase real.

`compileall` de `app/tests/scripts`, la ayuda CLI, `git diff --check` y la comprobación de espacios/UTF-8 de los ocho archivos cambiados/nuevos pasaron. Persiste una advertencia preexistente de Starlette/httpx; no se cambiaron dependencias. De los 90 archivos de la instantánea inicial, solo cambiaron los seis previstos, más dos archivos nuevos de pruebas; los 84 restantes conservan su hash, incluidos frontend/IA, `.env`, credenciales, migraciones y manifiesto de esquema. No se sobrescriben cambios locales anteriores ni se hacen commits/push.

#### Validación pendiente con Supabase aislado real

El diseño detallado de casos remotos de **6.9** sigue pendiente, no aprobado por estos tests. Para habilitarlo:

**Plan aplazado por decisión posterior del responsable, recogida en 6.12.** Los pasos siguientes no se ejecutan ahora ni se trasladan al principal. Se conserva el diseño para cuando exista un entorno real de prueba autorizado.

1. Obtener un proyecto Supabase **aislado y autorizado**, distinto del compartido; verificar ref/hosts API/BD por allowlist. Respaldar y aplicar 003 solo en ese entorno autorizado, comprobar guardia CLI y FastAPI. Usar identidades ficticias y bucket privado exclusivo; claves por configuración segura, sin cambiar `.env` del repositorio.
2. Registrar UUID/rutas/hashes propios más objetos de control semejantes y una foto confirmada. Probar API real, RLS y acceso Storage; confirmar que usuario ajeno no puede acceder. No copiar fotografías ciudadanas ni credenciales de producción.
3. Inducir fallo definitivo después de upload, fallo temporal de DELETE/403/404/5xx/acuse inválido y pérdida de respuesta, comprobando bytes, metadatos e historial antes/después. Verificar que el DELETE con ruta exacta y la ausencia idempotente del servicio real coinciden con el supuesto del simulador.
4. Perder la confirmación de commit con resultado confirmado y abortado; bloquear también la consulta de resolución. Ejecutar dos conciliadores, matar únicamente procesos del ensayo antes/después del commit, reiniciar y verificar cero borrados de fotos publicadas o controles.
5. Retardar el upload real más allá del primer DELETE; comprobar vigilancia y reintento de cuarentena. Ensayar parada/señales y fallos de red con el supervisor propuesto, midiendo drenaje, backlog y alertas antes de programar nada en un servicio real.
6. Conservar evidencia saneada y revisar resultados con el responsable antes de habilitar programación o solicitar ventana del compartido. Ninguna prueba remota ni limpieza se hace fuera de objetos propios autorizados.

**Riesgos pendientes:** Storage real y permisos/semántica de DELETE aún no ensayados; consistencia eventual y posible repetición idempotente tras caída; cuarentenas de larga duración sin retiro automático; latencia/bloqueos por reporte durante red y capacidad operativa sin medir. No hay scheduling ni alertas desplegadas; tampoco se han cerrado los gates de respaldo/restauración, sondas y autorización de 6.9. **NO-GO para migrar/desplegar en el compartido; Sprint 1 no cerrado.**

### 6.12. Revisión de alcance D2 y prioridades para el 19 de noviembre

**Decisión vigente:** mantener el proyecto Supabase principal para la aplicación y continuar las verificaciones con el PostgreSQL aislado local y los servicios simulados existentes. No crear un segundo proyecto por ahora, no aplicar 003 al compartido, no hacer pruebas destructivas allí ni configurar tareas reales. No se modifican credenciales, `.env`, backend, frontend, IA, migraciones ni pruebas para esta revisión. No hay push.

La revisión comparó `app/main.py`, esquemas/modelos, pruebas, contratos D3, frontend leído sin cambios y guías existentes. **Las 15 operaciones de negocio de Sprint 1 están implementadas.** No se encontró un endpoint del inventario D2 pendiente de construir. Los recursos municipales tienen API de vehículos/sitios/turnos, pero sus pantallas no están en el frontend actual. Esto debe decidirse en el guion; no se inventa una ausencia del backend para justificar un CRUD nuevo.

#### Qué falta para la aceptación funcional

1. **Entorno y versión de demo compatibles:** el backend actual exige 003. Si el principal sigue con 001, la guardia rechazará el arranque; `/health` no habilita negocio ni sustituye `/ready`. No se consultó el principal ahora ni se verificó qué versión está desplegada. Conservar la configuración no autoriza conectar esta rama al esquema anterior ni desactivar la guardia.
2. **Evidencia de un recorrido integrado de la misma versión:** `/me`, ubicación confirmada en móvil o navegador, POST 201, reporte propio, mismo UUID en listado/mapa municipal y rechazo 403 al ciudadano. Recargar/reiniciar sin perder el reporte. Fotografías opcionales y errores sin duplicar el reporte. Las simulaciones y el GPS físico pendiente deben declararse; la suite API aislada no se presenta como demo real móvil/Supabase.
3. **Revisión y aceptación del responsable:** fijar alcance de fotos/recursos, entorno, código y resultados. Los resultados manuales M01–M13 se mantienen como históricos; no sustituyen por sí solos esa aceptación de la versión nueva. No se marca cerrado Sprint 1 automáticamente.

La falta de autorización para 003 **bloquea el despliegue de esta versión en un principal anterior**, pero no la preparación funcional local. Si la hackatón requiere esta rama contra el principal, hay que resolver esa autorización/compatibilidad en una revisión posterior. El runner local crea y destruye su base: sirve como verificación, no como servidor persistente de demo para React.

#### Desarrollo Sprint 2 que puede avanzar ahora

El orden propuesto es cerrar el contrato de `CONTRATOS_D3.md`, mapear reportes/eventos reales a su DTO con fixtures, y añadir revisión municipal de agrupación con persistencia/auditoría en `events`, `event_reports` y `grouping_decisions` de 001. Esos modelos/servicios/endpoints aún no están implementados; no se anuncian como existentes. La aprobación corresponde al encargado y agrupar no cambia un reporte a `atendido`.

Para recursos se reutiliza lo que ya existe. Solo si el flujo lo exige se acordará una consulta municipal mínima de choferes, hoy ausente, sin perfiles públicos. Las propuestas/aprobación de rutas necesitan acordar entradas/salidas D3 y probar 002 en local cuando se implemente esa persistencia; 002 no es requisito del reporte ni de la agrupación de Sprint 1. No se implementa IA ni optimización en esta revisión.

El [plan D2](PLAN_D2_HACKATON.md) fija criterios verificables, dependencias y una secuencia propuesta: aceptación de Sprint 1 hasta el 1/11; primera integración de Sprint 2 del 2 al 8/11; recorrido conjunto del 9 al 13/11; estabilización del 14 al 16/11; congelación/ensayos 17–18/11 y hackatón el **19/11/2026**. Son fechas de coordinación propuestas, no servicios programados ni compromisos ya aceptados.

#### Pruebas aplazadas y límites de la evidencia

La tabla del plan distingue las pruebas de Storage real pendientes: privacidad/descarga/expiración de URLs, concurrencia de objetos reales, fallo de persistencia tras upload, commit incierto/resolución no disponible, acuses DELETE/errores/reintentos, uploads tardíos/reinicio y preservación de controles. Se conservan los diseños de 6.9/6.11. **No se ejecutan contra el principal** ni se considera que la simulación demuestra esos comportamientos del servicio remoto. Tampoco se exige crear ahora RECIWISE-TEST para seguir con funciones independientes.

Las doce omisiones de la suite mantienen su origen: dos de recursos piloto, nueve de acceso PostgREST anónimo real y una de JWT ciudadano real. La matriz adicional de Storage real es trabajo diseñado/pendiente, no nuevos tests aprobados ni skips producidos por esa suite. La autenticación criptográfica y permisos probados con claves ficticias, y los reinicios/exclusiones probados en PostgreSQL real local, conservan su validez dentro de su alcance.

Comando reutilizado para la regresión D2:

```powershell
.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase all
```

Usa un contenedor propio de PostgreSQL, nonce/base únicos y puerto ligado a `127.0.0.1`; aplica 001+003 solo allí, fuerza configuración ficticia de servicios, elimina variables de pruebas remotas y retira su contenedor al terminar. No se usa `.env` como destino de esas pruebas.

**Reejecución de esta revisión: 273 aprobadas, 0 fallidas, 0 errores y 12 omitidas**, **117,82 s**. Evidencia: **`.test-artifacts/reciwise-d2-test-8f58cacd7ce54b0dbf82529262962e02/`**, con `pytest.xml` (285 casos), `environment.json` (PostgreSQL 17.11, localhost, identidad y hashes) y `scope-verification.json`. Son los escenarios existentes, no se añadieron tests para aumentar el contador. Persiste la advertencia preexistente Starlette/httpx.

Solo se modifican documentación/guías: este archivo, `README.md`, `SPRINT1_PASO_A_PASO.md` y el nuevo `PLAN_D2_HACKATON.md`. Se comprueban enlaces locales y espacios; se conservan backend, tests, frontend, IA, migraciones, credenciales y `.env` respecto de la instantánea inicial. El runner retiró su contenedor; no hubo consultas/cambios en Supabase compartido ni se creó infraestructura remota.

**GO/NO-GO:** GO para desarrollo y regresiones locales, NO-GO para aplicar 003/desplegar la rama nueva en el principal. Siguen pendientes la revisión del despliegue, Storage real y su supervisión/respaldo; no son una prohibición de trabajar en el adaptador/revisión municipal local. No se declara cerrado Sprint 1.

### 6.13. Prueba integrada ciudadano → PostgreSQL → encargado → Leaflet

**Fecha:** 29/10/2026, America/Lima. Se revisaron frontend, FastAPI, modelos/esquemas, guardia 003 y pruebas. Los antiguos tests de navegador interceptaban los datos de negocio y usaban un token ficticio sin firma válida; el worker de concurrencia sustituía al actor. Se conservan para sus usos previos, pero no son evidencia de este nuevo recorrido autenticado.

#### Entorno y seguridad

El runner existente incorpora `--phase integrated`. Crea PostgreSQL 17.11 propio, base/nonce únicos y puerto ligado a `127.0.0.1`, aplica **001+003 únicamente allí**, añade una segunda identidad ciudadana ficticia y lanza servicios locales/Chrome. No conecta el backend actualizado al Supabase compartido.

| Componente | Comprobación real | Simulación o límite |
| --- | --- | --- |
| React, SDK Supabase y Leaflet | Código actual servido por Vite, clic/arrastre/confirmación, login y fotos en Chrome headless | No es un móvil físico ni una sesión remota Supabase |
| FastAPI | Uvicorn y HTTP reales; guardia 003 al arrancar y tras el reinicio | No es un despliegue de la rama en el principal |
| Auth/JWT | Firma ES256 efímera, JWKS por HTTP y validación original de firma/issuer/audience/expiración/perfil | Login/refresh/user/logout son un simulador local; no Supabase Auth remoto |
| Roles | Perfil PostgreSQL decide; metadata ficticio que afirma ser encargado no eleva al ciudadano | No hay selección de roles ni cabecera de actor que sustituya al JWT |
| Persistencia | PostgreSQL real; SELECT independiente READ ONLY/ROLLBACK y filas iguales tras reiniciar FastAPI | No se reinicia PostgreSQL ni se garantiza persistencia fuera del contenedor propio |
| Fotos | Funciones originales de Storage por HTTP: upload, firma, descarga, DELETE y errores | Storage simulado, con PNG ficticio y objeto de control |
| Mapa | Marcador/popup Leaflet de los datos guardados | Teselas sustituidas por PNG; solicitudes externas bloqueadas, no calles reales |

No se añaden bypasses ni opciones de pruebas a `app/` o al frontend de producción. El launcher no instala overrides de `get_current_actor`, `get_db` ni `verify_schema`. Solo sustituye la fábrica de sesiones de fotos en su proceso de pruebas para provocar un CHECK real después del upload simulado; conserva el coordinador y compensación existentes.

Los controles de evidencia/fallos/reinicio pertenecen al **simulador de pruebas**, ligados a loopback y una clave efímera de control; no son endpoints de FastAPI ni se despliegan. El worker exige marcador aislado, igualdad del destino de BD y URL local antes de importar la aplicación. La clave privada ES256, contraseña y sesiones se generan en memoria, sin archivos; se sanea la salida si Playwright incluye cabeceras en un error. No se guardan trazas/vídeos de sesión. Las capturas muestran datos ficticios después del login.

#### Reproducción

Requisitos: entorno Python/dependencias existentes, dependencias Node del frontend, Docker Desktop y Google Chrome instalado. El proceso usa puertos libres y configuración de pruebas por variables del proceso, sin editar `.env` ni reutilizar servidores abiertos.

```powershell
# Tipos, 39 tests frontend, build y cuatro escenarios UI/API/BD integrados.
.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase integrated

# Regresión D2 independiente del navegador.
.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase all
```

El build ejecuta `tsc --noEmit` y `vite build --outDir` en la evidencia, sin sustituir el `dist` anterior del usuario. La fase integrada no se incluye en `all` ni se suma al contador backend. El `testIgnore` del Playwright anterior separa suites con requisitos de servidores diferentes. Se cierran procesos propios y se retira el contenedor: es un ensayo reproducible, no un servidor persistente para presentar el 19/11.

#### Checklist ejecutado de aceptación local

| Estado | Criterio | Evidencia |
| --- | --- | --- |
| [x] | Login ciudadano válido de pruebas | SDK real recibe ES256; `/me` 200, rol ciudadano desde PostgreSQL pese al metadata privilegiado del simulador |
| [x] | Registro React/Leaflet | Clic, arrastre y confirmación; ningún POST antes de confirmar/enviar; coordenadas numéricas, POST 201 |
| [x] | Persistencia | SELECT READ ONLY independiente confirma UUID, autor, descripción y coordenadas iguales al payload |
| [x] | Consulta propia | React consulta `/reports/mine`; HTTP independiente 200 incluye el UUID guardado |
| [x] | Consulta municipal | Login encargado, `/municipal/reports` 200 con el mismo objeto, UUID y coordenadas |
| [x] | Mapa municipal | Círculo Leaflet, popup correcto, apertura de fotos y captura inspeccionada |
| [x] | Permisos/JWT | Ciudadano → municipal 403; ciudadano ajeno → detalle/fotos 404 y exclusión de su listado; token ausente/malformado → 401 |
| [x] | Foto con Storage simulado | Upload 201, slot/metadatos en PostgreSQL, consulta 200, imagen decodificada en ambas vistas y descarga de bytes idénticos al PNG |
| [x] | Reinicio FastAPI | PID distinto, `/ready` 200 con guardia real; filas/metadatos antes/después iguales; recarga conserva reporte y sesión |
| [x] | Validación/comunicación | Ubicación sin confirmar bloquea envío; payload inválido por HTTP 422; interrupción de transporte sin filas nuevas y reintento crea un solo reporte; CORS ajeno rechazado |
| [x] | Fallos de foto/persistencia | Storage simulado 503 → API/UI 502 y cuarentena; CHECK real tras upload → API/UI 503 y compensación; reintento 201 sin duplicar reporte |
| [x] | Objeto de control | `controls/keep.png` intacto; solo se elimina la ruta propia de la operación abortada |

El pase final usa el reporte **ficticio** `91669045-35dd-4836-9418-2c3f6d16ff0f`: coordenadas `-12.053758333689268, -75.3006362915039` iguales en payload, SQL y consulta municipal. SHA-256 del PNG recuperado: `6b1048f8a6d40bac0b2954c18fefa40c4ea7a96120fc2e54b7317c0e43c2bbec`. Los procesos FastAPI cambiaron de PID 26628 a 16952 y el JWKS se obtuvo dos veces, una por proceso.

La subida con resultado incierto conserva `quarantined`; el fallo definitivo queda `cleaned` tras compensar y el reintento exitoso `complete`. No se altera la cuarentena para simular una cola vacía. Datos y objetos ficticios se retiran con el entorno propio.

#### Resultados y evidencia

| Ejecución | Aprobadas | Fallidas/errores | Omitidas | Resultado |
| --- | --- | --- | --- | --- |
| Chrome/React/FastAPI/PostgreSQL nuevos | 4 | 0 | 0 | 26,89 s, pase final |
| Vitest frontend | 39 | 0 | 0 | Tipos TypeScript correctos |
| Build Vite | — | 0 | — | Correcto; advertencia preexistente de chunk >500 kB |
| Regresión D2 existente | 273 | 0 | 12 | 77,40 s |

**Integración final:** `.test-artifacts/reciwise-d2-test-5096c791ea64401e8242848ecaae6118/`:

- `browser-junit.xml`/`browser.log`: cuatro escenarios/salida saneada; `vitest.json`, logs y `frontend-build/`.
- `report-flow.json`: payload/respuesta, SQL y hash de bytes recuperados; `restart.json`: PIDs y lecturas SQL reales antes/después.
- `photo-failures.json`: estados y única ruta compensada; `http-*.json`: método/ruta/HTTP, sin cuerpos/cabeceras.
- `citizen.png`/`municipal-map.png`: capturas inspeccionadas, mapa base e imagen ficticios.
- `environment.json`/`integrated-environment.json`/`scope-verification.json`: identidad local, alcance y hashes.

**Regresión D2:** `.test-artifacts/reciwise-d2-test-7dbf1ec79fc94f20ac9db710c0da51ae/pytest.xml`, 285 casos: 273 aprobados y 12 skips históricos (2 de recursos piloto, 9 PostgREST anónimos reales, 1 JWT ciudadano real). No se declaran aprobados por las pruebas locales nuevas.

Primer intento integrado: **2 aprobados y 2 errores** del lector de evidencia nuevo; configuraba `dict_row` antes de que el helper READ ONLY comprobara una tupla. Se corrigió solo ese helper de pruebas. El siguiente pase dio 4/4 (32,33 s). El pase final añade igualdad de bytes/saneamiento de diagnósticos y vuelve a dar 4/4 (26,89 s). No se detectó un fallo funcional que requiera corregir la aplicación. Siguen las advertencias conocidas Starlette/httpx y tamaño de chunk.

#### Archivos de esta tarea

- Nuevos: `tests/integrated_services.py`, `tests/_integrated_api.py`, `tests/run_integrated_sprint1.py`, `frontend/e2e/integrated.config.ts` y `frontend/e2e/integrated/sprint1.spec.ts`.
- Ajustados: `tests/run_isolated_postgres.py` (fase), `frontend/playwright.config.ts` (separación de suites) y documentación `API_SPRINT1.md`/`PLAN_D2_HACKATON.md`.
- Sin cambios: producción backend/frontend, migraciones/rollback/manifiesto, dependencias, IA, `.env` y credenciales. Se preservan cambios locales previos; no hubo push.

#### Dictamen

**Listo para revisión de aceptación funcional de Sprint 1 D2 en el entorno local aislado probado.** El recorrido pedido está ejecutado; el responsable puede revisar checklist, resultados y capturas. No se declara firmado/aceptado por el equipo ni cerrado Sprint 1.

Pendientes:

- [ ] Revisión/aceptación del responsable y elección/ensayo del entorno de presentación persistente.
- [ ] Móvil físico, GPS/permiso del sistema y HTTPS si forman parte de la demo; aquí se usó clic/arrastre.
- [ ] Auth/JWKS y Storage remotos, privacidad/expiración, fallos/commit incierto/reintentos/controles de 6.9–6.11. El simulador no los aprueba.
- [ ] Autorización de 003/despliegue coordinado, diagnóstico/respaldo/restauración, readiness y operación/supervisión del conciliador en el alojamiento.

**NO-GO para desplegar esta rama en el principal sin esas revisiones/autorización. GO para contratos/adaptador, eventos, revisión de agrupaciones y preparación de propuestas de rutas de Sprint 2 en local.** No se consulta ni modifica el principal en esta tarea.

## 7. Contratos de integración

### 7.1. D1/React con D2/FastAPI

| Flujo | Lo que envía React | Lo que consume React |
| --- | --- | --- |
| Identidad | Bearer de la sesión Supabase a `/me` | `id` y rol efectivo del perfil |
| Registro ciudadano | JSON `ReportCreate`, con latitud/longitud como números y observación con zona horaria | `ReportOut`, HTTP 201 e ID creado |
| Consulta propia | Bearer y, si procede, `limit`/`offset` | Array `ReportOut[]` de esa cuenta |
| Fotos | FormData con `file` al reporte propio | `PhotoOut` 201; después GET para las URLs temporales |
| Consulta municipal | Bearer de encargado y filtros documentados | Array de reportes con coordenadas, IDs, fechas y estado |
| Vehículos | JSON `VehicleCreate` o `AvailabilityPatch` según operación | `VehicleOut` o array |
| Sitios | JSON `SiteCreate` al registrar | `SiteOut` o array; sus UUID se usan en los turnos |
| Turnos | JSON `ShiftCreate` con UUID existentes | `ShiftOut` o array; manejar 422 de validación y 409 de reserva |

La selección GPS/mapa es responsabilidad de la interfaz. Antes de confirmar y enviar no se registra ubicación en FastAPI. `source`, precisión, confirmación del marcador, `citizen_id`, `created_at`, estado y rol no son campos de `ReportCreate`. FastAPI sigue validando los datos aunque React ya los haya validado.

No hay endpoint para enumerar choferes/perfiles en esta API; al crear un turno se necesita un UUID de chofer autorizado ya existente. Si una interfaz municipal necesita buscar esos perfiles, ese contrato debe definirse explícitamente sin inventar una ruta en el frontend.

### 7.2. D2/D3 para agrupación posterior

La propuesta formal existente está en [CONTRATOS_D3.md](CONTRATOS_D3.md). Es un **contrato por acordar**, no un endpoint en producción.

| Origen D2 | Campo propuesto D3 | Observación |
| --- | --- | --- |
| `reports.id` | `id` | UUID de reporte |
| `reports.description` | `descripcion` | Conservar negaciones y números relevantes |
| `reports.latitude`, `reports.longitude` | `latitud`, `longitud` | Coordenadas WGS84 numéricas |
| `reports.observed_at` | `fecha_observacion` | Momento observado, con zona horaria |
| `reports.created_at` | `fecha_reporte` | Recepción fijada por el servidor, distinta de la observación |
| `reports.waste_type` | `tipo_residuo` | Opcional; no inventar valor |
| `event_reports.event_id` | `evento_asociado_id` | Relación operativa existente o null, no etiqueta de evaluación |
| `events.state`, `events.closed_at` | `estado_evento`, `fecha_cierre_evento` | Datos reales del candidato para distinguir recurrencias y eventos cerrados |

La respuesta operativa propuesta usa `reporte_nuevo_id`, `evento_candidato_id`, `similitud_texto`, `distancia_metros`, `diferencia_horas`, `sugerencia`, `motivos` y `version_configuracion`. Las sugerencias propuestas son `agrupar_candidato`, `requiere_revision` y `mantener_separado`; no son idénticas a la enumeración de decisiones persistidas de `grouping_decisions` y requieren un mapeo acordado.

El prototipo local ya integrado en `d3/probar_similitud.py` compara pares de CSV y produce `id_1`, `id_2`, similitud, distancia, diferencia temporal, tipos de residuo y versión. **Todavía no implementa el contrato operativo reporte/evento**, no se invoca desde FastAPI y no escribe vínculos ni decisiones en BD. No se modificó ni ejecutó su modelo en esta tarea.

Para conectar ambos componentes faltan el adaptador D2 de datos operativos, el mecanismo de revisión/autorización y la persistencia auditable de decisiones. `evento_esperado_id` pertenece a datasets de evaluación; nunca debe pasar al modelo, al JSON de negocio ni a `event_reports` como si fuera un UUID real.

### 7.3. D2/D3 para planificación y ejecución posterior

Para Sprint 2, D2 deberá reunir eventos abiertos/revisados, prioridades y factores, turno y chofer, vehículo y disponibilidad/capacidad conocida, sitios de salida/descarga, tiempos de servicio y compatibilidad de intervención/acceso. D3 devolverá una propuesta con orden, fuente de matriz vial, geometría, estimaciones, eventos excluidos, configuración y limitaciones.

Las estructuras `route_plans`/`route_stops` preparan la persistencia de esas propuestas. Todavía no hay endpoints de propuestas, aprobación o ejecución, ni un optimizador conectado. Las decisiones finales, campos exactos y permisos deben acordarse antes de desarrollar la integración. Un peso o volumen desconocido permanece desconocido; no se deduce capacidad desde una descripción textual.

Para Sprint 3 quedarán los endpoints del chofer para ruta asignada, visita, evidencia de cierre, incidencia y actualización operativa de estados. La existencia de `stop_incidents` no demuestra que esas operaciones estén disponibles.

## 8. Lista de verificación de D2 y estado de cierre

Las 15 operaciones solicitadas están presentes. No se encontró una ausencia dentro de ese listado. El plan de [Sprint 1](SPRINT1_PASO_A_PASO.md) también exige una demostración integrada y evidencia de entorno; las pruebas manuales comunicadas cubren parte de esa aceptación, pero no todas las validaciones siguientes. Otros compromisos no descritos en el repositorio deben confirmarse con el equipo, no inferirse como implementados.

### 8.1. Completado y probado, con origen de evidencia explícito

- [x] Registro/login Supabase y los tres roles: **manual M01–M02**.
- [x] JWT ES256 válido en el flujo comunicado: **manual M03**. ES256 y RS256 válidos están además comprobados automáticamente con claves efímeras y JWKS local; la prueba contra el servicio remoto es un alcance distinto.
- [x] Creación/consulta ciudadana y lectura municipal de reportes/coordenadas: **manual M04–M06 y automatizadas**.
- [x] Restricción por autor de reportes y fotos y denegación a chofer en creación/detalle: **automatizadas**.
- [x] Fotos privadas, alta y visualización: **manual M07**; firma/formato/límite y permisos con Storage sustituido: **automatizadas**.
- [x] Consulta de vehículos, alta/consulta de sitios y creación/recuperación de turno: **manual M08–M10**. Parte de altas, disponibilidad y validación de turnos también está automatizada.
- [x] 422 por vehículo no disponible y 409 por ocupación: **manual M11–M12 y automatizadas**. La exclusión concurrente se verificó además en PostgreSQL aislado con 003, sección 6.8.
- [x] Ciudadano y chofer rechazados con 403 en las **ocho operaciones municipales** GET/POST/PATCH; encargado autorizado con ES256/RS256 y respuesta exitosa. Evidencia automática con JWT real de prueba y perfiles SQLite; se conserva la evidencia manual M13.
- [x] CORS local y rechazo de origen ajeno, validaciones básicas de fecha/coordenadas y rechazo sin token: **automatizadas**.
- [x] Catálogo de API contrastado con OpenAPI y pruebas D2 sin fallos: **ejecutado para este documento**.
- [x] **Longitud de descripción de 3–2000 después del recorte:** corregida en `ReportCreate.description`, con 12 casos inválidos HTTP 422 y 7 válidos HTTP 201/recuperación; sus 27 pruebas de regresión siguen pasando dentro de la suite D2 actual.
- [x] **Autenticación y permisos:** 69 pruebas sin red ni credenciales reales; JWT ausente/malformado/vencido/firma/issuer/audience incorrectos, HS256, claims obligatorias, perfil ausente y roles. Se mantienen las **96 pruebas previas correctas**, sección 6.5.
- [x] **PostgreSQL real:** 39 casos de restricciones/relaciones y 20 de roles SQL/catálogo aprobados, con `ROLLBACK` obligatorio y hashes de las nueve tablas sin cambios, sección 6.6.
- [x] **Acceso directo anónimo:** nueve tablas rechazadas por PostgREST real y clave pública, sin credencial administrativa. RLS habilitado, permisos SQL revocados; la sesión de ciudadano real sigue pendiente.
- [x] **Persistencia con identidad de prueba, evidencia anterior:** mismos recursos piloto y fotografía recuperados tras reinicios reales de procesos FastAPI, BD `READ ONLY`, Storage real y campos/bytes iguales. Aquella ejecución dio **166 aprobadas, 1 omitida** (6.6); el login real no formó parte del reinicio.
- [x] **Concurrencia de turnos:** exclusiones PostgreSQL por vehículo/chofer, contigüidad permitida, 409 y reintentos acotados ante abortos conocidos. Probado en PostgreSQL aislado, sin aplicar 003 al proyecto compartido (6.8).
- [x] **Límite estricto de fotos:** posiciones SQL 1–3 únicas/no nulas, bloqueo por reporte, seis solicitudes simultáneas y SQL directo rechazado cuando viola restricciones. Probado en PostgreSQL aislado; mismo contrato público (6.8).
- [x] **Compensación y recuperación:** intención durable, conciliador, reintentos, commit incierto sin borrado en la solicitud, preservación de referencias y tres caídas/reinicios reales. PostgreSQL real y Storage simulado; **220 aprobadas, 12 omitidas, cero fallos/errores** (6.8).
- [x] **Errores de fotos:** 413/415 antes de efectos externos, configuración ausente 503, errores/timeout Storage 502 y fallos de persistencia/confirmación 503 comprobados con los entornos explícitos de 6.8.
- [x] **Recorrido integrado React/API/PostgreSQL (6.13):** cuatro escenarios Chrome aprobados, JWT ES256/JWKS local verificado, reporte y foto desde React, SELECT independiente, mismo reporte en Leaflet municipal, permisos, fallos/reintentos y reinicio FastAPI. Auth/Storage/teselas simulados declarados; listo para revisión de aceptación local.

### 8.2. Implementado, pero pendiente de prueba específica o evidencia ampliada

- [ ] Probar renovación/rotación y fallos de disponibilidad del servicio JWKS. Las firmas/claims negativas y el perfil ausente ya están cubiertos en la sección 6.5; no confundir esos casos con una prueba de rotación o conexión al servicio real.
- [ ] Probar RS256 contra el proyecto remoto si forma parte de la compatibilidad exigida al despliegue. La validación criptográfica RS256 con JWKS local ya está probada.
- [ ] Comprobar la compensación contra un destino/bucket Supabase de pruebas expresamente autorizado. **Aplazado: no se crea otro proyecto ni se prueba destructivamente el principal ahora (6.12).** Los 413/415, 503 y 502/timeout ya están probados con PostgreSQL aislado y transportes Storage simulados; esta limitación no bloquea desarrollo independiente.
- [ ] Cubrir UUID inválidos, paginación extrema, caja geográfica invertida, chofer inválido, sitios inactivos/tipo incorrecto y fechas de turno sin zona/intervalo inválido. Varias reglas están implementadas, pero no todas tienen aserción específica.
- [ ] Completar evidencia de acceso directo con JWT real de ciudadano. Restricciones/FKs, RLS habilitado, permisos SQL y denegación REST anónima ya están comprobados en la sección 6.6. El trigger de alta de perfiles y la configuración/privacidad efectiva del bucket requieren verificaciones específicas adicionales.
- [ ] Repetir el flujo de persistencia con sesiones reales de ciudadano/encargado. El reinicio de procesos y la recuperación sin cambios de reportes, recursos, turno y foto existentes ya se comprobaron con identidad de prueba y PostgreSQL/Storage reales, sección 6.6.
- [ ] Verificar expiración/renovación real de las URLs de fotos y que el objeto no tenga acceso público permanente. M07 acredita subida/visualización, no todos esos casos.
- [ ] Ensayar dispositivo móvil físico/HTTPS y el entorno persistente de presentación, y registrar aceptación del equipo. La prueba automática integrada de navegador/API/PostgreSQL **ya se ejecutó en 6.13**; no equivale a teléfono físico ni a despliegue Supabase. Se mantiene la evidencia manual histórica.

### 8.3. Pendiente de desarrollo o corrección identificada

- [ ] **Revisar y autorizar el despliegue de 003/backend.** Las correcciones de concurrencia están implementadas y probadas en aislamiento (6.8); no han sido aplicadas al proyecto compartido. Revisar previamente sus conflictos reales y coordinar la ventana sin escrituras.
- [x] **Guardia de esquema FastAPI (6.10).** Arranque y readiness verificados, bloqueo por defecto y rechazo de 001/esquemas parciales o incompatibles; sin migraciones automáticas ni bypass de producción.
- [x] **Operación segura del conciliador (6.11).** Guardia 003, diagnóstico READ ONLY, reclamación PostgreSQL, revalidación del reintento, errores saneados, parada y recuperación comprobados con Storage simulado.
- [ ] **Cerrar el resto del NO-GO del despliegue (6.9/6.12).** Siguen pendientes Storage real, restauración, sondas/programación/supervisión y autorización de la ventana. Las guardias no habilitan el despliegue por sí solas. **GO para seguir desarrollando/verificando funciones independientes en local; no se exige un segundo proyecto ahora.**
- [ ] **Programar y supervisar el conciliador en el servidor.** El ejecutor y la recuperación tras reinicio están probados, pero no se instaló una tarea periódica. Sin ejecución periódica no hay reintentos automáticos. Resolver con revisión explícita las cuarentenas y objetos preexistentes; no borrar fotos históricas.
- [ ] Definir el nivel requerido de validación de imágenes para el piloto: actualmente se comprueban tamaño/firma básica, sin decodificación completa. No documentar esa inspección completa como ya implementada.
- [ ] Acordar con el equipo cuáles de estas correcciones y controles son criterios obligatorios de cierre del piloto y cuáles se planifican como endurecimiento posterior. La ausencia de ese acuerdo no permite declarar el Sprint terminado.

### 8.4. Reservado para Sprint 2 o Sprint 3

- [ ] **Sprint 2:** agrupación operativa/revisión de eventos, auditoría mediante `grouping_decisions`, transiciones de estados y adaptadores D2/D3.
- [ ] **Sprint 2:** propuestas de rutas, persistencia de resultados de optimización, aprobación municipal y contratos definitivos de planificación. No hay que implementar IA/optimizadores dentro de esta tarea D2.
- [ ] **Sprint 3:** consulta de ruta asignada al chofer, ejecución de paradas, evidencia de cierre e incidencias operativas.
- [ ] Confirmar aplicación de la migración 002 cuando se vaya a utilizar; no se ejecuta por el solo hecho de documentarla.

**Estado de alcance:** concurrencia/consistencia, guardia y conciliador verificados en PostgreSQL aislado; nueva prueba integrada UI/API/BD ejecutada en 6.13. **273 pruebas D2 aprobadas y 12 omitidas, 39 frontend y 4 integradas aprobadas; cero fallos/errores finales, tipos/build correctos.** Se conservan producción backend/frontend, contratos, migraciones, IA, credenciales y cambios previos. No se consultó ni migró Supabase compartido; no hubo commits, push ni tareas reales. **Listo para revisión de aceptación funcional local; GO para Sprint 2 local, NO-GO para 003/despliegue de la rama en el principal.** Pendientes: firma del responsable, entorno persistente/móvil de demo, servicios reales y preparación del despliegue. **No se declara terminado el Sprint 1.**
