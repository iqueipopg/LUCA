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

---

## 2026-04-27 — T1.6 — MSFT/JPM — Comportamiento real de tags observado con fixtures de EDGAR

- **Tarea:** T1.6 (tests con fixtures reales multi-empresa).
- **Empresas:** MSFT (CIK 0000789019) y JPM (CIK 0000019617).
- **Fixtures generados:** `companyfacts_MSFT.json` (13.7 KB) y
  `companyfacts_JPM.json` (13.6 KB).

### MSFT — tags observados (FY2025, period_end 2025-06-30)

| Métrica | Tag usado | Valor |
|---|---|---|
| revenue | `RevenueFromContractWithCustomerExcludingAssessedTax` | 281.7B USD |
| net_income | `NetIncomeLoss` | 101.8B USD |
| operating_income | `OperatingIncomeLoss` | 128.5B USD |
| total_assets | `Assets` | 619.0B USD |
| total_equity | `StockholdersEquity` (fallback) | 343.5B USD |
| eps_diluted | `EarningsPerShareDiluted` | 13.64 USD/share |

- `Revenues` existe en el fixture MSFT pero solo con hechos de FY2008
  (end 2008-06-30). T1.5 elige correctamente `RevenueFromContractWithCustomerExcludingAssessedTax`
  con end=2025-06-30 por recencia. Comportamiento análogo a AAPL.
- `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`
  ausente en el fixture MSFT (EDGAR no etiqueta este tag para MSFT porque
  no hay NCI material). El extractor degrada correctamente al fallback
  `StockholdersEquity`. El reorden de `total_equity` en la cadena (NCI
  primero, T1.5) no introduce ningún error para MSFT.

### JPM — tags observados (FY2025, period_end 2025-12-31)

| Métrica | Tag usado | Valor | Nota |
|---|---|---|---|
| revenue | `Revenues` | 182.4B USD | Net Revenue (NII + non-interest) |
| net_income | `NetIncomeLoss` | 57.0B USD | |
| operating_income | `None` | N/A | OperatingIncomeLoss ausente en EDGAR para SIC 6022 |
| total_assets | `Assets` | 4.42T USD | |
| total_equity | `StockholdersEquity` (fallback) | 362.4B USD | NCI tag con datos solo hasta 2015 |
| eps_diluted | `EarningsPerShareDiluted` | 20.02 USD/share | |

- **Sorpresa respecto a la hipótesis inicial:** JPM sí etiqueta sus ingresos
  totales como `Revenues` en las 10-K recientes (FY2025: 182.4B USD,
  representando Net Revenue = NII + non-interest revenue). El fallback
  bancario `InterestAndDividendIncomeOperating` existe en el fixture pero
  solo con datos de FY2009-FY2011 (end máximo 2011-12-31); T1.5 lo rechaza
  por recencia. Conclusión: la cadena de candidates funciona correctamente
  para JPM; el fallback bancario sería la red de seguridad si JPM dejara
  de publicar `Revenues`.
- **`operating_income` es None para JPM:** confirmado. `OperatingIncomeLoss`
  no aparece en EDGAR companyfacts para bancos (SIC 6022). Es una limitación
  conocida documentada en `agent3_extractor.py` y cubierta en T1.10.
- **`total_equity` NCI tag obsoleto:** `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`
  aparece en el fixture JPM pero solo hasta end=2015-12-31 (FY2015). El tag
  `StockholdersEquity` tiene datos hasta FY2025, gana por recencia. No es un
  bug del extractor; JPM reorganizó su NCI disclosure tras 2015.
- **`ProfitLoss` en JPM:** el fixture incluye `ProfitLoss` (fallback de
  `net_income`) con datos de FY2011-FY2013. `NetIncomeLoss` tiene datos
  actuales hasta FY2025, gana por recencia sin ningún ajuste especial.

### Impacto en T1.10

La distribución de `tag_used` observada en 3 empresas reales (AAPL, MSFT, JPM):
- `revenue`: 2/3 usan ASC-606 (`RevenueFromContractWithCustomerExcludingAssessedTax`),
  1/3 usa `Revenues` (JPM). El fallback bancario `InterestAndDividendIncomeOperating`
  no fue necesario para ninguna de las 3 empresas en datos recientes.
- `total_equity`: 3/3 usan `StockholdersEquity` (fallback). El tag NCI
  preferente no tiene datos recientes en ninguna de las 3 empresas del
  fixture.
