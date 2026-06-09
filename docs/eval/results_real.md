# LUCA — Resultados reales de evaluación (FUENTE DE VERDAD ÚNICA)

> **Este archivo manda.** Toda tabla y figura del paper lee de aquí (y de los CSV citados),
> NUNCA de números recordados de memoria. Generado re-corriendo los scripts de evaluación el
> **2026-06-09**.

## TL;DR

| Enfoque | Accuracy global (N=60) | Fuente CSV |
|---|---|---|
| **L3 (XBRL estructurado)** | **100.0 %** (60/60) | `eval_extraction_20260609_120408.csv` |
| **Baseline LLM structured** | **50.0 %** (30/60) | `eval_baseline_structured_20260609_120832.csv` |
| **Baseline LLM naive** | **3.3 %** (2/60) | `eval_baseline_naive_20260609_120626.csv` |

**Deltas (rango honesto, por varianza del baseline LLM):**
- **L3 − mejor baseline (structured) ≈ +48–50 pp** ← titular del paper (la extracción híbrida
  XBRL bate al LLM puro). Es un **rango**, no un valor exacto: structured oscila **50.0–51.7 %**
  entre ejecuciones porque el `seed` no se aplica a Ollama (no determinista). Con L3 = 100 %
  determinista, el delta va de +48.3 pp (run de 51.7 %) a +50.0 pp (run de 50.0 %).
- structured − naive ≈ +47–48 pp.
- L3 − naive ≈ +96–97 pp.

> **L3 es 100 % determinista** (XBRL, sin LLM): su 100 % no tiene varianza. La incertidumbre del
> rango viene solo del baseline LLM.

## Alcance

- **N = 60 datapoints** = **6 métricas core** × **10 tickers**.
- Métricas core: `revenue, net_income, operating_income, total_assets, total_equity, eps_diluted`.
- `cash` y `long_term_debt` están **fuera de scope** (future work): existen en el esquema de L3
  pero **no están anotadas** en `data/gold_standard.xlsx`, así que el evaluador omite esas filas
  (no entran como misses). Confirmado: 0/0 en ambas.
- Tickers: AAPL, MSFT, GOOGL, META, AMZN, NVDA, JPM, KO, JNJ, WMT.
- Comparación **numérica** con tolerancia relativa 0.5 % (`_eval_common.compare_values`); los
  valores del gold se leen como floats de Excel (sin separadores de millar). Confirmado, sin
  cambios de código.

## Verificación de fiscal_year (sin time-skew)

Se comparó `gold_fiscal_year` vs `predicted_fiscal_year` por fila. **No hay time-skew.**

- AAPL, MSFT, GOOGL, META, AMZN, KO, JNJ, JPM → FY **2025** en gold y en L3. ✓
- NVDA, WMT → FY **2026** en gold y en L3. ✓ (12 filas = 2 tickers × 6 métricas)
- Únicas 2 filas con `predicted_fiscal_year` vacío: **JPM/operating_income** y
  **JNJ/operating_income**. No es skew: el valor es `null` en gold y en L3 (bancos / JNJ no
  publican el subtotal de operating income), y `null == null` cuenta como match. El campo FY queda
  vacío simplemente porque no hay fact.

## Accuracy por métrica (N=60)

| Métrica | L3 | structured | naive |
|---|---|---|---|
| revenue | 100 % (10/10) | 40 % (4/10) | 0 % (0/10) |
| net_income | 100 % (10/10) | 30 % (3/10) | 0 % (0/10) |
| operating_income | 100 % (10/10) | 50 % (5/10) | 20 % (2/10) |
| total_assets | 100 % (10/10) | 50 % (5/10) | 0 % (0/10) |
| total_equity | 100 % (10/10) | 50 % (5/10) | 0 % (0/10) |
| eps_diluted | 100 % (10/10) | 80 % (8/10) | 0 % (0/10) |
| **Global** | **100 % (60/60)** | **50 % (30/60)** | **3.3 % (2/60)** |

> **Nota sobre el naive:** sus 2 únicos "aciertos" son justamente JPM/JNJ operating_income
> (`null==null`). Es decir, el naive no extrae correctamente **ningún** valor numérico real; su
> señal efectiva es ≈ 0 %. (Coincide con el veredicto T1.9a del diario: naive REFUTADA, 2 hits.)

## Reportado vs real (conciliación de cada cifra)

