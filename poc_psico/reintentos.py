"""Reintentos ante un 503 (servicio sobrecargado): 3 reintentos con espera 2**0, 2**1 y 2**2 segundos."""
import asyncio
import logging
import re
import time

logger = logging.getLogger(__name__)

REINTENTOS = 3


def es_503(error: Exception) -> bool:
    """True si el error es un 503: por su código, por el de su respuesta o por el texto del mensaje."""
    for objeto in (error, getattr(error, "response", None)):
        if getattr(objeto, "status_code", None) == 503:
            return True
    return re.search(r"\b503\b", str(error)) is not None


def _espera(intento: int) -> int:
    return 2**intento  # 1, 2, 4


def con_reintentos_503(funcion, *args, esperar=time.sleep, **kwargs):
    for intento in range(REINTENTOS + 1):
        try:
            return funcion(*args, **kwargs)
        except Exception as error:
            if not es_503(error) or intento == REINTENTOS:
                raise
            segundos = _espera(intento)
            logger.warning("503 (servicio sobrecargado): reintento %d de %d en %d s", intento + 1, REINTENTOS, segundos)
            esperar(segundos)


async def acon_reintentos_503(funcion, *args, aesperar=asyncio.sleep, **kwargs):
    for intento in range(REINTENTOS + 1):
        try:
            return await funcion(*args, **kwargs)
        except Exception as error:
            if not es_503(error) or intento == REINTENTOS:
                raise
            segundos = _espera(intento)
            logger.warning("503 (servicio sobrecargado): reintento %d de %d en %d s", intento + 1, REINTENTOS, segundos)
            await aesperar(segundos)


REINTENTOS_FORMATO = 2


def es_error_de_formato(error: Exception) -> bool:
    """True si el LLM devolvió una salida estructurada inválida (ValidationError / OutputParserException)."""
    from langchain_core.exceptions import OutputParserException
    from pydantic import ValidationError

    return isinstance(error, (ValidationError, OutputParserException))


def con_reintentos_formato(funcion, *args, corregir=None, **kwargs):
    """Reintenta sin espera si el modelo rompió el contrato (p. ej. una lista entregada como texto). 503 se maneja aparte.

    Repetir la misma petición no sirve: a temperatura 0 y con la caché de LLM activa (celda 1.1) devuelve la misma respuesta
    mala sin llamar al modelo. `corregir(args, error) -> args` permite cambiar la petición en cada reintento."""
    for intento in range(REINTENTOS_FORMATO + 1):
        try:
            return funcion(*args, **kwargs)
        except Exception as error:
            if not es_error_de_formato(error) or intento == REINTENTOS_FORMATO:
                raise
            logger.warning("Salida con formato inválido: reintento %d de %d", intento + 1, REINTENTOS_FORMATO)
            if corregir:
                args = corregir(args, error)