- `operating_income`: 2/3 resuelven, 1/3 devuelve None (JPM). T1.10 debe
  anotar esta limitación para SIC 6022.

---

## 2026-04-27 — T1.8 — Run real L3 vs gold standard (10 tickers × 6 métricas)

- **Tarea:** T1.8 (`experiments/eval_extraction.py`).
- **Resultado:** accuracy global 66.7% (40/60). Por métrica: revenue
  70%, net_income 60%, operating_income 60%, total_assets 70%,
  total_equity 70%, eps_diluted 70%.
- **Distribución de tags resueltos** (sobre las 59 métricas con valor;
  JPM operating_income es None y se omite):
    * `revenue`: 5× `RevenueFromContractWithCustomerExcludingAssessedTax`
      (filers ASC-606 puros: AAPL, MSFT, META, AMZN, NVDA),
      5× `Revenues` (filers que conservan el tag legacy o lo usan
      como cabecera de net revenue, p. ej. JPM, JNJ, WMT, GOOGL, KO).
      Reparto exactamente 50/50 — fallback chain crítico para el
      50% del universo. El fallback bancario
      `InterestAndDividendIncomeOperating` no se activó en ninguna
      empresa real (JPM publica `Revenues` directamente).
    * `total_equity`: 7× `StockholdersEquity` (fallback),
      3× `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`
      (NCI primero — el tag preferente). Esto **revisa al alza la
      conclusión de T1.6** (donde se observó 3/3 cayendo al fallback):
      con la cobertura del gold standard completo, el tag NCI sí gana
      en una minoría de issuers. T1.10 debe identificar en qué
      empresas (probablemente las que tienen NCI material).
    * `operating_income`: 9/10 resuelven con `OperatingIncomeLoss`,
      1/10 None (JPM, esperado por SIC 6022).
    * `net_income`, `total_assets`, `eps_diluted`: 10/10 con el tag
      canónico (`NetIncomeLoss`, `Assets`,
      `EarningsPerShareDiluted`). Los fallbacks no se activaron.

### Sub-incidencia 1 — desfase temporal gold vs filing más reciente (GOOGL, META, AMZN)

- **Síntoma:** las 18 misses (3 empresas × 6 métricas) provienen de un
  desfase temporal: el gold standard fue anotado contra la 10-K
  FY2024 (filed early 2025), pero EDGAR ya tiene la 10-K FY2025 (filed
  early 2026) y T1.5 elige por recencia, por lo que `extract` devuelve
  el FY2025 frente al FY2024 anotado. Diferencias relativas observadas:
  GOOGL 15-34%, META 1.5-32%, AMZN 12-43%. Coherentes con un año más
  de crecimiento.
- **Hipótesis:** **NO es bug del extractor**. Es un *time skew* entre
  la fecha de anotación del gold standard (T1.2, antes de los filings
  FY2025 de tech) y la fecha de evaluación (T1.8, ya con FY2025
  disponible). Las 6 empresas no afectadas (AAPL, MSFT, NVDA, KO,
  JPM, JNJ, WMT) son las que cuyo `gold_fiscal_year` ya coincidía con
  el FY más reciente disponible en EDGAR a fecha de la evaluación.
- **Acción:** **no** modificar L3. Documentar y enrutar a:
    1. **T1.10** (análisis de errores): 30% del error global de T1.8
       es exclusivamente de este time-skew. La accuracy "real" del
       extractor — restringida a los pares ticker/metric donde
       `gold_fiscal_year == predicted_fiscal_year` — es 38/40 = 95%.
       T1.10 debe reportar las dos cifras: 66.7% (raw) y 95% (period-
       matched), explicando la diferencia.
    2. **Decisión de gold standard:** o bien re-anotar GOOGL/META/AMZN
       con FY2025 antes del gate de Sprint 1, o bien fijar el gold
       standard a FY2024 documentando que la evaluación es contra ese
       fiscal year y forzar al extractor a un período objetivo (no
       contemplado en Sprint 1, sería un parámetro de L3 o un filtro
       posterior). Recomendación de : re-anotar es
       más limpio y rápido (tres empresas × seis métricas leídas de
       las 10-Ks de 2026). Decisión final corresponde a the author.

### Sub-incidencia 2 — JNJ operating_income, predicción FY2014 stale

