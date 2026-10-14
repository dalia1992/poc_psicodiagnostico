"""Captura respuestas reales del MCP CIE-11. Uso: python scripts/spike_mcp.py"""
import asyncio
import json
import os
import pathlib

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")
URL = os.getenv(
    "AGENT_MCP_URL",
    "https://cie11-mcp-server.orangerock-5a17ced7.eastus.azurecontainerapps.io/sse",
)
FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def guardar(nombre, herramienta, args, contenido):
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / f"{nombre}.json").write_text(
        json.dumps({"tool": herramienta, "args": args, "content": contenido}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"--- {nombre}: {type(contenido).__name__}")
    print(json.dumps(contenido, ensure_ascii=False, default=str)[:700])


def primer_json(contenido):
    texto = contenido
    if isinstance(contenido, list):
        texto = contenido[0]["text"]
    return json.loads(texto) if isinstance(texto, str) else texto


async def main():
    cliente = MultiServerMCPClient({"clinica_mcp": {"transport": "sse", "url": URL}})
    tools = {t.name: t for t in await cliente.get_tools()}
    print("Tools:", sorted(tools))

    args = {"query": {"termino": "trastorno depresivo"}}
    mms = await tools["icd11_buscar_codigo_mms"].ainvoke(args)
    guardar("mms_depresion", "icd11_buscar_codigo_mms", args, mms)

    primero = primer_json(mms)["resultados_mms"][0]
    args = {"query": {"uri_entidad": primero["uri_api"]}}
    guardar("criterios_depresion", "icd11_obtener_criterios_clinicos", args,
            await tools["icd11_obtener_criterios_clinicos"].ainvoke(args))

    args = {"query": {"termino": "depresión"}}
    guardar("fundacion_depresion", "icd11_buscar_fundacion", args,
            await tools["icd11_buscar_fundacion"].ainvoke(args))

    args = {"query": {"termino": "tristeza"}}
    guardar("sintomas_tristeza", "icd11_buscar_sintomas_y_signos", args,
            await tools["icd11_buscar_sintomas_y_signos"].ainvoke(args))

    args = {"query": {"termino": "zzzxqwv"}}
    guardar("mms_vacio", "icd11_buscar_codigo_mms", args,
            await tools["icd11_buscar_codigo_mms"].ainvoke(args))


asyncio.run(main())
