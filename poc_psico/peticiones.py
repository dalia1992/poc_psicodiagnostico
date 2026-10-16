"""POST a OpenRouter con los errores del flujo; lo comparten el guardrail, el decisor JEV y la búsqueda de guías."""
import requests

from .errores import FlujoDetenido


def post_openrouter(
    post, url: str, payload: dict, api_key: str, timeout, *, sin_conexion: str, respondio: str, error=FlujoDetenido
):
    """POST con JSON. Levanta `error` si no hay conexión o si el estado no es 200 (con `status_code`, que lee es_503).

    `sin_conexion` es el inicio del mensaje de red; `respondio` es el del estado y lleva el marcador {codigo}."""
    try:
        r = post(url, json=payload, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
    except requests.RequestException as e:
        raise error(f"{sin_conexion}: {e}") from e
    if r.status_code != 200:
        fallo = error(f"{respondio.format(codigo=r.status_code)}: {r.text[:200]}")
        fallo.status_code = r.status_code
        raise fallo
    return r