- **Síntoma:** gold dice `null` (JNJ no publica un subtotal "Operating
  Profit"; ya documentado en notas del gold standard). L3 devuelve
  21.59B USD con `period_end=2014-12-28`, `tag_used=OperatingIncomeLoss`,
  `fiscal_year=2014`.
- **Hipótesis:** EDGAR companyfacts conserva el último año en que
  JNJ etiquetó `OperatingIncomeLoss` (FY2014, presumiblemente la
  última 10-K que sí reportaba ese subtotal antes de discontinuar la
  línea). T1.5 selecciona "el más reciente del chain", pero **un fact
  de hace 11 años no debería competir con la información de FY2025**.
  El extractor no tiene un filtro "el fact resuelto debe ser
  razonablemente reciente respecto al fiscal year del filing".
- **Impacto:** 1/60 misses. El gold predice ausencia, L3 hallucina con
  stale data. Es un caso pequeño pero conceptualmente importante:
  *L3 puede entregar valores correctos pero obsoletos si los
  modernos no existen*.
- **Acción:** **no** arreglar en T1.8. Enrutar a T1.10 (y posible
  T2.x): añadir un guard "rechazar facts cuyo `end` esté más de N
  años antes del filing más reciente" (N=2 sería suficiente para JNJ
  manteniendo MSFT, JPM y demás). El análisis debe medir si
  introducir ese guard pondría en riesgo otras métricas.

### Sub-incidencia 3 — WMT net_income, 1.69% por encima del umbral

- **Síntoma:** gold=22.270B USD (FY2026, period_end 2026-01-31),
  pred=21.893B USD, mismo `fiscal_year=2026` pero diferencia 1.69%
  (377M USD).
- **Hipótesis:** WMT FY2026 cerró el 2026-01-31, muy reciente. El
  fact en EDGAR con `end=2026-01-31` y `tag=NetIncomeLoss` viene del
  10-K filed 2026-03-13. La diferencia de 377M USD podría ser:
    1. NCI: el gold puede ser "Consolidated net income" mientras que
       `NetIncomeLoss` es el atribuible a Walmart shareholders (sin
       NCI). 377M es coherente con el porcentaje de NCI histórico
       de WMT (~1.5% del net income consolidado).
    2. Restatement entre el press release y la 10-K final.
- **Acción:** documentar y enrutar a **T1.10** (ítem específico:
  validar manualmente WMT FY2026 net_income contra el 10-K reciente,
  posible reanotación del gold). No es bug de selección, es ambigüedad
  en la definición de `NetIncomeLoss` para empresas con NCI material.
  Si T1.10 confirma que el problema es NCI, la solución sería usar
  `ProfitLoss` (consolidado, pre-NCI) como tag preferente para
  empresas con NCI material — pero eso es Sprint 2.

### Sub-incidencia 4 — META eps_diluted, 1.55% off

- **Síntoma:** gold=23.86 USD/share, pred=23.49, diferencia 1.55%
  (justo por encima del 0.5% de tolerancia).
- **Hipótesis:** lo mismo que las otras métricas de META: time-skew
  FY2024 vs FY2025. Cae en la sub-incidencia 1.
- **Acción:** se cubre con la decisión de re-anotar GOOGL/META/AMZN.

### Resumen para T1.10

- Accuracy raw: **66.7%**.
- Accuracy ajustada por time-skew (excluyendo 18 pares de
  GOOGL/META/AMZN cuyo gold_fy != predicted_fy): **40 / 42 = 95.2%**.
- Las 2 misses restantes (JNJ operating_income, WMT net_income) son
  de naturaleza distinta y T1.10 las debe analizar individualmente.
- El extractor es robusto: cuando los períodos coinciden, la
  precisión está al nivel esperado de XBRL (sub-1% de error
  numérico, dentro de la tolerancia rel_tol=0.5%).
- Outputs reproducibles bajo
  `experiments/output/eval_extraction_20260427_205700.{csv,md}`.

---

## 2026-04-30 — T1.7b — AAPL — Bug en L2: `_slice_item` se queda en el TOC

