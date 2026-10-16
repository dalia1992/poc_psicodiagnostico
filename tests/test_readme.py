import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def test_el_readme_cubre_colab_local_y_pruebas():
    texto = (RAIZ / "README.md").read_text(encoding="utf-8")
    for esperado in (
        "## Opción A: Google Colab",
        "## Opción B: Jupyter local",
        "## Pruebas unitarias",
        "OPENROUTER_API_KEY",
        ".env.example",
        "POC_ENV_FILE",
        "uv sync",
        "PoC_psicodiagnostico.ipynb",
        "## Problemas frecuentes",
    ):
        assert esperado in texto


def test_los_comandos_del_readme_existen_en_el_proyecto():
    texto = (RAIZ / "README.md").read_text(encoding="utf-8")
    mencionados = (
        "scripts/spike_guardrail.py",
        "scripts/spike_mcp.py",
        "poc_psico/esquemas.py",
        "poc_psico/nodos.py",
        "poc_psico/guardrail.py",
    )
    for archivo in mencionados:
        assert archivo in texto, f"el README no menciona {archivo}"
        assert (RAIZ / archivo).exists(), f"el README menciona {archivo} y no existe"
