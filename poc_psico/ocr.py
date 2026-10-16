"""OCR de notas manuscritas con Mistral OCR vía OpenRouter (la foto sale a esos servicios sin anonimizar)."""
import base64
import io
import pathlib
import re
import time

import requests
from PIL import Image, UnidentifiedImageError

from .errores import FlujoDetenido
from .peticiones import post_openrouter
from .reintentos import con_reintentos_503

EXTENSIONES = {".jpg", ".jpeg", ".png"}
URL_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
# El plugin file-parser solo parsea PDF (un JPEG directo responde 200 sin texto). El modelo de chat solo acompaña
# la petición: su respuesta se ignora y max_tokens bajo evita esperar su generación (spike 2026-10-14).
MODELO_ACOMPANANTE = "openai/gpt-4o-mini"
LADO_MAXIMO_MISTRAL = 2000


class OcrError(FlujoDetenido):
    """No se pudo leer la imagen; el flujo no continúa con texto inventado o incompleto."""


def es_imagen(entrada) -> bool:
    """True si la entrada es la ruta de una foto y no una viñeta en texto."""
    texto = str(entrada).strip()
    return bool(texto) and "\n" not in texto and len(texto) < 500 and pathlib.Path(texto).suffix.lower() in EXTENSIONES


def _cargar(ruta: pathlib.Path, lado: int) -> Image.Image:
    if not ruta.is_file():
        raise OcrError(f"El archivo de la foto no existe: {ruta}")
    try:
        with Image.open(ruta) as original:
            imagen = original.convert("RGB")  # descarta la transparencia de los PNG
    except (UnidentifiedImageError, OSError) as e:
        raise OcrError(f"No se pudo abrir {ruta.name} como imagen: {e}") from e
    imagen.thumbnail((lado, lado))
    return imagen


def _codificar(imagen: Image.Image, formato: str, **opciones) -> str:
    salida = io.BytesIO()
    imagen.save(salida, formato, **opciones)
    return base64.b64encode(salida.getvalue()).decode()


def _saturado(error: Exception) -> bool:
    """503, 429 o el 400 "rate limited" que el motor de parseo responde de forma intermitente (reintentos 1, 2 y 4 s)."""
    codigo = getattr(error, "status_code", None)
    return codigo in (429, 503) or (codigo == 400 and "rate limit" in str(error).lower())


def _texto_de_anotaciones(respuesta: dict) -> str:
    anotaciones = respuesta["choices"][0]["message"].get("annotations") or []
    partes = [
        parte.get("text", "")
        for a in anotaciones if a.get("type") == "file"
        for parte in a["file"].get("content", []) if parte.get("type") == "text"
    ]
    return re.sub(r"</?file\b[^>]*>", "", "\n".join(partes)).strip()


def leer_imagen_mistral(
    ruta, api_key, post=requests.post, url=URL_OPENROUTER, modelo=MODELO_ACOMPANANTE, timeout=120, esperar=time.sleep
) -> str:
    """Transcribe la foto con Mistral OCR vía OpenRouter: la convierte a PDF de una página y lee las anotaciones."""
    if not api_key:
        raise OcrError("Falta OPENROUTER_API_KEY para usar Mistral OCR")
    pdf = _codificar(_cargar(pathlib.Path(ruta), LADO_MAXIMO_MISTRAL), "PDF", resolution=150)
    payload = {
        "model": modelo,
        "max_tokens": 16,
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Responde solo OK."},
            {"type": "file", "file": {"filename": "vineta.pdf", "file_data": "data:application/pdf;base64," + pdf}},
        ]}],
        "plugins": [{"id": "file-parser", "pdf": {"engine": "mistral-ocr"}}],
    }

    def llamar():
        return post_openrouter(
            post, url, payload, api_key, timeout, error=OcrError, sin_conexion="No se pudo conectar con OpenRouter",
            respondio="OpenRouter respondió {codigo}",
        )

    r = con_reintentos_503(llamar, esperar=esperar, reintentable=_saturado)
    try:
        texto = _texto_de_anotaciones(r.json())
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise OcrError("OpenRouter devolvió un formato inesperado de respuesta") from e
    if not texto:
        raise OcrError("No se pudo leer texto en la imagen: Mistral OCR no devolvió texto")
    return texto
