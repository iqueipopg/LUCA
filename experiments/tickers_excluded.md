# Corpus S&P 100 — exclusiones del screening (T5.1)

Lista fuente: constituyentes del S&P 100 según Wikipedia
(tabla de componentes fechada 2025-09-22, consultada 2026-08-19),
101 tickers. Reglas de exclusión pre-registradas:
presenta 20-F en lugar de 10-K; menos de 3 10-K anuales con company
facts XBRL cubriendo FY2022-FY2024; clase de acción duplicada del
mismo CIK; ticker ausente del mapa de EDGAR. La lista incluida se
congela en `corpus_tickers.txt` ANTES de la extracción; no se
permiten retiradas post-hoc.

**Incluidos: 96. Excluidos: 5.**

| Ticker | Motivo de exclusión |
|--------|---------------------|
| BLK | menos de 3 10-K anuales con company facts XBRL cubriendo FY2022-FY2024 (faltan: FY2022, FY2023) |
| GEV | menos de 3 10-K anuales con company facts XBRL cubriendo FY2022-FY2024 (faltan: FY2022, FY2023) |
| GOOG | clase de acción duplicada de GOOGL (mismo CIK 0001652044); una sola fila por entidad |
| HONA | la entidad a la que EDGAR mapea el ticker (Honeywell Aerospace Inc., CIK 0002089271) no tiene ningún 10-K en su índice de submissions (entidad de nueva creación: spin-off o reorganización en holding; los 10-K históricos pertenecen a otro CIK y no se persiguen: sin special-casing por empresa) |
| XOM | la entidad a la que EDGAR mapea el ticker (ExxonMobil Holdings Corp, CIK 0002115436) no tiene ningún 10-K en su índice de submissions (entidad de nueva creación: spin-off o reorganización en holding; los 10-K históricos pertenecen a otro CIK y no se persiguen: sin special-casing por empresa) |
