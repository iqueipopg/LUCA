# T2.2 — Item 1A Chunker Spec

**Tarea:** T2.2 (Sprint 2, L4 Qualitative)
**Status:** contrato pre-implementación
**Inputs informantes:** `docs/exploration/item1a_structure_scouting.md` (scouting AAPL / JPM / WMT, 2026-05-05)

## Objetivo

Particionar el texto del Item 1A de un 10-K (Inline XBRL) en chunks consumibles por L4 (extracción cualitativa con Qwen 7B, ventana 8K). El chunker es un componente **puramente estructural**: no extrae riesgos, solo prepara los bloques de texto y su metadata.

## Inputs / Outputs

**Input:** HTML iXBRL del 10-K + offsets del bloque Item 1A (`item1a_start`, `item1a_end`), ya disponibles del scaffolding de S1.

**Output:** `Item1AChunkSet` (Pydantic v2):

```python
class Chunk(BaseModel):
    chunk_id: str            # ej. "AAPL_2024_item1a_007"
    text: str                # contenido del chunk, sin tags
    char_start: int          # offset absoluto en el HTML del 10-K
    char_end: int
    anchor_text: str | None  # sub-header bold que abre el chunk (None si fallback por longitud)
    anchor_level: int        # 1 = category label, 2 = full-sentence header, 3 = sub-chunk por longitud
    in_summary: bool         # True si pertenece al Risk Factor Summary
    token_estimate: int      # chars/4

class Item1AChunkSet(BaseModel):
    ticker: str
    fiscal_year: int
    item1a_token_estimate: int
    summary_present: bool
    summary_chunks: list[Chunk]   # bullets pre-clasificados del Summary (solo JPM-like)
    body_chunks: list[Chunk]      # cuerpo principal post-Summary
    warnings: list[str]           # avisos no fatales (ej. ningún sub-header detectado)
```

## Detección de sub-headers

### Criterio principal (bold-leading)

Un sub-header es el primer leaf de texto de un `<div>` cuyo span padre tiene `font-weight ≥ 600` (incluye `bold`, `700`, `800`, `900`).

### Cotas de longitud (recalibradas vs scouting)

- **Mínimo: ≥ 2 palabras.** Recupera category labels como "Strategic Risks", "Financial Risks" que la cota anterior (≥3 palabras) rechazaba. FPs de 1 palabra ("Summary", "Political", etc.) se descartan por reglas anti-FP separadas.
- **Máximo: ≤ 300 chars.** Recupera las frases-cabecera largas que dominan en WMT (la mayoría caen en 130–200 chars). Por encima de 300 chars ya no es un sub-header sino un párrafo de cuerpo.

Justificación cuantitativa: con cotas ≥3 / ≤120 (spec original del scouting) WMT detecta solo 2 anchors sobre un Item 1A de 23K tokens. Con cotas ≥2 / ≤300, WMT recupera ~25 anchors reales.

### Niveles de anchor

- `anchor_level = 1` si el texto del sub-header tiene ≤ 4 palabras → category label (tipo "Strategic Risks").
- `anchor_level = 2` si tiene > 4 palabras → frase-cabecera de riesgo individual.

Esta distinción es informativa (permite reportar la estructura jerárquica detectada en el paper) pero **no cambia el chunking** — todos los anchors generan chunks por igual.

## Aislamiento del Risk Factor Summary

### Detección

Dentro de los primeros 5 000 chars del Item 1A:

1. Localizar el primer sub-header con texto de ≤ 2 palabras.
2. Localizar el primer sub-header de `anchor_level ≥ 2` que aparece
   después de ese punto. Llámalo `next_l2_anchor`. Si no existe (no
   observado en los 3 fixtures, defensivo), usar
   `item1a_start + 10000` como bound.
3. En el rango `[short_header_end, next_l2_anchor]`, contar
   caracteres `•`. Si hay ≥ 3 bullets, marcar
   `summary_start = offset del sub-header corto`.
4. Si no se cumple, no hay Summary.

**Nota de calibración:** una versión anterior de este spec usaba una
ventana fija de 500 chars para contar bullets. Esto fallaba en JPM,
cuyos bullets miden 300–1000 chars cada uno, de modo que solo 1
bullet cabía en la ventana. La detección por rango hasta el siguiente
anchor L2 es robusta a la longitud variable de los bullets sin
introducir FPs en AAPL/WMT (que no tienen `•` en Item 1A → bullet
count = 0).

### Fin del Summary

`summary_end` = el primer sub-header bold de `anchor_level ≥ 2` (frase-cabecera) que aparece **después** del último bullet `•` en el rango candidato.

### Procesamiento

