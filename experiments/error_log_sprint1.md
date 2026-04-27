# Sprint 1 — error log

Bitácora de incidencias detectadas mientras se construye el extractor L3 y la
infraestructura de evaluación. Cada entrada lleva timestamp ISO, tarea origen,
empresa o tag involucrado, y la hipótesis de causa.

---

## 2026-04-27 — T1.3 — AAPL — Tag `Revenues` con cobertura limitada

- **Empresa:** AAPL (CIK 0000320193).
- **Tag primario afectado:** `us-gaap:Revenues`.
- **Síntoma:** el fixture `tests/fixtures/companyfacts_AAPL.json` solo
  contiene un único hecho anual (FY2017, end `2017-09-30`, accn
  `0000320193-18-000145`). El resto de slices del bloque son
  trimestrales con `fp == "FY"`. Por eso `extract` elige correctamente
  ese FY2017 como dato más reciente disponible, pero el resto de
  métricas reportan FY2025.
- **Hipótesis:** Apple migró a `RevenueFromContractWithCustomerExcludingAssessedTax`
  con ASC 606 (FY2018+) y dejó de etiquetar la línea como `Revenues`.
  El fixture es real pero recortado y refleja esa realidad.
- **Acción:** dejar el tag primario tal cual (`Revenues`) en T1.3. El
  fallback se cubre en **T1.4** añadiendo
  `RevenueFromContractWithCustomerExcludingAssessedTax` y
  `SalesRevenueNet` como alternativas. Hasta entonces, la extracción de
  AAPL para `revenue` apuntará a FY2017, no a FY2025; el evaluador
  cuantitativo (T1.8) lo verá como métrica fuera de período y bajará
  recall, lo cual es la señal correcta para priorizar T1.4.

---

## 2026-04-27 — T1.4 — AAPL — La cadena de fallbacks no rescata FY2025 en revenue

- **Empresa:** AAPL (CIK 0000320193).
- **Tags involucrados:** `us-gaap:Revenues` (primario) vs
  `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` (fallback 1).
- **Síntoma:** tras incorporar la cadena
  `("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
  "SalesRevenueNet")` y verificar que el AAPL real (fixture trimmed)
  resuelve `revenue`, `extract` sigue eligiendo `Revenues` con
  `period_end=2017-09-30` (FY2017). El fallback ASC 606 no se activa
  porque el primario tiene un hecho anual válido (`form=10-K`, `fp=FY`,
  duración ≈ 370 días) procedente de la 10-K de 2018.
- **Hipótesis:** EDGAR companyfacts agrega el histórico completo de
  filings; cualquier tag que apareciese en una 10-K antigua sigue
  estando "vivo" indefinidamente. El contrato actual de T1.4 es
  "primario gana siempre que tenga un fact válido", lo cual es
  estrictamente correcto pero no resuelve este caso. Un fact de FY2017
  no debería competir contra uno de FY2025; falta filtro temporal entre
  tags candidatos.
- **Impacto:** AAPL `revenue` apunta a 229.234B USD (FY2017) en lugar
  de 416.161B USD (FY2025). Esto hará que **T1.8** marque AAPL revenue
  como fallo de período, no de extracción. El evaluador debe
  distinguir ambos casos (tag correcto vs período correcto) en su
  reporte por métrica.
- **Acción:** **no** sobre-extender T1.4 (queda fuera de scope según
  briefing). Documentar aquí y enrutar a:
    1. **T1.5** (período + currency handling) como ámbito natural para
       añadir un filtro "preferir el tag candidato cuyo fact más reciente
       esté dentro de los últimos N años" o similar.
    2. **T1.10** (análisis de errores): este caso es el ejemplo
       canónico de "tag legacy que ensombrece al moderno"; usarlo para
       motivar la métrica de cobertura por fallback en el reporte
       final.
- **Test que pinea el comportamiento actual:**
  `tests/test_agent3_extractor.py::TestExtractFallbackChain::test_aapl_fixture_revenue_still_resolves_with_legacy_revenues_tag`
  (sustituido en T1.5 por
  `test_aapl_fixture_revenue_resolves_to_asc606_fy2025_under_t15`).

---

## 2026-04-27 — T1.5 — AAPL — Resolución del bug de selección entre tags

- **Empresa:** AAPL (CIK 0000320193).
- **Tags involucrados:** `Revenues` (primario, FY2017) vs
  `RevenueFromContractWithCustomerExcludingAssessedTax` (fallback 1,
  FY2025).
- **Cambio de algoritmo:** la selección dejó de ser *"primer candidato
  con cualquier hecho válido gana"* y pasó a ser *"hecho más reciente a
  lo largo de TODA la cadena de candidatos gana, con el `end` como
  clave principal y la prioridad del tag como tie-break"*. Implementado
  en `agents.agent3_extractor._collect_annual_candidates` +
  `_extract_metric`.
- **Impacto en AAPL fixture:**
    * Antes (T1.4): `revenue` = 229.234B USD (FY2017, tag `Revenues`,
      accn 2018), resto de métricas en FY2025 → mezcla de períodos,
      `top-level fiscal_year=2025` engañoso.
    * Después (T1.5): `revenue` = 416.161B USD (FY2025, tag
      `RevenueFromContractWithCustomerExcludingAssessedTax`, accn
      `0000320193-25-000079`). Las 6 métricas resuelven al mismo
      FY2025 con la misma accession; trazabilidad completa.
- **Decisiones de diseño:**
    1. **Tie-break por prioridad de tag.** Si dos candidatos exponen
       hechos con el mismo `end`, gana el primero del chain. Esto
       preserva la semántica original de "preferir el tag canónico"
       cuando los datos son redundantes (caso típico: empresas que
       publican `Revenues` y `RevenueFromContract...` con valores
       idénticos durante años de transición ASC 606).
    2. **Umbral de duración 320d sin cambios.** Se mantiene
       `_MIN_ANNUAL_DURATION_DAYS = 320`. Suficiente para descartar
       trimestres (~90d) y stub-years de cambio de fiscal year
       (200–300d), sin tirar 52-week (~364d) ni 53-week (~371d). Test
       nuevo `test_stub_year_under_320_days_is_rejected` lo cubre.
    3. **USD-only declarado.** Documentado en docstring del módulo y
       de `extract`. Métricas que solo aparecen en EUR/CAD/JPY → `None`.
       Sin conversión FX en Sprint 1.
    4. **Nuevo campo `accession` en el output.** Necesario para T1.10
       (cuando una métrica difiera del gold standard, hay que poder
       trazarla al filing que la generó).
- **Tests modificados:**
    * `test_primary_tag_wins_when_both_primary_and_fallback_exist` →
      renombrado a `test_primary_tag_wins_on_tie_when_both_have_same_end_date`,
      con asserts adaptados a la nueva semántica.
    * Pin AAPL T1.4 sustituido por
      `test_aapl_fixture_revenue_resolves_to_asc606_fy2025_under_t15`,
      que ahora exige `tag_used=RevenueFromContractWithCustomerExcludingAssessedTax`
      y `period_end=2025-09-27`.
- **Tests nuevos T1.5:**
  `test_fallback_wins_when_more_recent_than_primary` (escenario AAPL
  sintético), `test_primary_wins_tie_break_when_end_dates_match`,
  `test_eur_only_metric_returns_none_no_conversion`,
  `test_stub_year_under_320_days_is_rejected`,
  `test_full_52_week_year_is_accepted`,
  `test_extracted_metric_includes_accession`,
  `test_extracted_metric_accession_is_none_when_absent_in_fact`.
- **Suite:** 80/80 pasan (era 73/73 antes de T1.5).