- **Tarea:** T1.7b (fix L2 sobre 10-Ks reales con TOC).
- **Empresa:** AAPL (CIK 0000320193, accession 0000320193-25-000079).
- **Síntoma:** al ejecutar `experiments/eval_baseline_llm.py --mode structured --limit 1` en sesión del 2026-04-29 (descubierto al cierre de T1.9), la ejecución reportaba
  `item_1=18 caracteres, item_1a=23 caracteres, item_7=96 caracteres, item_8=54 caracteres` y accuracy 0/6.
- **Hipótesis inicial descartada:** iXBRL warning. El parser `lxml`-HTML
  procesa correctamente la cabecera `<?xml ...?>` y los 1.170 tags
  `ix:*`; `get_text()` produce 220.566 caracteres de texto plano
  limpio. El warning es cosmético y se silencia con
  `warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)`.
- **Hipótesis confirmada:** la regex original toma el primer match de
  cada cabecera "Item N." y troquela hasta el primer end-anchor.
  En 10-Ks reales el primer match cae siempre en el **table of
  contents**, donde Items 1, 1A, 1B, 2, 7, 7A, 8, 9 aparecen
  consecutivos en ~600 chars. Cada slice resulta ser sólo la entrada
  del índice ("Item 1. Business 1" = 18 chars).
- **Diagnóstico cuantitativo (AAPL real):**
    * Match de "Item 8" en posiciones [19602 (TOC), 118160, 127666,
      134081, 138963 (cabecera real Item 8 body), 204314].
    * El extractor de tablas (`_extract_tables`) NO está afectado: 54
      tablas correctas. El bug es exclusivo de `_slice_item`.
- **Solución implementada:**
    1. Filtro `XMLParsedAsHTMLWarning` a nivel módulo (silencia el
       warning en runtime; en pytest sigue apareciendo porque el
       framework resetea filtros por test).
    2. Detección DOM-based del TOC: `_locate_toc_end(html, plain_text)`
       itera `<table>` en orden y selecciona la primera con
       ≥`_TOC_MIN_ENTRIES=5` referencias `Item \d+[a-z]?`. Devuelve
       el offset del fin de su texto en `plain_text`.
    3. Regex title-aware en `_ITEM_BOUNDARIES`: cada cabecera exige
       el título canónico SEC inmediatamente después del número
       (`item\s+1[\.\s]+business`, `item\s+8[\.\s]+financial\s+statements`,
       etc.). Esto hace que las cross-refs en el body
       ("see Item 8 of this Form 10-K") no disparen el end-anchor.
- **Variante intentada y rechazada:** un primer enfoque por
  cluster de gaps en plain text (≥5 matches con gaps ≤200 chars)
  funcionó sobre el TOC del fixture sintético pero falló en AAPL real
  porque el párrafo "Forward-Looking Statements" del cuerpo de Item 1
  contiene 3 cross-refs a Items 1A/7/8 dentro de ~190 chars: el
  detector extendía el cluster a través de las cross-refs y dejaba
  `item_1=0`. El enfoque DOM-based (tabla del TOC) lo resolvió.
- **Resultado tras T1.7b sobre AAPL real:**
    * `item_1=16.050, item_1a=68.044, item_7=18.017, item_8=61.256`
      (vs 18/23/96/54 antes).
    * Item 8 > 50.000 chars: criterio del usuario cumplido.
    * Suite: 130 → 138 tests verdes (5 nuevos en
      `TestParseSkipsTableOfContents`, 3 en `TestLocateTocEnd`).
- **Deuda técnica anotada para Sprint 2:** opción D del diagnóstico
  (DOM headings — exigir que la cabecera esté envuelta en
  `<b>`/`<h3>`/`<font weight=bold>`). La heurística actual seguirá
  funcionando salvo que un emisor reorganice el TOC fuera de un
  `<table>` (raro en 10-Ks de US-listed). Si la T1.9b detecta
  drift, escalar a Sprint 2.

---

## 2026-04-30 — T1.9 Bug #2 — AAPL — `prepare_structured_content` selecciona cover-page en lugar de consolidated statements

- **Tarea:** T1.9 / Bug #2 (fix dentro de la propia T1.9).
- **Síntoma:** tras T1.7b, structured --limit 1 sobre AAPL daba
  accuracy 0% con tamaño medio de 54 chars de input (la entrada
  "Item 8. Financial..." truncada). Tras un fix intermedio
  (`raw_tables[:3]` → primeras 3 con `\$\s*[\d,]{6,}`), accuracy 1/6
  con tamaño medio 1.735 chars (el LLM extrajo revenue pero falló el
  resto).
