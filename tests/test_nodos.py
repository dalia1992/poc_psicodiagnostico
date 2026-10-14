import json

from poc_psico.esquemas import ReporteClinico, SintomasPaciente
from poc_psico.nodos import crear_extractor, crear_redactor


class EstructuradoFalso:
    def __init__(self, resultado):
        self.resultado, self.llamadas = resultado, []

    def invoke(self, mensajes):
        self.llamadas.append(mensajes)
        return self.resultado


class LLMFalso:
    def __init__(self, resultado):
        self.estructurado = EstructuradoFalso(resultado)
        self.esquema = None
        self.metodo = None

    def with_structured_output(self, esquema, method=None):
        self.esquema, self.metodo = esquema, method
        return self.estructurado


def test_extractor_devuelve_dict_y_usa_function_calling():
    llm = LLMFalso(SintomasPaciente(emocionales=["tristeza"], edad=34))
    extraer = crear_extractor(llm)
    assert extraer("[PER_1] de 34 años")["emocionales"] == ["tristeza"]
    assert llm.esquema is SintomasPaciente and llm.metodo == "function_calling"
    assert llm.estructurado.llamadas[0][1] == ("human", "[PER_1] de 34 años")


def test_redactor_solo_envia_codigo_titulo_y_criterios_no_urls():
    reporte = ReporteClinico(hipotesis=[])
    llm = LLMFalso(reporte)
    redactar = crear_redactor(llm)
    candidatos = [{"codigo": "6A70", "titulo": "T", "url": "https://x/1001", "definicion": "D", "inclusiones": [], "exclusiones": []}]
    salida = redactar({"emocionales": ["tristeza"]}, candidatos, [{"codigo": "6A71", "titulo": "R", "url": "https://x/1002"}], "notas")
    assert salida is reporte
    enviado = llm.estructurado.llamadas[0][1][1]
    assert "6A70" in enviado and "6A71" in enviado and "notas" in enviado
    assert "https://x" not in enviado
    assert json.loads(enviado)["sintomas"]["emocionales"] == ["tristeza"]
