# Integración de la actualización local de Sprint 1

Fecha: **29 de octubre de 2026**. Fuente: `_actualizacion_sprint1/`. Base comparada: `fb05d2f`.

Se leyeron los siete archivos de la entrega y sus equivalentes antes de modificar el proyecto. La carpeta recibida se conserva intacta como referencia local y está excluida de Git. No se copiaron credenciales ni archivos de entorno.

## Comparación y decisiones

| Entrega | Proyecto existente | Integración |
| --- | --- | --- |
| `frontend/src/components/CitizenPanel.jsx` | `ReportForm.tsx`, `LocationPicker.tsx`, `Reports.tsx`, `Photos.tsx` | Ya había GPS bajo demanda, mapa, arrastre y confirmación. Se añadió el bloqueo del botón hasta confirmar, el origen de la selección y el recordatorio de señalar la acumulación. Se conservan la paginación, fotos, cliente JWT y manejo de respuestas GPS tardías. |
| `frontend/src/components/ReportMap.jsx` | `LocationMap.tsx` y `MapView.tsx` | El selector React Leaflet y el mapa municipal ya estaban implementados. Se mantienen los iconos empaquetados, la precisión GPS y el arrastre. No se crea un segundo mapa ni se cambia la vista municipal. |
| `frontend/src/styles.css` | Hoja existente y clases de ubicación | La entrega corresponde a otro diseño y estructura. Se reutilizan los estilos actuales; la sustitución global afectaría componentes existentes. |
| `d3/probar_similitud.py` | Ruta nueva; reutiliza `geo_temporal.py` y `preparar_datos.py` | Se incorpora el comparador local con el mismo modelo candidato, campos de salida y versión. Se añade validación de datos/vectores, coseno normalizado y error claro si falta la dependencia opcional. |
| `tests/test_d3_similitud.py` | Ruta nueva; tres tests D3 existentes | Se incorporan las dos pruebas entregadas y se amplían con casos de coseno conocido, vectores inválidos, validación previa, exclusión de notas/etiquetas y exportación CLI de ajuste. |
| `d3/SPRINT1_MODELO.md` | Ruta nueva y `d3/README.md` | Se adaptan los comandos al proyecto y se separa la dependencia opcional en `d3/requirements.txt`. Se documenta qué se verificó y qué exige inferencia real. |
| `GUIA_CIERRE_SPRINT1.md` | Guías actuales del repositorio | Sus criterios se usan para aceptación; no se sustituyen las guías por cifras o rutas de otra copia. Este documento registra los resultados locales actuales. |

Los JSX recibidos importan `Photos.jsx` y `lib/api.js`, que no existen en esta estructura TypeScript. Su comportamiento se integra en los componentes actuales en vez de introducir imports rotos. Se mantienen `waste_type` opcional/libre y las reglas de fecha de FastAPI; la entrega no justifica imponer nuevas enumeraciones al backend.

## Comportamiento resultante

- La ubicación empieza sin seleccionar; el centro del mapa no cuenta como punto del reporte.
- GPS solo se solicita al pulsar su botón. Se conservan carga, precisión y errores, y la alternativa por mapa.
- Se puede tocar, hacer clic o arrastrar el marcador. Después de confirmar se usa **Corregir ubicación** para editar y volver a confirmar.
- **Registrar reporte** está desactivado mientras no exista una ubicación confirmada. El handler también valida esta condición.
- El ciudadano ve el origen del punto y el recordatorio de que debe señalar la basura, no simplemente la posición del dispositivo.
- El POST conserva coordenadas numéricas, descripción, fecha con zona horaria y tipo opcional. No se envían precisión, origen ni confirmación como campos nuevos.
- D3 calcula rasgos por pares del conjunto de ajuste y exporta CSV. No se conecta a FastAPI, no agrupa automáticamente y no cambia estados ni tablas.

## Resultados comprobados

| Ejecución | Resultado |
| --- | --- |
| `npm run check` | **39 tests correctos** y tipos correctos |
| `npm run build` | **Compilación correcta**; permanece la advertencia de un chunk superior a 500 kB |
| Suite Python completa | **31 tests correctos**: 11 existentes y 20 del comparador D3 |
| `PLAYWRIGHT_CHANNEL=chrome npm run test:browser` | **6 pruebas correctas**: GPS simulado, bloqueo/confirmación, clic, arrastre, selección táctil, fotos y vista municipal |
| HTTP con FastAPI real | Chrome recibe `/health` **200** y `/me` sin token **401**, con CORS correcto |
| CLI D3 | `--help` funciona. Sin Sentence Transformers indica la instalación opcional y no escribe archivos. La exportación de **15 pares** se comprueba con encoder artificial en un directorio temporal |

Las pruebas de negocio usan Auth/API/Storage simulados o SQLite. La prueba de archivos temporales de pytest necesitó ejecutarse con permisos fuera del entorno restringido de Windows; no se modificó la aplicación para resolver ese permiso.

## Pendientes

- Probar GPS físico y permisos reales del sistema en un móvil mediante HTTPS.
- Registrar y consultar con las cuentas reales de Supabase, validar JWKS/PostgreSQL y comprobar fotos del bucket privado.
- Instalar la dependencia opcional y descargar/ejecutar el candidato semántico sobre ajuste. No hay resultados reales del modelo ni métricas de calidad en esta entrega.
- Revisar etiquetas con otro integrante, acordar contrato D2/D3 y congelar reglas antes de procesar evaluación.
- Continuar la verificación de recursos municipales en la siguiente etapa. Esta integración no declara cerrado todo el Sprint 1.

Para los comandos de arranque y las dos opciones de ubicación, consultar [frontend/README.md](../frontend/README.md). Para ejecutar D3, consultar [SPRINT1_MODELO.md](../d3/SPRINT1_MODELO.md).
