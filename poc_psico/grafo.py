"""Workflow guardrail -> extraer -> agente CIE-11 -> reporte, y ejecutar() con anonimización previa."""
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Awaitable, Callable

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from .errores import FlujoDetenido
from .esquemas import ReporteClinico, SintomasPaciente
from .guardrail import pasa_guardrail
from .ocr import es_imagen
from .pii import MapaPII, anonimizar
from .reporte import render_markdown, validar_hipotesis
from .traza import contar_errores, contar_rondas, ensamblar_candidatos, extraer_traza, resumen_traza, texto_final


class Estado(TypedDict, total=False):
    texto_anon: str
    prob_clinico: float
    continuar: bool
    sintomas: dict
    candidatos: list
    alternativas: list
    notas_agente: str
    traza_tools: list
    rondas_agente: int
    errores_tools: int
    reporte_md: str
    advertencias: list


@dataclass
class Componentes:
    ner: Callable[[str], list]
    guardrail: Callable[[str], float]
    extraer: Callable[[str], dict]
    agente: Callable[[dict], Awaitable[list]]
    redactar: Callable[[dict, list, list, str], ReporteClinico]
    umbral: float = 0.5
    fecha: Callable[[], date] = date.today
    ocr: Callable[[str], str] | None = None  # ruta de foto -> texto; solo si la entrada es una foto


@contextmanager
def _cronometro(metricas: dict, nombre: str):
    inicio = time.perf_counter()
    try:
        yield
    finally:
        metricas[nombre] = round(time.perf_counter() - inicio, 3)


def construir_workflow(c: Componentes, metricas: dict):
    def nodo_guardrail(estado: Estado) -> dict:
        with _cronometro(metricas, "guardrail"):
            prob = c.guardrail(estado["texto_anon"])
        return {"prob_clinico": prob, "continuar": pasa_guardrail(prob, c.umbral)}

    def nodo_extraer(estado: Estado) -> dict:
        with _cronometro(metricas, "extraer"):
            sintomas = c.extraer(estado["texto_anon"])
        if not SintomasPaciente.model_validate(sintomas).hay_sintomas():
            raise FlujoDetenido("No se identificaron síntomas en el texto")
        return {"sintomas": sintomas}

    async def nodo_agente(estado: Estado) -> dict:
        with _cronometro(metricas, "agente"):
            mensajes = await c.agente(estado["sintomas"])
        traza = extraer_traza(mensajes)
        candidatos, alternativas = ensamblar_candidatos(traza)
        errores = contar_errores(mensajes)
        if not candidatos:
            usadas = ", ".join(dict.fromkeys(p["herramienta"] for p in traza)) or "ninguna"
            detalle = f"; {errores} llamada(s) a tools terminaron en error" if errores else ""
            raise FlujoDetenido(
                f"Ninguna hipótesis llegó con código CIE-11{detalle}. El agente hizo {contar_rondas(mensajes)} ronda(s) "
                f"(tools: {usadas}; {resumen_traza(traza)}). Último mensaje: {texto_final(mensajes)[:300]}"
            )
        return {
            "candidatos": candidatos,
            "alternativas": alternativas,
            "notas_agente": texto_final(mensajes),
            "traza_tools": traza,
            "rondas_agente": contar_rondas(mensajes),
            "errores_tools": errores,
        }

    def nodo_reporte(estado: Estado) -> dict:
        with _cronometro(metricas, "reporte"):
            reporte = c.redactar(
                estado["sintomas"], estado["candidatos"], estado["alternativas"], estado["notas_agente"]
            )
        hipotesis, advertencias = validar_hipotesis(reporte, estado["candidatos"])
        if not hipotesis:
            raise FlujoDetenido("El reporte no contiene hipótesis con código obtenido de las tools")
        markdown = render_markdown(estado["sintomas"], hipotesis, reporte, estado["alternativas"], c.fecha())
        return {"reporte_md": markdown, "advertencias": advertencias}

    grafo = StateGraph(Estado)
    grafo.add_node("guardrail", nodo_guardrail)
    grafo.add_node("extraer", nodo_extraer)
    grafo.add_node("agente", nodo_agente)
    grafo.add_node("reporte", nodo_reporte)
    grafo.add_edge(START, "guardrail")
    grafo.add_conditional_edges(
        "guardrail", lambda e: "extraer" if e["continuar"] else END, {"extraer": "extraer", END: END}
    )
    grafo.add_edge("extraer", "agente")
    grafo.add_edge("agente", "reporte")
    grafo.add_edge("reporte", END)
    return grafo.compile()


async def ejecutar(entrada: str, c: Componentes) -> dict:
    """Si la entrada es una foto la lee con OCR; anonimiza (fuera del grafo, para que el original no quede en las trazas),
    corre el grafo y reinserta los nombres. `texto_ocr` devuelve el texto leído para que se revise."""
    entrada = str(entrada)
    resultado = {
        "estado_final": "error", "razon": "", "texto_anon": "", "prob_clinico": None, "sintomas": None,
        "candidatos": [], "alternativas": [], "traza_tools": [], "rondas_agente": 0, "reporte_md": "",
        "advertencias": [], "latencias": {}, "texto_ocr": None,
    }
    if not entrada or not entrada.strip():
        resultado["razon"] = "La entrada está vacía"
        return resultado

    mapa, metricas = MapaPII(), {}
    try:
        texto = entrada
        if es_imagen(entrada):
            if c.ocr is None:
                raise FlujoDetenido("La entrada es una foto, pero no hay un componente OCR configurado")
            with _cronometro(metricas, "ocr"):
                texto = resultado["texto_ocr"] = c.ocr(entrada.strip())
        with _cronometro(metricas, "anonimizar"):
            resultado["texto_anon"] = anonimizar(texto, c.ner, mapa)
        final = await construir_workflow(c, metricas).ainvoke({"texto_anon": resultado["texto_anon"]})
    except FlujoDetenido as e:
        resultado["razon"] = str(e)
        return resultado
    except Exception as e:
        resultado["razon"] = f"Falla inesperada ({type(e).__name__}): {e}"
        return resultado
    finally:
        resultado["latencias"] = dict(metricas)

    resultado["prob_clinico"] = final.get("prob_clinico")
    if not final.get("continuar"):
        resultado["estado_final"] = "fuera_de_alcance"
        resultado["razon"] = (
            f"Probabilidad de contexto clínico {final.get('prob_clinico')} por debajo del umbral {c.umbral}"
        )
        return resultado

    reporte_md, desconocidos = mapa.reinsertar(final["reporte_md"])
    resultado.update(
        estado_final="ok",
        sintomas=final["sintomas"],
        candidatos=final["candidatos"],
        alternativas=final["alternativas"],
        traza_tools=final["traza_tools"],
        rondas_agente=final["rondas_agente"],
        reporte_md=reporte_md,
        advertencias=final.get("advertencias", []) + [f"Placeholder sin valor en el mapa: {p}" for p in desconocidos],
    )
    return resultado
