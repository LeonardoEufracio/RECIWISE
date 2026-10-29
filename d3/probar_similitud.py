"""Prototipo local de similitud D3 del Sprint 1.

Adaptado de _actualizacion_sprint1/d3/probar_similitud.py tras compararlo
con los contratos y la preparación de datos existentes.
No agrupa reportes ni modifica estados o datos del backend.

    python -m d3.probar_similitud

Por defecto usa ajuste. --evaluar requiere una decisión explícita del equipo.
"""
import argparse
import csv
from datetime import datetime
from itertools import combinations
from math import fsum, isfinite, sqrt

from .geo_temporal import diferencia_horas, distancia_metros
from .preparar_datos import CAMPOS_ENTRADA, SALIDA, preparar

MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
VERSION = "d3-sprint1-prototipo-v1"
CAMPOS_SALIDA = [
    "id_1", "id_2", "similitud_texto", "distancia_metros",
    "diferencia_horas", "tipo_residuo_1", "tipo_residuo_2",
    "version_configuracion",
]


def crear_pares(filas, encoder):
    """Calcula coseno, Haversine y horas sin pasar etiquetas al encoder.

    Solo la descripción pasa al modelo. Las fechas, coordenadas y tipos
    se procesan por separado; no se decide si representan el mismo evento.
    """
    if not filas:
        return []
    if any(not set(CAMPOS_ENTRADA).issubset(fila) for fila in filas):
        raise ValueError("Faltan campos de entrada")
    datos = []
    ids = set()
    for fila in filas:
        descripcion = fila["descripcion"]
        if not isinstance(descripcion, str) or not descripcion.strip():
            raise ValueError("La descripción no puede estar vacía")
        if fila["id"] in ids:
            raise ValueError("ID de reporte repetido")
        ids.add(fila["id"])
        lat, lon = float(fila["latitud"]), float(fila["longitud"])
        distancia_metros(lat, lon, lat, lon)  # Valida límites antes del encoder.
        observada = datetime.fromisoformat(fila["fecha_observacion"])
        reportada = datetime.fromisoformat(fila["fecha_reporte"])
        diferencia_horas(observada, reportada)  # Exige zonas horarias.
        if reportada < observada:
            raise ValueError("Reporte anterior a observación")
        datos.append((lat, lon, observada))

    vectores = encoder.encode([fila["descripcion"] for fila in filas],
                             normalize_embeddings=True, show_progress_bar=False)
    if len(vectores) != len(filas):
        raise ValueError("El modelo no devolvió un vector por reporte")
    vectores = [[float(valor) for valor in vector] for vector in vectores]
    dimension = len(vectores[0])
    if not dimension or any(len(vector) != dimension for vector in vectores):
        raise ValueError("Los vectores deben tener la misma dimensión no vacía")
    if any(not isfinite(valor) for vector in vectores for valor in vector):
        raise ValueError("Los vectores deben contener números finitos")
    normas = [sqrt(fsum(valor * valor for valor in vector)) for vector in vectores]
    if any(not isfinite(norma) or norma == 0 for norma in normas):
        raise ValueError("Los vectores deben tener norma finita y distinta de cero")

    resultado = []
    for i, j in combinations(range(len(filas)), 2):
        a, b = filas[i], filas[j]
        lat_a, lon_a, fecha_a = datos[i]
        lat_b, lon_b, fecha_b = datos[j]
        producto = fsum(x * y for x, y in zip(vectores[i], vectores[j]))
        # La normalización explícita evita asumir que cualquier encoder
        # suministrado cumple normalize_embeddings; limitar solo el redondeo.
        similitud = max(-1.0, min(1.0, producto / (normas[i] * normas[j])))
        resultado.append({
            "id_1": a["id"], "id_2": b["id"],
            "similitud_texto": round(similitud, 6),
            "distancia_metros": round(distancia_metros(lat_a, lon_a, lat_b, lon_b), 2),
            "diferencia_horas": round(diferencia_horas(fecha_a, fecha_b), 2),
            "tipo_residuo_1": a["tipo_residuo"], "tipo_residuo_2": b["tipo_residuo"],
            "version_configuracion": VERSION,
        })
    return resultado


def main(argv=None):
    parser = argparse.ArgumentParser(description="RECIWISE D3: comparación semántica inicial")
    parser.add_argument("--evaluar", action="store_true",
                        help="Procesa el conjunto reservado. No usar para ajustar reglas.")
    args = parser.parse_args(argv)
    particion = "evaluacion" if args.evaluar else "ajuste"
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise SystemExit("Falta la dependencia opcional: instala con python -m pip install -r d3/requirements.txt") from exc

    preparar()  # Valida particiones por evento y exporta entradas sin etiquetas.
    ruta = SALIDA / f"entradas_{particion}.csv"
    with ruta.open(encoding="utf-8", newline="") as archivo:
        filas = list(csv.DictReader(archivo))
    print(f"Modelo candidato: {MODELO}")
    print(f"Partición: {particion} (datos simulados; etiquetas excluidas)")
    modelo = SentenceTransformer(MODELO)
    pares = crear_pares(filas, modelo)
    destino = SALIDA / f"comparaciones_{particion}.csv"
    with destino.open("w", encoding="utf-8", newline="") as archivo:
        writer = csv.DictWriter(archivo, fieldnames=CAMPOS_SALIDA)
        writer.writeheader()
        writer.writerows(pares)
    print(f"Comparaciones calculadas: {len(pares)}")
    print(f"Archivo: {destino}")
    print("Estas puntuaciones NO son probabilidades ni decisiones de agrupación.")
    print("No se han ajustado umbrales ni evaluado precisión en este paso.")


if __name__ == "__main__":
    main()
