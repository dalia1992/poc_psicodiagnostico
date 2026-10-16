import pytest
import requests

from poc_psico.errores import FlujoDetenido
from poc_psico.guias import buscar_guias_apa, consulta_desde_candidatos, solo_apa

CANDIDATOS = [
    {"codigo": "6A70", "titulo": "Trastorno depresivo de episodio único", "url": "https://icd.who.int/x"},
    {"codigo": "6B00", "titulo": "Trastorno de ansiedad generalizada", "url": "https://icd.who.int/y"},
]


def cita(url, titulo="Guía", contenido="Resumen de la guía."):
    return {"type": "url_citation", "url_citation": {"url": url, "title": titulo, "content": contenido}}


class RespuestaFalsa:
    def __init__(self, status=200, cuerpo=None, texto=""):
        self.status_code, self._cuerpo, self.text = status, cuerpo, texto

    def json(self):
        if isinstance(self._cuerpo, Exception):
            raise self._cuerpo
        return self._cuerpo


def respuesta_con(*anotaciones):
    return RespuestaFalsa(cuerpo={"choices": [{"message": {"content": "ok", "annotations": list(anotaciones)}}]})


class PostFalso:
    def __init__(self, *respuestas):
        self.respuestas, self.llamadas = list(respuestas), []

    def __call__(self, url, json=None, headers=None, timeout=None):
        self.llamadas.append({"url": url, "json": json, "headers": headers})
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_la_consulta_usa_solo_titulos_de_la_cie11():
    q = consulta_desde_candidatos(CANDIDATOS)
    assert "Trastorno depresivo de episodio único" in q and "Trastorno de ansiedad generalizada" in q
    assert "6A70" not in q


def test_la_consulta_se_limita_a_los_primeros_candidatos():
    muchos = [{"codigo": f"X{i}", "titulo": f"Entidad {i}"} for i in range(10)]
    q = consulta_desde_candidatos(muchos, maximo=3)
    assert "Entidad 2" in q and "Entidad 3" not in q


@pytest.mark.parametrize("url,esperado", [
    ("https://www.apa.org/depression-guideline", True),
    ("https://apa.org/x", True),
    ("https://psychiatry.apa.org/y", True),
    ("https://apa.org.evil.com/x", False),
    ("https://notapa.org/x", False),
    ("https://example.com/apa.org", False),
    ("no es una url", False),
])
def test_solo_apa_acepta_el_dominio_y_sus_subdominios(url, esperado):
    assert bool(solo_apa([cita(url)])) is esperado


def test_la_peticion_restringe_el_dominio_y_no_lleva_datos_del_paciente():
    post = PostFalso(respuesta_con(cita("https://www.apa.org/g")))
    buscar_guias_apa(CANDIDATOS, "clave", post=post)
    enviado = post.llamadas[0]["json"]
    plugin = enviado["plugins"][0]
    assert plugin["id"] == "web" and plugin["include_domains"] == ["apa.org"] and plugin["engine"] == "exa"
    assert enviado["max_tokens"] >= 2000
    assert "exclude_domains" not in plugin
    assert post.llamadas[0]["headers"]["Authorization"] == "Bearer clave"
    assert "Trastorno depresivo" in str(enviado["messages"])


def test_devuelve_titulo_url_y_cita_recortada():
    largo = "x" * 1000
    post = PostFalso(respuesta_con(cita("https://www.apa.org/g", "Guía de depresión", largo)))
    guias = buscar_guias_apa(CANDIDATOS, "clave", post=post)
    assert guias[0]["titulo"] == "Guía de depresión" and guias[0]["url"] == "https://www.apa.org/g"
    assert 0 < len(guias[0]["cita"]) <= 300


def test_descarta_citas_fuera_de_apa_y_duplicadas():
    post = PostFalso(respuesta_con(
        cita("https://www.apa.org/g"), cita("https://www.apa.org/g"), cita("https://blog.example.com/z")))
    guias = buscar_guias_apa(CANDIDATOS, "clave", post=post)
    assert [g["url"] for g in guias] == ["https://www.apa.org/g"]


def test_sin_anotaciones_devuelve_lista_vacia():
    assert buscar_guias_apa(CANDIDATOS, "clave", post=PostFalso(respuesta_con())) == []


def test_sin_candidatos_no_llama_a_la_red():
    post = PostFalso()
    assert buscar_guias_apa([], "clave", post=post) == []
    assert post.llamadas == []


def test_sin_clave_falla():
    with pytest.raises(FlujoDetenido, match="OPENROUTER_API_KEY"):
        buscar_guias_apa(CANDIDATOS, "", post=PostFalso())


def test_error_http_levanta_flujo_detenido():
    with pytest.raises(FlujoDetenido, match="402"):
        buscar_guias_apa(CANDIDATOS, "clave", post=PostFalso(RespuestaFalsa(402, texto="sin créditos")))


def test_error_de_red_levanta_flujo_detenido():
    with pytest.raises(FlujoDetenido, match="conectar"):
        buscar_guias_apa(CANDIDATOS, "clave", post=PostFalso(requests.ConnectionError("caído")))


def test_formato_inesperado_levanta_flujo_detenido():
    with pytest.raises(FlujoDetenido, match="formato"):
        buscar_guias_apa(CANDIDATOS, "clave", post=PostFalso(RespuestaFalsa(cuerpo={"otra": 1})))


def test_reintenta_un_503_y_luego_responde():
    post = PostFalso(RespuestaFalsa(503, texto="overload"), respuesta_con(cita("https://www.apa.org/g")))
    esperas = []
    guias = buscar_guias_apa(CANDIDATOS, "clave", post=post, esperar=esperas.append)
    assert len(guias) == 1 and esperas == [1]


def test_la_cita_se_limpia_de_encabezados_markdown_y_puntos_suspensivos():
    guias = solo_apa([cita("https://www.apa.org/g", contenido="## GUÍA\n\n...\n\nRecomienda terapia.")])
    assert guias[0]["cita"] == "GUÍA Recomienda terapia."