- Cada bullet del Summary genera un `Chunk` independiente en `summary_chunks` (`anchor_text` = etiqueta-categoría del bullet, ej. "Political", "Credit"; `in_summary = True`; `anchor_level = 1`).
- El cuerpo principal se procesa sobre el rango `[summary_end, item1a_end]`, **NO** sobre `[item1a_start, item1a_end]`. Esto elimina los FPs de bullet-labels del Summary apareciendo como sub-headers fantasma.
- Si no hay Summary detectado, `summary_chunks = []` y el cuerpo se procesa sobre todo el Item 1A.

## Construcción de chunks del cuerpo

1. Localizar todos los sub-headers en el rango del cuerpo (detector + cotas + anti-FP).
2. Cada chunk = `[anchor_i, anchor_{i+1})`. El último llega hasta `item1a_end`.
3. **Fallback por longitud** si un chunk excede 4 000 tokens (16 000 chars):
   - Cortar en límite de párrafo (`<div>` boundary) más cercano a múltiplos de ~12 000 chars.
   - Overlap de ~500 chars entre sub-chunks para preservar contexto.
   - Sub-chunks resultantes: `anchor_text = None`, `anchor_level = 3`, `chunk_id` con sufijo (`_001a`, `_001b`, ...).
4. **Garantía dura:** ningún chunk con `token_estimate > 4 000`. Si tras sub-chunking por párrafo algún chunk sigue grande (improbable), forzar corte a `chars = 16 000` y añadir warning al `Item1AChunkSet`.

### Cota de 4K (no 6K)

Qwen 7B ventana 8K → reservar ~2K para system prompt + few-shot examples, ~1.5K para output JSON, ~0.5K de margen. Quedan ~4K para el chunk. Conservador a propósito: es más simple debuggear chunks pequeños que arreglar respuestas truncadas.

## Filtros anti-FP

Aplicados tras detección bold-leading, antes de construir chunks:

1. **Numéricos puros / numeración de página:** descartar si el texto del anchor matchea `^\d+$`, `^Page \d+$`, o `^Part [IVX]+( and [IVX]+)?$`. Captura los "31", "Parts I and II" observados como FPs en JPM.
2. **Repetición a través del filing:** si el mismo texto-anchor aparece ≥ 3 veces en el documento completo (no solo en Item 1A), descartar como header de página repetido.
3. **Bold de 1 palabra:** descartar como sub-header (no entra ni en nivel 1 ni en nivel 2). Combinado con el aislamiento del Summary, esto elimina los bullet-labels del Summary como FPs en el caso de que el aislamiento falle.

## Evaluación

Manual y ligera. No hace falta framework elaborado.

- **Gold standard:** sobre AAPL / JPM / WMT (los 3 ya scoutados en `docs/exploration/`), construir manualmente la lista de sub-headers correctos eyeballeando el PDF del 10-K en EDGAR. Esfuerzo: 1–2h total. Output: `data/gold_chunker_anchors.json`.
- **Métricas reportables en el paper:**
  - Anchor **precision / recall** vs gold por ticker.
  - **Max chunk size** observado (token_estimate y char count).
  - **% de Item 1A cubierto** por chunks. Debería ser 100%; <100% indica bug en construcción de rangos.
- Sin gold de chunks per se, solo de anchors. La frontera de chunks deriva determinísticamente de anchors + reglas de fallback, así que no aporta evaluarla por separado.

## Limitaciones conocidas

Documentar en el paper, no esconder:

1. El chunker depende casi enteramente de bold-leading via `font-weight ≥ 600`. En filers con bold inconsistente (no observado en AAPL/JPM/WMT pero plausible en small-caps o filings antiguos), el recall caería.
2. Las cotas (≥2 palabras, ≤300 chars) están calibradas sobre 3 tickers de sectores distintos (tech / banking / retail). Generalización a un corpus mayor no testeada — mencionar como future work.
3. El fallback por longitud es agnóstico al contenido: si parte un riesgo a la mitad, L4 recibe dos chunks parciales del mismo riesgo. Aceptable porque las métricas downstream (tone, categoría) son por-chunk y agregables, pero introduce ruido.
4. La detección del Summary es estructural y puede fallar si un filer pone `•` por motivos no-Summary en los primeros 5K chars. No observado en AAPL/JPM/WMT.

## Plan de implementación (para CC)

Una sola pasada autocontenida, 4 archivos:

- `agents/agent4_qualitative/chunker.py` — lógica del chunker.
- `agents/agent4_qualitative/models.py` — Pydantic `Chunk` y `Item1AChunkSet`.
- `tests/agent4_qualitative/test_chunker.py` — tests unitarios + fixtures de AAPL/JPM/WMT (ya en `data/cache/`).
- `scripts/eval_chunker.py` — eval ligera contra `data/gold_chunker_anchors.json`.

**Criterio de cierre:**
- Tests passing.
- Eval reportando precision/recall por ticker.
- Cero chunks con `token_estimate > 4 000` en los 3 fixtures.
- `summary_chunks` no vacío para JPM; vacío para AAPL y WMT.