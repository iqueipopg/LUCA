# T1.9 — Baseline LLM (structured) vs gold standard

Generado: 2026-06-09T12:08:32

CSV detallado: `eval_baseline_structured_20260609_120832.csv`

Prompt: `config/prompts/baseline_extraction.txt`


## Modo de input

- Modo: **structured**
- Tickers evaluados: **10**
- Llamadas LLM con respuesta: **10/10**
- Tamaño medio de contenido: **5,782 chars** (~1,446 tokens estimados)
- Tiempo medio por llamada: **4.6 s**

## Resumen agregado

- Pares evaluados: **60**
- Coincidencias: **30**
- Accuracy global: **50.0%** (30/60)

## Breakdown por métrica

### `revenue` — accuracy 40.0% (4/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 416,161,000,000 | 416,161,000,000 | OK | 0.0000% |
| MSFT | 281,724,000,000 | 281,724,000,000 | OK | 0.0000% |
| GOOGL | 402,836,000,000 | 4,028,360,000 | MISS | 99.0000% |
| META | 200,966,000,000 | 200,966,000 | MISS | 99.9000% |
| AMZN | 716,924,000,000 | 716,924,000 | MISS | 99.9000% |
| NVDA | 215,938,000,000 | 215,938,000,000 | OK | 0.0000% |
| JPM | 182,447,000,000 | 182,447,000,000 | OK | 0.0000% |
| KO | 47,941,000,000 | 47,941,000 | MISS | 99.9000% |
| JNJ | 94,193,000,000 | null | MISS | — |
| WMT | 713,163,000,000 | null | MISS | — |

### `net_income` — accuracy 30.0% (3/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 112,010,000,000 | 93,736,000,000 | MISS | 16.3146% |
| MSFT | 101,832,000,000 | 101,832,000,000 | OK | 0.0000% |
| GOOGL | 132,170,000,000 | 132,170,000 | MISS | 99.9000% |
| META | 60,458,000,000 | 60,458,000 | MISS | 99.9000% |
| AMZN | 77,670,000,000 | 77,670,000 | MISS | 99.9000% |
| NVDA | 120,067,000,000 | 120,067,000,000 | OK | 0.0000% |
| JPM | 57,048,000,000 | 57,048,000,000 | OK | 0.0000% |
| KO | 13,107,000,000 | 13,107,000 | MISS | 99.9000% |
| JNJ | 26,804,000,000 | null | MISS | — |
| WMT | 21,893,000,000 | 22,270,000,000 | MISS | 1.7220% |

### `operating_income` — accuracy 50.0% (5/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 133,050,000,000 | 13,305,000,000 | MISS | 90.0000% |
| MSFT | 128,528,000,000 | 128,528,000,000 | OK | 0.0000% |
| GOOGL | 129,039,000,000 | 129,039,000 | MISS | 99.9000% |
| META | 83,276,000,000 | 83,276,000 | MISS | 99.9000% |
| AMZN | 79,975,000,000 | 79,975,000 | MISS | 99.9000% |
| NVDA | 130,387,000,000 | 130,387,000,000 | OK | 0.0000% |
| JPM | null | null | OK | — |
| KO | 13,762,000,000 | 13,762,000 | MISS | 99.9000% |
| JNJ | null | null | OK | — |
| WMT | 29,825,000,000 | 29,825,000,000 | OK | 0.0000% |

### `total_assets` — accuracy 50.0% (5/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 359,241,000,000 | 359,241,000,000 | OK | 0.0000% |
| MSFT | 619,003,000,000 | 619,003,000,000 | OK | 0.0000% |
| GOOGL | 595,281,000,000 | 5,952,810,000 | MISS | 99.0000% |
| META | 366,021,000,000 | 366,021,000 | MISS | 99.9000% |
| AMZN | 818,042,000,000 | 818,042,000 | MISS | 99.9000% |
| NVDA | 206,803,000,000 | 206,803,000,000 | OK | 0.0000% |
| JPM | 4,424,900,000,000 | 442,490,000,000 | MISS | 90.0000% |
| KO | 104,816,000,000 | 104,816,000 | MISS | 99.9000% |
| JNJ | 199,210,000,000 | 199,210,000,000 | OK | 0.0000% |
| WMT | 284,668,000,000 | 284,668,000,000 | OK | 0.0000% |

### `total_equity` — accuracy 50.0% (5/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 73,733,000,000 | 73,733,000,000 | OK | 0.0000% |
| MSFT | 343,479,000,000 | 343,479,000,000 | OK | 0.0000% |
| GOOGL | 415,265,000,000 | 4,152,650,000 | MISS | 99.0000% |
| META | 217,243,000,000 | 217,243,000 | MISS | 99.9000% |
| AMZN | 411,065,000,000 | 411,065,000 | MISS | 99.9000% |
| NVDA | 157,293,000,000 | 157,293,000,000 | OK | 0.0000% |
| JPM | 362,438,000,000 | 362,438,000,000 | OK | 0.0000% |
| KO | 34,275,000,000 | 34,275,000 | MISS | 99.9000% |
| JNJ | 81,544,000,000 | 81,544,000,000 | OK | 0.0000% |
| WMT | 105,887,000,000 | null | MISS | — |

### `cash` — accuracy 0.0% (0/0)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|

### `long_term_debt` — accuracy 0.0% (0/0)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|

