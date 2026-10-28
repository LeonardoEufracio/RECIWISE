"""Valida ejemplos SIMULADOS y exporta entradas sin etiquetas.

Uso desde la raíz del repo:
    python -m d3.preparar_datos
"""
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from uuid import UUID

BASE = Path(__file__).resolve().parent
DATASET = BASE / "data" / "ejemplos_etiquetados.csv"
SALIDA = BASE / "output"
CAMPOS_ENTRADA = [
    "id", "descripcion", "latitud", "longitud", "fecha_observacion",
    "fecha_reporte", "tipo_residuo",
]
PARTICIONES = {"ajuste", "evaluacion"}


def validar(filas: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Rechaza fugas: un mismo evento no puede estar en dos particiones."""
    eventos = defaultdict(set)
    ids = set()
    resultado = {split: [] for split in PARTICIONES}
    for fila in filas:
        identificador = str(UUID(fila["id"]))
        if identificador in ids:
            raise ValueError(f"ID de reporte repetido: {identificador}")
        ids.add(identificador)
        if not fila["descripcion"].strip():
            raise ValueError(f"Descripción vacía: {identificador}")
        lat, lon = float(fila["latitud"]), float(fila["longitud"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"Coordenadas inválidas: {identificador}")
        observado = datetime.fromisoformat(fila["fecha_observacion"])
        reportado = datetime.fromisoformat(fila["fecha_reporte"])
        if not (observado.tzinfo and observado.utcoffset() is not None
                and reportado.tzinfo and reportado.utcoffset() is not None):
            raise ValueError(f"Fecha sin zona horaria: {identificador}")
        if reportado < observado:
            raise ValueError(f"Reporte anterior a observación: {identificador}")
        if fila["origen_dato"] != "simulado":
            raise ValueError("El origen de este dataset debe ser simulado")
        split = fila["particion"]
        if split not in PARTICIONES:
            raise ValueError(f"Partición inesperada: {split}")
        evento = fila["evento_esperado_id"].strip()
        if not evento:
            raise ValueError(f"Falta evento esperado para {identificador}")
        eventos[evento].add(split)
        resultado[split].append(fila)
    contaminados = [key for key, splits in eventos.items() if len(splits) > 1]
    if contaminados:
        raise ValueError(f"Fuga de etiquetas entre ajuste y evaluación: {contaminados}")
    if not all(resultado.values()):
        raise ValueError("Se necesitan ejemplos en ambas particiones")
    return resultado


def preparar() -> dict[str, int]:
    with DATASET.open(newline="", encoding="utf-8") as archivo:
        filas = list(csv.DictReader(archivo))
    grupos = validar(filas)
    SALIDA.mkdir(exist_ok=True)
    for nombre, registros in grupos.items():
        ruta = SALIDA / f"entradas_{nombre}.csv"
        with ruta.open("w", encoding="utf-8", newline="") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=CAMPOS_ENTRADA)
            escritor.writeheader()
            escritor.writerows({k: fila[k] for k in CAMPOS_ENTRADA} for fila in registros)
    return {nombre: len(registros) for nombre, registros in grupos.items()}


if __name__ == "__main__":
    conteos = preparar()
    print("Entradas preparadas (sin evento_esperado_id):", conteos)
    print("Importante: los eventos de evaluación permanecen reservados.")
