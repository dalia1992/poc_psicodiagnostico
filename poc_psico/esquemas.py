"""Contratos de salida (Pydantic). El LLM también lee las descripciones: están escritas como instrucciones."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SintomasPaciente(BaseModel):
    """Datos clínicos extraídos de la viñeta ya anonimizada."""

    paciente_ref: Optional[str] = Field(
        default=None,
        description="Placeholder de la persona que es el paciente, por ejemplo [PER_1], solo si aparece; si no, null",
    )
    edad: Optional[int] = Field(default=None, description="Edad en años solo si aparece escrita; si no, null")
    sexo: Optional[Literal["femenino", "masculino", "otro"]] = Field(
        default=None, description="Sexo del paciente solo si aparece; si no, null"
    )
    cognitivos: list[str] = Field(default_factory=list, description="Síntomas cognitivos (atención, memoria, pensamiento)")
    emocionales: list[str] = Field(default_factory=list, description="Síntomas emocionales o afectivos")
    conductuales: list[str] = Field(default_factory=list, description="Cambios conductuales observables")
    afectacion_social: list[str] = Field(
        default_factory=list, description="Afectación en el trabajo, la familia o las relaciones sociales"
    )
    temporalidad: Optional[str] = Field(
        default=None, description="Duración o evolución de los síntomas si se menciona; si no, null. No inventar"
    )
    datos_faltantes: list[str] = Field(
        default_factory=list,
        description="Datos clínicos relevantes que no aparecen y deberían recabarse (edad, duración, severidad, etc.)",
    )

    def hay_sintomas(self) -> bool:
        return any([self.cognitivos, self.emocionales, self.conductuales, self.afectacion_social])


class HipotesisRedactada(BaseModel):
    codigo: str = Field(description="Código CIE-11 EXACTO de uno de los candidatos recibidos; nunca otro")
    justificacion: str = Field(description="Por qué los síntomas del caso encajan con los criterios de esa entidad")
    criterios_cumplidos: list[str] = Field(default_factory=list, description="Criterios que el caso sí cumple")
    criterios_no_cumplidos: list[str] = Field(
        default_factory=list, description="Criterios que faltan o no se pueden confirmar con la información dada"
    )


class PruebaSugerida(BaseModel):
    nombre: str = Field(description="Solo el nombre de la prueba, por ejemplo Inventario de Ansiedad de Beck")
    motivo: str = Field(description="Una frase sobre por qué sería útil para este caso")


class ReporteClinico(BaseModel):
    hipotesis: list[HipotesisRedactada] = Field(description="Ordenadas de la más a la menos plausible")
    ambiguedades: list[str] = Field(default_factory=list, description="Ambigüedades en la búsqueda o en el caso")
    diferenciales: list[str] = Field(default_factory=list, description="Diagnósticos diferenciales y exclusiones a considerar")
    datos_faltantes: list[str] = Field(default_factory=list, description="Datos a recabar para confirmar o descartar")
    pruebas: list[PruebaSugerida] = Field(default_factory=list, description="Pruebas complementarias: solo nombre y motivo")