### `eps_diluted` — accuracy 80.0% (8/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 7.46 | 7.46 | OK | 0.0000% |
| MSFT | 13.64 | 13.64 | OK | 0.0000% |
| GOOGL | 10.81 | 10.81 | OK | 0.0000% |
| META | 23.49 | 23.49 | OK | 0.0000% |
| AMZN | 7.17 | 7.17 | OK | 0.0000% |
| NVDA | 4.9 | 4.9 | OK | 0.0000% |
| JPM | 20.02 | 20.02 | OK | 0.0000% |
| KO | 3.04 | 3.04 | OK | 0.0000% |
| JNJ | 11.03 | null | MISS | — |
| WMT | 2.73 | null | MISS | — |

## Breakdown por empresa

### AAPL — accuracy 66.7% (4/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 416,161,000,000 | 416,161,000,000 | OK |
| net_income | 112,010,000,000 | 93,736,000,000 | MISS |
| operating_income | 133,050,000,000 | 13,305,000,000 | MISS |
| total_assets | 359,241,000,000 | 359,241,000,000 | OK |
| total_equity | 73,733,000,000 | 73,733,000,000 | OK |
| eps_diluted | 7.46 | 7.46 | OK |

### MSFT — accuracy 100.0% (6/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 281,724,000,000 | 281,724,000,000 | OK |
| net_income | 101,832,000,000 | 101,832,000,000 | OK |
| operating_income | 128,528,000,000 | 128,528,000,000 | OK |
| total_assets | 619,003,000,000 | 619,003,000,000 | OK |
| total_equity | 343,479,000,000 | 343,479,000,000 | OK |
| eps_diluted | 13.64 | 13.64 | OK |

### GOOGL — accuracy 16.7% (1/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 402,836,000,000 | 4,028,360,000 | MISS |
| net_income | 132,170,000,000 | 132,170,000 | MISS |
| operating_income | 129,039,000,000 | 129,039,000 | MISS |
| total_assets | 595,281,000,000 | 5,952,810,000 | MISS |
| total_equity | 415,265,000,000 | 4,152,650,000 | MISS |
| eps_diluted | 10.81 | 10.81 | OK |

### META — accuracy 16.7% (1/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 200,966,000,000 | 200,966,000 | MISS |
| net_income | 60,458,000,000 | 60,458,000 | MISS |
| operating_income | 83,276,000,000 | 83,276,000 | MISS |
| total_assets | 366,021,000,000 | 366,021,000 | MISS |
| total_equity | 217,243,000,000 | 217,243,000 | MISS |
| eps_diluted | 23.49 | 23.49 | OK |

### AMZN — accuracy 16.7% (1/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 716,924,000,000 | 716,924,000 | MISS |
| net_income | 77,670,000,000 | 77,670,000 | MISS |
| operating_income | 79,975,000,000 | 79,975,000 | MISS |
| total_assets | 818,042,000,000 | 818,042,000 | MISS |
| total_equity | 411,065,000,000 | 411,065,000 | MISS |
| eps_diluted | 7.17 | 7.17 | OK |

### NVDA — accuracy 100.0% (6/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 215,938,000,000 | 215,938,000,000 | OK |
| net_income | 120,067,000,000 | 120,067,000,000 | OK |
| operating_income | 130,387,000,000 | 130,387,000,000 | OK |
| total_assets | 206,803,000,000 | 206,803,000,000 | OK |
| total_equity | 157,293,000,000 | 157,293,000,000 | OK |
| eps_diluted | 4.9 | 4.9 | OK |

### JPM — accuracy 83.3% (5/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 182,447,000,000 | 182,447,000,000 | OK |
| net_income | 57,048,000,000 | 57,048,000,000 | OK |
| operating_income | null | null | OK |
| total_assets | 4,424,900,000,000 | 442,490,000,000 | MISS |
| total_equity | 362,438,000,000 | 362,438,000,000 | OK |
| eps_diluted | 20.02 | 20.02 | OK |

### KO — accuracy 16.7% (1/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 47,941,000,000 | 47,941,000 | MISS |
| net_income | 13,107,000,000 | 13,107,000 | MISS |
| operating_income | 13,762,000,000 | 13,762,000 | MISS |
| total_assets | 104,816,000,000 | 104,816,000 | MISS |
| total_equity | 34,275,000,000 | 34,275,000 | MISS |
| eps_diluted | 3.04 | 3.04 | OK |

### JNJ — accuracy 50.0% (3/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 94,193,000,000 | null | MISS |
| net_income | 26,804,000,000 | null | MISS |
| operating_income | null | null | OK |
| total_assets | 199,210,000,000 | 199,210,000,000 | OK |
| total_equity | 81,544,000,000 | 81,544,000,000 | OK |
| eps_diluted | 11.03 | null | MISS |

### WMT — accuracy 33.3% (2/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 713,163,000,000 | null | MISS |
| net_income | 21,893,000,000 | 22,270,000,000 | MISS |
| operating_income | 29,825,000,000 | 29,825,000,000 | OK |
| total_assets | 284,668,000,000 | 284,668,000,000 | OK |
| total_equity | 105,887,000,000 | null | MISS |
| eps_diluted | 2.73 | null | MISS |

## Distribución de tipos de respuesta

| categoría | n |
|---|---:|
| match | 30 |
| miss_wrong_value | 24 |
| miss_predicted_null | 6 |
