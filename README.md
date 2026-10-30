# RECIWISE — Backend y base de datos inicial (Sprint 1)

**Estado real (29/10/2026):** API FastAPI de reportes/recursos, frontend React de pruebas y prototipo D3 de similitud. D2 tiene concurrencia, recuperación y guardia de esquema comprobadas en PostgreSQL local aislado con Storage simulado; la evidencia manual anterior de Supabase se distingue de esa suite en [API_SPRINT1.md](docs/API_SPRINT1.md). La agrupación operativa, aprobación de rutas y ejecución por chofer **aún no están implementadas**. La aceptación integrada y el despliegue de la versión nueva siguen pendientes.

**Prioridad hackatón: 19 de noviembre de 2026.** Se conserva el proyecto Supabase principal; no se crea otro proyecto ahora, no se aplica 003 al compartido ni se hacen pruebas destructivas allí. Desarrollo y regresión continúan localmente. **GO local / NO-GO para desplegar esta rama en el principal**, que requiere esquema 003. Ver [pendientes estrictos y secuencia D2](docs/PLAN_D2_HACKATON.md).

**Frontend de pruebas (28/10/2026):** [contratos y resultados comprobados](frontend/README.md). Incluye React + Vite, Supabase Auth, Leaflet, fotos e historial HTTP. Sus instrucciones iniciales de esquema deben leerse con el requisito 003 del backend actual, explicado abajo.

**Actualización Sprint 1 (29/10/2026):** [comparación e integración de la entrega local](docs/INTEGRACION_SPRINT1.md). Se integraron las diferencias del formulario GPS/mapa y el [prototipo semántico D3](d3/SPRINT1_MODELO.md), manteniendo los contratos y permisos existentes. La inferencia con el modelo real sigue pendiente.

## Arquitectura

- Frontend local de pruebas: React + Vite + TypeScript + Supabase Auth + Leaflet (`frontend/`).
- Backend: Python + FastAPI (D2).
- Persistencia: PostgreSQL de Supabase; Supabase Auth emite el token JWT.
- Fotos opcionales: Supabase Storage en bucket **privado**.
- D3: consumirá reportes y devolverá propuestas de agrupación/rutas a través de contratos a consensuar (`docs/CONTRATOS_D3.md`).

La decisión de diseño para esta primera versión es **FastAPI como única puerta de acceso a los datos**; no se exponen tablas de negocio mediante la API directa de Supabase. Por eso las tablas se crean con RLS habilitado y sin permisos `anon` o `authenticated`. El backend usa conexión PostgreSQL de servidor, nunca en el navegador.

## Contenido

```
RECIWISE/
├── frontend/           # interfaz, .env.example, pruebas y guía de integración
├── app/
│   ├── config.py       # variables de entorno
│   ├── db.py           # SQLAlchemy y sesiones
│   ├── main.py         # endpoints
│   ├── models.py       # modelos de Sprint 1
│   ├── schemas.py      # validación de entrada/salida
│   ├── security.py     # validación de JWT Supabase y roles
│   ├── storage.py      # bucket privado y URLs de lectura temporales
│   ├── photo_uploads.py # cuota, intención durable y compensación
│   ├── reconcile_photos.py # CLI de diagnóstico/recuperación
│   └── schema_guard.py # compatibilidad 003, sin migración automática
├── migrations/
│   ├── 001_sprint1.sql # reportes, perfiles, eventos, recursos, revisión
│   ├── 002_sprint2_3_estructura.sql # tablas de rutas, paradas e incidencias
│   └── 003_sprint1_concurrencia.sql # exclusiones, posiciones y registro durable
├── docs/PLAN_D2_HACKATON.md
├── docs/CONTRATOS_D3.md
├── tests/
├── .env.example
└── requirements.txt
```

## 1. Proyecto Supabase y compatibilidad

