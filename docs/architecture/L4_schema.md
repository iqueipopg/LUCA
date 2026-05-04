# L4 Output Schema

**Versión:** 1.0
**Agente:** `agents/agent4_qualitative.py`
**Estado:** aprobado para Sprint 2 (2026-05-04)
**Consumidores downstream:** L5 (Analyst), L7 (Writer), L8 (Explainer)

---

## Propósito

L4 extrae contenido cualitativo de los Items 1A (Risk Factors) y 7 (MD&A) de un 10-K.
Este documento fija el contrato del output JSON.
Cualquier cambio breaking aquí requiere bump de `schema_version` y migration plan.

---

## Output principal

L4 escribe un único archivo `outputs/intermediate/{TICKER}_L4.json` con esta estructura:

```json
{
  "schema_version": "1.0",
  "agent": "L4",
  "ticker": "AAPL",
  "filing_accession": "0000320193-25-000123",
  "filing_date": "2025-11-02",
  "extracted_at": "2026-05-04T15:23:00Z",
  "model": {
    "name": "qwen2.5:7b-instruct-q4_K_M",
    "temperature": 0.1,
    "seed": 42
  },
  "chunks": [
    {
      "chunk_id": "1A_001",
      "item": "1A",
      "offset_start": 0,
      "offset_end": 8412,
      "subheader": "Macroeconomic and geopolitical conditions"
    }
  ],
  "risks": [
    {
      "id": "R-AAPL-001",
      "title": "Macroeconomic and geopolitical conditions",
      "summary": "Global economic slowdowns and geopolitical tensions may reduce consumer demand for the Company's products.",
      "literal_quote": "A significant portion of the Company's net sales is generated outside of the United States...",
      "source_chunk_id": "1A_001"
    }
  ],
  "forward_looking": [
    {
      "id": "FL-AAPL-001",
      "text": "The Company expects gross margin to improve modestly in fiscal 2026 driven by Services mix.",
      "time_horizon": "next_fy",
      "hedge_strength": "medium",
      "source_chunk_id": "7_003"
    }
  ],
  "management_tone": {
    "score": 4,
    "label": "cautiously_optimistic",
    "rationale": "Tono predominantemente positivo en perspectivas de Services y márgenes, con menciones explícitas de incertidumbre en hardware sales y FX.",
    "evidence_quotes": [
      {"text": "We are confident in our ability to...", "source_chunk_id": "7_001"},
      {"text": "However, foreign exchange volatility may continue to pressure...", "source_chunk_id": "7_005"}
    ]
  },
  "meta": {
    "chunks_processed": 8,
    "chunks_with_risks": 8,
    "total_input_tokens_estimated": 24500,
    "warnings": []
  }
}
```

---

## Top-level fields

| Campo | Tipo | Required | Descripción |
|-------|------|----------|-------------|
| `schema_version` | string | sí | "1.0" en Sprint 2. Bump en cambios breaking. |
| `agent` | string | sí | Constante "L4". |
| `ticker` | string | sí | Identifier del filing (uppercase). |
| `filing_accession` | string | sí | SEC accession number (formato `XXXXXXXXXX-XX-XXXXXX`). |
| `filing_date` | string | sí | ISO 8601 (YYYY-MM-DD). Mismo valor que en L1/L3. |
| `extracted_at` | string | sí | ISO 8601 UTC con sufijo `Z`. |
| `model` | object | sí | Metadata del modelo invocado: `name`, `temperature`, `seed`. |
| `chunks` | array | sí | Lista de chunks procesados (puede estar vacía si Items 1A y 7 ausentes). |
| `risks` | array | sí | Lista de `risk_item` (puede estar vacía). |
| `forward_looking` | array | sí | Lista de `forward_looking_statement` (puede estar vacía). |
| `management_tone` | object | sí | Siempre presente, con defaults documentados si Item 7 ausente. |
| `meta` | object | sí | Stats y warnings. |

---

## `chunk` schema

| Campo | Tipo | Required | Descripción |
|-------|------|----------|-------------|
| `chunk_id` | string | sí | Formato `{item}_{idx:03d}`. Ej: `"1A_001"`, `"7_003"`. |
| `item` | string | sí | `"1A"` \| `"7"` \| `"7A"` (extensible). |
| `offset_start` | int | sí | Offset relativo al inicio del item (no al documento completo). |
| `offset_end` | int | sí | Offset exclusivo. `text[offset_start:offset_end]` reproduce el chunk. |
| `subheader` | string | no | Primer header/bold detectado en el chunk. |

El texto literal de los chunks **no** se incluye en este JSON. Se persiste en `outputs/intermediate/{TICKER}_chunks.json` y L8 lo carga bajo demanda.

---

## `risk_item` schema

| Campo | Tipo | Required | Descripción |
|-------|------|----------|-------------|
| `id` | string | sí | Formato `R-{TICKER}-{idx:03d}`. Único dentro de `risks`. |
| `title` | string | sí | Frase corta generada por el LLM. Máx 100 chars. |
| `summary` | string | sí | Paráfrasis 2-3 frases en español, generada por el LLM. |
| `literal_quote` | string | sí | Cita verbatim del 10-K. Máx 300 chars. Ancla para trazabilidad L8. |
| `source_chunk_id` | string | sí | Debe existir en `chunks[]`. |

**No incluye** `category` (responsabilidad de L5) ni `severity` (fuera de Sprint 2).

