"""Explora la Decisions API con JEV (typesafe). Uso: python scripts/spike_guardrail.py (lee OPENROUTER_API_KEY del .env o del entorno)"""
import json
import os
import pathlib
import sys

import requests
from dotenv import load_dotenv

URL = "https://openrouter.ai/api/alpha/decisions"
MODELO = "typesafe/jev-1.14-20261014"
FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures"

TEXTOS = {
    "clinico": (
        "[PER_1], mujer de 34 años, refiere desde hace 4 meses tristeza casi todos los días, "
        "pérdida de interés, insomnio y dificultad para concentrarse en el trabajo."
    ),
    "cocina": "¿Me recomiendas una receta de pan amasado para el fin de semana?",
}
PREGUNTA = {
    "es_clinico": {
        "type": "noul",
        "instructions": "El texto es una nota o viñeta clínica de psicología que describe a un paciente "
        "con síntomas, conducta, emociones o antecedentes de salud mental.",
    }
}


def main() -> int:
    load_dotenv(FIXTURES.parent.parent / ".env")
    clave = os.environ.get("OPENROUTER_API_KEY")
    if not clave:
        print("Falta OPENROUTER_API_KEY: defínela en el archivo .env o en el entorno")
        return 2
    FIXTURES.mkdir(parents=True, exist_ok=True)
    codigo_salida = 0
    for nombre, texto in TEXTOS.items():
        payload = {"model": MODELO, "state": texto, "questions": PREGUNTA}
        r = requests.post(
            URL,
            json=payload,
            headers={"Authorization": f"Bearer {clave}", "Content-Type": "application/json"},
            timeout=60,
        )
        print(f"--- {nombre}: HTTP {r.status_code}")
        print(r.text[:1500])
        if r.status_code == 200:
            (FIXTURES / f"decisions_{nombre}.json").write_text(
                json.dumps(r.json(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        else:
            codigo_salida = 1
    return codigo_salida


if __name__ == "__main__":
    sys.exit(main())
