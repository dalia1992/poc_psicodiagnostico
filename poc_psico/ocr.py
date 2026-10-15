"""OCR de notas manuscritas: Mistral OCR vía OpenRouter (rápido; la foto sale a esos servicios) o un VLM local con Ollama (la foto no sale del equipo)."""
import base64
import io
import pathlib
import re
import time

import requests
from PIL import Image, UnidentifiedImageError

from .errores import FlujoDetenido

URL_OLLAMA = "http://localhost:11434/api/chat"
MODELO_OCR = "qwen2.5vl:3b"
LADO_MAXIMO = 1280  # píxeles; con más resolución el modelo tarda y ocupa más RAM sin leer mejor (spike 2026-10-13)
EXTENSIONES = {".jpg", ".jpeg", ".png"}
URL_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
# El plugin file-parser solo parsea PDF (un JPEG directo responde 200 sin texto). El modelo de chat solo acompaña
# la petición: su respuesta se ignora y max_tokens bajo evita esperar su generación (spike 2026-10-14).
MODELO_ACOMPANANTE = "openai/gpt-4o-mini"
LADO_MAXIMO_MISTRAL = 2000
ESPERAS_SATURACION = (1, 2, 4)  # segundos; el motor de parseo responde 400 "rate limited" de forma intermitente
INSTRUCCION = (
    "Transcribe literalmente el texto manuscrito en español de esta imagen. "
    "Responde solo con la transcripción, sin comentarios."
)


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


def _preparar(ruta: pathlib.Path) -> str:
    return _codificar(_cargar(ruta, LADO_MAXIMO), "JPEG", quality=90)


def leer_imagen(ruta, modelo=MODELO_OCR, post=requests.post, url=URL_OLLAMA, timeout=300) -> str:
    """Transcribe la foto con el modelo local. `keep_alive: 0` lo descarga de memoria al terminar (8 GB de RAM)."""
    payload = {
        "model": modelo,
        "stream": False,
        "keep_alive": 0,
        "options": {"temperature": 0},
        "messages": [{"role": "user", "content": INSTRUCCION, "images": [_preparar(pathlib.Path(ruta))]}],
    }
    try:
        r = post(url, json=payload, timeout=timeout)
    except requests.RequestException as e:
        raise OcrError(f"No se pudo conectar con Ollama en {url}: arranca el servicio con `ollama serve` ({e})") from e
    if r.status_code == 404:
        raise OcrError(f"Ollama no tiene el modelo {modelo}: descárgalo con `ollama pull {modelo}`")
    if r.status_code != 200:
        raise OcrError(f"Ollama respondió {r.status_code}: {r.text[:200]}")
    try:
        texto = r.json()["message"]["content"].strip()
    except (KeyError, TypeError, ValueError) as e:
        raise OcrError("Ollama devolvió un formato inesperado de respuesta") from e
    if not texto:
        raise OcrError("No se pudo leer texto en la imagen: la transcripción salió vacía")
    return texto


def _saturado(r) -> bool:
    return r.status_code in (429, 503) or (r.status_code == 400 and "rate limit" in r.text.lower())


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
    cabeceras = {"Authorization": f"Bearer {api_key}"}
    for intento in range(len(ESPERAS_SATURACION) + 1):
        try:
            r = post(url, json=payload, headers=cabeceras, timeout=timeout)
        except requests.RequestException as e:
            raise OcrError(f"No se pudo conectar con OpenRouter: {e}") from e
        if r.status_code == 200:
            break
        if not _saturado(r) or intento == len(ESPERAS_SATURACION):
            raise OcrError(f"OpenRouter respondió {r.status_code}: {r.text[:200]}")
        esperar(ESPERAS_SATURACION[intento])
    try:
        texto = _texto_de_anotaciones(r.json())
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise OcrError("OpenRouter devolvió un formato inesperado de respuesta") from e
    if not texto:
        raise OcrError("No se pudo leer texto en la imagen: Mistral OCR no devolvió texto")
    return texto
