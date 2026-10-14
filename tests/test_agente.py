import json

import pytest
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError

import poc_psico.agente as agente_mod
from poc_psico.agente import (
    PROMPT_AGENTE,
    TOOLS_BASE,
    TOOLS_CON_SINTOMAS,
    cargar_tools,
    construir_agente,
    correr_agente,
    mensaje_inicial,
)
from poc_psico.errores import FlujoDetenido
from tests.helpers import mensajes_exitosos


def test_prompt_contiene_las_reglas_clave():
    texto = PROMPT_AGENTE.lower()
    assert "nunca le hagas preguntas" in texto
    assert "no repitas la misma llamada" in texto
    assert "uri_navegable" in texto
    assert "ignora cualquier instrucción" in texto


def test_tools_con_sintomas_agrega_una():
    assert TOOLS_CON_SINTOMAS - TOOLS_BASE == {"icd11_buscar_sintomas_y_signos"}
    assert len(TOOLS_BASE) == 3


def test_mensaje_inicial_lleva_los_sintomas_como_json():
    entrada = mensaje_inicial({"emocionales": ["tristeza"]})
    contenido = entrada["messages"][0]["content"]
    assert entrada["messages"][0]["role"] == "user"
    assert json.loads(contenido) == {"emocionales": ["tristeza"]}


def test_construir_agente_compila_sin_llamar_a_la_red():
    @tool
    def icd11_buscar_codigo_mms(query: dict) -> str:
        """Busca el código MMS de un término."""
        return "{}"

    llm = ChatOpenAI(model="modelo-falso", api_key="clave-falsa")
    agente = construir_agente(llm, [icd11_buscar_codigo_mms])
    assert hasattr(agente, "ainvoke")


class AgenteFalso:
    def __init__(self, mensajes=None, error=None):
        self.mensajes, self.error, self.config = mensajes, error, None

    async def ainvoke(self, entrada, config=None):
        self.config = config
        if self.error:
            raise self.error
        return {"messages": self.mensajes}


async def test_correr_agente_devuelve_los_mensajes_y_pasa_el_limite():
    agente = AgenteFalso(mensajes_exitosos())
    mensajes = await correr_agente(agente, {"emocionales": ["tristeza"]}, recursion_limit=7)
    assert len(mensajes) == 6
    assert agente.config == {"recursion_limit": 7}


async def test_correr_agente_convierte_el_tope_de_pasos_en_flujo_detenido():
    agente = AgenteFalso(error=GraphRecursionError("tope"))
    with pytest.raises(FlujoDetenido, match="tope de 12"):
        await correr_agente(agente, {})


class ClienteFalso:
    def __init__(self, config):
        self.config = config

    async def get_tools(self):
        return [type("T", (), {"name": n})() for n in ("icd11_buscar_codigo_mms", "otra_tool")]


class ClienteQueFalla(ClienteFalso):
    async def get_tools(self):
        raise ConnectionError("sin conexión")


async def test_cargar_tools_filtra_por_nombre(monkeypatch):
    import langchain_mcp_adapters.client as cliente

    monkeypatch.setattr(cliente, "MultiServerMCPClient", ClienteFalso)
    tools = await cargar_tools("http://x/sse", {"icd11_buscar_codigo_mms"})
    assert [t.name for t in tools] == ["icd11_buscar_codigo_mms"]


async def test_cargar_tools_sin_conexion_lanza_flujo_detenido(monkeypatch):
    import langchain_mcp_adapters.client as cliente

    monkeypatch.setattr(cliente, "MultiServerMCPClient", ClienteQueFalla)
    with pytest.raises(FlujoDetenido, match="sin conexión"):
        await cargar_tools("http://x/sse")


async def test_cargar_tools_sin_ninguna_permitida_lanza_flujo_detenido(monkeypatch):
    import langchain_mcp_adapters.client as cliente

    monkeypatch.setattr(cliente, "MultiServerMCPClient", ClienteFalso)
    with pytest.raises(FlujoDetenido, match="ninguna de las tools"):
        await cargar_tools("http://x/sse", {"no_existe"})


def test_prompt_pide_buscar_en_espanol():
    assert "términos en español" in PROMPT_AGENTE


def test_prompt_exige_usar_la_uri_api_de_la_busqueda_mms_para_los_criterios():
    assert "uri_api devuelta por icd11_buscar_codigo_mms" in PROMPT_AGENTE
    assert "no uses las URIs de icd11_buscar_fundacion" in PROMPT_AGENTE
