# LUCA — LLM-based Unified Corporate Analyst

Pipeline multi-agente para la extracción estructurada y generación de memos de inversión a partir de documentos financieros regulatorios (10-Ks de SEC EDGAR, informes anuales de CNMV).

Proyecto AI Lab 2025-2026 · Grado en Ingeniería Matemática e IA · ICAI-ICADE.

## Idea en una frase

Le das un 10-K, LUCA te devuelve un investment memo estructurado con métricas extraídas, análisis de riesgos y outlook.

## Arquitectura en una línea

Pipeline de 8 agentes L1→L8, enfoque híbrido (XBRL programático para números + LLM local para texto cualitativo), Qwen 2.5 7B cuantizado en GPU consumer (RTX 4060 8GB).

## Cómo empezar

1. Lee `INSTALL.md` para montar el entorno.
2. Lee las reglas del proyecto para entender el proyecto y las convenciones.
3. Lee `ARCHITECTURE.md` para entender el pipeline.

## Estructura

```
luca/
├── README.md                    # Este archivo
├── INSTALL.md                   # Setup paso a paso
├── las reglas del proyecto                    # Contexto y reglas del proyecto
├── ARCHITECTURE.md              # Diseño del pipeline
├── SPRINT_PLAN.md               # Planificación de sprints
│   ├── settings.json            # Config compartida (commiteada)
│   ├── settings.local.json      # Config local (no commiteada, ver template)
│   └── mcp.json                 # Servidores MCP
├── config/
│   └── agents.json              # Config de los agentes del pipeline LUCA
├── config.yaml                  # Config global del pipeline
├── data/
│   └── gold_standard_template.json  # Template de anotación manual
├── skills/                      # Skills de dominio (SEC, XBRL, LLM local)
└── requirements.txt             # Dependencias Python
```

## Narrativa del proyecto

Spin-off directo del TFG del autor (SAM — Systematic Agent for Meta-analysis, pipeline para revisiones sistemáticas clínicas). LUCA demuestra que la arquitectura multi-agente de SAM es **domain-agnostic** y generaliza a otros dominios con documentos estructurados.
