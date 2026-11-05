# RECIWISE: demostración funcional de los tres perfiles

Preparada el 31 de octubre de 2026. Solo desarrollo local; **NO-GO de despliegue compartido**. No constituye aceptación formal del equipo.

## Qué se demuestra

Ciudadano y encargado trabajan con React, Leaflet, FastAPI y PostgreSQL reales. El chofer ejecuta una ruta únicamente gracias a una **autorización ficticia insertada por la fixture existente en PostgreSQL desechable**. No se llama a un proveedor D3 ni se acredita la cadena de aprobación real.

Antes de mostrar el chofer, anunciar: **«Cambiamos a un escenario de ejecución autorizado ficticiamente. Esta ruta no se ha calculado ni aprobado a partir del reporte recién registrado».** Su recorrido tiene tres eventos de prueba predefinidos. Los reportes ciudadanos no pasan a atendidos al asociarlos o al terminar esta ruta.

| Elemento | Naturaleza |
| --- | --- |
| React, mapas Leaflet, contratos HTTP y persistencia PostgreSQL | Reales, con código de negocio existente. |
| Autenticación | SDK normal contra Auth/JWKS local simulado; firma ES256, issuer, audience y perfil PostgreSQL verificados por FastAPI. Sin bypass. |
| Fotografías | API real con Storage HTTP simulado; archivo técnico PNG de 1×1, ficticio. No acredita Supabase Storage real. |
| Fondo del mapa | Teselas simuladas; el fondo puede verse liso. Marcadores, selección y coordenadas son de Leaflet real. |
| Aprobación municipal de propuestas | Bloqueada: botón deshabilitado y FastAPI 409. |
| Autorización del recorrido positivo del chofer | Supuesto de prueba SQL, solo en el contenedor desechable. No es un endpoint ni una integración D3 nueva. |
| Móvil | Viewport de 390×844; no sustituye la prueba con un celular físico y HTTPS. |

## Iniciar en VS Code / Windows

Prerrequisitos ya usados por el proyecto: Docker Desktop local activo, `.venv`, dependencias de `frontend` y Google Chrome. No requiere un nuevo proyecto Supabase. Mantener una terminal dedicada:

```powershell
Set-Location 'C:\Users\DELL INSPIRON\Documents\RECIWISE'
.\.venv\Scripts\python.exe tests\run_isolated_postgres.py --phase demo
```

El comando:

1. Rechaza un contexto Docker remoto antes de preparar datos.
2. Crea su propio contenedor PostgreSQL 17 y volumen anónimo desechables, publicados solo en loopback.
3. Prepara las dependencias mínimas `auth`/`storage` de las migraciones y aplica **001+002+003 solo allí**. No modifica archivos de migración ni actualiza el manifiesto de esquema.
4. Comprueba nombre, ID, etiqueta, puerto, montaje y marcador de la base antes de insertar la fixture de ejecución. Rechaza también el contenedor local persistente.
5. Arranca `app.main:app` normal, con guardia de esquema y autenticación activas; Vite usa el lanzador existente con carga de `.env` deshabilitada. Las conexiones se pasan por variables de proceso, sin editar archivos ni credenciales.
6. Abre sesiones independientes de Chrome para los tres perfiles y anuncia **`DEMO READY`**. Las cuentas son `citizen@example.test`, `manager@example.test` y `driver@example.test`; las contraseñas efímeras se utilizan en memoria, sin imprimirse ni guardarse.

Utilizar las direcciones anunciadas en esa terminal. **No son necesariamente 5173/8001**: esos puertos pertenecen al entorno persistente, que puede continuar abierto. Cada demo utiliza puertos propios para API, React y Auth/Storage.

Se crea `.test-artifacts/reciwise-d2-test-<id>/demo.json`, con URLs e IDs públicos de las fixtures; no contiene contraseñas ni JWT. `demo-ready.json` acredita los tres perfiles preparados. El PNG técnico para el formulario está en `DEMO-imagen-tecnica.png` en esa misma carpeta.

No es necesario introducir ni compartir una contraseña para presentar: el lanzador ya inicia sesión por el formulario real de React. Si se cierra sesión y se necesita repetir el acceso, reiniciar esta demo; no usar las credenciales de `.localdev` ni de Supabase principal.

## Datos iniciales, todos ficticios

- Dos reportes del ciudadano: `DEMO FICTICIA: reporte inicial con fotografía` y `DEMO FICTICIA: reporte disponible para asociación manual`.
- Un evento manual inicial asociado al primer reporte, con su historial real de auditoría.
- Una unidad de revisión disponible y otra rotulada `NO DISPONIBLE`, sin inventar capacidad ni placa.
- Dos puntos de prueba (salida/descarga) y dos turnos: el turno activo de la fixture de chofer y otro futuro para revisar propuestas.
- Dos propuestas pendientes, sin recorrido calculado y no operativas. `demo.json` identifica sus IDs como `proposals.reject` y `proposals.cancel`.
- Un recorrido con tres paradas y autorización ficticia para `driver@example.test`; `driver2@example.test` no puede consultar ese recorrido. La ventana del turno es aproximadamente dos horas desde la preparación: reiniciar la demo si caduca.

