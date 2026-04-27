# ARCHITECTURE.md — Diseño del pipeline LUCA

## Visión general

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  L1 Ingest   │──▶│  L2 Parser   │──▶│ L3 Structured│──▶│L4 Qualitative│
│  (EDGAR/PDF) │   │ (segmentador)│   │ (XBRL, sin   │   │  (LLM)       │
│              │   │              │   │   LLM)       │   │              │
└──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
                                             │                   │
                                             ▼                   ▼
                                      ┌──────────────────────────────┐
                                      │      L5 Analyst              │
                                      │  (derived metrics, risk      │
                                      │   classification, sentiment) │
                                      └──────────────────────────────┘
                                                   │
                              ┌────────────────────┼──────────────────┐
                              ▼                    ▼                  ▼
                       ┌─────────────┐      ┌─────────────┐    ┌─────────────┐
                       │ L6 Compar.  │      │  L7 Writer  │    │ L8 Explainer│
                       │ (opcional)  │      │    (memo)   │    │ (xlsx + md) │
                       └─────────────┘      └─────────────┘    └─────────────┘
```

## Agentes del pipeline

### L1 — Ingestion (`agents/agent1_ingestion.py`)

**Input:** ticker (ej. "AAPL") o CIK + filing_type (10-K, 10-Q) + fecha opcional.
**Proceso:** consulta SEC EDGAR API, descarga el filing más reciente en HTML y los datos XBRL asociados (companyfacts).
**Output:** dict con `{company, ticker, cik, filing_date, html_content, xbrl_data, source_urls}`.
**Sin LLM.**
**Tests:** mock de requests.get, verificar manejo de 429, CIK padding, User-Agent presente.

### L2 — Parser (`agents/agent2_parser.py`)

**Input:** output de L1.
**Proceso:** segmenta el HTML en items del 10-K (Item 1 Business, Item 1A Risk Factors, Item 7 MD&A, Item 8 Financial Statements). Para PDF (CNMV), extrae texto por secciones detectadas heurísticamente.
**Output:** dict con `{item_1, item_1a, item_7, item_8, raw_tables}`.
**Sin LLM.**
**Tests:** parsing de 10-Ks sample (Apple, Microsoft), verificar que cada item aparece.

### L3 — Structured Extractor (`agents/agent3_extractor.py`)

**Input:** `xbrl_data` de L1.
**Proceso:** mapea tags US-GAAP a métricas estándar. Extrae:
- Revenue (`us-gaap:Revenues`, `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`)
- Net Income (`us-gaap:NetIncomeLoss`)
- Total Assets, Total Liabilities, Total Equity
- Operating Income, EBITDA (derivado: OpIncome + D&A)
- Cash, Debt (long-term + short-term)
- EPS, Shares Outstanding
**Output:** dict con métricas numéricas por período (FY y trimestres).
**Sin LLM. 100% determinista.**
**Tests:** fixtures de companyfacts JSON, verificar mapping correcto, manejo de tags alternativos.

### L4 — Qualitative Extractor (`agents/agent4_qualitative.py`)

**Input:** secciones de texto de L2 (Item 1A, Item 7).
**Proceso:** LLM (Qwen) extrae:
- Top 5-10 riesgos mencionados en Item 1A (con cita literal corta)
- Forward-looking statements y guidance en Item 7
- Management tone (cauto/optimista/neutral)
**Output:** JSON estructurado con `{risks: [...], guidance: [...], tone: str}`.
**Con LLM local. Un prompt por sección, chunking si excede ventana.**
**Tests:** mocks de respuesta Ollama, verificar parsing de JSON de salida, edge cases.

### L5 — Analyst (`agents/agent5_analyst.py`)

**Input:** outputs de L3 y L4.
**Proceso:** computa métricas derivadas (gross margin, operating margin, net margin, ROA, ROE, debt-to-equity, YoY growth). Clasifica riesgos por categoría (operational, financial, regulatory, market, tech). Asigna sentiment score al guidance.
**Output:** dict con análisis completo.
**Sin LLM en métricas derivadas. LLM opcional para clasificación de riesgos (si se quiere más fino).**
**Tests:** cálculos matemáticos con fixtures, verificar división por cero, clasificación de riesgos.

### L6 — Comparables (`agents/agent6_comparables.py`) — *opcional*

**Input:** 2+ outputs de L5.
**Proceso:** alinea métricas entre empresas, calcula deltas, ranking por métrica.
**Output:** tabla comparable + narrativa breve.
**Con LLM para la narrativa.**
**Tests:** cálculos de deltas, manejo de empresas de sectores distintos (warning).

### L7 — Writer (`agents/agent7_writer.py`)

**Input:** output de L5 (y opcionalmente L6).
**Proceso:** genera investment memo en Markdown con secciones:
1. Executive Summary
2. Company Overview
3. Financial Highlights (tabla + comentario)
4. Risk Analysis
5. Outlook & Guidance
6. Appendix (raw metrics)
**Output:** `outputs/memos/<ticker>_<date>.md`.
**Con LLM. Temperature 0.3 para secciones factuales, 0.5 para Outlook.**
**Tests:** mocks de LLM, verificar estructura del markdown, secciones presentes.

### L8 — Explainer (`agents/agent8_explainer.py`)

**Input:** todo el estado del pipeline.
**Proceso:** genera `<ticker>_raw.xlsx` con todas las métricas y trazas de cada agente (inspirado en A9 de SAM). Genera `explainability.md` en español explicando las decisiones del pipeline.
**Output:** Excel + Markdown.
**Sin LLM (plantilla + datos). Opcional: LLM para narrativa de explainability.**
**Tests:** schema del Excel, secciones del markdown, caracteres especiales.

## Decisiones de diseño

### ¿Por qué híbrido XBRL + LLM?

Porque los 10-Ks de SEC EDGAR vienen con datos XBRL (eXtensible Business Reporting Language) taggeados. Extraer "revenue" de XBRL es un `dict lookup`, no necesita LLM. Esto da **precisión perfecta en números** y **deja el LLM solo para lo que no está estructurado** (riesgos en texto libre, guidance). Consecuencias:

- Ahorro masivo de VRAM: el LLM procesa chunks cortos, no 10-Ks enteros.
- Precision/recall numérica ≈ 100% (limitada solo por mapping de tags).
- Permite correr todo en RTX 4060.

### ¿Por qué Qwen 2.5 7B y no un modelo más grande?

Restricción dura: 8GB de VRAM. Qwen 2.5 7B Q4_K_M ocupa ~4.7GB, deja margen. Es SOTA open-source para su tamaño, especialmente en español e inglés. Para tareas de extracción estructurada desde texto ya segmentado, 7B es suficiente.

### ¿Por qué Ollama y no llama-cpp directo?

Ollama expone una API HTTP local, simplifica mocking en tests y permite cambiar de modelo con un solo comando. Coste: una capa de abstracción extra, pero merece la pena.

### ¿Por qué 10-Ks y no earnings calls?

Estructura predecible (items 1-15 fijados por la SEC), formato estándar (HTML + XBRL), acceso libre. Earnings calls serían línea futura.

## Flujo de datos

```
ticker = "AAPL"
    │
    ▼
L1 ─▶ {html, xbrl, meta}
    │
    ▼
L2 ─▶ {item_1a_text, item_7_text, item_8_tables}
    │
    ├─▶ L3 (xbrl) ─▶ {revenue: [...], ebitda: [...], ...}
    │
    └─▶ L4 (text) ─▶ {risks: [...], guidance: [...], tone: "..."}
                         │
                         ▼
                    L5 ─▶ {metrics_derived, risk_categories, sentiment}
                         │
                         ├─▶ L7 ─▶ memo.md
                         │
                         └─▶ L8 ─▶ raw.xlsx + explainability.md
```

## Dependencias externas

- **SEC EDGAR**: `https://data.sec.gov/api/xbrl/companyfacts/CIK<10-digit-CIK>.json` y `https://www.sec.gov/cgi-bin/browse-edgar`. Gratis, exige User-Agent, rate limit 10 req/s.
- **Ollama**: servidor local en `http://localhost:11434`.
- **CNMV** (opcional): sin API pública, scraping manual o descarga previa.
