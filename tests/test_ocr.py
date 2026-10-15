import base64
import io

import pytest
import requests
from PIL import Image

from poc_psico.errores import FlujoDetenido
from poc_psico.ocr import MODELO_OCR, OcrError, es_imagen, leer_imagen, leer_imagen_mistral


class Respuesta:
    def __init__(self, status=200, cuerpo=None, texto=""):
        self.status_code, self._cuerpo, self.text = status, cuerpo, texto

    def json(self):
        return self._cuerpo


def ok(texto):
    return Respuesta(200, {"message": {"content": texto}})


@pytest.fixture
def foto(tmp_path):
    ruta = tmp_path / "vineta.jpg"
    Image.new("RGB", (3000, 2000), "white").save(ruta)
    return ruta


def test_es_imagen_reconoce_rutas_de_foto_y_no_texto_clinico():
    assert es_imagen("/tmp/vineta.JPG")
    assert es_imagen("vineta.png")
    assert not es_imagen("Lucía, 28 años. Refiere ansiedad.")
    assert not es_imagen("Refiere ansiedad.\nFoto: nota.jpg")
    assert not es_imagen("")


def test_leer_imagen_devuelve_el_texto_sin_espacios_sobrantes(foto):
    assert leer_imagen(foto, post=lambda *a, **k: ok("  Lucía 28 años\n")) == "Lucía 28 años"


def test_leer_imagen_envia_una_imagen_reducida_al_modelo_local_y_lo_descarga_de_memoria(foto):
    visto = {}

    def post(url, json, timeout):
        visto.update(url=url, json=json)
        return ok("texto")

    leer_imagen(foto, post=post)
    cuerpo = visto["json"]
    assert visto["url"].startswith("http://localhost:11434")
    assert cuerpo["model"] == MODELO_OCR and cuerpo["stream"] is False
    assert cuerpo["keep_alive"] == 0
    assert cuerpo["options"]["temperature"] == 0
    (imagen,) = cuerpo["messages"][0]["images"]
    enviada = Image.open(io.BytesIO(base64.b64decode(imagen)))
    assert max(enviada.size) == 1280


def test_leer_imagen_acepta_png_con_transparencia(tmp_path):
    ruta = tmp_path / "nota.png"
    Image.new("RGBA", (200, 100), (255, 255, 255, 0)).save(ruta)
    assert leer_imagen(ruta, post=lambda *a, **k: ok("hola")) == "hola"


def test_archivo_inexistente_detiene_el_flujo(tmp_path):
    with pytest.raises(OcrError, match="no existe"):
        leer_imagen(tmp_path / "nada.jpg", post=lambda *a, **k: ok("x"))


def test_archivo_que_no_es_imagen_detiene_el_flujo(tmp_path):
    ruta = tmp_path / "roto.jpg"
    ruta.write_text("esto no es una imagen")
    with pytest.raises(OcrError, match="imagen"):
        leer_imagen(ruta, post=lambda *a, **k: ok("x"))


def test_ollama_apagado_dice_como_arrancarlo(foto):
    def post(*a, **k):
        raise requests.ConnectionError("rechazada")

    with pytest.raises(OcrError, match="ollama serve"):
        leer_imagen(foto, post=post)


def test_modelo_no_instalado_dice_el_comando_para_descargarlo(foto):
    with pytest.raises(OcrError, match=f"ollama pull {MODELO_OCR}"):
        leer_imagen(foto, post=lambda *a, **k: Respuesta(404, texto="model not found"))


def test_otro_error_http_se_reporta_con_su_codigo(foto):
    with pytest.raises(OcrError, match="500"):
        leer_imagen(foto, post=lambda *a, **k: Respuesta(500, texto="boom"))


def test_texto_vacio_detiene_el_flujo_y_no_inventa(foto):
    with pytest.raises(OcrError, match="No se pudo leer texto"):
        leer_imagen(foto, post=lambda *a, **k: ok("   "))


def test_respuesta_sin_el_formato_esperado_detiene_el_flujo(foto):
    with pytest.raises(OcrError, match="formato"):
        leer_imagen(foto, post=lambda *a, **k: Respuesta(200, {"otra": 1}))


