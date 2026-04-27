# SPRINT_PLAN.md — Roadmap de LUCA

AI Lab = 180h máximas según la guía docente. Dividido en 5 sprints de ~2 semanas cada uno. Dejamos holgura al final para el paper y la defensa.

## Sprint 0 — Scaffold operativo (10-15h)

**Objetivo:** que un `pipeline --ticker AAPL` pase por L1→L2 y devuelva un dict sin errores. Nada inteligente, solo plumbing.

Tareas:
- **T0.1** Estructura de directorios: `agents/`, `tests/`, `outputs/`, `experiments/`, `config/`.
- **T0.2** `config.yaml` con rutas, modelo, endpoints, timeouts. Decido yo los valores.
- **T0.3** `config/agents.json` con config por-agente (temperatura, max_tokens, max_input_chars).
- **T0.4** Logger centralizado en `agents/_logging.py`.
- **T0.5** Cliente Ollama en `agents/_llm_client.py` con retry, timeout y mockeable en tests.
- **T0.6** `agents/agent1_ingestion.py` — stub que descarga 10-K + companyfacts de EDGAR.
- **T0.7** `agents/agent2_parser.py` — stub que segmenta HTML en items.
- **T0.8** Tests unitarios para T0.5, T0.6, T0.7 con mocks.
- **T0.9** Script CLI `run_pipeline.py` que encadena L1→L2 y printea el dict.

Criterio de cierre: correr `python run_pipeline.py --ticker AAPL` sin excepciones.

## Sprint 1 — L3 Structured Extractor + gold standard (20-25h)

**Objetivo:** métricas numéricas extraídas con precisión perfecta desde XBRL, evaluadas contra gold standard.

Tareas:
- **T1.1** Mapping US-GAAP → métricas estándar en `agents/agent3_extractor.py`. Empezar por 6 métricas: revenue, net income, total assets, total equity, operating income, EPS.
- **T1.2** Manejo de tags alternativos (ej. Revenues vs RevenueFromContractWithCustomer).
- **T1.3** Extracción por período (FY vs quarterly), currency handling.
- **T1.4** Tests extensivos con fixtures reales (companyfacts de Apple, Microsoft, JPMorgan).
- **T1.5** Script `scripts/annotate_gold_standard.py` — yo meto los números a mano para 10-15 empresas. Genera `data/gold_standard.json`.
- **T1.6** `experiments/eval_extraction.py` — corre L3 contra gold_standard, reporta precision/recall por métrica.

Criterio de cierre: ≥95% accuracy en las 6 métricas para las 10-15 empresas del gold standard.

## Sprint 2 — L4 Qualitative + L5 Analyst (25-30h)

**Objetivo:** extracción cualitativa funcional y análisis derivado.

Tareas:
- **T2.1** Prompts de Qwen para extracción de riesgos en `agents/agent4_qualitative.py`. Diseñar output JSON estructurado.
- **T2.2** Chunking de Item 1A si excede ventana de contexto (8K tokens por defecto).
- **T2.3** Extracción de forward-looking statements en Item 7.
- **T2.4** Management tone analysis (prompt sencillo con escala 1-5).
- **T2.5** `agents/agent5_analyst.py` — métricas derivadas (márgenes, ratios, YoY).
- **T2.6** Clasificación de riesgos por categoría (operational / financial / regulatory / market / tech).
- **T2.7** Tests con mocks de Ollama, fixtures de texto real.

Criterio de cierre: para AAPL 10-K 2023, extraer ≥5 riesgos coherentes, calcular márgenes y YoY sin errores matemáticos.

## Sprint 3 — L7 Writer + L8 Explainer (25-30h)

**Objetivo:** memo final + trazabilidad.

Tareas:
- **T3.1** Plantilla de memo en `agents/agent7_writer.py` con 6 secciones.
- **T3.2** Prompts por sección, con temperaturas calibradas.
- **T3.3** `agents/agent8_explainer.py` — Excel de 20+ columnas con trazas.
- **T3.4** `explainability.md` en español, generado desde templates.
- **T3.5** Integración E2E: `run_pipeline.py` completo de L1 a L8.
- **T3.6** Tests de smoke E2E con mocks.

Criterio de cierre: `python run_pipeline.py --ticker AAPL` genera `outputs/memos/AAPL.md`, `outputs/AAPL_raw.xlsx` y `outputs/AAPL_explainability.md`.

## Sprint 4 — Experimentos + paper + defensa (40-50h)

**Objetivo:** contenido para el paper y la defensa.

Tareas:
- **T4.1** Experimento 1: evaluación contra gold standard (L3 precision/recall).
- **T4.2** Experimento 2: comparación de calidad entre HTML (10-K) y PDF (CNMV). Esta es la pregunta de investigación complementaria.
- **T4.3** Experimento 3: ablation study — pipeline con y sin L3 (solo LLM vs híbrido).
- **T4.4** Figuras del paper (matplotlib): accuracy por métrica, comparativa de formatos, latencia por agente.
- **T4.5** Escribir paper en LaTeX. Estructura: intro, related work, architecture, experiments, discussion, conclusion.
- **T4.6** Preparar slides para defensa (Beamer o PowerPoint).

Criterio de cierre: paper en PDF + slides + demo funcional.

## Sprint 5 (buffer, 20-30h)

Reservado para imprevistos, refinamiento, feedback de David.

## Tareas fuera de scope (para después del AI Lab)

- Integración con Streamlit UI.
- Soporte de CNMV más robusto (PDFs con tablas complejas).
- L6 Comparables si queda tiempo en Sprint 5.
- Earnings calls como fuente adicional.
- Valoración DCF automatizada.

## Contabilidad de horas (estimación)

| Sprint | Horas | Acumulado |
|--------|-------|-----------|
| 0 | 15 | 15 |
| 1 | 25 | 40 |
| 2 | 30 | 70 |
| 3 | 30 | 100 |
| 4 | 50 | 150 |
| 5 | 30 | 180 |

Total: 180h. Cabe.
