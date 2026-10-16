import pytest
import requests

from poc_psico.errores import FlujoDetenido
from poc_psico.guias import _dominio_permitido, buscar_guias_apa, consulta_desde_candidatos, solo_dominios

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
    """Una respuesta por búsqueda; si se pasa una sola, se repite (hay una búsqueda de evaluación y otra de intervención)."""

    def __init__(self, *respuestas):
        self.respuestas, self.llamadas = list(respuestas), []
        self.repetir = len(respuestas) == 1

    def __call__(self, url, json=None, headers=None, timeout=None):
        self.llamadas.append({"url": url, "json": json, "headers": headers})
        r = self.respuestas[0] if self.repetir else self.respuestas.pop(0)
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
def test_dominio_permitido_acepta_el_dominio_y_sus_subdominios(url, esperado):
    assert _dominio_permitido(url, ["apa.org"]) is esperado
    assert bool(solo_dominios([cita(url)], ["apa.org"])) is esperado


def test_la_peticion_restringe_el_dominio_y_no_lleva_datos_del_paciente():
    post = PostFalso(respuesta_con(cita("https://www.apa.org/g")))
    buscar_guias_apa(CANDIDATOS, "clave", post=post)
    assert len(post.llamadas) == 4
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
    post = PostFalso(RespuestaFalsa(503, texto="overload"), respuesta_con(cita("https://www.apa.org/g")),
                     respuesta_con(), respuesta_con(), respuesta_con())
    esperas = []
    guias = buscar_guias_apa(CANDIDATOS, "clave", post=post, esperar=esperas.append)
    assert len(guias) == 1 and esperas == [1]


def test_la_cita_se_limpia_de_encabezados_markdown_y_puntos_suspensivos():
    guias = solo_dominios([cita("https://www.apa.org/g", contenido="## GUÍA\n\n...\n\nRecomienda terapia.")], ["apa.org"])
    assert guias[0]["cita"] == "GUÍA Recomienda terapia."


def test_hace_cuatro_busquedas_cada_una_restringida_a_su_dominio():
    post = PostFalso(
        respuesta_con(cita("https://www.apa.org/eval", "Evaluación")),
        respuesta_con(cita("https://www.apa.org/trat", "Tratamiento")),
        respuesta_con(cita("https://www.imss.gob.mx/guiasclinicas/161GER.pdf", "GPC IMSS")),
        respuesta_con(cita("https://www.who.int/publications/mhgap", "mhGAP")),
    )
    guias = buscar_guias_apa(CANDIDATOS, "clave", post=post)
    dominios = [c["json"]["plugins"][0]["include_domains"] for c in post.llamadas]
    assert dominios == [["apa.org"], ["apa.org"], ["imss.gob.mx"], ["who.int"]]
    textos = [str(c["json"]["messages"]).lower() for c in post.llamadas]
    assert "evaluación" in textos[0] and "incomplet" in textos[0]
    assert "intervención" in textos[1]
    assert "imss" in textos[2] and "mhgap" in textos[3]
    assert [g["tipo"] for g in guias] == ["evaluacion", "intervencion", "imss", "oms"]


def test_cada_busqueda_descarta_ligas_de_otros_dominios_aunque_el_servidor_las_devuelva():
    post = PostFalso(respuesta_con(cita("https://www.apa.org/g"), cita("https://www.who.int/x")))
    guias = buscar_guias_apa(CANDIDATOS, "clave", post=post)
    assert {(g["tipo"], g["url"]) for g in guias} == {("evaluacion", "https://www.apa.org/g"), ("oms", "https://www.who.int/x")}


def test_las_busquedas_de_apa_y_oms_prefieren_espanol_con_ingles_de_respaldo_y_ninguna_lleva_codigos():
    post = PostFalso(respuesta_con())
    buscar_guias_apa(CANDIDATOS, "clave", post=post)
    for llamada in post.llamadas:
        assert "6A70" not in str(llamada["json"]["messages"])
    for i in (0, 1, 3):
        mensaje = str(post.llamadas[i]["json"]["messages"])
        assert "español" in mensaje and "inglés" in mensaje


def test_una_liga_repetida_entre_busquedas_se_conserva_solo_una_vez():
    post = PostFalso(respuesta_con(cita("https://www.apa.org/g"), cita("https://www.imss.gob.mx/a"), cita("https://www.who.int/b")))
    guias = buscar_guias_apa(CANDIDATOS, "clave", post=post)
    assert [(g["tipo"], g["url"]) for g in guias] == [
        ("evaluacion", "https://www.apa.org/g"), ("imss", "https://www.imss.gob.mx/a"), ("oms", "https://www.who.int/b")]


def test_si_una_busqueda_falla_falla_todo_para_no_dar_guias_a_medias():
    post = PostFalso(respuesta_con(cita("https://www.apa.org/g")), RespuestaFalsa(402, texto="sin créditos"))
    with pytest.raises(FlujoDetenido, match="402"):
        buscar_guias_apa(CANDIDATOS, "clave", post=post)
