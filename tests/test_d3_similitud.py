import csv
import sys
from types import SimpleNamespace

import pytest

from d3.preparar_datos import CAMPOS_ENTRADA, DATASET, validar
from d3.probar_similitud import VERSION, crear_pares
from d3 import probar_similitud as comparador


class FakeEncoder:
    def __init__(self):
        self.texts = None

    def encode(self, texts, normalize_embeddings, show_progress_bar):
        self.texts = texts
        assert normalize_embeddings is True
        assert show_progress_bar is False
        return [[1.0, 0.0] for _ in texts]


def test_crear_pares_no_incluye_etiquetas_como_entrada():
    with DATASET.open(encoding='utf-8', newline='') as f:
        filas = list(csv.DictReader(f))
    grupos = validar(filas)
    filas_ajuste = [{k: r[k] for k in CAMPOS_ENTRADA} for r in grupos['ajuste']]
    encoder = FakeEncoder()
    pares = crear_pares(filas_ajuste, encoder)
    assert len(pares) == 15  # 6 informes => 6*5/2 comparaciones
    assert encoder.texts == [f['descripcion'] for f in filas_ajuste]
    assert all('evento_esperado_id' not in p for p in pares)
    assert all(p['version_configuracion'] == VERSION for p in pares)
    assert all(p['similitud_texto'] == pytest.approx(1.0) for p in pares)


def test_mismas_palabras_muy_lejos_no_implican_misma_acumulacion():
    with DATASET.open(encoding='utf-8', newline='') as f:
        filas = list(csv.DictReader(f))
    por_id = {f['id']: f for f in filas}
    a = por_id['00000000-0000-4000-8000-000000000003']
    b = por_id['00000000-0000-4000-8000-000000000004']
    pares = crear_pares([{k: r[k] for k in CAMPOS_ENTRADA} for r in (a, b)], FakeEncoder())
    assert pares[0]['similitud_texto'] == 1.0
    assert pares[0]['distancia_metros'] > 1000


def filas_ajuste():
    with DATASET.open(encoding='utf-8', newline='') as archivo:
        return validar(list(csv.DictReader(archivo)))['ajuste']


def test_etiquetas_y_notas_nunca_entran_al_modelo_aunque_se_reciban():
    filas = filas_ajuste()
    encoder = FakeEncoder()
    pares = crear_pares(filas, encoder)
    assert encoder.texts == [fila['descripcion'] for fila in filas]
    assert all(set(par) == set(comparador.CAMPOS_SALIDA) for par in pares)
    assert all('EV_SIM_' not in str(par) for par in pares)


@pytest.mark.parametrize(('vectores', 'esperado'), [
    ([[2, 0], [0, 3]], 0),
    ([[2, 0], [-4, 0]], -1),
    ([[2, 0], [3, 0]], 1),
])
def test_coseno_conocido_y_normalizacion(vectores, esperado):
    class Encoder(FakeEncoder):
        def encode(self, texts, normalize_embeddings, show_progress_bar):
            super().encode(texts, normalize_embeddings, show_progress_bar)
            return vectores

    par = crear_pares(filas_ajuste()[:2], Encoder())[0]
    assert par['similitud_texto'] == pytest.approx(esperado)
    assert par['diferencia_horas'] == pytest.approx(0.25)
    assert 0 < par['distancia_metros'] < 10


@pytest.mark.parametrize('vectores', [
    [[1, 0]], [[], []], [[1, 0], [1]],
    [[float('nan'), 0], [1, 0]], [[float('inf'), 0], [1, 0]],
    [[0, 0], [1, 0]],
])
def test_rechaza_vectores_incompletos_o_no_finitos(vectores):
    class Encoder(FakeEncoder):
        def encode(self, texts, normalize_embeddings, show_progress_bar):
            return vectores

    with pytest.raises(ValueError):
        crear_pares(filas_ajuste()[:2], Encoder())


@pytest.mark.parametrize('cambio', [
    {'descripcion': '   '}, {'latitud': '91'}, {'longitud': 'nan'},
    {'fecha_observacion': '2026-10-25T09:00:00'},
    {'fecha_reporte': '2026-10-24T09:00:00-05:00'},
])
def test_valida_datos_antes_de_invocar_modelo(cambio):
    filas = filas_ajuste()[:2]
    filas[0].update(cambio)
    encoder = FakeEncoder()
    with pytest.raises(ValueError):
        crear_pares(filas, encoder)
    assert encoder.texts is None


def test_entradas_vacias_campos_ausentes_e_ids_repetidos():
    encoder = FakeEncoder()
    assert crear_pares([], encoder) == []
    with pytest.raises(ValueError, match='Faltan campos'):
        crear_pares([{'descripcion': 'Basura'}], encoder)
    fila = filas_ajuste()[0]
    with pytest.raises(ValueError, match='repetido'):
        crear_pares([fila, fila], encoder)
    assert encoder.texts is None


def test_cli_por_defecto_solo_codifica_ajuste_y_exporta_15_pares(tmp_path, monkeypatch):
    filas = filas_ajuste()
    with (tmp_path / 'entradas_ajuste.csv').open('w', encoding='utf-8', newline='') as archivo:
        writer = csv.DictWriter(archivo, fieldnames=CAMPOS_ENTRADA)
        writer.writeheader()
        writer.writerows({campo: fila[campo] for campo in CAMPOS_ENTRADA} for fila in filas)
    reservado = tmp_path / 'entradas_evaluacion.csv'
    reservado.write_text('RESERVADO: no debe leerse ni codificarse', encoding='utf-8')
    encoder = FakeEncoder()

    def load_model(nombre):
        assert nombre == comparador.MODELO
        return encoder

    monkeypatch.setitem(sys.modules, 'sentence_transformers', SimpleNamespace(SentenceTransformer=load_model))
    monkeypatch.setattr(comparador, 'SALIDA', tmp_path)
    monkeypatch.setattr(comparador, 'preparar', lambda: None)
    comparador.main([])
    with (tmp_path / 'comparaciones_ajuste.csv').open(encoding='utf-8', newline='') as archivo:
        reader = csv.DictReader(archivo)
        assert reader.fieldnames == comparador.CAMPOS_SALIDA
        assert len(list(reader)) == 15
    assert encoder.texts == [fila['descripcion'] for fila in filas]
    assert reservado.read_text(encoding='utf-8') == 'RESERVADO: no debe leerse ni codificarse'
    assert not (tmp_path / 'comparaciones_evaluacion.csv').exists()


def test_dependencia_opcional_ausente_da_instruccion_sin_escribir_archivos(monkeypatch):
    monkeypatch.setitem(sys.modules, 'sentence_transformers', None)

    def no_preparar():
        pytest.fail('No preparar archivos si falta la dependencia opcional')

    monkeypatch.setattr(comparador, 'preparar', no_preparar)
    with pytest.raises(SystemExit, match='d3/requirements.txt'):
        comparador.main([])
