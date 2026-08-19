# Corpus S&P 100 — informe de cobertura (T5.1)

Cobertura de la extracción estructurada L3 (sin LLM) sobre el
corpus congelado en `corpus_tickers.txt`. Este informe mide
COBERTURA, no accuracy: la única afirmación de accuracy sigue
siendo el gold standard N=60 (`docs/eval/results_real.md`).

## Totales

- Filings 10-K procesados: **288**
- Empresas: **96** (FY2022-FY2024, 3 años por empresa)
- Celdas métrica: 1728 (6 métricas core x 288 filings)
- Cobertura de campos: **1653/1728 = 95.7%**
- Nulls por motivo: not_applicable_convention=36, tag_absent=39
- Restatements documentados: 133 (ver `restatements_log.md`)
- Extensiones de la cadena de tags: 2 (ver `chain_changelog.md`)

## Cobertura por métrica

| Métrica | Cobertura | % | Motivo dominante de null |
|---------|-----------|---|--------------------------|
| revenue | 288/288 | 100.0% | n/a |
| net_income | 288/288 | 100.0% | n/a |
| operating_income | 219/288 | 76.0% | not_applicable_convention |
| total_assets | 288/288 | 100.0% | n/a |
| total_equity | 288/288 | 100.0% | n/a |
| eps_diluted | 282/288 | 97.9% | tag_absent |

## Cobertura por sector (división SIC)

| Sector | Cobertura | % |
|--------|-----------|---|
| Finance, Insurance & Real Estate | 231/270 | 85.6% |
| Manufacturing | 813/846 | 96.1% |
| Retail Trade | 144/144 | 100.0% |
| Services | 267/270 | 98.9% |
| Transportation, Communications & Utilities | 198/198 | 100.0% |
