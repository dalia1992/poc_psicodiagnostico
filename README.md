# PoC · Asistente de apoyo al psicodiagnóstico (LC-B + LC-C)

Convierte una viñeta clínica en texto libre en un reporte Markdown con síntomas clasificados, hipótesis CIE-11 (código y liga a la OMS) y datos faltantes.

```
(foto → OCR local) → texto → anonimizar (NER local) → guardrail (span-01-lite) → extraer síntomas → agente CIE-11 (MCP en Azure) → reporte
```

Los nombres, lugares y organizaciones se sustituyen por `[PER_1]`, `[LOC_1]`, `[ORG_1]` antes de llamar a cualquier servicio externo y se reinsertan al final, solo en el reporte.

> Trabaja solo con datos sintéticos o anonimizados: OpenRouter y, si usas Mistral OCR, Mistral reciben tus datos y pueden registrar el uso.

## Qué necesitas

- Una clave de OpenRouter: crea una cuenta en [openrouter.ai](https://openrouter.ai) y una clave en [openrouter.ai/keys](https://openrouter.ai/keys). El notebook usa `anthropic/claude-haiku-5.5`, un modelo de pago (US$0.10 de entrada y US$0.50 de salida por millón de tokens), así que la cuenta necesita créditos. La alternativa gratuita, `nvidia/nemotron-3-ultra-550b-a55b:free`, queda comentada en la celda 1.1: la cuenta gratuita permite 50 llamadas al día y 20 por minuto (una corrida completa usa cerca de 8) y en una prueba con foto tardó 194 s, contra 52 s con Haiku 5.5.
- El servidor MCP CIE-11 en Azure ya está desplegado; su URL es el valor por defecto de `AGENT_MCP_URL` en el notebook.
- Para Colab: una cuenta de Google. Para local: macOS o Linux y [uv](https://docs.astral.sh/uv/).

## Opción A: Google Colab

1. **Deja la carpeta en Drive.** Debe estar en `Mi unidad/LLM solutions architect/Módulo 5/poc_psicodiagnostico/` (si usas Google Drive para escritorio, ya está sincronizada). Si la pones en otro lugar, cambia `RUTA_PROYECTO` en la celda 0.2.
2. **Abre el notebook.** En [colab.research.google.com](https://colab.research.google.com): *Archivo → Abrir cuaderno → Google Drive*, y elige `PoC_psicodiagnostico.ipynb`.
3. **Guarda tu clave como secreto.** En la barra izquierda abre el ícono de llave (*Secretos*), agrega `OPENROUTER_API_KEY` con tu clave y activa *Acceso del notebook*. Nunca pegues la clave en una celda.
4. **(Opcional) GPU.** *Entorno de ejecución → Cambiar tipo de entorno de ejecución → T4*. Acelera el NER; no es obligatoria.
5. **Ejecuta todo.** *Entorno de ejecución → Ejecutar todas*. Autoriza el acceso a Drive cuando lo pida la celda 0.2. La primera vez tarda varios minutos: instala las dependencias y descarga el modelo NER (más de 2 GB).
6. **Comprueba cada punto de control.**
   - Celda 0.2: imprime `Paquete cargado desde ...`.
   - Celda 1.1: `Prueba de conexión: OK`.
   - Celda 1.2: imprime las entidades de la frase de ejemplo.
   - Celda 3.1: lista las tools del MCP (`icd11_buscar_fundacion`, `icd11_buscar_codigo_mms`, `icd11_obtener_criterios_clinicos`).
   - Celda 4.1: ejecuta los casos P1 a P4 y muestra cuántos quedaron en `PASS`.
   - Celda 4.3: imprime `OK, se detuvo con: ...` (la falla de conexión debe detener el flujo).
7. **Descarga la evidencia.** La celda 4.2 guarda `registro_pruebas_LC-B+C.csv` en el panel de archivos de Colab (se borra al cerrar la sesión): descárgalo o muévelo a Drive.
8. **Prueba tu propia viñeta** en la celda 5.
9. **Si editas el paquete** (`poc_psico/*.py` en Drive), reinicia la sesión (*Entorno de ejecución → Reiniciar sesión*) y vuelve a ejecutar: Python no recarga los módulos ya importados.

Privacidad: en Colab el NER corre en la máquina virtual de Google, por lo que el texto original sí pasa por ella; no llega a ningún LLM ni a OpenRouter. El OCR de fotos con Mistral envía la foto a OpenRouter (ver la sección de la foto).

## Opción B: Jupyter local

1. **Instala uv** (una vez): `curl -LsSf https://astral.sh/uv/install.sh | sh`.
2. **Entra a la carpeta del proyecto**:

   ```bash
   cd "/ruta/a/Módulo 5/poc_psicodiagnostico"
   ```

3. **Crea el entorno fuera de Google Drive** (evita sincronizar miles de archivos) e instala todo:

   ```bash
   export UV_PROJECT_ENVIRONMENT=~/.venvs/poc_psico
   uv sync --python 3.12 --extra ner --extra notebook
   ```

   Descarga torch y transformers (varios GB). Agrega la línea `export` a tu `~/.zshrc` o `~/.bashrc` para no repetirla.
4. **Guarda tu clave en un archivo `.env`** (el notebook y los scripts lo leen solos; `.gitignore` lo excluye del repositorio):

   ```bash
   cp .env.example .env
   ```

   Abre `.env` y escribe `OPENROUTER_API_KEY=tu-clave`. Si ya tienes la variable exportada en tu shell, esa tiene prioridad sobre el archivo.

   > **Ojo con Google Drive.** Si esta carpeta se sincroniza con Drive, `.env` también se sube a tu Drive. Para evitarlo guarda el archivo fuera de la carpeta, por ejemplo `~/.config/poc_psico/env`, y apunta a él antes de abrir Jupyter: `export POC_ENV_FILE=~/.config/poc_psico/env`.

5. **Abre Jupyter desde la carpeta del proyecto**, para que el notebook encuentre `poc_psico/`:

   ```bash
   ~/.venvs/poc_psico/bin/jupyter lab
   ```

6. Abre `PoC_psicodiagnostico.ipynb` y *Run → Run All Cells*. La celda 0.1 solo avisa que usas el entorno local; la 0.2 toma la carpeta actual. Los puntos de control son los mismos que en Colab. El CSV queda junto al notebook.
7. **Si editas el paquete**, reinicia el kernel (*Kernel → Restart Kernel*).

Privacidad: en local el NER corre en tu equipo y el texto original no sale de él.

## Guías clínicas (APA, IMSS y OMS)

Después de la búsqueda CIE-11, `poc_psico/guias.py` hace cuatro búsquedas web con el plugin `web` de OpenRouter, cada una restringida a un dominio con `include_domains` (el filtro lo aplica OpenRouter, no el prompt): APA (`apa.org`) para evaluación y diagnóstico diferencial, con énfasis en qué hacer si falta información; APA para intervención; guías de práctica clínica del IMSS (`imss.gob.mx`); y guías de la OMS (`who.int`, incluye mhGAP). El reporte añade la subsección *Guías clínicas consultadas*, agrupada por fuente, con título, liga y una cita corta. Las búsquedas de APA y OMS prefieren páginas en español y usan las de inglés si no hay.

- **Privacidad:** a las búsquedas solo viajan los títulos de las entidades CIE-11 candidatas, nunca datos del paciente ni códigos.
- **Seguridad:** el texto de la web no pasa por ningún LLM; solo se imprimen título, liga y cita, y `_dominio_permitido` descarta cualquier liga fuera del dominio de esa búsqueda.
- **IMSS:** sus guías usan códigos CIE-10 (F32, F33), no CIE-11, y la de depresión (clave IMSS-161-09) es de 2009: confirma su vigencia en el catálogo. Algunos títulos de los PDF salen genéricos (por ejemplo «Guía de práctica clínica»).
- **Costo y tolerancia a fallas:** añade cuatro búsquedas por caso (hasta 3 resultados cada una, unos US$0.03 y 35 s en total). Si una falla, el reporte sale sin guías y con una advertencia. Para desactivarlas pon `BUSCAR_GUIAS_APA = False` en la celda 2.1.

## Foto de una nota manuscrita (OCR)

`ejecutar()` acepta la ruta de una foto `.jpg` o `.png` en lugar del texto. La foto se lee con OCR (`poc_psico/ocr.py`) y el texto leído sigue el flujo normal. El motor se elige en `OCR_MOTOR` (celda 2.1):

| Motor | Tiempo del paso (mismo caso) | Error de caracteres | La foto... |
|---|---|---|---|
| `"mistral"` (predeterminado): Mistral OCR vía OpenRouter | unos 3 a 4 s | 13.9 % | **sale a OpenRouter y Mistral** con los nombres sin anonimizar |
| `"local"`: `qwen2.5vl:3b` con [Ollama](https://ollama.com) | 38 a 53 s | 5.2 % | no sale de tu equipo; solo Jupyter local |

Medido con una sola foto manuscrita sintética y una corrida por motor (M1 de 8 GB, 2026-10-14): son cifras de orientación, no una tasa de error. Mistral conservó la última línea que el local perdió, pero leyó el nombre en mayúsculas ("LUCTA" por "Lucía"); el NER lo partió en dos entidades y el reporte quedó con "LU" como nombre. No se filtra el nombre, pero **revisa el nombre y `r["texto_ocr"]`**: un error de lectura puede cambiar el sentido clínico.

**Mistral OCR** solo necesita `OPENROUTER_API_KEY` y funciona también en Colab. La foto se convierte a PDF de una página dentro del nodo, porque el plugin `file-parser` no lee un JPEG directo. Cuesta unos US$0.002 por foto más el modelo acompañante `openai/gpt-4o-mini` (centavos; su respuesta se ignora). El motor de parseo a veces responde `400 rate limited`: el nodo reintenta solo 3 veces (1, 2 y 4 s).

**OCR local:** instala Ollama y descarga el modelo una vez (unos 3.2 GB): `ollama pull qwen2.5vl:3b`; deja el servicio activo (`ollama serve`). Con 8 GB de RAM ocupa unos 3.7 GB y se descarga solo al terminar (`keep_alive: 0`); no lo corras a la vez que el NER. PaddleOCR-VL con transformers saturó el swap en ese equipo y se descartó. **Con datos reales usa `"local"` y Jupyter local**: es el único motor que no envía la foto a terceros.

Uso: en el notebook, celda 5.1, escribe la ruta en `RUTA_FOTO`; o desde Python: `await ejecutar("foto.jpg", componentes)`. Para medir tu caso: `scripts/spike_ocr.py foto.jpg transcripcion.txt` (motor local, con tiempo y tasa de error por carácter).

## Pruebas unitarias

No necesitan claves ni red; usan componentes falsos.

```bash
~/.venvs/poc_psico/bin/python -m pytest -q
```

Dos pruebas se omiten hasta que existan los fixtures reales de `scripts/spike_guardrail.py` y `scripts/spike_mcp.py` (necesitan `OPENROUTER_API_KEY` y acceso al MCP).

## Qué editar

Solo las celdas marcadas `# EDITA AQUÍ` del notebook: umbral del guardrail, URL del MCP, tools permitidas, prompt del agente, máximo de rondas del agente y casos de prueba. Los contratos (`poc_psico/esquemas.py`) y los prompts del extractor y del redactor (`poc_psico/nodos.py`) se editan en esos archivos. Para regenerar el notebook tras cambiar `scripts/build_notebook.py`:

```bash
~/.venvs/poc_psico/bin/python scripts/build_notebook.py
```

## Problemas frecuentes

| Síntoma | Qué hacer |
|---|---|
| `ModuleNotFoundError: poc_psico` en la celda 0.2 | La ruta de la carpeta es incorrecta: ajusta `RUTA_PROYECTO` (Colab) o abre Jupyter desde la carpeta del proyecto (local). |
| `401` o `User not found` | La clave está mal copiada, o el secreto no tiene *Acceso del notebook* activado (Colab). |
| El notebook te pide la clave por teclado | No encontró `OPENROUTER_API_KEY`: revisa que `.env` esté en la carpeta del proyecto (o que `POC_ENV_FILE` apunte a él) y que la línea no tenga espacios ni comillas de más. |
| `429` o `rate limit` (también en el guardrail: `La Decisions API respondió 429`) | Superaste 20 llamadas por minuto o 50 por día; el límite diario cuenta modelos gratuitos y Decisions API juntos. Espera al día siguiente, o carga 10 créditos en OpenRouter para subir el límite a 1000 por día. El flujo falla cerrado: nunca deja pasar un texto sin guardrail. |
| `503` o `system overload` | El servicio está sobrecargado. El guardrail, el extractor, el redactor y las llamadas del agente al modelo reintentan solos 3 veces, esperando 1, 2 y 4 segundos (`poc_psico/reintentos.py`); verás un aviso por cada reintento. Si persiste, el flujo se detiene con el error. |
| `GuardrailError: Formato inesperado de la Decisions API` | La respuesta de `span-01-lite` no tiene la forma esperada: revisa `RUTA_PROB` en `poc_psico/guardrail.py` con `scripts/spike_guardrail.py`. Si no se resuelve, usa el plan B (`guardrail_llm`) en la celda 3.1. |
| `No se pudo conectar al MCP CIE-11` | Comprueba `AGENT_MCP_URL`. Si el servicio de Azure estaba inactivo, la primera conexión puede tardar o fallar: reintenta. |
| El agente no llama a las tools o responde con errores de formato | El modelo gratuito puede fallar en tool calling y ser lento. En la celda 1.1 usa `anthropic/claude-haiku-5.5` (el predeterminado del notebook) o cambia `MODEL_ID`, `base_url` y la clave por `gpt-4.1-mini` y `OPENAI_API_KEY`, y anótalo en la celda 6. |
| `El agente alcanzó el tope de N pasos` | El agente ve en cada turno cuántas rondas lleva y cuántas le quedan, y al agotarse se le quitan las tools; si aun así llega al tope, sube `MAX_RONDAS` en la celda 2.1 o simplifica las tools permitidas. |
| `No se identificaron síntomas en el texto` | La viñeta no describe síntomas; el flujo se detiene a propósito. |
| `No se pudo conectar con Ollama` o `Ollama no tiene el modelo` | Arranca `ollama serve` o abre la app, y ejecuta `ollama pull qwen2.5vl:3b`. |
| El equipo se pone lento durante el OCR | Cierra otras aplicaciones; el modelo necesita unos 4 GB libres. Si falla de nuevo, reduce `LADO_MAXIMO` en `poc_psico/ocr.py`. |
| La entrada es una foto, pero no hay un componente OCR | `Componentes` no recibió `ocr=`: en el notebook se arma en la celda 3.1. |
| `OpenRouter respondió 400 ... rate limited` en el OCR | El motor de parseo de Mistral está saturado; el nodo ya reintentó 3 veces. Espera un minuto y repite. |
| Tras editar un `.py` no cambia nada | Reinicia la sesión o el kernel. |