Las altas de preparación usan los endpoints existentes, excepto la fixture de autorización ya existente, que necesita SQL de prueba explícito. No se fabrican resultados de D3 desde React ni se exportan autorizaciones a otra base.

## Guion de presentación (12–15 minutos)

### 1. Ciudadano, 3 minutos

1. Mostrar `citizen@example.test` y el perfil **ciudadano** obtenido de `/me`. El formulario municipal no está disponible.
2. En «Registrar acumulación de basura», escribir una descripción inequívoca, por ejemplo `DEMO FICTICIA EN VIVO: acumulación de prueba`.
3. Pulsar «Elegir en el mapa», seleccionar un lugar y, si hace falta, arrastrar el marcador. Mostrar que «Registrar reporte» requiere confirmar la ubicación; no hay entradas obligatorias de latitud/longitud ni GPS automático.
4. Confirmar ubicación, revisar fecha/hora y enviar una sola vez. Anotar el ID mostrado. Esperado: **POST `/reports` 201**, coordenadas numéricas y aparición en «Mis reportes» con etiqueta «Pendiente» (`recibido`).
5. Abrir fotografías y subir `DEMO-imagen-tecnica.png` al reporte nuevo. Mostrar confirmación, imagen y «Renovar enlaces». Es una imagen técnica de conectividad, no una fotografía de basura real.
6. Recargar: sesión, ID, ubicación y fotografía deben recuperarse. Mostrar el formulario/listado en el viewport móvil ya preparado.

### 2. Encargado municipal, 5 minutos

1. Cambiar a la ventana `manager@example.test`; mostrar `/me` con **encargado_municipal** y «Modo real» (FastAPI local, datos ficticios).
2. «Reportes ciudadanos» → «Actualizar listado». Buscar el reporte registrado en vivo; contrastar ID, texto, coordenadas, estado, marcador y fotografía. El filtro usa `GET /municipal/reports`; la búsqueda por texto se aplica a la página actual.
3. «Eventos o puntos de atención» → «Crear evento manual». Escribir una intervención rotulada DEMO, elegir/confirmar ubicación, seleccionar el reporte nuevo y revisar antes de confirmar la creación. Mostrar su detalle, mapa y asociado. **El reporte conserva su estado.**
4. «Revisión de agrupaciones»: abrir el segundo reporte inicial sin asociación, elegir como candidato el evento manual creado y «Confirmar agrupación». Revisar el diálogo y «Confirmar decisión». Abrir el historial para mostrar actor, operación y relación persistida. No se ejecuta similitud, sugerencia automática ni agrupación D3. Si aparece 409, actualizar y revisar el estado antes de emitir otra decisión; no repetir ciegamente.
5. «Recursos operativos»: recorrer Vehículos/Sitios/Turnos. Mostrar la unidad NO DISPONIBLE y su opción deshabilitada para nuevos turnos. Para el conflicto, intentar el mismo vehículo o chofer con un horario superpuesto al turno futuro: revisar y confirmar; esperar **409** con mensaje comprensible, sin otra reserva. Cancelar el formulario. No tocar el turno activo del chofer.
6. «Planificación de rutas» → «Propuestas recibidas»: mostrar las dos propuestas **pendientes y NO OPERATIVAS**, sin distancia, duración o geometría inventadas.
7. «Decisiones e historial»: abrir el ID `proposals.reject`, mostrar aprobación deshabilitada, elegir rechazar, escribir motivo DEMO, revisar y confirmar. Abrir su historial. Para `proposals.cancel`, hacer lo mismo eligiendo cancelar. Ambos quedan `cancelada`; la acción auditada distingue `reject` de `cancel`. Ya no aparecen en el listado de propuestas activas, pero siguen consultables por su historial municipal.

No cancelar el recorrido del chofer antes de mostrar su ejecución. Las dos propuestas pendientes son independientes de esa fixture.

### 3. Chofer, 4 minutos

