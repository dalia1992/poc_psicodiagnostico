from datetime import date

from poc_psico.esquemas import HipotesisRedactada, PruebaSugerida, ReporteClinico
from poc_psico.reporte import render_markdown, validar_hipotesis

CANDIDATOS = [
    {
        "codigo": "6A70",
        "titulo": "Trastorno depresivo de episodio único",
        "url": "https://icd.who.int/browse/2024-01/mms/es#1001",
        "definicion": "Episodio depresivo.",
        "inclusiones": [],
        "exclusiones": [],
    }
]
ALTERNATIVAS = [{"codigo": "6A71", "titulo": "Trastorno depresivo recurrente", "url": "https://icd.who.int/browse/2024-01/mms/es#1002"}]
SINTOMAS = {
    "paciente_ref": "[PER_1]", "edad": 34, "sexo": "femenino",
    "cognitivos": ["dificultad para concentrarse"], "emocionales": ["tristeza"], "conductuales": [],
    "afectacion_social": ["faltas al trabajo"], "temporalidad": "4 meses", "datos_faltantes": [],
}


def reporte_base(**extra):
    base = dict(
        hipotesis=[HipotesisRedactada(codigo="6A70", justificacion="Tristeza persistente.", criterios_cumplidos=["Ánimo bajo"], criterios_no_cumplidos=["Duración no confirmada"])],
        ambiguedades=["Podría ser recurrente"],
        diferenciales=["Descartar trastorno bipolar"],
        datos_faltantes=["Antecedentes de episodios previos"],
        pruebas=[PruebaSugerida(nombre="Inventario de Depresión de Beck", motivo="Cuantificar severidad")],
    )
    base.update(extra)
    return ReporteClinico(**base)


def test_validar_descarta_codigos_que_no_vienen_de_las_tools():
    rep = reporte_base(hipotesis=[
        HipotesisRedactada(codigo="6A70", justificacion="ok"),
        HipotesisRedactada(codigo="9Z99", justificacion="inventada"),
    ])
    finales, advertencias = validar_hipotesis(rep, CANDIDATOS)
    assert [h["codigo"] for h in finales] == ["6A70"]
    assert any("9Z99" in a for a in advertencias)


def test_validar_no_duplica_hipotesis():
    rep = reporte_base(hipotesis=[HipotesisRedactada(codigo="6A70", justificacion="a"), HipotesisRedactada(codigo="6A70", justificacion="b")])
    finales, _ = validar_hipotesis(rep, CANDIDATOS)
    assert len(finales) == 1


def test_validar_toma_titulo_y_url_del_candidato_no_del_llm():
    finales, _ = validar_hipotesis(reporte_base(), CANDIDATOS)
    assert finales[0]["titulo"] == "Trastorno depresivo de episodio único"
    assert finales[0]["url"].startswith("https://icd.who.int")
    assert finales[0]["justificacion"] == "Tristeza persistente."


def test_render_incluye_las_siete_secciones_y_codigo_y_liga():
    rep = reporte_base()
    finales, _ = validar_hipotesis(rep, CANDIDATOS)
    md = render_markdown(SINTOMAS, finales, rep, ALTERNATIVAS, date(2026, 10, 15))
    for titulo in ("## 1. Datos del caso", "## 2. Síntomas por categoría", "## 3. Hipótesis diagnósticas",
                   "## 4. Diferenciales y exclusiones", "## 5. Datos faltantes por recabar",
                   "## 6. Pruebas complementarias sugeridas", "## 7. Aviso"):
        assert titulo in md
    assert "`6A70`" in md
    assert "[Abrir en el navegador OMS](https://icd.who.int/browse/2024-01/mms/es#1001)" in md
    assert "[PER_1]" in md and "2026-10-15" in md
    assert "Trastorno depresivo recurrente" in md  # alternativa descartada, con su código


def test_render_marca_categorias_vacias_y_datos_no_indicados():
    sintomas = {**SINTOMAS, "conductuales": [], "edad": None, "sexo": None, "paciente_ref": None}
    rep = reporte_base()
    finales, _ = validar_hipotesis(rep, CANDIDATOS)
    md = render_markdown(sintomas, finales, rep, [], date(2026, 10, 15))
    assert "Ninguno identificado" in md
    assert "No indicada" in md and "No identificado" in md


def test_sintomas_inician_con_mayuscula():
    sintomas = {**SINTOMAS, "emocionales": ["ansiedad en situaciones con mucha gente", "tristeza"]}
    rep = reporte_base()
    finales, _ = validar_hipotesis(rep, CANDIDATOS)
    md = render_markdown(sintomas, finales, rep, [], date(2026, 10, 15))
    assert "- Ansiedad en situaciones con mucha gente" in md
    assert "- Dificultad para concentrarse" in md
    assert "- ansiedad" not in md


def test_pruebas_solo_nombre_y_motivo_con_aviso():
    rep = reporte_base()
    finales, _ = validar_hipotesis(rep, CANDIDATOS)
    md = render_markdown(SINTOMAS, finales, rep, [], date(2026, 10, 15))
    seccion = md.split("## 6. Pruebas complementarias sugeridas")[1].split("## 7.")[0]
    assert "**Inventario de Depresión de Beck**: Cuantificar severidad" in seccion
    assert "a validar por el profesional" in seccion


def test_todos_los_items_del_reporte_inician_en_mayuscula():
    from datetime import date

    from poc_psico.esquemas import ReporteClinico
    from poc_psico.reporte import render_markdown

    reporte = ReporteClinico.model_validate(
        {
            "hipotesis": [],
            "ambiguedades": ["duración poco clara"],
            "diferenciales": ["trastorno de ansiedad"],
            "datos_faltantes": ["edad de inicio"],
            "pruebas": [{"nombre": "inventario de beck", "motivo": "evaluar gravedad"}],
        }
    )
    hip = [{"titulo": "trastorno x", "codigo": "1A", "url": "u", "justificacion": "cumple criterios",
            "criterios_cumplidos": ["ánimo bajo"], "criterios_no_cumplidos": ["duración"]}]
    md = render_markdown({"emocionales": ["tristeza"]}, hip, reporte, [{"titulo": "otro x", "codigo": "2B", "url": "u"}], date(2026, 1, 1))
    for esperado in ["- Duración poco clara", "- Trastorno de ansiedad", "- Edad de inicio", "**Inventario de beck**: Evaluar gravedad",
                     "### 1. Trastorno x", "**Justificación:** Cumple criterios", "- Ánimo bajo", "- Duración", "- Otro x", "- Tristeza"]:
        assert esperado in md


def test_el_reporte_incluye_las_guias_apa_con_liga_y_cita():
    guias = [{"titulo": "Guía de depresión", "url": "https://www.apa.org/g", "cita": "Recomienda terapia."}]
    md = render_markdown(SINTOMAS, [], reporte_base(), [], date(2026, 10, 15), guias)
    assert "### Guías clínicas de la APA" in md
    assert "[Guía de depresión](https://www.apa.org/g)" in md and "Recomienda terapia." in md
    assert md.index("### Guías clínicas de la APA") < md.index("## 7. Aviso")


def test_sin_guias_no_hay_seccion_de_guias():
    assert "Guías clínicas" not in render_markdown(SINTOMAS, [], reporte_base(), [], date(2026, 10, 15))