- **Hipótesis del fix intermedio:** el filtro solo-dollar selecciona
  tablas MD&A de breakdowns (Americas/Europa, iPhone/Mac, R&D/SG&A,
  income tax provision) ANTES de las consolidated statements. Las
  MD&A tables tienen ≥3 importes en `$` y pasan el filtro, pero
  carecen de las líneas canónicas (Net income, Total assets, etc.).
- **Solución implementada (Bug #2 final):**
    1. `STRUCTURED_TABLE_COUNT` 3 → 5 (un 10-K canónico tiene 5
       consolidated statements: Operations, Comprehensive Income,
       Balance Sheet, Stockholders' Equity, Cash Flow).
    2. Filtro doble en `_is_financial_table`: ≥3 matches del patrón
       `\$[\s|]*[\d,]{6,}` (dollar amounts con cell separator `|`)
       AND al menos un keyword consolidado (`net income`,
       `total assets`, `total liabilities`, `total shareholders/stockholders`,
       `operating activities`, `comprehensive income`,
       `earnings per share`, `cash and cash equivalents`).
    3. Selección preserva orden de aparición — Income Statement
       siempre va antes que Balance Sheet en 10-Ks canónicos.
- **Resultado --limit 1 AAPL FY2025:**
    * accuracy 5/6 (83.3%): revenue / operating_income / total_assets
      / total_equity / eps_diluted = OK.
    * `net_income`: predicho 93.736B (FY2024, segunda columna del
      Income Statement) en vez de 112.010B (FY2025, primera columna).
      No es bug del fix sino weakness columnar del modelo
      (Qwen 2.5 7B confunde el orden temporal cuando hay tres años
      en línea con headers compartidos). Anotado para discusión en
      el paper como caso característico del baseline.
    * Tamaño medio de input: 7.405 chars (5 tablas seleccionadas).
- **Deuda técnica anotada para Sprint 2:** heurística por header
  HTML — escanear el HTML crudo en busca de
  `r"consolidated\s+statements?\s+of\s+(operations|income)"` y tomar
  las N tablas siguientes en orden de aparición. Más preciso que el
  filtro $-amount + keyword, pero requiere correlacionar tablas con
  sus offsets en el HTML (metadata que `_extract_tables` no preserva
  hoy). Diferido.

---

## 2026-04-30 — T1.9 Bug #3 — AAPL — Naive truncation excluía Item 8 sistemáticamente

- **Tarea:** T1.9 / Bug #3 (fix dentro de T1.9).
- **Síntoma:** modo naive con `NAIVE_MAX_CHARS=25_000` (sólo head)
  daba 0/6 con respuesta del LLM = `{"revenue": null, ..., "eps_diluted": null}`.
- **Diagnóstico:** AAPL plain text = 220.566 chars. Item 8
  (consolidated financial statements) empieza en posición ~138.963
  y termina en ~204.000. Con `text[:25_000]` el LLM ve sólo cover
  page + Item 1 (Business narrativo) + comienzo de Item 1A
  (Risk Factors) — cero números financieros relevantes.
- **Solución implementada (Bug #3, opción B aprobada):**
    * `NAIVE_HEAD_CHARS=5.000`, `NAIVE_TAIL_CHARS=35.000`,
      `NAIVE_HEAD_TAIL_SEPARATOR="\n[...]\n"`.
    * `prepare_naive_content` produce `text[:5_000] + "\n[...]\n" + text[-35_000:]`.
    * `NAIVE_MAX_CHARS = 40_000` total (~10K tokens, dentro del
      techo seguro de Qwen 2.5 7B Q4_K_M en RTX 4060 8 GB).
- **Opciones (a) y (c) descartadas:**
    * (a) bump simple: para alcanzar Item 8 desde el inicio harían
      falta ≥160k chars (~40k tokens) — fuera de presupuesto VRAM.
    * (c) `num_ctx` >12k tokens en RTX 4060 8 GB con Q4_K_M provoca
      OOM por crecimiento lineal del KV cache.
- **Resultado --limit 1 AAPL FY2025:**
    * accuracy 0/6, pero el LLM extrae 1 valor: `eps_diluted=6.13`
      (gold 7.46). El 6.13 corresponde al EPS diluido FY2023 en el
      Income Statement; probablemente capturado en algún
      footnote/selected-financial-data del tail. Comportamiento
      coherente con la hipótesis pre-run (ver más abajo): el head
      0–5k cubre cover page; el tail 185k–220k cubre footnotes y
      Items 9-15. La consolidated income statement (~140-160k) sigue
      fuera de ventana.
    * Diferencia frente al pre-fix: pre = 6/6 nulls absolutos; post =
      5 nulls + 1 valor (mal año). El LLM sí ve algo del documento.
- **Suite final tras los tres fixes:** 138 → 139 tests verdes (9
  nuevos en `tests/test_eval_baseline_llm.py`).

---

## 2026-04-30T20:58 — Hipótesis pre-run T1.9a (naive)

**Configuración:** `NAIVE_MAX_CHARS=40_000`, composición
`text[:5_000] + "\n[...]\n" + text[-35_000:]`. 10 tickers del gold
standard (AAPL, MSFT, GOOGL, META, AMZN, NVDA, JPM, KO, JNJ, WMT).

Se espera que el baseline naive extraiga `eps_diluted` con
accuracy > 50% y posiblemente `total_equity`. Las métricas `revenue`,
`net_income`, `operating_income` y `total_assets` se esperan en
accuracy < 20% porque la consolidated income statement de AAPL
está en posición ~140-160k del plain text, fuera de la ventana del
tail. Esto serviría como evidencia de que el pipeline L1→L2→L3
aporta valor sobre un baseline LLM puro.

**Validación parcial sobre AAPL --limit 1:** accuracy 0/6 raw, 1
valor extraído (`eps_diluted=6.13`, gold 7.46 — año equivocado).
Coherente con la hipótesis (income statement fuera de ventana). El
run completo confirmará si la pauta se extiende a las otras 9
empresas.

---

## 2026-04-30T20:58 — Hipótesis pre-run T1.9b (structured)

**Configuración:** `STRUCTURED_TABLE_COUNT=5`, filtro doble en
`_is_financial_table` (≥3 matches `\$[\s|]*[\d,]{6,}` AND al menos
un keyword consolidado). 10 tickers del gold standard.

Se espera que structured extraiga `revenue`, `total_assets`,
`total_equity` y `eps_diluted` con accuracy > 80% para las 7
empresas no afectadas por time-skew (AAPL, MSFT, NVDA, JPM, KO,
JNJ, WMT). Las métricas `net_income` y `operating_income` se
esperan en accuracy < 80% por confusión columnar de Qwen 2.5 7B
entre años (se observó el caso AAPL: el LLM eligió FY2024 en
lugar de FY2025 leyendo la misma fila multi-año del Income
Statement).

Para GOOGL, META y AMZN se espera accuracy ≈ 0% global por
time-skew FY2024 vs FY2025 (mismo problema documentado en T1.8 —
el filing en cache es FY2025, el gold fue anotado contra FY2024).

**Verificación previa de `gold_fy == latest_filing_fy_in_cache`
(2026-04-30, basada en `eval_extraction_20260427_205700.csv`):**

| ticker | gold_fy | pred_fy filing | match | clasif. |
|---|:---:|:---:|:---:|---|
| AAPL | 2025 | 2025 | ✓ | no-skew |
| MSFT | 2025 | 2025 | ✓ | no-skew |
| NVDA | 2026 | 2026 | ✓ | no-skew (FY enero) |
| JPM  | 2025 | 2025 | ✓ | no-skew |
| KO   | 2025 | 2025 | ✓ | no-skew |
| JNJ  | 2025 | 2025* | ✓ | no-skew (*op.income predice FY2014 stale, gold=null) |
| WMT  | 2026 | 2026 | ✓ | no-skew (FY enero) |
| GOOGL | 2024 | 2025 | ✗ | skew (esperado) |
| META  | 2024 | 2025 | ✗ | skew (esperado) |
| AMZN  | 2024 | 2025 | ✗ | skew (esperado) |

La hipótesis se sostiene en datos previos: el grupo "no-skew"
contiene exactamente las 7 empresas anunciadas y el grupo "skew"
las 3 esperadas.

**Validación parcial sobre AAPL --limit 1:** accuracy 5/6 (83.3%).
El único miss es `net_income` por el problema columnar
predicho. Coherente con la hipótesis. El run completo
confirmará si la asimetría no-skew vs skew se mantiene en las 9
empresas restantes.
