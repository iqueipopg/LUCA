# LUCA — LLM-based Unified Corporate Analyst

Pipeline multi-agente para la extracción estructurada y generación de memos de inversión a partir de documentos financieros regulatorios (10-Ks de SEC EDGAR, informes anuales de CNMV).

Proyecto AI Lab 2025-2026 · Grado en Ingeniería Matemática e IA · ICAI-ICADE.

## Idea en una frase

Le das un 10-K, LUCA te devuelve un investment memo estructurado con métricas extraídas, análisis de riesgos y outlook.

## Arquitectura en una línea

Pipeline de 8 agentes L1→L8, enfoque híbrido (XBRL programático para números + LLM local para texto cualitativo), Qwen 2.5 7B cuantizado en GPU consumer (RTX 4060 8GB).

## Estado actual (Sprint 2)

Pipeline **E2E funcional de L1 a L7** (sin L6/L8). Resultados clave sobre el gold standard (60 datapoints = 6 métricas × 10 empresas):

| Enfoque | Precisión |
|---|---|
| **L3 (XBRL estructurado)** | **100 %** (determinista) |
| Baseline LLM structured | ~50 % |
| Baseline LLM naive | 3.3 % |

Brecha L3 vs mejor baseline: **≈ +48–50 pp** (titular del paper). Fuente de verdad de los números: `docs/eval/results_real.md`.

- **Implementado y evaluado:** L1 (ingestion), L2 (parser + chunker Item 1A), L3 (extractor estructurado XBRL).
- **Implementado (capa cualitativa, pendiente de revisión humana):** L4 (extracción de riesgos), L5 (métricas derivadas deterministas + clasificación con Qwen), L7 (investment memo).
- **Paper** (AI Lab) en `docs/paper/` (IEEEtran, español, 10 págs, `main.pdf`).
- **240 tests** verdes (mocks 100 % offline).
- **Future work:** L6, L8, capa de deduplicación de riesgos, forward-looking statements, tono directivo, métricas `cash`/`long_term_debt`, categorías `reputation`/`conduct`.

## Ejecutar el pipeline

```bash
# Pipeline E2E (L1→L7) y memo de inversión para un ticker
venv/bin/python run_pipeline.py --ticker AAPL --memo

# Evaluación del extractor estructurado y los baselines LLM
venv/bin/python experiments/eval_extraction.py
venv/bin/python experiments/eval_baseline_llm.py --mode structured
venv/bin/python experiments/eval_baseline_llm.py --mode naive

# Regenerar figuras y tabla del paper desde los CSV reales
venv/bin/python experiments/make_figures.py
```

Requiere Ollama sirviendo `qwen2.5:7b-instruct-q4_K_M` en local y `SEC_USER_AGENT` en `.env`.

## Cómo empezar

1. Lee `INSTALL.md` para montar el entorno.
2. Lee las reglas del proyecto para entender el proyecto y las convenciones.
3. Lee `ARCHITECTURE.md` para entender el pipeline.

## Estructura

```
luca/
├── README.md                         # Este archivo
├── INSTALL.md                        # Setup paso a paso
├── las reglas del proyecto                         # Contexto y reglas del proyecto
├── ARCHITECTURE.md                   # Diseño del pipeline
├── SPRINT_PLAN.md                    # Planificación de sprints
├── run_pipeline.py                   # CLI orquestador L1→L7 (flag --memo)
│   ├── settings.json                 # Config compartida (commiteada)
│   ├── settings.local.json           # Config local (no commiteada)
│   └── mcp.json                      # Servidores MCP
├── config/
│   └── agents.json                   # Config de los agentes del pipeline LUCA
├── config.yaml                       # Config global del pipeline
├── data/
│   └── gold_standard_template.json   # Template de anotación manual
├── skills/                           # Skills de dominio (SEC, XBRL, LLM local)
│   ├── sec-edgar/                    # Interfaz a SEC EDGAR API
│   ├── xbrl-parsing/                 # Parseo y extracción XBRL
│   └── local-llm/                    # Cliente Ollama/Qwen
├── agents/                           # Código del pipeline L1→L8
│   ├── _logging.py                   # Logging centralizado
│   ├── _config.py                    # Carga de configuración
│   ├── _llm_client.py                # Cliente LLM local (Ollama/Qwen)
│   ├── _edgar_client.py              # Cliente SEC EDGAR
│   ├── _gold_schema.py               # Constantes del gold standard
│   ├── _schemas.py                   # Contrato Pydantic de salida L4
│   ├── agent1_ingestion.py           # L1: Descarga de documentos
│   ├── agent2_parser.py              # L2: Parsing y segmentación
│   ├── agent3_extractor.py           # L3: Extracción estructurada (XBRL)
│   ├── agent4_qualitative/           # L4: chunker Item 1A + extracción de riesgos
│   ├── agent5_analyst.py             # L5: métricas derivadas + clasificación
│   └── agent7_writer.py              # L7: investment memo (Qwen)
├── tests/                            # Tests unitarios e integración (240)
├── experiments/                      # Eval (extraction, baselines) + figuras del paper
│   ├── eval_extraction.py            # L3 vs gold standard
│   ├── eval_baseline_llm.py          # Baselines LLM (naive/structured)
│   └── make_figures.py               # Figuras + results.tex del paper
├── docs/
│   ├── eval/results_real.md          # Fuente de verdad de los resultados
│   ├── paper/                        # Paper IEEEtran (main.tex, main.pdf, figuras)
│   └── review/                       # Cola de revisión humana (L4/L5)
├── scripts/                          # Utilidades (anotación del gold, etc.)
└── requirements.txt                  # Dependencias Python
```

## Narrativa del proyecto

Spin-off directo del TFG del autor (SAM — Systematic Agent for Meta-analysis, pipeline para revisiones sistemáticas clínicas). LUCA demuestra que la arquitectura multi-agente de SAM es **domain-agnostic** y generaliza a otros dominios con documentos estructurados.