**Conclusión de la conciliación: el diario de Sprint 1 y las reglas del proyecto son CONSISTENTES con los
números reales.** La única corrección de fondo es L3 98.3 %→100 % (resolución de JNJ/JPM
operating_income). El prompt de esta sesión sobre-estimó ligeramente los baselines.

| Cifra | Fuente reportada | Real (2026-06-09) | Conciliación |
|---|---|---|---|
| L3 global | 98.3 % (59/60) — diario línea 41, las reglas del proyecto | **100 % (60/60)** | **Cambio real y explicado.** El miss de Sprint 1 era **JNJ/operating_income** (deuda de criterio aplazada, ver diario "Lo que NO se hizo"). El gold pasó a `null` (JNJ/JPM no publican el subtotal) y L3 también devuelve `null` → `null==null` = match. La subida es esa resolución, no un cambio de datos. |
| L3 global | 100 % — prompt | **100 %** | Coincide. ✓ |
| structured global | +46.7 pp bajo L3 ⇒ ≈ 51.6 %; 31/60 = 51.7 % implícito en el diario ("structured 32→31") | **50.0 % (30/60)** este run; **51.7 % (31/60)** en el CSV de Sprint 1 en disco | **Consistente.** Diferencia = 1 fila de revenue por **varianza run-to-run del LLM** (`model.seed` no se aplica a Ollama). Rango 50–52 %. |
| structured global | 53.3 % — prompt | **50–51.7 %** | Dentro de la varianza del LLM; el prompt redondeó al alza ~1-3 pp. |
| naive global | +48.3 pp bajo structured ⇒ 3.3 %; 2 hits = 3.3 % (diario T1.9a) | **3.3 % (2/60)** | **Consistente exacto.** |
| naive global | ~10-15 % — prompt | **3.3 % (2/60)** | El prompt sobre-estimó; el real reproducible es 3.3 % (el run de Sprint 1 en disco ya daba 2/60). |

### Aviso sobre lecturas erróneas del diario (para que no se vuelvan a citar)

Conviene no confundir tres números del diario que NO son la accuracy global de un baseline:
- **66.7 %** (línea 55) = accuracy de structured en el **subconjunto no-skew** (28/42), no global.
- **+46.7 pp** (línea 41) = **delta** L3−structured, no la accuracy del naive.
- **+48.3 pp** (línea 41) = **delta** structured−naive.

(Un resumen intermedio de esta sesión llegó a tratar 66.7 % y 46.7 como accuracies globales del
diario; es incorrecto y queda descartado aquí.)

## Conclusión del gate

- Números reales reproducibles: **100 % / 50 % / 3.3 %** (L3 / structured / naive), coherentes con
  los CSV de Sprint 1 en disco (±1 fila de varianza LLM en structured) y con los deltas de
  las reglas del proyecto y el diario.
- **El titular del paper se mantiene y se refuerza:** la extracción híbrida XBRL (L3) supera al
  LLM-only por **~+48–50 pp** sobre el mejor baseline (structured, rango por varianza del LLM) y
  por **~+96–97 pp** sobre el naive. L3 es 100 % determinista; el rango procede solo del baseline.
- **Sin time-skew** y **sin discrepancias inexplicadas.** La única corrección de fondo (L3
  98.3→100 %) está explicada por la resolución documentada de JNJ/JPM operating_income.
- **Acción:** el paper usa estos números (vía `experiments/make_figures.py` → `results.tex`). Nada
  pendiente que bloquee; si acaso, el usuario puede actualizar la cabecera de las reglas del proyecto de 98.3 %
  a 100 % cuando quiera.

## Reproducibilidad

```
venv/bin/python experiments/eval_extraction.py
venv/bin/python experiments/eval_baseline_llm.py --mode structured
venv/bin/python experiments/eval_baseline_llm.py --mode naive
```

- `model.seed` está registrado como 42 pero **`LLMClient.chat` no lo pasa a Ollama** → los
  baselines LLM no son seed-deterministas; esperar ±1-2 filas de varianza entre runs. L3 sí es
  determinista (XBRL, sin LLM).
- Modelo: `qwen2.5:7b-instruct-q4_K_M` local vía Ollama (sin APIs externas).
- CSV fuente de este informe:
  - `experiments/output/eval_extraction_20260609_120408.csv`
  - `experiments/output/eval_baseline_structured_20260609_120832.csv`
  - `experiments/output/eval_baseline_naive_20260609_120626.csv`
