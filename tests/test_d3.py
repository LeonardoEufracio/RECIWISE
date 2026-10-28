from datetime import datetime
import csv
import pytest
from d3.geo_temporal import distancia_metros, diferencia_horas
from d3.preparar_datos import DATASET, CAMPOS_ENTRADA, preparar, validar, SALIDA


def test_geo_temporal():
    assert distancia_metros(-12, -75, -12, -75) == pytest.approx(0)
    assert 100 < distancia_metros(-12, -75, -12.001, -75) < 120
    assert diferencia_horas(datetime.fromisoformat("2026-10-26T09:00:00-05:00"),
                            datetime.fromisoformat("2026-10-26T16:00:00+02:00")) == 0
    with pytest.raises(ValueError):
        distancia_metros(-91, -75, -12, -75)
    with pytest.raises(ValueError):
        diferencia_horas(datetime(2026, 10, 26), datetime.fromisoformat("2026-10-26T09:00:00-05:00"))


def test_d3_dataset_separated_by_event_and_excludes_labels():
    total = preparar()
    assert total == {"ajuste": 6, "evaluacion": 6}
    with DATASET.open(encoding="utf-8", newline="") as archivo:
        filas = list(csv.DictReader(archivo))
    assert len(filas) == 12
    assert all(fila["origen_dato"] == "simulado" for fila in filas)
    for split in ("ajuste", "evaluacion"):
        with (SALIDA / f"entradas_{split}.csv").open(encoding="utf-8", newline="") as f:
            lector = csv.DictReader(f)
            assert lector.fieldnames == CAMPOS_ENTRADA
            assert "evento_esperado_id" not in lector.fieldnames


def test_reject_label_leakage():
    with DATASET.open(encoding="utf-8", newline="") as archivo:
        filas = list(csv.DictReader(archivo))
    filas[1]["particion"] = "evaluacion"
    with pytest.raises(ValueError, match="Fuga de etiquetas"):
        validar(filas)
