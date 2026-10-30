# RECIWISE — Sprint 1: guía de implementación

**Ventana de trabajo del plan maestro:** 25 de octubre al 1 de noviembre de 2026; hackatón **19 de noviembre de 2026**. **Revisión de alcance: 29/10/2026.** Backend y frontend implementados, con pruebas locales y evidencia manual previa diferenciadas en [API_SPRINT1.md](API_SPRINT1.md). La aceptación integrada y el despliegue de la versión nueva siguen pendientes.

**Decisión vigente:** conservar el proyecto Supabase principal para la aplicación, sin crear un segundo proyecto por ahora. No aplicar 003 ni ejecutar pruebas destructivas en el principal. Desarrollo/verificación con PostgreSQL local aislado y servicios simulados; [prioridades y criterios D2](PLAN_D2_HACKATON.md). Las pruebas con Storage real quedan pendientes y no detienen funciones independientes.

## Objetivo demostrable (1 de noviembre)

Una persona entra con cuenta ciudadana, envía una descripción y ubicación desde el celular, consulta su reporte y el encargado autenticado visualiza ese reporte en un listado/mapa. La foto es opcional. No se necesita que la IA agrupe ni que el optimizador cree rutas para esta demostración.

## Paso A — Base de datos (D2)

1. Conservar las credenciales, cuentas, bucket y datos del proyecto principal. No copiarlo a las pruebas ni crear RECIWISE-TEST.
2. No ejecutar 001, 002, 003 ni su reversión en el compartido desde esta guía. El backend nuevo requiere 003; si allí sigue 001, rechazará el arranque. No desactivar la guardia para continuar.
3. Reutilizar `.venv\Scripts\python.exe tests/run_isolated_postgres.py --phase all`: crea una base PostgreSQL local propia, aplica 001+003 solo allí, configura Auth/Storage ficticios y retira el contenedor al terminar. No es un servidor persistente de demo.
4. Revisar JUnit y manifiesto en `.test-artifacts/`; distinguir los casos PostgreSQL, SQLite y Storage simulado y las omisiones remotas.
5. Para la demostración, identificar primero entorno/esquema/versión compatibles y declarar si usa servicios simulados. Una integración de esta rama con el principal requiere una autorización posterior de despliegue/003.
6. Mantener roles privilegiados administrados; nunca ofrecer selección pública de encargado/chofer. La evidencia histórica de cuentas/roles/bucket está en 6.1 de la guía API y no se reescribe como inexistente ni se presenta como una nueva validación.

**Verificación:** exclusiones, slots, durabilidad, recuperación, guardia y permisos probados en su entorno explícito; sin modificaciones del principal. Privacidad/compensación de Storage real bajo fallos quedan pendientes.

## Paso B — Levantar API FastAPI (D2)

1. Reutilizar el entorno Python y dependencias existentes. En otra instalación, instalar `requirements.txt`; no reemplazar `.env` del proyecto ni usar sus secretos en fixtures.
2. Ejecutar el runner aislado del paso A para regresión. Mantiene la guardia real en PostgreSQL y sustituye servicios externos con implementaciones explícitas de pruebas.
3. Para servir React, preparar y ensayar un entorno compatible independiente de las transacciones efímeras del runner. **No iniciar esta rama con el `.env` del principal si su esquema no cumple 003.**
4. Solo en el entorno compatible preparado, iniciar FastAPI con `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`; consultar `/ready`. `/health` solo comprueba el proceso.
5. El backend conserva JWKS RS256/ES256; no usar HS256 ni una cabecera de actor ficticio como si fuera un JWT real. Los workers internos de tests no se despliegan como API pública.
6. Ensayar con React o cliente HTTP: `/me`, crear reporte, consultar `/reports/mine` y recuperar el mismo UUID como encargado con `GET /municipal/reports`.
7. Verificar coordenadas `latitude`/`longitude`, denegación municipal `403` al ciudadano y persistencia tras recarga/reinicio. Registrar si Auth/Storage/GPS son simulados o reales, sin guardar tokens.

**Verificación:** aceptación integrada de la versión de demo pendiente. Hay evidencia manual previa con Supabase y automática local; cada una conserva su alcance. No se repiten ahora pruebas remotas ni se consideran equivalentes SQLite, PostgreSQL local y Supabase Storage real.

## Paso C — Frontend móvil primero (D1)

1. Reutilizar el frontend React + Vite existente: login, formulario GPS/mapa, `Mis reportes`, fotos, listado/mapa municipal e historial HTTP. No rehacer pantallas funcionales ni exigir diseño visual definitivo.
2. Usar Supabase Auth para login. Cada petición protegida a FastAPI lleva `Authorization: Bearer <access_token>`.
3. Formulario envía `description`, `latitude`, `longitude`, `observed_at` (ISO 8601 con zona horaria) y `waste_type` opcional. El servidor genera `created_at`.
4. Con Leaflet, pintar marcadores provenientes de `GET /municipal/reports`; no dibujar puntos inventados como si fueran municipales.
5. Conservar errores de validación, permisos, conexión y ubicación, así como fotos opcionales. Un fallo de foto no debe exigir volver a crear el reporte.
6. Probar en pantalla pequeña y grande. La conversión a PWA o APK puede venir después de asegurar el flujo principal.

**Verificación:** ciudadano y encargado ven sus pantallas sin exponer secretos. Ver [evidencia previa de ubicación](VERIFICACION_UBICACION_SPRINT1.md); GPS físico y HTTPS del teléfono siguen siendo una comprobación manual pendiente.

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

- [x] Operaciones previstas de D2 implementadas, incluidos recursos y permisos; evidencia en la guía API.
- [x] Concurrencia, recuperación y guardia verificadas en PostgreSQL aislado y Storage simulado.
- [ ] Entorno y versión compatibles de demo identificados, sin tocar el principal ni omitir la guardia.
- [ ] Identidades/roles de la demo verificados y servicios reales/simulados declarados.
- [ ] Ciudadano puede enviar y consultar su reporte desde una pantalla móvil.
- [ ] Encargado puede verlo en un mapa usando la API.
- [ ] Fotos opcionales probadas end-to-end (si se incluyen en la demo inicial).
- [ ] Ejemplos simulados D3 revisados y evaluación separada por evento.
- [ ] Contratos D1–D2–D3 confirmados.
- [ ] Versión conjunta ensayada y aceptada, con evidencia de IDs/HTTP/persistencia. Si requiere despliegue en el principal, contar antes con autorización de migración/despliegue.

No marcar estas casillas como completadas solo por tener scripts o archivos preparados.

Storage real bajo fallos, supervisión del alojamiento, respaldo/restauración y autorización de 003 siguen como pendientes del despliegue. No bloquean el contrato/adaptador y la revisión municipal local de Sprint 2. Secuencia propuesta hasta el 19/11 en [PLAN_D2_HACKATON.md](PLAN_D2_HACKATON.md).
