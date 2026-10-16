import ast
import pathlib

import nbformat

RUTA_NOTEBOOK = pathlib.Path(__file__).resolve().parent.parent / "PoC_psicodiagnostico.ipynb"


def cargar_notebook():
    return nbformat.read(RUTA_NOTEBOOK, as_version=4)


def _codigo_ejecutable(celda) -> str:
    lineas = [l for l in celda.source.splitlines() if not l.lstrip().startswith(("%", "!"))]
    return "\n".join(lineas)


def test_el_notebook_es_valido_y_todas_las_celdas_compilan():
    nb = cargar_notebook()
    nbformat.validate(nb)
    for celda in nb.cells:
        if celda.cell_type == "code":
            compile(_codigo_ejecutable(celda), "<celda>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)


def test_conserva_las_celdas_edita_aqui_y_el_modelo_del_template():
    codigo = "\n".join(c.source for c in cargar_notebook().cells if c.cell_type == "code")
    assert codigo.count("# EDITA AQUÍ") >= 3
    assert "nvidia/nemotron-3-ultra-550b-a55b:free" in codigo
    assert "https://openrouter.ai/api/v1" in codigo
    assert "MMG/xlm-roberta-large-ner-spanish" in codigo
    assert "UMBRAL_GUARDRAIL" in codigo and "TOOLS_PERMITIDAS" in codigo
    assert "AGENT_MCP_URL" in codigo
    assert "cargar_env" in codigo


def test_el_notebook_no_imprime_el_reporte_en_el_registro_csv():
    codigo = "\n".join(c.source for c in cargar_notebook().cells if c.cell_type == "code")
    assert "reporte_md" not in codigo.split("def describir")[1].split("\n\n")[0]


def test_el_notebook_usa_max_rondas_y_no_el_limite_de_pasos():
    codigo = "\n".join(c.source for c in cargar_notebook().cells if c.cell_type == "code")
    assert "MAX_RONDAS = 5" in codigo
    assert "construir_agente(llm, tools, SYSTEM_PROMPT_AGENTE, MAX_RONDAS)" in codigo
    assert "correr_agente(agente, sintomas, MAX_RONDAS)" in codigo
    assert "RECURSION_LIMIT" not in codigo


def test_el_ocr_del_notebook_usa_solo_mistral():
    codigo = "\n".join(c.source for c in cargar_notebook().cells if c.cell_type == "code")
    assert "from poc_psico.ocr import leer_imagen_mistral" in codigo
    assert 'leer_imagen_mistral(ruta, os.environ["OPENROUTER_API_KEY"])' in codigo
    assert "ocr=_ocr" in codigo
    assert "RUTA_FOTO" in codigo
    assert "OCR_MOTOR" not in codigo and "Ollama" not in codigo


def test_el_display_del_registro_muestra_una_columna_con_las_rondas_del_agente_y_el_csv_no_cambia():
    codigo = "\n".join(c.source for c in cargar_notebook().cells if c.cell_type == "code")
    assert "def rondas_de(observado" in codigo
    assert 'registro.assign(rondas=registro["observado"].map(rondas_de))' in codigo
    assert '["id", "tipo", "veredicto_auto", "rondas", "latencia_s", "observado", "error"]' in codigo
    assert '"latencia_s": latencia, "error": error,' in codigo  # la fila del CSV sigue sin columna nueva
