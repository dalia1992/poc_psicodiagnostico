"""Búsqueda de guías clínicas (APA, IMSS y OMS) con el plugin web de OpenRouter (filtro de dominio del lado del servidor).

Solo viajan a la búsqueda los títulos de las entidades CIE-11 candidatas: nunca datos del paciente. El texto que
devuelve la web no se pasa a ningún LLM; solo se conservan título, liga y una cita corta que se imprimen en el reporte.
"""
import re
import time
from urllib.parse import urlparse

import requests

from .errores import FlujoDetenido
from .ocr import URL_OPENROUTER
from .reintentos import con_reintentos_503

MAX_RESULTADOS = 3
MAX_CANDIDATOS = 3
MAX_CITA = 300
MAX_EXTRACTO = 2500  # lo que ve el redactor de cada guía; la cita corta del reporte es MAX_CITA
PIE_ES_EN = (
    " Prefiere páginas en español; si no hay, usa las de inglés (traduce los nombres de los trastornos al inglés para "
    "buscarlas). Responde en dos frases y cita siempre las fuentes."
)
PIE_ES = " Responde en dos frases y cita siempre las fuentes."
# tipo -> (dominio al que se restringe la búsqueda, enunciado, pie). El orden es el del reporte.
FUENTES = {
    "evaluacion": (
        "apa.org",
        "Busca guías de la American Psychological Association sobre la evaluación y el diagnóstico diferencial de: "
        "{temas}. Prioriza lo que orienta qué evaluar, qué información recabar y cómo proceder cuando la información "
        "clínica es incompleta o ambigua.",
        PIE_ES_EN,
    ),
    "intervencion": (
        "apa.org",
        "Busca guías de práctica clínica de la American Psychological Association con recomendaciones de "
        "intervención y tratamiento basadas en evidencia para: {temas}.",
        PIE_ES_EN,
    ),
    "imss": (
        "imss.gob.mx",
        "Busca las guías de práctica clínica mexicanas del IMSS sobre diagnóstico y tratamiento de: {temas}. "
        "Incluye la guía de evidencias y recomendaciones y la de referencia rápida si existen.",
        PIE_ES,
    ),
    "oms": (
        "who.int",
        "Busca guías y recomendaciones de la Organización Mundial de la Salud (por ejemplo mhGAP) sobre la "
        "evaluación y el manejo de: {temas}.",
        PIE_ES_EN,
    ),
}
MODELO_BUSQUEDA = "anthropic/claude-haiku-5.5"
MOTOR = "exa"  # medido 2026-10-15: ~US$0.008 por búsqueda y 3 resultados; el nativo de Anthropic cuesta ~US$0.023


def consulta_desde_candidatos(candidatos: list, maximo: int = MAX_CANDIDATOS) -> str:
    titulos = [c["titulo"] for c in candidatos[:maximo]]
    return "; ".join(titulos)


def _dominio_permitido(url: str, dominios: list) -> bool:
    """True si el host de la liga es uno de los dominios o un subdominio suyo (apa.org.evil.com no pasa)."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return any(host == d or host.endswith("." + d) for d in dominios)


def solo_dominios(anotaciones: list, dominios: list) -> list:
    """Convierte las anotaciones url_citation en guías, descartando duplicados y cualquier liga fuera de los dominios."""
    guias, vistas = [], set()
    for a in anotaciones:
        if a.get("type") != "url_citation":
            continue
        d = a.get("url_citation") or {}
        url = d.get("url", "")
        if not _dominio_permitido(url, dominios) or url in vistas:
            continue
        vistas.add(url)
        extracto = " ".join(re.sub(r"(?m)^#+\s*|\s*\.\.\.\s*", " ", d.get("content") or "").split())[:MAX_EXTRACTO]
        guias.append(
            {"titulo": " ".join((d.get("title") or url).split()), "url": url, "cita": extracto[:MAX_CITA], "extracto": extracto}
        )
    return guias


def buscar_guias_apa(
    candidatos: list, api_key: str, post=requests.post, url=URL_OPENROUTER, modelo=MODELO_BUSQUEDA, timeout=120,
    esperar=time.sleep,
) -> list:
    """Devuelve [{titulo, url, cita, tipo}], con tipo en FUENTES (evaluacion, intervencion, imss, oms); vacía si no hay candidatos."""
    if not api_key:
        raise FlujoDetenido("Falta OPENROUTER_API_KEY para buscar guías clínicas")
    if not candidatos:
        return []
    cabeceras = {"Authorization": f"Bearer {api_key}"}
    temas = consulta_desde_candidatos(candidatos)
    guias, vistas = [], set()
    for tipo, (dominio, enunciado, pie) in FUENTES.items():  # secuencial: si una falla, falla todo y no se entregan guías a medias
        plugin = {"id": "web", "engine": MOTOR, "include_domains": [dominio], "max_results": MAX_RESULTADOS}
        for g in _buscar(enunciado.format(temas=temas) + pie, [dominio], plugin, cabeceras, post, url, modelo, timeout, esperar):
            if g["url"] not in vistas:
                vistas.add(g["url"])
                guias.append({**g, "tipo": tipo, "id": f"G{len(guias) + 1}"})
    return guias


def _buscar(pregunta, dominios, plugin, cabeceras, post, url, modelo, timeout, esperar) -> list:
    payload = {
        "model": modelo,
        "max_tokens": 2000,  # el razonamiento cuenta: con 600 se corta (finish_reason=length) y a veces no cita
        "temperature": 0,
        "messages": [{"role": "user", "content": pregunta}],
        "plugins": [plugin],
    }

    def llamar():
        try:
            r = post(url, json=payload, headers=cabeceras, timeout=timeout)
        except requests.RequestException as e:
            raise FlujoDetenido(f"No se pudo conectar con OpenRouter para buscar guías: {e}") from e
        if r.status_code != 200:
            error = FlujoDetenido(f"OpenRouter respondió {r.status_code} al buscar guías: {r.text[:200]}")
            error.status_code = r.status_code  # lo lee es_503 para reintentar solo ese caso
            raise error
        return r

    r = con_reintentos_503(llamar, esperar=esperar)
    try:
        anotaciones = r.json()["choices"][0]["message"].get("annotations") or []
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as e:
        raise FlujoDetenido("OpenRouter devolvió un formato inesperado al buscar guías") from e
    return solo_dominios(anotaciones, dominios)
