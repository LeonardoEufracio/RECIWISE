# Sprint 1: prototipo de similitud D3 integrado

Integrado el **29 de octubre de 2026** desde `_actualizacion_sprint1/d3/probar_similitud.py`, después de revisar el contrato y la preparación de datos existentes. El script es una herramienta local; no añade endpoints ni modifica reportes, eventos o estados en PostgreSQL.

**Estado comprobado:** las pruebas pasan con encoders artificiales. Sentence Transformers y el modelo real no están instalados en el entorno revisado; no se presentan resultados de inferencia real ni métricas de calidad.

## Ejecutar con el modelo real

Desde la raíz del proyecto, se puede usar un entorno independiente del backend:

```powershell
python -m venv .venv-d3
.\.venv-d3\Scripts\python.exe -m pip install -r d3/requirements.txt
.\.venv-d3\Scripts\python.exe -m d3.probar_similitud
```

En Linux/macOS, usar `.venv-d3/bin/python` en lugar de `.venv-d3\Scripts\python.exe`. La carpeta del entorno está excluida de Git. Las pruebas del comparador no requieren instalar este paquete.

El primer uso descarga el candidato público `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` de Hugging Face. No hace falta una clave Supabase. El script no carga `.env`, no consulta tablas y no envía reportes a la API; usa exclusivamente los datos simulados de `d3/data/`.

Antes de generar las entradas valida IDs, fechas, coordenadas y la separación por eventos con `preparar_datos.py`. Por defecto se codifican las seis descripciones de **ajuste**, que producen **15 pares** en `d3/output/comparaciones_ajuste.csv`. Los CSV de comparaciones son artefactos locales excluidos de Git.

No ejecutar `--evaluar` durante la exploración de reglas o umbrales. Esta opción procesa la partición reservada y debe utilizarse después de congelar las decisiones experimentales. No se utilizó con el modelo real durante la integración.

## Contrato y controles

- El encoder recibe solo la lista de `descripcion`, con `normalize_embeddings=True`. IDs, coordenadas, fechas, tipos, etiquetas y notas no se concatenan al texto.
- Se calculan por separado Haversine en metros y diferencia absoluta de horas entre observaciones con zona horaria.
- Se calcula coseno normalizado; se rechazan vectores vacíos, con dimensiones distintas, no finitos o de norma cero. También se validan datos antes de invocar el encoder.
- La salida contiene `id_1`, `id_2`, `similitud_texto`, `distancia_metros`, `diferencia_horas`, `tipo_residuo_1`, `tipo_residuo_2` y `version_configuracion` (`d3-sprint1-prototipo-v1`). Nunca incluye `evento_esperado_id` ni notas de etiquetado.
- Las puntuaciones no son probabilidades, umbrales de aceptación ni decisiones de agrupación. Texto igual con puntos lejanos sigue requiriendo revisión.

## Pruebas y evidencia

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m d3.probar_similitud --help
```

La suite Python completa pasa **31 pruebas**: las 11 existentes de API/datos y 20 del comparador. Comprueba textos enviados al encoder, exclusión de etiquetas/notas, cosenos conocidos, distancia y tiempo, entradas inválidas, vectores inválidos, generación de 15 filas y selección de ajuste por defecto. Los archivos de prueba se escriben en un directorio temporal, sin producir resultados semánticos ficticios en `d3/output/`.

Si falta la dependencia opcional, el CLI muestra cómo instalar `d3/requirements.txt` y termina sin generar archivos. Este comportamiento también se verificó.

En el entorno restringido de esta revisión, pytest necesitó permiso para crear y leer su carpeta temporal en Windows. Se utilizó una ruta nueva dentro de `.test-artifacts/` con `--basetemp`; no se cambiaron permisos de los archivos del proyecto para resolverlo.

## Pendiente experimental

Ejecutar el modelo real sobre ajuste, registrar versiones instaladas y revisar errores con otro integrante. Después, acordar el contrato operativo con D2 y congelar reglas antes de usar evaluación. El dataset sigue siendo pequeño y simulado; este prototipo no implementa la salida operativa `agrupar_candidato / requiere_revision / mantener_separado`.

Referencias del candidato y su API: [modelo multilingüe](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2), [similitud textual](https://www.sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html) e [instalación opcional](https://www.sbert.net/docs/installation.html).
