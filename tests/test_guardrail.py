import json
import pathlib

import pytest
import requests

from poc_psico.errores import FlujoDetenido
from poc_psico.guardrail import (
    ClasificacionClinica,
    GuardrailError,
    consultar_decisions,
    construir_payload,
    extraer_prob,
    guardrail_llm,
    pasa_guardrail,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


class RespuestaFalsa:
    def __init__(self, estado=200, cuerpo=None, texto=""):
        self.status_code = estado
        self._cuerpo = cuerpo
        self.text = texto or json.dumps(cuerpo)

    def json(self):
        return self._cuerpo


def test_payload_contiene_modelo_estado_y_pregunta():
    p = construir_payload("texto anonimizado")
    assert p["model"] == "respan/span-01-lite:free"
    assert p["state"] == "texto anonimizado"
    assert "es_clinico" in p["questions"]


def test_guardrail_error_es_un_flujo_detenido():
    assert issubclass(GuardrailError, FlujoDetenido)


def test_extraer_prob_sigue_la_ruta():
    resp = {"a": {"b": 0.8}}
    assert extraer_prob(resp, ruta=("a", "b")) == pytest.approx(0.8)


@pytest.mark.parametrize("resp", [{}, {"a": {}}, {"a": {"b": "no es número"}}, {"a": {"b": 1.5}}])
def test_extraer_prob_con_formato_inesperado_lanza_error(resp):
    with pytest.raises(GuardrailError):
        extraer_prob(resp, ruta=("a", "b"))


def test_consultar_decisions_devuelve_la_probabilidad(monkeypatch):
    import poc_psico.guardrail as g

    monkeypatch.setattr(g, "RUTA_PROB", ("p",))
    llamadas = {}

    def post(url, json, headers, timeout):
        llamadas.update(url=url, json=json, headers=headers)
        return RespuestaFalsa(200, {"p": 0.93})

    assert consultar_decisions("texto", "clave-falsa", post=post, ruta=("p",)) == pytest.approx(0.93)
    assert llamadas["url"].endswith("/decisions")
    assert llamadas["headers"]["Authorization"] == "Bearer clave-falsa"


def test_consultar_decisions_con_http_no_200_lanza_error():
    post = lambda url, json, headers, timeout: RespuestaFalsa(429, texto="rate limit")
    with pytest.raises(GuardrailError, match="429"):
        consultar_decisions("texto", "k", post=post)


def test_consultar_decisions_con_falla_de_red_lanza_error():
    def post(url, json, headers, timeout):
        raise requests.ConnectionError("sin red")

    with pytest.raises(GuardrailError, match="sin red"):
        consultar_decisions("texto", "k", post=post)


class ClasificadorFalso:
    def __init__(self, es_clinico):
        self.es_clinico = es_clinico
        self.recibido = None

    def invoke(self, mensajes):
        self.recibido = mensajes
        return ClasificacionClinica(es_clinico=self.es_clinico)


def test_guardrail_llm_devuelve_1_o_0():
    assert guardrail_llm("texto", ClasificadorFalso(True)) == 1.0
    assert guardrail_llm("texto", ClasificadorFalso(False)) == 0.0


def test_pasa_guardrail_usa_el_umbral_inclusivo():
    assert pasa_guardrail(0.5, 0.5) is True
    assert pasa_guardrail(0.49, 0.5) is False


@pytest.mark.skipif(
    not (FIXTURES / "decisions_clinico.json").exists(), reason="falta el fixture del spike (Task 2)"
)
def test_fixtures_reales_separan_clinico_de_cocina():
    clinico = json.loads((FIXTURES / "decisions_clinico.json").read_text(encoding="utf-8"))
    cocina = json.loads((FIXTURES / "decisions_cocina.json").read_text(encoding="utf-8"))
    p_clinico, p_cocina = extraer_prob(clinico), extraer_prob(cocina)
    assert p_clinico >= 0.5 > p_cocina
