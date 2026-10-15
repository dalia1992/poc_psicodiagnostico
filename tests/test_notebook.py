import ast

import nbformat

from scripts.build_notebook import construir


def _codigo_ejecutable(celda) -> str:
    lineas = [l for l in celda.source.splitlines() if not l.lstrip().startswith(("%", "!"))]
    return "\n".join(lineas)


def test_el_notebook_es_valido_y_todas_las_celdas_compilan():
    nb = construir()
    nbformat.validate(nb)
    for celda in nb.cells:
        if celda.cell_type == "code":
            compile(_codigo_ejecutable(celda), "<celda>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)


def test_conserva_las_celdas_edita_aqui_y_el_modelo_del_template():
    codigo = "\n".join(c.source for c in construir().cells if c.cell_type == "code")
    assert codigo.count("# EDITA AQUÍ") >= 3
    assert "nvidia/nemotron-3-ultra-550b-a55b:free" in codigo
    assert "https://openrouter.ai/api/v1" in codigo
    assert "MMG/xlm-roberta-large-ner-spanish" in codigo
    assert "UMBRAL_GUARDRAIL" in codigo and "TOOLS_PERMITIDAS" in codigo
    assert "AGENT_MCP_URL" in codigo
    assert "cargar_env" in codigo


def test_el_notebook_no_imprime_el_reporte_en_el_registro_csv():
    codigo = "\n".join(c.source for c in construir().cells if c.cell_type == "code")
    assert "reporte_md" not in codigo.split("def describir")[1].split("\n\n")[0]


def test_el_notebook_usa_max_rondas_y_no_el_limite_de_pasos():
    codigo = "\n".join(c.source for c in construir().cells if c.cell_type == "code")
    assert "MAX_RONDAS = 5" in codigo
    assert "construir_agente(llm, tools, SYSTEM_PROMPT_AGENTE, MAX_RONDAS)" in codigo
    assert "correr_agente(agente, sintomas, MAX_RONDAS)" in codigo
    assert "RECURSION_LIMIT" not in codigo


def test_el_motor_de_ocr_se_elige_en_una_celda_edita_aqui_y_mistral_es_el_predeterminado():
    codigo = "\n".join(c.source for c in construir().cells if c.cell_type == "code")
    assert 'OCR_MOTOR = "mistral"' in codigo
    assert "from poc_psico.ocr import leer_imagen, leer_imagen_mistral" in codigo
    assert 'if OCR_MOTOR == "local"' in codigo
    assert 'leer_imagen_mistral(ruta, os.environ["OPENROUTER_API_KEY"])' in codigo
    assert "ocr=_ocr" in codigo
    assert "RUTA_FOTO" in codigo
