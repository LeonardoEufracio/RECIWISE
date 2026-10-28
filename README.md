# RECIWISE — Backend y base de datos inicial (Sprint 1)

**Estado real:** incluye migraciones versionadas, API FastAPI de reportes y recursos y un frontend local de pruebas. La integración autenticada con las cuentas y el almacenamiento reales de Supabase sigue pendiente de validación; no se ha desplegado el aplicativo. La IA, aprobación de rutas y ejecución por chofer **aún no están implementadas**.

**Frontend de pruebas (28/10/2026):** [instrucciones de arranque, contratos y resultados comprobados](frontend/README.md). Incluye React + Vite, Supabase Auth, Leaflet, fotos e historial HTTP. El código funcional de `app/` se conserva sin cambios.

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
│   └── storage.py      # bucket privado y URLs de lectura temporales
├── migrations/
│   ├── 001_sprint1.sql # reportes, perfiles, eventos, recursos, revisión
│   └── 002_sprint2_3_estructura.sql # tablas de rutas, paradas e incidencias
├── docs/CONTRATOS_D3.md
├── tests/
├── .env.example
└── requirements.txt
```

## 1. Crear el proyecto Supabase

1. Crear el proyecto y anotar **Project URL**, la cadena PostgreSQL, y la **service role key**; no subir secretos al repositorio.
2. En el panel SQL Editor ejecutar **primero** `migrations/001_sprint1.sql`. La migración crea perfiles, reportes, eventos y relaciones, recursos y un bucket privado de imágenes.
3. La migración `002_sprint2_3_estructura.sql` es opcional ahora: prepara tablas de planificación para el Sprint 2 y de ejecución para el Sprint 3.
4. En Supabase Auth habilitar el proveedor deseado para el piloto (correo/contraseña, por ejemplo). El disparador crea cada nuevo perfil como `ciudadano`. Para un encargado o chofer, un administrador verificado debe cambiar `profiles.role` **desde SQL Editor**, nunca desde registro público.
5. **Importante:** este backend verifica tokens usando **JWKS asimétrico** (RS256/ES256). Revisar en Auth > JWT Signing Keys que el proyecto tenga una clave asimétrica activa; los proyectos que usan únicamente HS256 heredado no funcionarán con esta versión de verificación. Ver: https://supabase.com/docs/guides/auth/jwts

## 2. Iniciar el backend

```bash
cd RECIWISE
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env       # en Windows: copy .env.example .env
```

Rellenar `.env`. `DATABASE_URL` debe ser la conexión PostgreSQL **de servidor**. Si se usa pooler transaccional con psycopg, revisar la cadena de conexión según el panel de Supabase; no compartir la contraseña.

```bash
uvicorn app.main:app --reload
```

Abrir `http://127.0.0.1:8000/docs` para probar los endpoints. Para ejecutar los tests (no requieren Supabase):

```bash
pytest -q
```

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

1. Registrar un usuario ciudadano con Auth y conseguir su JWT de acceso.
2. `POST /reports` con token ciudadano → debe responder `201` y `status: recibido`.
3. `GET /reports/mine` → debe devolver el reporte anterior.
4. Crear/promover un usuario encargado desde una sesión administrativa verificada de Supabase.
5. `GET /municipal/reports` con token municipal → debe mostrar el reporte, y la vista de mapa podrá utilizar `latitude/longitude`.
6. Confirmar que el usuario ciudadano recibe `403` si intenta llamar al listado municipal.
7. Probar vehículo marcado `available: false`: el alta de turno debe devolver `422`.

## 6. Límites y controles antes de producción

- **No hay datos reales ni un despliegue validado.** Pruebas SQLite verifican lógica de API; todavía hay que ejecutar integración contra un Supabase de prueba.
- El envío de imágenes verifica tamaño y la firma básica del archivo, pero **no** decodifica ni analiza completamente imágenes. Para un servicio público harían falta controles adicionales de seguridad, moderación, privacidad, límites de petición y limpieza de archivos huérfanos si falla la BD tras subir al bucket.
- El límite de tres fotos se comprueba en aplicación y podría sufrir carreras bajo carga; endurecerlo si se ofrece servicio público.
- El conflicto de turnos se comprueba antes del `INSERT`; no es a prueba de simultaneidad. En despliegue real establecer una restricción de solapamiento en PostgreSQL.
- Las cadenas `status` representan fases, no dan por atendido un reporte al agruparlo. En el Sprint 2 se documentarán las transiciones y auditoría.
- No se infiere volumen/carga desde la descripción ni se calculan ahorros, optimización o capacidades sin datos.
- Revisar políticas de privacidad, retención de fotos, uso de coordenadas, protección contra abuso, y permisos/estado operativo municipal antes del despliegue.
- No aplicar roles municipales por la interfaz de registro pública. Existen cuentas ciudadanas únicamente hasta su promoción validada por un administrador.

## 7. Próximos pasos compartidos

**D1:** integrar Supabase Auth en React, adjuntar el JWT a FastAPI, formulario y `Mis reportes`, mapa municipal con filtros.

**D2:** configurar un proyecto Supabase de prueba, ejecutar migración 001, crear cuentas piloto, ejecutar tests de integración, confirmar contratos y documentar las modificaciones de esquema.

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