def test_ocr_error_es_un_flujo_detenido():
    assert issubclass(OcrError, FlujoDetenido)


# --- Mistral OCR vía OpenRouter (plugin file-parser; solo parsea PDF, así que la foto se convierte) ---


def anotada(texto):
    contenido = [{"type": "text", "text": f'<file name="vineta.pdf">\n{texto}\n</file>'}]
    anotacion = {"type": "file", "file": {"name": "vineta.pdf", "content": contenido}}
    return Respuesta(200, {"choices": [{"message": {"content": "OK", "annotations": [anotacion]}}]})


def test_mistral_envia_la_foto_como_pdf_con_el_plugin_y_devuelve_el_texto_sin_la_etiqueta_file(foto):
    visto = {}

    def post(url, json, headers, timeout):
        visto.update(url=url, json=json, headers=headers)
        return anotada("Lucía 28 años")

    assert leer_imagen_mistral(foto, "clave-falsa", post=post) == "Lucía 28 años"
    assert visto["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert visto["headers"]["Authorization"] == "Bearer clave-falsa"
    assert visto["json"]["plugins"] == [{"id": "file-parser", "pdf": {"engine": "mistral-ocr"}}]
    assert visto["json"]["max_tokens"] <= 16
    parte = visto["json"]["messages"][0]["content"][1]["file"]
    assert parte["file_data"].startswith("data:application/pdf;base64,")
    assert base64.b64decode(parte["file_data"].split(",", 1)[1]).startswith(b"%PDF")


def test_mistral_sin_clave_detiene_el_flujo_sin_llamar(foto):
    def post(*a, **k):
        raise AssertionError("no debe llamar")

    with pytest.raises(OcrError, match="OPENROUTER_API_KEY"):
        leer_imagen_mistral(foto, "", post=post)


def test_mistral_reintenta_cuando_el_motor_de_parseo_esta_saturado(foto):
    respuestas = [Respuesta(400, texto="Failed to parse the file: The document parsing engine is currently rate limited."),
                  anotada("hola")]
    esperas = []
    assert leer_imagen_mistral(foto, "k", post=lambda *a, **k: respuestas.pop(0), esperar=esperas.append) == "hola"
    assert esperas == [1]


def test_mistral_si_la_saturacion_persiste_se_detiene_con_el_motivo(foto):
    saturado = Respuesta(400, texto="engine is currently rate limited")
    esperas = []
    with pytest.raises(OcrError, match="rate limited"):
        leer_imagen_mistral(foto, "k", post=lambda *a, **k: saturado, esperar=esperas.append)
    assert esperas == [1, 2, 4]


@pytest.mark.parametrize("status", [401, 402, 500])
def test_mistral_otros_errores_http_no_se_reintentan_y_dicen_el_codigo(foto, status):
    llamadas = []

    def post(*a, **k):
        llamadas.append(1)
        return Respuesta(status, texto="error")

    with pytest.raises(OcrError, match=str(status)):
        leer_imagen_mistral(foto, "k", post=post, esperar=lambda s: None)
    assert len(llamadas) == 1


def test_mistral_sin_texto_en_las_anotaciones_detiene_el_flujo_y_no_inventa(foto):
    sin_anotaciones = Respuesta(200, {"choices": [{"message": {"content": "OK"}}]})
    with pytest.raises(OcrError, match="No se pudo leer texto"):
        leer_imagen_mistral(foto, "k", post=lambda *a, **k: sin_anotaciones)


def test_mistral_error_de_red_detiene_el_flujo(foto):
    def post(*a, **k):
        raise requests.ConnectionError("sin red")

    with pytest.raises(OcrError, match="OpenRouter"):
        leer_imagen_mistral(foto, "k", post=post)


def test_mistral_con_archivo_que_no_es_imagen_detiene_el_flujo(tmp_path):
    ruta = tmp_path / "roto.jpg"
    ruta.write_text("no es imagen")
    with pytest.raises(OcrError, match="imagen"):
        leer_imagen_mistral(ruta, "k", post=lambda *a, **k: anotada("x"))
