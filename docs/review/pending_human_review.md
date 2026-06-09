# Cola de revisión humana — outputs de Qwen (modo auto)

> Generado por la sesión E2E del 2026-06-09. El pipeline siguió construyendo
> (L7 demo) sobre estos outputs, pero **ninguna afirmación cualitativa derivada
> de ellos entra al paper sin que el usuario la revise**: en el LaTeX van
> marcadas con `% TODO(human)`. Las cifras deterministas (L3, márgenes, ratios,
> YoY) NO requieren revisión.

## Qué hay que revisar y por qué

### 1. Riesgos crudos de L4 (`outputs/intermediate/{TICKER}_L4.json`)

| Ticker | Riesgos | Chunks | Chunks con riesgos | Notas |
|---|---|---|---|---|
| AAPL | 87 | 33 | 27 | 8 flags `literal_quote not verbatim` |
| JPM | 105 | 57 | 52 | 2 chunks con JSON inválido (descartados); 7 flags `not verbatim` |

Revisar: que los riesgos sean reales y no alucinados, que `summary` (español)
sea fiel al `literal_quote`, y que no haya duplicados por solape de sub-chunks.

**Conteo VALIDADO contra los filings (2026-06-09).** Resuelto por revisión humana
(ver `docs/review/l4_risk_audit.md`, `AAPL_subheaders.txt`, `JPM_subheaders.txt`):

- **AAPL FY2025:** **27 factores reales** (27 encabezados negrita L2; las 5
  categorías salen aisladas con 0 riesgos; sin Risk Factor Summary). 68
  sub-aspectos crudos → fragmentación ~2.5×. El extractor cubrió **26 de 27**
  (1A_021 legal proceedings = 0 riesgos, limitación del extractor). *"26" es
  cobertura del extractor, NO el nº de factores.* Los tres números se mantienen
  separados en el memo.
- **JPM FY2026:** **43 factores reales** (los 43 chunks `in_summary=false`, L2,
  1A_015–1A_057). El 52 del audit estaba inflado por (a) 13 chunks del Risk
  Factor Summary contados como factores y (b) fragmentación dentro del summary
  (bullet "Operational" → 6 sub-riesgos). ~16 riesgos del summary duplican body.

Reincorporado: el memo de AAPL lleva la frase validada (determinista, vía
`risk_factor_note` en L7, no del LLM); el paper documenta los **dos modos de
inflado** (fragmentación en todos; contaminación summary↔body solo con Risk
Factor Summary) y los requisitos de la capa de dedup de future work.

### 2. Clasificación de riesgos de L5 (`outputs/intermediate/{TICKER}_L5.json`)

Datos crudos para auditar: `docs/review/L5_classification_{AAPL,JPM}.txt` (todos),
`L5_unclassified_{AAPL,JPM}.txt` (los null con quote completa),
`L5_by_category_{technological,operational}.txt` (por categoría, summary completa).

| Ticker | Sin clasificar | Distribución por categoría |
|---|---|---|
| AAPL | 4 / 68 | operational 15, regulatory 13, financial 13, market 10, technological 10, geopolitical 3 |
| JPM | 10 / 105 | regulatory 27, operational 22, market 15, technological 12, financial 11, geopolitical 8 |

**Mecanismo:** clasificación por riesgo individual; Qwen ve solo `{id, title, summary}`
(no el subheader ni `source_chunk_id`), devuelve `{id, category}`, sin score. Lotes de
20 (un único lote de ~100 dejaba 78 sin clasificar). `null` = el LLM no devolvió
categoría válida para ese id.

**Diagnóstico de los 14 null (validado con reintento aislado batch=1, 2026-06-09):**

- **AAPL (4): omisión-en-lote, NO inclasificables.** `R-AAPL-016/017/020/024`. Al
  reintentarlas solas salen 016/017/020 → operational y 024 → financial. Es el LLM
  omitiendo ids del JSON del lote.
- **JPM (10) = 5 gap de cobertura del config + 5 relacionados con financial:**
  - **Gap de vocabulario (reputación):** `R-JPM-015/079/093/094/096`. "reputation"
    (y "conduct") son categorías de primer nivel del filing que **las 6 del config no
    cubren** (operational/financial/regulatory/market/technological/geopolitical).
    Null honesto, no forzar. **Doble causa en `-079`/`-094`/`-096`:** además del gap,
    son sub-trozos fragmentados de `1A_053` (reputación), sin contexto propio.
  - **Mapeos financieros — NO es gap, es el mismo bug de omisión-en-lote:**
    `R-JPM-004` (credit), `-005` (liquidity), `-006` (capital), `-048` (default de
    contrapartes), `-059` (downgrade). "financial" SÍ está en las 6. Reintento aislado:
    `-048` y `-059` (body real, `1A_029`/`1A_034`) salen **financial** → el clasificador
    SÍ mapea credit/downgrade→financial cuando no se omite en el lote. `-004/005/006`
    vienen del bloque summary (`in_summary=True`) → se descartarían por la dedup de
    future work de todos modos.

**Implicación:** la mayoría de los null no son "el 7B no sabe clasificar" sino
**inestabilidad de la salida JSON en lote** (recuperable bajando el batch o con
reintento). La excepción real es el **gap de cobertura** (reputation/conduct), que no
se arregla con reintentos.

**DECISIÓN DE METODOLOGÍA PENDIENTE (del usuario):** ampliar el config con `reputation`
y `conduct` como categorías, **vs** documentar el gap y dejar esos riesgos sin
categoría. NO tocar nada (ni config, ni reintegrar los reintentos a los JSON) hasta
que el usuario decida. Los reintentos batch=1 fueron solo diagnósticos; no se
escribieron en `{TICKER}_L5.json`.

## Los 4 puntos de cuidado (notas del plan)

1. **`literal_quote` best-effort.** Qwen a veces parafrasea o añade puntos
   suspensivos; cuando la cita no es subcadena literal del chunk se marca con un
   warning en `meta.warnings` (no se descarta el riesgo). Hacer spot-check de una
   muestra antes de citar literales en el paper.
2. **Casi-duplicados en JPM por solape de sub-chunks.** Los chunks grandes se
   parten con solape de 500 chars; un mismo riesgo puede aparecer en dos
   `1A_NNN` adyacentes con ids distintos. Revisar antes de contar riesgos.
3. **`model.seed` no determinista.** El contrato L4 registra `seed=42` pero
   `LLMClient.chat` NO pasa el seed a Ollama → los riesgos/clasificación no son
   reproducibles bit a bit entre runs. Mencionar en reproducibilidad del paper
   (o extender `LLMClient.chat` para pasar `seed`, tarea aparte).
4. **Vocabulario de categorías: 6 del config, no 5 del prompt.** Se usan las 6
   de `config/agents.json::L5_analyst.risk_categories`
   (`operational/financial/regulatory/market/technological/geopolitical`). El
   prompt original de la sesión listaba 5 (`tech` en vez de `technological`, sin
   `geopolitical`). Por decisión del usuario manda el config; se anota aquí. Si
   se quiere alinear el doc `L4_schema.md` (que menciona 5), reconciliar antes de
   escribir un `L5_schema.md` formal.

## Estado del pipeline (para contexto)

- L1, L2, L3: implementados y evaluados (Sprint 1). L3 = 100% (ver
  `docs/eval/results_real.md`).
- L4-mínimo (solo riesgos), L5 (derivadas + clasificación), L7 (memo AAPL):
  implementados esta sesión. Forward-looking, management tone, L6, L8 y las
  métricas cash/long_term_debt quedan como future work.
- Memo demo: `outputs/memos/AAPL_2025-10-31.md`.
