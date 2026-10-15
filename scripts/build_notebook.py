"""Genera PoC_psicodiagnostico.ipynb. Uso: python scripts/build_notebook.py"""
import pathlib
import textwrap

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def md(texto):
    return new_markdown_cell(textwrap.dedent(texto).strip())


def code(texto):
    return new_code_cell(textwrap.dedent(texto).strip())


def construir():
    celdas = [
        md("""
            # PoC · Asistente de apoyo al psicodiagnóstico (LC-B + LC-C)
            **Kit PoC · Colab + LangChain + OpenRouter** · Etapa 1: entrada de texto

            Flujo: el texto se **anonimiza** (NER local; nombres, lugares y organizaciones no salen de la VM) →
            **guardrail** de contexto clínico (`respan/span-01-lite:free`) → **extraer** síntomas →
            **agente CIE-11** (MCP en Azure) → **reporte** Markdown con código y liga OMS.

            1. Abre este cuaderno en Colab y monta Google Drive cuando lo pida (la carpeta `poc_psicodiagnostico` debe estar en tu Drive).
            2. Guarda `OPENROUTER_API_KEY` en los Secretos de Colab (acceso del notebook activado) o, en local, en el archivo `.env`.
            3. Ejecuta todo. Una corrida completa usa cerca de 8 llamadas al modelo; la cuenta gratuita permite 50 por día.

            > Trabaja solo con datos sintéticos o anonimizados: el endpoint gratuito del modelo registra el uso.
            """),
        md("## 0 · Instalación, Drive y clave (no editar)"),
        code("""
            # 0.1 · Dependencias (no editar). En Colab se instalan aquí; en local vienen de uv sync (ver README)
            import subprocess
            import sys

            if "google.colab" in sys.modules:
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", "-qU",
                    "langchain>=1.4,<2", "langchain-openai>=1.6,<2", "langgraph>=1.2,<2",
                    "langchain-mcp-adapters", "transformers", "torch", "pydantic", "requests", "pandas",
                ])
            else:
                print("Entorno local: las dependencias vienen de uv sync (ver README).")
            """),
        code("""
            # 0.2 · Drive y ruta del paquete poc_psico (no editar)
            import os
            import sys

            RUTA_PROYECTO = "/content/drive/MyDrive/LLM solutions architect/Módulo 5/poc_psicodiagnostico"
            try:
                from google.colab import drive
                drive.mount("/content/drive")
            except Exception:
                RUTA_PROYECTO = os.getcwd()
            sys.path.insert(0, RUTA_PROYECTO)
            from poc_psico import grafo  # falla aquí si la ruta no es correcta
            print("Paquete cargado desde", RUTA_PROYECTO)
            """),
        code("""
            # 0.3 · Clave de OpenRouter (no editar). Colab: Secretos. Local: archivo .env (ver README)
            import getpass
            from poc_psico.entorno import cargar_env

            if cargar_env(os.path.join(RUTA_PROYECTO, ".env")):
                print("Variables cargadas desde .env")

            def leer_secreto(nombre: str, obligatorio: bool = True):
                try:
                    from google.colab import userdata
                    valor = userdata.get(nombre)
                    if valor:
                        return valor
                except Exception:
                    pass
                if os.environ.get(nombre):
                    return os.environ[nombre]
                if obligatorio:
                    return getpass.getpass(f"Pega tu {nombre}: ")
                return None

            os.environ["OPENROUTER_API_KEY"] = leer_secreto("OPENROUTER_API_KEY")
            langsmith_key = leer_secreto("LANGSMITH_API_KEY", obligatorio=False)
            if langsmith_key:
                os.environ["LANGSMITH_API_KEY"] = langsmith_key
                os.environ["LANGSMITH_TRACING"] = "true"
                os.environ["LANGSMITH_PROJECT"] = "kit-poc"
            print("Clave cargada. LangSmith:", "activo" if langsmith_key else "desactivado")
            """),
        md("## 1 · Modelo y NER (no editar)"),
        code("""
            # 1.1 · Modelo único del curso: OpenRouter + NVIDIA Nemotron 3 Ultra (no editar)
            from langchain_openai import ChatOpenAI
            from langchain_core.globals import set_llm_cache
            from langchain_core.caches import InMemoryCache

            TEMPLATE_ID = "LC-B+C"
            # MODEL_ID = "nvidia/nemotron-3-ultra-550b-a55b:free"
            MODEL_ID = "anthropic/claude-haiku-5.5"
            set_llm_cache(InMemoryCache())

            llm = ChatOpenAI(
                model=MODEL_ID,
                api_key=os.environ["OPENROUTER_API_KEY"],
                base_url="https://openrouter.ai/api/v1",
                temperature=0,
                max_tokens=4096,
                timeout=120,
                max_retries=3,
                default_headers={"HTTP-Referer": "https://colab.research.google.com", "X-Title": "Kit PoC BSG"},
            )

            def texto(mensaje) -> str:
                return mensaje.text if hasattr(mensaje, "text") else str(mensaje.content)

            print("Prueba de conexión:", texto(llm.invoke("Responde solo con la palabra OK.")))
            """),
        code("""
            # 1.2 · Modelo NER en español (corre en la VM de Colab; no usa API externa)
            from transformers import pipeline

            ner_es = pipeline("ner", model="MMG/xlm-roberta-large-ner-spanish", aggregation_strategy="simple")
            print(ner_es("Mi nombre es Dalia Camacho y vivo en CDMX"))
            """),
        md("## 2 · Tu caso (EDITA AQUÍ)"),
        code("""
            # EDITA AQUÍ · 2.1 Guardrail, MCP y agente
            UMBRAL_GUARDRAIL = 0.5          # probabilidad mínima de "contexto de psicología clínica"
            AGENT_MCP_URL = os.getenv(
                "AGENT_MCP_URL",
                "https://cie11-mcp-server.orangerock-5a17ced7.eastus.azurecontainerapps.io/sse",
            )
            from poc_psico.agente import TOOLS_BASE, TOOLS_CON_SINTOMAS, PROMPT_AGENTE
            TOOLS_PERMITIDAS = TOOLS_BASE   # prueba también TOOLS_CON_SINTOMAS y compara las rondas
            SYSTEM_PROMPT_AGENTE = PROMPT_AGENTE
            MAX_RONDAS = 5                 # rondas de tools que puede dar el agente (el agente ve cuántas lleva)
            # OCR de fotos manuscritas: "mistral" (OpenRouter, unos 4 s; la foto sale a OpenRouter y Mistral antes de anonimizar)
            # o "local" (Ollama con qwen2.5vl:3b, unos 40 a 50 s; la foto no sale de tu equipo, solo en Jupyter local)
            OCR_MOTOR = "mistral"
            """),
        code("""
            # EDITA AQUÍ · 2.2 Contrato de síntomas y de reporte
            # Los contratos Pydantic y los prompts del extractor y del redactor están en
            # poc_psico/esquemas.py y poc_psico/nodos.py; edítalos ahí y reinicia el entorno.
            from poc_psico.esquemas import SintomasPaciente, ReporteClinico
            print("Síntomas:", list(SintomasPaciente.model_fields))
            print("Reporte:", list(ReporteClinico.model_fields))
            """),
        code("""
            # EDITA AQUÍ · 2.3 Casos de prueba (sintéticos)
            from poc_psico.casos import CASOS
            print(f"{len(CASOS)} casos:", [c["id"] for c in CASOS])
            """),
        md("## 3 · Construcción del flujo (no editar)"),
        code("""
            # 3.1 · Componentes y grafo (no editar)
            from poc_psico.agente import cargar_tools, construir_agente, correr_agente
            from poc_psico.grafo import Componentes, construir_workflow, ejecutar
            from poc_psico.guardrail import consultar_decisions
            from poc_psico.nodos import crear_extractor, crear_redactor
            from poc_psico.ocr import leer_imagen, leer_imagen_mistral

            tools = await cargar_tools(AGENT_MCP_URL, TOOLS_PERMITIDAS)
            agente = construir_agente(llm, tools, SYSTEM_PROMPT_AGENTE, MAX_RONDAS)

            async def _agente(sintomas):
                return await correr_agente(agente, sintomas, MAX_RONDAS)

            def _ocr(ruta):
                if OCR_MOTOR == "local":
                    return leer_imagen(ruta)
                return leer_imagen_mistral(ruta, os.environ["OPENROUTER_API_KEY"])

            def _guardrail(texto):
                return consultar_decisions(texto, os.environ["OPENROUTER_API_KEY"])

            componentes = Componentes(
                ner=ner_es,
                guardrail=_guardrail,
                extraer=crear_extractor(llm),
                agente=_agente,
                redactar=crear_redactor(llm),
                umbral=UMBRAL_GUARDRAIL,
                ocr=_ocr,
            )
            print("Tools:", [t.name for t in tools])
            """),
        code("""
            # 3.2 · Dibujo del workflow (no editar)
            try:
                from IPython.display import Image, display
                display(Image(construir_workflow(componentes, {}).get_graph().draw_mermaid_png()))
            except Exception:
                print(construir_workflow(componentes, {}).get_graph().draw_mermaid())
            """),
        md("## 4 · Pruebas y evidencia (no editar)"),
        code("""
            # 4.1 · Ejecuta los casos y registra la evidencia (no editar)
            import json
            import time
            import pandas as pd

            def describir(r: dict) -> str:
                if r is None:
                    return ""
                resumen = {
                    "estado": r["estado_final"], "razon": r["razon"], "prob_clinico": r["prob_clinico"],
                    "codigos": [c["codigo"] for c in r["candidatos"]], "rondas_agente": r["rondas_agente"],
                    "latencias_s": r["latencias"], "advertencias": r["advertencias"],
                }
                return json.dumps(resumen, ensure_ascii=False)

            async def correr_casos(casos, componentes):
                filas = []
                for caso in casos:
                    print(f"→ {caso['id']} · {caso['tipo']}")
                    inicio = time.perf_counter()
                    resultado, error = None, ""
                    try:
                        resultado = await ejecutar(caso["entrada"], componentes)
                    except Exception as exc:
                        error = f"{type(exc).__name__}: {exc}"
                    latencia = round(time.perf_counter() - inicio, 2)
                    try:
                        paso = resultado is not None and bool(caso["verificar"](resultado))
                    except Exception as exc:
                        paso, error = False, error or f"Error al verificar: {exc}"
                    filas.append({
                        "template": TEMPLATE_ID, "id": caso["id"], "tipo": caso["tipo"], "entrada": caso["entrada"],
                        "esperado": caso["esperado"], "criterio": caso["criterio"], "observado": describir(resultado),
                        "veredicto_auto": "PASS" if paso else "FAIL", "veredicto_final": "",
                        "latencia_s": latencia, "error": error,
                    })
                return pd.DataFrame(filas)

            registro = await correr_casos(CASOS, componentes)
            pd.set_option("display.max_colwidth", 220)
            display(registro[["id", "tipo", "veredicto_auto", "observado", "latencia_s", "error"]])
            print(f"\\nResultado automático: {(registro.veredicto_auto == 'PASS').sum()} de {len(registro)} casos en PASS")
            """),
        code("""
            # 4.2 · Guarda el registro de pruebas (no editar)
            archivo = f"registro_pruebas_{TEMPLATE_ID}.csv"
            registro.to_csv(archivo, index=False, encoding="utf-8-sig")
            print("Registro guardado:", archivo)
            """),
        code("""
            # 4.3 · Falla de conexión al MCP: el flujo debe detenerse sin reporte (no editar)
            from poc_psico.agente import cargar_tools
            from poc_psico.errores import FlujoDetenido

            async def _agente_roto(sintomas):
                await cargar_tools("https://no-existe.invalid/sse", TOOLS_PERMITIDAS)

            roto = Componentes(ner=ner_es, guardrail=_guardrail, extraer=crear_extractor(llm), agente=_agente_roto,
                               redactar=crear_redactor(llm), umbral=UMBRAL_GUARDRAIL)
            r = await ejecutar(CASOS[0]["entrada"], roto)
            assert r["estado_final"] == "error" and r["reporte_md"] == "", r
            print("OK, se detuvo con:", r["razon"])
            """),
        md("## 5 · Prueba libre y reporte"),
        code("""
            # 5 · Prueba libre: escribe tu viñeta sintética
            entrada = "Paciente de 41 años con ánimo irritable, preocupación constante y tensión muscular desde hace 8 meses."
            r = await ejecutar(entrada, componentes)
            print(r["estado_final"], "|", r["razon"])
            from IPython.display import Markdown
            Markdown(r["reporte_md"]) if r["reporte_md"] else None
            """),
        code("""
            # 5.1 · Prueba con foto de una nota manuscrita (motor en OCR_MOTOR, celda 2.1; ver README)
            RUTA_FOTO = ""  # EDITA AQUÍ: ruta a tu foto .jpg o .png; déjalo vacío para omitir
            from IPython.display import Markdown
            if RUTA_FOTO:
                r = await ejecutar(RUTA_FOTO, componentes)
                print("Texto leído (revísalo: un error de lectura cambia el sentido clínico):\\n", r["texto_ocr"])
                print(r["estado_final"], "|", r["razon"], "|", r["latencias"])
                Markdown(r["reporte_md"]) if r["reporte_md"] else None
            """),
        md("""
            ## 6 · Cierre del PoC
            Completa esta celda antes de entregar (doble clic para editar).

            - **Hipótesis evaluada:**
            - **Resultado:** _ de 4 casos en PASS, con veredicto revisado.
            - **Evidencia principal:** (rondas del agente, latencias, códigos obtenidos)
            - **Guardrail:** Decisions API o plan B con LLM, y por qué.
            - **Limitación principal:**
            - **Decisión:** continuar / ajustar / descartar.
            """),
    ]
    nb = new_notebook(cells=celdas)
    nb.metadata["colab"] = {"provenance": []}
    nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    return nb


if __name__ == "__main__":
    destino = RAIZ / "PoC_psicodiagnostico.ipynb"
    nbformat.write(construir(), destino)
    print("Notebook escrito en", destino)
