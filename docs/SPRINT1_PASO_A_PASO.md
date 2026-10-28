# RECIWISE — Sprint 1: guía de implementación

**Ventana de trabajo del plan maestro:** 25 de octubre al 1 de noviembre de 2026. **Estado de verificación:** código local generado y probado; no hay evidencia de Supabase conectado, frontend integrado, repositorio del equipo ni despliegue.

## Objetivo demostrable (1 de noviembre)

Una persona entra con cuenta ciudadana, envía una descripción y ubicación desde el celular, consulta su reporte y el encargado autenticado visualiza ese reporte en un listado/mapa. La foto es opcional. No se necesita que la IA agrupe ni que el optimizador cree rutas para esta demostración.

## Paso A — Base de datos (D2)

1. Crear un proyecto de prueba Supabase y guardar secretos solo en el backend.
2. Abrir `migrations/001_sprint1.sql` y ejecutarlo en SQL Editor. No ejecutar `002` como requisito del Sprint 1.
3. Comprobar en Database que existen `profiles`, `reports`, `report_photos`, `vehicles`, `service_sites`, `shifts`, `events`, `event_reports` y `grouping_decisions`.
4. Confirmar en Storage que existe el bucket **privado** `reciwise-reportes`.
5. Crear cuenta de prueba ciudadana mediante Auth y confirmar que existe `profiles` con `role='ciudadano'`.
6. Crear segunda cuenta de prueba y promocionarla como `encargado_municipal` **solo** en SQL Editor después de verificar identidad. Nunca exponer una opción de selección de rol privilegiado en el registro público.

**Verificación:** esquema creado sin errores, rol ciudadano por defecto, bucket privado y roles restringidos.

## Paso B — Levantar API FastAPI (D2)

1. Instalar Python compatible con las dependencias y crear entorno virtual.
2. `pip install -r requirements.txt`.
3. Copiar `.env.example` a `.env` y completar `DATABASE_URL`, `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` exclusivamente en máquina/servidor.
4. Verificar que Supabase usa claves JWT asimétricas RS256/ES256; esta API inicial valida JWKS y no admite automáticamente proyectos antiguos con HS256.
5. `uvicorn app.main:app --reload` y abrir `http://127.0.0.1:8000/docs`.
6. `pytest -q` para ejecutar pruebas locales.
7. Desde React o un cliente HTTP con JWT de usuario real, crear un reporte y consultar `GET /reports/mine`.
8. Con un JWT de encargado, consultar `GET /municipal/reports` y verificar la ubicación, con `latitud/longitud` en la respuesta como `latitude/longitude`.
9. Confirmar que un ciudadano obtiene `403` al pedir `/municipal/reports`.

**Verificación:** prueba integrada con Supabase real pendiente hasta que el equipo conecte el proyecto. Las pruebas locales SQLite **no** la sustituyen.

## Paso C — Frontend móvil primero (D1)

1. Crear React + Vite, diseño responsive de las pantallas de login, registro ciudadano, `Mis reportes` y lista/mapa municipal.
2. Usar Supabase Auth para login. Cada petición protegida a FastAPI lleva `Authorization: Bearer <access_token>`.
3. Formulario envía `description`, `latitude`, `longitude`, `observed_at` (ISO 8601 con zona horaria) y `waste_type` opcional. El servidor genera `created_at`.
4. Con Leaflet, pintar marcadores provenientes de `GET /municipal/reports`; no dibujar puntos inventados como si fueran municipales.
5. Mostrar errores de validación, falta de permisos, conexión y ubicación. Incorporar carga de foto opcional desde móvil.
6. Probar en pantalla pequeña y grande. La conversión a PWA o APK puede venir después de asegurar el flujo principal.

**Verificación:** ciudadano y encargado ven sus pantallas respectivas sin exponer los secretos del backend.

## Paso D — Preparación D3 (responsable de IA/optimización)

1. Leer y acordar `docs/CONTRATOS_D3.md` con D2.
2. Revisar los **12 ejemplos simulados** de `d3/data/ejemplos_etiquetados.csv` y los casos especiales de `d3/data/casos_para_revision.csv`.
3. Ejecutar `python -m d3.preparar_datos` y verificar que `evento_esperado_id` no aparece en las entradas del modelo.
4. Revisar etiquetas con otro integrante; documentar desacuerdos, y agregar ejemplos de distintas redacciones, lugares, recurrencia e intervención.
5. Entregar funciones `distancia_metros` y `diferencia_horas` y revisar sus pruebas.
6. En el próximo paso, probar el modelo candidato de similitud semántica, medir errores y documentar criterios preliminares sin utilizar los ejemplos reservados para elegir umbrales.

**Verificación:** datos reproducibles, separación por eventos y decisiones abiertas explícitas.

## Contrato de integración inicial

- D1 ↔ D2: JSON del endpoint `POST /reports` y lectura de `/reports/mine`, `/municipal/reports`.
- D2 ↔ D3: `docs/CONTRATOS_D3.md`. La IA propone candidatos, no actualiza automáticamente el estado de atención.
- D1 ↔ D3: valores de similitud, distancia, tiempo, motivos y resultado a mostrar cuando se implemente la revisión municipal (Sprint 2).

## Cierre del Sprint 1 (lista de comprobación)

- [ ] Supabase de prueba creado y migración ejecutada.
- [ ] Dos cuentas de prueba con roles correctos.
- [ ] Backend conectado a PostgreSQL y JWT de Supabase.
- [ ] Ciudadano puede enviar y consultar su reporte desde una pantalla móvil.
- [ ] Encargado puede verlo en un mapa usando la API.
- [ ] Fotos opcionales probadas end-to-end (si se incluyen en la demo inicial).
- [ ] Ejemplos simulados D3 revisados y evaluación separada por evento.
- [ ] Contratos D1–D2–D3 confirmados.
- [ ] Versión conjunta desplegada y demostrada.

No marcar estas casillas como completadas solo por tener scripts o archivos preparados.
