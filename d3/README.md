# RECIWISE — Entregable inicial D3 (Sprint 1)

**Estado: prototipo de similitud integrado, sin modelo semántico real ejecutado todavía.** Se incorporó la entrega de `_actualizacion_sprint1` después de compararla con el proyecto. Las pruebas usan un encoder artificial; no son resultados científicos ni datos levantados en El Tambo.

## Archivos

- `data/ejemplos_etiquetados.csv`: 12 reportes **100 % simulados**, organizados en eventos esperados; seis para ajuste y seis para evaluación inicial. `evento_esperado_id` es una **etiqueta de referencia**, no un dato que reciba el modelo.
- `data/casos_para_revision.csv`: un caso ambiguo y dos ejemplos de calidad inválida. No deben entrenarse como verdades de agrupación ni introducirse en la base como reportes válidos.
- `preparar_datos.py`: valida filas y exporta `output/entradas_ajuste.csv` y `output/entradas_evaluacion.csv`, **sin** la columna de evento esperado.
- `geo_temporal.py`: calcula Haversine en metros y diferencia absoluta de horas entre fechas con zona horaria. No calcula distancia vial ni decide agrupaciones.
- `probar_similitud.py`: calcula similitud coseno, distancia y diferencia temporal para todos los pares de una partición. Usa solo descripciones como entrada del modelo, valida vectores y produce un CSV sin etiquetas. Por defecto procesa **ajuste**.
- `requirements.txt`: dependencia opcional `sentence-transformers`, separada de las dependencias del backend.
- [SPRINT1_MODELO.md](SPRINT1_MODELO.md): ejecución, campos de salida, verificaciones y límites del prototipo integrado.

## Reproducir la preparación

Desde la carpeta raíz (`RECIWISE`):

```bash
python -m d3.preparar_datos
python -m pytest -q tests/test_d3.py tests/test_d3_similitud.py
```

Se espera un resumen de **6 filas de ajuste y 6 de evaluación**. Los datos están preparados exclusivamente como base de desarrollo. Son demasiado pequeños para afirmar rendimiento generalizable.

## Qué se ha separado y qué falta

Las particiones se asignaron por **evento completo**: ningún identificador `evento_esperado_id` figura a la vez en ajuste y evaluación. El programa rechaza ese caso. Aun así, una persona del equipo debe revisar las etiquetas y los escenarios. El identificador del evento **no** debe añadirse a embeddings, campos de texto ni características de entrada.

Para probar agrupación automática, antes hay que completar:

1. Acordar con D2 los nombres y tipos de campo en `docs/CONTRATOS_D3.md`, incluidas fechas de observación y reporte.
2. Etiquetar y revisar más casos; reunir también pares negativos, casos ambiguos, contradicciones y recurrencias.
3. Instalar y ejecutar el candidato `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` con el script ya integrado, preferentemente en entorno aislado. El modelo real no se ha descargado ni corrido aquí.
4. Combinar **puntuación de texto**, proximidad geográfica, diferencia temporal, tipo de intervención y estado del evento. Definir los umbrales con los datos de ajuste, **no** con el conjunto reservado de evaluación.
5. Producir sugerencias explicables (`agrupar_candidato`, `requiere_revision`, `mantener_separado`) y razones. Nunca usar una puntuación como probabilidad calibrada.
6. Revisar especialmente el caso de evento antiguo cerrado vs acumulación nueva; consultar el estado y la fecha de cierre **del candidato**, no deducir el cierre solo a partir del texto.

## Mapeo de datos con D2

| D3 (contrato de intercambio) | API/base D2 | Comentario |
|---|---|---|
| `id` | `reports.id` | Identificador único del reporte |
| `descripcion` | `reports.description` | No modificar negaciones ni números relevantes |
| `latitud` / `longitud` | `reports.latitude` / `reports.longitude` | WGS84, valores numéricos |
| `fecha_observacion` | `reports.observed_at` | Fecha de lo observado, con zona horaria |
| `fecha_reporte` | `reports.created_at` | Fecha de recepción del reporte, fijada por servidor |
| `tipo_residuo` | `reports.waste_type` | Información opcional, no inventarla |
| `evento_asociado_id` | `event_reports.event_id` | Relación existente, no etiqueta esperada |
| `estado_evento` | `events.state` | Estado real del evento candidato, si existe |
| `fecha_cierre_evento` | `events.closed_at` | Puede ser nula |

El archivo `ejemplos_etiquetados.csv` es **externo a PostgreSQL** y sus eventos `EV_SIM_...` son etiquetas para evaluación. No son UUID reales de `events`, ni se insertan en `event_reports`.

**Criterio de entrega D3 en este primer paso:** contrato revisado con D2, conjunto de ejemplos etiquetado y revisión hecha por un segundo integrante, script reproducible y pruebas locales. El archivo entregado hoy cubre la estructura inicial; la revisión humana y la validación real siguen pendientes.