1. Anunciar la separación de escenarios: la autorización de esta ruta es **ficticia y exclusiva de esta base desechable**. Expandir «Limitaciones del resultado»; el lanzador ya las deja abiertas.
2. Mostrar `driver@example.test`, perfil **chofer**, «Mis recorridos», tres paradas y el mapa. No dispone de navegación municipal. La exclusión de otro chofer se comprueba en las pruebas, con 404 al consultar este ID.
3. «Revisar inicio de recorrido» → «Confirmar operación de ruta». Solo inicia si turno/recursos/autorización son elegibles. Esperado: **200**, `en_ejecucion`.
4. Primera parada: «Registrar parada atendida», revisar y confirmar.
5. Segunda parada: escribir un motivo ficticio y un tipo, por ejemplo `acceso_bloqueado`; «Registrar incidencia», revisar y confirmar.
6. Tercera parada: indicar motivo de no atención, «Registrar no atención», revisar y confirmar.
7. Con todas las paradas registradas, «Revisar fin de recorrido» y confirmar. Esperado: `finalizada`, con estados `atendida`, `incidencia`, `no_atendida` y registro de responsables/fechas/motivos.
8. Recargar y recuperar la misma ruta y su historial. No afirmar que este recorrido cerró el reporte ciudadano ni que valida un optimizador real.

Los comandos incorporan `operation_id` y revisión esperada mediante el frontend existente. Ante un resultado incierto, consultar su recuperación antes de reenviar. Los fallos y conflictos están cubiertos por la regresión, sin introducirlos innecesariamente durante la presentación.

## Detener y repetir

Pulsar **Ctrl+C en la terminal de la demo**. El padre solicita una parada mediante `demo.stop`, espera al cierre de sus sesiones/procesos y elimina únicamente el contenedor identificado y su volumen anónimo. No detiene el entorno persistente ni modifica Supabase.

Alternativa desde otra terminal, sustituyendo `<id>` por la carpeta anunciada de **esa** demo:

```powershell
New-Item -ItemType File -Path '.test-artifacts\reciwise-d2-test-<id>\demo.stop' -Force | Out-Null
```

Repetir el comando de inicio crea datos, identidades y puertos nuevos. No conserva la ejecución anterior; sí conserva evidencia local ignorada por Git. No borrar ni reinicializar `.localdev` para restablecer la demo.

## Ensayo y regresión reproducibles

```powershell
# Preparación de tres sesiones sin ventanas; valida recuperación tras reiniciar FastAPI.
.\.venv\Scripts\python.exe tests\run_isolated_postgres.py --phase demo --demo-check

# Frontera de aislamiento del nuevo lanzador; pruebas unitarias, sin servicios remotos.
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests\test_demo_support.py

# Regresión existente: tres perfiles, ciudadano móvil, eventos, agrupaciones,
# rechazo/cancelación, ejecución del chofer, fotografías, permisos y reinicio.
.\.venv\Scripts\python.exe tests\run_isolated_postgres.py --phase integrated

# Regresión completa backend; incluye los casos existentes de ejecución.
.\.venv\Scripts\python.exe tests\run_isolated_postgres.py --phase all
```

El integrado reutiliza los **10 casos existentes**, TypeScript, Vitest y build; se ampliaron el caso ciudadano a móvil y el de decisiones para verificar rechazo exitoso desde React. No se reconstruyeron pantallas ni se duplicaron casos de negocio. Las pruebas de ejecución positiva, compensación y mutaciones del guion se realizan exclusivamente en contenedores desechables.

Para confirmar que el aplicativo persistente sigue intacto, con `local_dev.py up` activo en otra terminal:

```powershell
.\.venv\Scripts\python.exe scripts\check_local_dev.py
.\.venv\Scripts\python.exe scripts\validate_municipal_local.py
```

Estos comandos reutilizan las fixtures locales ya existentes. El chofer persistente **debe seguir sin recorridos autorizados**: no es un fallo y no se soluciona copiando el recibo de pruebas.

## Bloqueos de la demostración final

- El recorrido condicionado del chofer es demostrable localmente; la cadena real propuesta D3 → verificación → aprobación operativa sigue bloqueada. No se tocaron sus algoritmos ni contratos.
- Supabase Auth/Storage reales, RLS remoto, fallos de red remotos y conciliación real siguen pendientes. La demo no los acredita.
- Falta validar en celular físico y HTTPS. Los viewports móviles no prueban hardware GPS ni permisos del dispositivo.
- Las reglas de cierre de eventos/reportes requieren aceptación del equipo; esta demo consulta sus estados y conserva `recibido` al asociar, sin inventar transiciones de atención.
- Aplicar 003 y desplegar en Supabase compartido requiere respaldo, diagnóstico, autorización y revisión posterior. Mantener **NO-GO** hasta satisfacer esas condiciones.
- Otro integrante debe ensayar el guion, comprobar las evidencias y aceptar los límites antes de presentar el MVP como aprobado por el equipo.

Los resultados y directorios de la ejecución final se registran en [INTEGRACION_FULLSTACK_SPRINT2.md](INTEGRACION_FULLSTACK_SPRINT2.md). No se publicaron credenciales ni hubo push, merge o despliegue.
