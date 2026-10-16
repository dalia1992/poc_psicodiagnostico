"""Prueba real del OCR: lee una foto o un PDF con Mistral OCR (OpenRouter) y, si das la transcripción correcta, mide el error.

Uso: ~/.venvs/poc_psico/bin/python scripts/spike_ocr.py foto.jpg [transcripcion.txt]
Requiere OPENROUTER_API_KEY (del .env o del entorno). El archivo sale a OpenRouter y Mistral: solo datos sintéticos.
"""
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from poc_psico.entorno import cargar_env  # noqa: E402
from poc_psico.ocr import leer_archivo_mistral  # noqa: E402


def tasa_error_por_caracter(referencia: str, hipotesis: str) -> float:
    """Distancia de Levenshtein entre ambos textos (espacios normalizados) sobre la longitud de la referencia."""
    ref, hip = " ".join(referencia.split()), " ".join(hipotesis.split())
    anterior = list(range(len(hip) + 1))
    for i, a in enumerate(ref, 1):
        actual = [i]
        for j, b in enumerate(hip, 1):
            actual.append(min(anterior[j] + 1, actual[j - 1] + 1, anterior[j - 1] + (a != b)))
        anterior = actual
    return anterior[-1] / max(len(ref), 1)


if __name__ == "__main__":
    cargar_env()
    inicio = time.perf_counter()
    texto = leer_archivo_mistral(sys.argv[1], os.environ.get("OPENROUTER_API_KEY"))
    print(f"Tiempo: {time.perf_counter() - inicio:.1f} s")
    if len(sys.argv) > 2:
        referencia = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")
        print(f"CER: {tasa_error_por_caracter(referencia, texto):.3f}")
    print("--- texto leído ---\n" + texto)
