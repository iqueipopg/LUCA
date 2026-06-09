# Paper LUCA — build y mantenimiento

Esqueleto del paper (AI Lab). Estructura: intro, related work, architecture,
experiments, discussion, conclusion.

## Archivos

- `main.tex` — documento raíz (6 secciones, tabla de agentes con estado, figuras).
- `results.tex` — **generado**, tabla de accuracy por métrica. No editar a mano.
- `figures/` — **generadas** (`fig_l3_accuracy_by_metric.pdf`, `fig_approach_comparison.pdf`).
- `references.bib` — bibliografía (placeholder; rellenar).

## Regenerar números y figuras (desde CSV reales)

Las cifras del paper salen de los CSV de evaluación, nunca de memoria ni del
diario. La fuente de verdad es `docs/eval/results_real.md`.

```
# 1) (si hace falta) re-correr la evaluación
venv/bin/python experiments/eval_extraction.py
venv/bin/python experiments/eval_baseline_llm.py --mode structured
venv/bin/python experiments/eval_baseline_llm.py --mode naive

# 2) regenerar figuras + results.tex desde los CSV más recientes
venv/bin/python experiments/make_figures.py
```

## Compilar

```
cd docs/paper
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

## Checklist para el humano (`% TODO(human)` en main.tex)

- [ ] Idioma final (el esqueleto está en inglés; el pipeline produce español).
- [ ] Autores y afiliación.
- [ ] Abstract, intro, related work, discussion, conclusion.
- [ ] **No publicar afirmaciones cualitativas (riesgos L4, clasificación L5,
      prosa del memo L7) sin revisarlas** — ver `docs/review/pending_human_review.md`.
      Están marcadas con `% TODO(human)`.
- [ ] Rellenar `references.bib`.