1. Conservar proyecto principal, cuentas, credenciales y archivos `.env` existentes. No crear RECIWISE-TEST ni ejecutar migraciones en el compartido por seguir esta guía.
2. **Este backend exige 001+003.** La guardia rechaza 001 sin 003, esquemas parciales/incompatibles y conexiones no verificables. Si el principal sigue con el esquema anterior, esta rama no puede servirse allí hasta una revisión y autorización posteriores. No se verificó en esta revisión qué versión está desplegada hoy.
3. Para desarrollo, el runner existente crea un PostgreSQL local desechable con 001+003 y servicios simulados. No reutiliza datos ni credenciales reales como fixtures. La migración 002 depende de 001 y prepara rutas/paradas/incidencias; no es requisito de Sprint 1 y no se aplica ahora al compartido.
4. Auth conserva JWKS RS256/ES256 y perfiles administrados. No existe selección pública de roles privilegiados. Los 69 casos negativos/de permisos usan tokens y claves ficticias; los flujos manuales previos con Supabase están documentados por separado.
5. Storage real bajo fallos queda pendiente con un destino y permiso específicos. No trasladar pruebas destructivas al principal por no disponer de otro proyecto. [Lista de casos y condiciones](docs/PLAN_D2_HACKATON.md#5-pendientes-de-supabase-real-sin-bloquear-funciones-independientes).

## 2. Verificar y preparar el backend

```bash
cd RECIWISE
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Los pasos de instalación son para una máquina nueva; reutilizar el entorno existente si ya está listo. Conservar `.env`; las credenciales y la conexión PostgreSQL son exclusivas del servidor. Para la regresión actual en Windows, con Docker Desktop disponible, ejecutar desde la raíz:

```powershell
.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase all
```

El runner configura su propia base/servicios, registra evidencia en `.test-artifacts/` y retira el contenedor. No prepara un servidor persistente de demo para React. En Linux/macOS, usar el intérprete del entorno correspondiente para el mismo script.

**Solo con un entorno compatible 003 ya preparado y revisado**, iniciar la API con su configuración segura:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Consultar `/ready` para preparación y `/docs` para contratos; `/health` solo mide el proceso. No iniciar esta rama con la configuración del principal anterior ni desactivar la guardia para conseguir un 200. Para el flujo integrado de demo y lo que falta, consultar [la guía actualizada de Sprint 1](docs/SPRINT1_PASO_A_PASO.md).

## 3. Autenticación desde React

El frontend inicia sesión con **Supabase Auth** y toma el `access_token` real de la sesión. En cada petición a FastAPI añade:

```http
Authorization: Bearer <access_token>
```

En cada request protegida, FastAPI valida firma (JWKS), emisor, audiencia, vencimiento y luego consulta el rol verdadero en `profiles`. **No** confía en un rol enviado desde React. El rol de chofer existe, pero sus endpoints operativos comienzan en Sprint 3; no tiene acceso general a reportes.

No poner nunca `DATABASE_URL`, la contraseña de PostgreSQL o `SUPABASE_SERVICE_ROLE_KEY` en el bundle de Vite.

## 4. API Sprint 1

| Método | Endpoint | Permiso | Uso |
|---|---|---|---|
| GET | `/health` | Público | Verificar proceso de API (no mide BD) |
| GET | `/me` | Cualquier cuenta | Identidad + rol efectivo |
| POST | `/reports` | Ciudadano | Crear reporte |
| GET | `/reports/mine` | Ciudadano | Sus reportes |
| GET | `/reports/{id}` | Dueño o encargado | Detalle |
| POST | `/reports/{id}/photos` | Ciudadano dueño | Imagen opcional (JPG/PNG/WebP, 5 MB, 3 por reporte) |
| GET | `/reports/{id}/photos` | Dueño o encargado | Lista con URL temporal (5 min) |
| GET | `/municipal/reports` | Encargado | Mapa/listado, límites, estado, paginación |
| GET/POST | `/municipal/vehicles` | Encargado | Recursos de vehículos |
| PATCH | `/municipal/vehicles/{id}/availability` | Encargado | Disponibilidad |
| GET/POST | `/municipal/sites` | Encargado | Salida y descarga |
| GET/POST | `/municipal/shifts` | Encargado | Turnos y validación básica |

Ejemplo de `POST /reports`:

```json
{
  "description": "Hay residuos acumulados cerca de la esquina",
  "latitude": -12.065,
  "longitude": -75.21,
  "observed_at": "2026-10-27T15:30:00-05:00",
  "waste_type": "mixto"
}
```

Esos valores son **datos ficticios de formato**; nunca deben presentarse como reportes reales de El Tambo. `created_at` (fecha de envío) lo fija PostgreSQL, separado de `observed_at`.

El listado municipal permite filtrar por `status` y por caja geográfica `north/south/east/west`, en coordenadas WGS84; es adecuado para mostrar marcadores en Leaflet. No hay un sector piloto oficial definido todavía, así que el backend valida coordenadas globalmente sin fingir límites del distrito. Se acordará un perímetro permitido posteriormente.

## 5. Cómo probar el flujo conjunto

Guion de aceptación para un entorno compatible previamente identificado. No se ejecutó contra el principal en esta revisión; si se usan servicios simulados debe indicarse.

1. Registrar un usuario ciudadano con Auth y conseguir su JWT de acceso.
2. `POST /reports` con token ciudadano → debe responder `201` y `status: recibido`.
3. `GET /reports/mine` → debe devolver el reporte anterior.
4. Crear/promover un usuario encargado desde una sesión administrativa verificada de Supabase.
5. `GET /municipal/reports` con token municipal → debe mostrar el reporte, y la vista de mapa podrá utilizar `latitude/longitude`.
6. Confirmar que el usuario ciudadano recibe `403` si intenta llamar al listado municipal.
7. Probar vehículo marcado `available: false`: el alta de turno debe devolver `422`.

## 6. Límites y controles antes de producción

- **La versión nueva no tiene despliegue validado.** Se distingue evidencia manual histórica, SQLite para lógica de API/permisos y PostgreSQL real aislado para restricciones/carreras/recuperación. Las pruebas pendientes con Storage real no se consideran aprobadas por las simulaciones.
- El envío de imágenes verifica tamaño y firma básica, sin decodificación completa. La compensación durable y el conciliador ya están implementados y probados localmente; privacidad/moderación/retención, fallos del servicio real y operación del alojamiento requieren revisión adicional.
- Con 003, slots únicos 1–3 y bloqueo de reporte garantizan el máximo de fotos incluso con concurrencia. Las peticiones a Storage y PostgreSQL no son atómicas: la consistencia es eventual, hay cuarentenas y pueden repetirse DELETE idempotentes tras una caída.
- Con 003, exclusiones PostgreSQL de vehículo y chofer impiden reservas superpuestas y permiten intervalos contiguos. Mantienen HTTP 409; la consulta previa sigue siendo una validación temprana. **003 no se ha aplicado al compartido por esta tarea.**
- Las cadenas `status` representan fases, no dan por atendido un reporte al agruparlo. En el Sprint 2 se documentarán las transiciones y auditoría.
- No se infiere volumen/carga desde la descripción ni se calculan ahorros, optimización o capacidades sin datos.
- Revisar políticas de privacidad, retención de fotos, uso de coordenadas, protección contra abuso, y permisos/estado operativo municipal antes del despliegue.
- No aplicar roles municipales por la interfaz de registro pública. Existen cuentas ciudadanas únicamente hasta su promoción validada por un administrador.

## 7. Próximos pasos compartidos

**D1:** reutilizar Auth/JWT, GPS/mapa, fotos, `Mis reportes` y consulta municipal existentes. Ensayar la misma versión junto con D2 y verificar móvil/HTTPS; no rehacer pantallas que ya funcionan.

**D2:** aceptar el recorrido funcional en un entorno compatible, mantener regresión aislada y preparar contrato/adaptador/revisión municipal de Sprint 2. No crear otro Supabase ni migrar el principal ahora. Ver [orden y criterios hasta el 19/11](docs/PLAN_D2_HACKATON.md).

**D3:** acordar con D2 el contrato en `docs/CONTRATOS_D3.md`, preparar ejemplos etiquetados separados por evento e integrar un módulo de comparación **sin** cambiar aún el estado de los reportes. Después se conectarán propuestas de agrupación y OR-Tools.

Fecha objetivo del MVP completo: **19 de noviembre de 2026**; la fecha no equivale a código integrado o desplegado.

## 8. Material añadido para iniciar Sprint 1 con D3

Se añadieron `d3/` y `docs/SPRINT1_PASO_A_PASO.md`:

- **12 reportes simulados**, separados por eventos: 6 registros para ajuste y 6 para evaluación inicial. No son reportes municipales ni cifras de campo.
- Casos especiales de descripción ambigua y errores de coordenadas/fecha.
- Programa para validar particiones y exportar entradas sin `evento_esperado_id`.
- Funciones reproducibles de **distancia aérea Haversine** y **diferencia de tiempo**; no usan IA ni matriz vial.
- Pruebas específicas para evitar filtración de etiquetas entre particiones.

Ejecutar:

```bash
python -m d3.preparar_datos
pytest -q
```

El modelo semántico, sus resultados y el ajuste de umbrales siguen pendientes. Leer `d3/README.md` antes de usar el dataset. La primera demostración del Sprint 1 se concentra en registro y consulta de reportes, **no** en rutas ni agrupación automática.