Los tres campos textuales (`title`, `summary`, `literal_quote`) sirven a consumidores distintos:
- `title`: header en el Excel de L8 y subtítulo en el memo de L7.
- `summary`: cuerpo del memo (L7).
- `literal_quote`: trazabilidad fuerte (L8) sin necesidad de offsets exactos.

---

## `forward_looking_statement` schema

| Campo | Tipo | Required | Descripción |
|-------|------|----------|-------------|
| `id` | string | sí | Formato `FL-{TICKER}-{idx:03d}`. |
| `text` | string | sí | Texto del FLS (parafraseado o literal según el prompt). |
| `time_horizon` | enum | sí | Ver enums abajo. |
| `hedge_strength` | enum | sí | Ver enums abajo. |
| `source_chunk_id` | string | sí | Debe existir en `chunks[]`. |

### Enums

**`time_horizon`:**
- `current_quarter` — referencia explícita al trimestre en curso
- `next_fy` — siguiente año fiscal
- `medium_3_5y` — horizonte 3-5 años
- `long_term` — horizonte >5 años o "long-term"
- `unspecified` — sin horizonte temporal claro

**`hedge_strength`:**
- `none` — afirmación directa ("We will...")
- `low` — hedging débil ("We expect...", "We anticipate...")
- `medium` — hedging moderado ("We may...", "We plan to...")
- `high` — hedging fuerte ("Could potentially...", "May or may not...")

---

## `management_tone` schema

Siempre presente, incluso si Item 7 está vacío.

| Campo | Tipo | Required | Descripción |
|-------|------|----------|-------------|
| `score` | int | sí | 1-5, donde 1=negative y 5=optimistic. |
| `label` | enum | sí | Ver enum abajo. |
| `rationale` | string | sí | Justificación 1-3 frases en español. |
| `evidence_quotes` | array | sí | 0-5 items, cada uno `{text, source_chunk_id}`. |

**`label` enum** (mapping a score):
- `negative` (1)
- `cautious` (2)
- `neutral` (3)
- `cautiously_optimistic` (4)
- `optimistic` (5)

**Defaults si Item 7 no existe:**
```json
{
  "score": 3,
  "label": "neutral",
  "rationale": "Item 7 not available in filing.",
  "evidence_quotes": []
}
```
Y `meta.warnings += ["Item 7 not found or empty"]`.

---

## `meta` schema

| Campo | Tipo | Required | Descripción |
|-------|------|----------|-------------|
| `chunks_processed` | int | sí | Total de chunks invocados al LLM. |
| `chunks_with_risks` | int | sí | Chunks que produjeron al menos 1 riesgo. Métrica para el paper. |
| `total_input_tokens_estimated` | int | sí | Suma de tokens de input estimados (tiktoken o equivalente). |
| `warnings` | array of strings | sí | Lista de warnings (puede estar vacía). |

---

## Invariantes

1. Todo `source_chunk_id` referenciado en `risks`, `forward_looking` o `management_tone.evidence_quotes` **debe** existir en `chunks[]`.
2. Todos los `id` deben ser únicos dentro de su lista.
3. `extracted_at` debe terminar en `Z` (UTC).
4. `model.name` debe coincidir con el valor de `config.yaml -> llm.model`.
5. `score` y `label` en `management_tone` deben ser consistentes según el mapping del enum.

---

## Política de límites suaves

**Riesgos:**
- Si `len(risks) > 30`: append a `meta.warnings`: `"Risk count exceeds threshold (30): {count} risks extracted"`. **No se trunca.**
- Si `len(risks) == 0` y Item 1A existe: append `"Item 1A processed but zero risks extracted"` (señal de fallo del LLM).

**Item 1A ausente o vacío:**
- `risks`: `[]`
- `chunks` no contiene chunks `1A_*`
- `meta.warnings += ["Item 1A not found or empty"]`

**Item 7 ausente o vacío:**
- `forward_looking`: `[]`
- `management_tone`: defaults documentados arriba
- `chunks` no contiene chunks `7_*`
- `meta.warnings += ["Item 7 not found or empty"]`

---

## Decisiones de scope (Sprint 2)

**Severity de riesgos: fuera.** No incluida en L4 ni en L5. Decisión tomada el 2026-05-04 por carga de scope y ausencia de rúbrica clara. Re-evaluable si L7 (Sprint 3) requiere priorización.

**Categoría de riesgos: en L5.** L4 no clasifica. L5 toma `{TICKER}_L4.json` y emite `{TICKER}_L5.json` con campo `category` añadido a cada `risk_item`. Las cinco categorías canónicas (`operational` | `financial` | `regulatory` | `market` | `tech`) se documentarán en `docs/architecture/L5_schema.md`.

**Cross-references entre riesgos: fuera.** Sprint 4 candidate.

**Hedge_strength como enum, no float.** Más robusto contra variabilidad del LLM.

---

## Versionado

Cualquier cambio breaking requiere:
1. Bump de `schema_version` (1.0 → 1.1 para additive, 1.0 → 2.0 para breaking).
2. Migration script en `scripts/migrate_l4_schema.py`.
3. Re-run de L4 sobre todo el gold standard.

Cambios additive (nuevos campos opcionales) mantienen 1.0.x.

---

## Validación

L4 valida su propio output contra este schema antes de escribir, usando Pydantic models en el módulo de schemas del repo (convención: `agents/_schemas.py` o equivalente). Output inválido → exception, no escritura. Tests en `tests/test_l4_schema.py`.
