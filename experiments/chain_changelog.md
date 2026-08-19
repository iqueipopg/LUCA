# Corpus S&P 100 — cambios en las cadenas de tags US-GAAP (T5.1)

Cada extensión de `_TAG_CANDIDATES` (agents/agent3_extractor.py)
motivada por el triaje de nulls del corpus. Regla: solo extensiones
deterministas, siempre en última posición de la cadena (en empates de
fecha la prioridad favorece a los tags existentes, así que ninguna
selección previa puede cambiar). Tras cada cambio se re-ejecuta el run
completo y el gate de coherencia (regresión gold 60/60).

## 2026-08-19 — revenue += RegulatedAndUnregulatedOperatingRevenue

- **Ticker motivador:** DUK (también resuelve NEE).
- **Diagnóstico:** las utilities reguladas (SIC 4911/4931) publican el
  total de ingresos operativos bajo el elemento de la taxonomía de
  utilities `RegulatedAndUnregulatedOperatingRevenue` y omiten
  `Revenues`. Valores verificados contra los totales reportados
  (DUK FY2022 28,768 M USD; NEE FY2022 20,956 M USD).
- **Posición:** última de la cadena.
- **Descartado:** `RevenueFromContractWithCustomerIncludingAssessedTax`
  (incluye impuestos repercutidos; no es el total de la cuenta de
  resultados).

## 2026-08-19 — net_income += NetIncomeLossAvailableToCommonStockholdersBasic

- **Ticker motivador:** BKNG.
- **Diagnóstico:** BKNG no publica `NetIncomeLoss` ni `ProfitLoss` sin
  dimensiones en FY2022-FY2024; la línea available-to-common sí está y
  coincide con el beneficio neto reportado (3,058 / 4,289 / 5,882 M
  USD). Cuando existen dividendos preferentes el tag infra-estima por
  ese importe; aceptado para un last-resort documentado.
- **Posición:** última de la cadena.

## Casos triados SIN cambio de cadena

- **operating_income `tag_absent` (BMY, COP, CVX, EMR, GE, IBM, JNJ,
  LLY, MRK, NKE, PFE):** estos emisores no publican un subtotal de
  beneficio operativo en su cuenta de resultados; no existe variante
  legítima de `OperatingIncomeLoss` en sus company facts. El
  `OtherOperatingIncomeExpenseNet` de COP es una partida, no un total:
  añadirlo sería incorrecto. Se mantiene null.
- **eps_diluted (BRK.B, V):** el BPA se etiqueta solo con dimensiones
  de clase de acción (Class A/B), y el endpoint companyfacts excluye
  hechos dimensionados. Ausencia estructural del formato XBRL agregado;
  se mantiene null. Verificable en los propios filings:
  - V, 10-K FY2024:
    https://www.sec.gov/ix?doc=/Archives/edgar/data/1403161/000140316124000058/v-20240930.htm
  - BRK.B, 10-K FY2024:
    https://www.sec.gov/ix?doc=/Archives/edgar/data/1067983/000095017025025210/brka-20241231.htm
