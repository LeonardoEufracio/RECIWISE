# Sprint 1: verificación de ubicación ciudadana

Fecha: **29 de octubre de 2026**. Versión revisada: `070415d` en `main`, coincidente con `origin/main` al revisar el repositorio.

## Estado revisado

La selección de ubicación ya está integrada en el frontend actual mediante `LocationPicker.tsx` y `LocationMap.tsx`, con React Leaflet. Se conserva esta implementación y se ejecutan sus comprobaciones; esta revisión no sustituye código funcional.

El formulario utiliza el contrato existente de `POST /reports`: `description`, `latitude` y `longitude` numéricos, `observed_at` con zona horaria y `waste_type` opcional. La confirmación, la procedencia de la selección y la precisión pertenecen a la interfaz y no se agregan al esquema de FastAPI.

La configuración pública de `frontend/.env.local` está presente, utiliza el formato publishable y referencia el mismo proyecto Supabase que el backend. Esto no prueba por sí solo un inicio de sesión válido ni la conexión a PostgreSQL o Storage. No se copian claves ni valores de configuración a este documento.

## Resultados ejecutados

| Comprobación | Resultado | Alcance |
| --- | --- | --- |
| `npm run check` | **39 pruebas correctas** y tipos correctos | Componentes, contrato de envío, autenticación y permisos de interfaz con servicios simulados |
| `npm run build` | **Correcto** | Compilación TypeScript y Vite; permanece la advertencia de tamaño de un chunk superior a 500 kB |
| `python -m pytest -q -p no:cacheprovider` | **11 pruebas correctas** | API, permisos, CORS, fotos con almacenamiento simulado y pruebas D3 existentes |
| `PLAYWRIGHT_CHANNEL=chrome npm run test:browser` | **6 pruebas correctas** | Chrome con mapas y arrastre reales, coordenadas GPS simuladas, teselas y servicios de negocio simulados |
| HTTP desde Chrome contra Uvicorn real | **`/health` 200 y `/me` sin token 401** | Confirma comunicación con FastAPI y CORS; no verifica una sesión Supabase autenticada |
| Integridad de archivos protegidos | **27 archivos comparados, sin cambios** | `.env*` de raíz/frontend, backend, migraciones, D3 y componentes existentes de autenticación, fotos y consulta municipal |

La advertencia de Starlette/httpx del backend continúa siendo una deprecación; los tests pasan.

## Flujo ciudadano comprobado

- Iniciar sesión o montar el formulario no solicita GPS.
- **Usar mi ubicación** solicita `getCurrentPosition` al pulsar, muestra carga y precisión cuando existe y presenta errores comprensibles de permiso, disponibilidad o espera.
- **Elegir en el mapa** permite clic o toque y arrastrar el marcador. No pide GPS.
- Elegir una ubicación y confirmarla son pasos separados del envío. Intentar registrar sin confirmar no hace `POST /reports`.
- **Corregir ubicación** exige confirmar el punto corregido antes de registrar.
- La selección permanece en memoria de la interfaz; no se guarda en localStorage/sessionStorage ni se envía a FastAPI antes de registrar. El mapa base descarga teselas según el área visible.
- Se ignoran respuestas GPS tardías después de elegir manualmente o desmontar el formulario.
- El envío conserva las coordenadas numéricas y la autorización Bearer. Las pruebas de regresión de fotos y consulta municipal pasan.

## Comprobación manual pendiente

Con backend y frontend iniciados según `frontend/README.md`, entrar con una cuenta ciudadana real:

1. Pulsar **Usar mi ubicación**, aceptar el permiso y comprobar visualmente el punto y la precisión. Confirmar la ubicación y después registrar el reporte.
2. Crear otra selección mediante **Elegir en el mapa**, tocar un lugar, arrastrar el marcador y confirmar. Usar **Corregir ubicación** para comprobar que vuelve a exigir confirmación.
3. Denegar el permiso del navegador y comprobar que sigue disponible la elección manual.

El GPS físico y los permisos del sistema deben probarse en un dispositivo real. Para móvil se requiere HTTPS; en desarrollo se admite localhost. Una dirección HTTP de la red local, como `http://192.168.x.x:5173`, no equivale a localhost del teléfono.

Las pruebas automáticas no validan credenciales reales de Supabase, firma JWKS del proyecto, escritura real en PostgreSQL ni subida al bucket privado. Esos pasos quedan pendientes de integración con las cuentas existentes; no se crearon reportes en Supabase durante esta revisión.

## Actualización adicional y siguientes pasos

La revisión del proyecto, las ramas remotas y la búsqueda por nombre en las carpetas locales consultadas no identificó otra actualización Sprint 1. Para comparar e integrar esa entrega hace falta su ruta local exacta.

La carpeta `d3/` actual contiene preparación de datos simulados y funciones geográficas/temporales; todavía no contiene el nuevo prototipo de similitud semántica mencionado. D3 y las mejoras de recursos municipales quedan para la siguiente etapa. Esta verificación de ubicación no declara completado el Sprint 1 entero.
