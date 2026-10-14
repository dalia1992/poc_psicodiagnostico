"""Validación de hipótesis contra las tools y renderizado del reporte en Markdown."""
from datetime import date

from .esquemas import ReporteClinico


def validar_hipotesis(reporte: ReporteClinico, candidatos: list):
    """Une cada hipótesis con su candidato. Código, título y liga salen de la tool, nunca del LLM."""
    por_codigo = {c["codigo"]: c for c in candidatos}
    finales, advertencias, vistos = [], [], set()
    for h in reporte.hipotesis:
        candidato = por_codigo.get(h.codigo)
        if candidato is None:
            advertencias.append(f"Se descartó la hipótesis con código {h.codigo}: no fue obtenido de las tools")
            continue
        if h.codigo in vistos:
            continue
        vistos.add(h.codigo)
        finales.append(
            {
                **candidato,
                "justificacion": h.justificacion,
                "criterios_cumplidos": h.criterios_cumplidos,
                "criterios_no_cumplidos": h.criterios_no_cumplidos,
            }
        )
    return finales, advertencias


def _lista(items, vacio="Ninguno identificado") -> str:
    return "\n".join(f"- {i}" for i in items) if items else f"- {vacio}"


def render_markdown(sintomas: dict, hipotesis: list, reporte: ReporteClinico, alternativas: list, fecha: date) -> str:
    partes = [
        "# Reporte de apoyo al psicodiagnóstico",
        "## 1. Datos del caso",
        f"- Paciente: {sintomas.get('paciente_ref') or 'No identificado'}",
        f"- Edad: {sintomas['edad'] if sintomas.get('edad') is not None else 'No indicada'}",
        f"- Sexo: {sintomas.get('sexo') or 'No indicado'}",
        f"- Temporalidad: {sintomas.get('temporalidad') or 'No indicada'}",
        f"- Fecha del reporte: {fecha.isoformat()}",
        "## 2. Síntomas por categoría",
    ]
    for etiqueta, clave in (
        ("Cognitivos", "cognitivos"),
        ("Emocionales", "emocionales"),
        ("Conductuales", "conductuales"),
        ("Afectación social", "afectacion_social"),
    ):
        partes += [f"### {etiqueta}", _lista(sintomas.get(clave))]

    partes.append("## 3. Hipótesis diagnósticas (de la más a la menos plausible)")
    for i, h in enumerate(hipotesis, 1):
        partes += [
            f"### {i}. {h['titulo']} — `{h['codigo']}`",
            f"[Abrir en el navegador OMS]({h['url']})",
            f"**Justificación:** {h['justificacion']}",
            "**Criterios cumplidos:**",
            _lista(h["criterios_cumplidos"], "Ninguno indicado"),
            "**Criterios no cumplidos o sin confirmar:**",
            _lista(h["criterios_no_cumplidos"], "Ninguno indicado"),
        ]
    if reporte.ambiguedades:
        partes += ["### Ambigüedades", _lista(reporte.ambiguedades)]

    partes += ["## 4. Diferenciales y exclusiones", _lista(reporte.diferenciales, "Ninguno indicado")]
    if alternativas:
        partes.append("### Alternativas consultadas y descartadas")
        partes += [f"- {a['titulo']} (`{a['codigo']}`) — [OMS]({a['url']})" for a in alternativas]

    partes += ["## 5. Datos faltantes por recabar", _lista(reporte.datos_faltantes, "Ninguno indicado")]
    partes += [
        "## 6. Pruebas complementarias sugeridas",
        "> Sugerencias a validar por el profesional. Solo se indica el nombre de la prueba: no se incluyen cuestionarios ni formas de calificación.",
    ]
    partes += [f"- **{p.nombre}**: {p.motivo}" for p in reporte.pruebas] or ["- Ninguna sugerida"]
    partes += [
        "## 7. Aviso",
        "Este reporte contiene hipótesis de apoyo generadas con ayuda de IA a partir de la CIE-11. No es un diagnóstico: la decisión clínica es del profesional.",
    ]
    return "\n\n".join(partes) + "\n"
