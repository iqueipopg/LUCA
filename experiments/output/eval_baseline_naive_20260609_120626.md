# T1.9 — Baseline LLM (naive) vs gold standard

Generado: 2026-06-09T12:06:26

CSV detallado: `eval_baseline_naive_20260609_120626.csv`

Prompt: `config/prompts/baseline_extraction.txt`


## Modo de input

- Modo: **naive**
- Tickers evaluados: **10**
- Llamadas LLM con respuesta: **10/10**
- Tamaño medio de contenido: **40,007 chars** (~10,002 tokens estimados)
- Tiempo medio por llamada: **9.0 s**

## Resumen agregado

- Pares evaluados: **60**
- Coincidencias: **2**
- Accuracy global: **3.3%** (2/60)

## Breakdown por métrica

### `revenue` — accuracy 0.0% (0/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 416,161,000,000 | null | MISS | — |
| MSFT | 281,724,000,000 | null | MISS | — |
| GOOGL | 402,836,000,000 | 231,860,000,000 | MISS | 42.4431% |
| META | 200,966,000,000 | 279,800,000,000 | MISS | 39.2275% |
| AMZN | 716,924,000,000 | 391,035,000,000 | MISS | 45.4566% |
| NVDA | 215,938,000,000 | 102,869,000,000 | MISS | 52.3618% |
| JPM | 182,447,000,000 | null | MISS | — |
| KO | 47,941,000,000 | 391,035,000,000 | MISS | 715.6588% |
| JNJ | 94,193,000,000 | null | MISS | — |
| WMT | 713,163,000,000 | 568,900,000,000 | MISS | 20.2286% |

### `net_income` — accuracy 0.0% (0/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 112,010,000,000 | null | MISS | — |
| MSFT | 101,832,000,000 | null | MISS | — |
| GOOGL | 132,170,000,000 | 47,920,000,000 | MISS | 63.7437% |
| META | 60,458,000,000 | 34,610,000,000 | MISS | 42.7536% |
| AMZN | 77,670,000,000 | 26,748,000,000 | MISS | 65.5620% |
| NVDA | 120,067,000,000 | 34,755,000,000 | MISS | 71.0537% |
| JPM | 57,048,000,000 | null | MISS | — |
| KO | 13,107,000,000 | 24,876,000,000 | MISS | 89.7917% |
| JNJ | 26,804,000,000 | null | MISS | — |
| WMT | 21,893,000,000 | 32,410,000,000 | MISS | 48.0382% |

### `operating_income` — accuracy 20.0% (2/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 133,050,000,000 | null | MISS | — |
| MSFT | 128,528,000,000 | null | MISS | — |
| GOOGL | 129,039,000,000 | 58,830,000,000 | MISS | 54.4091% |
| META | 83,276,000,000 | 56,810,000,000 | MISS | 31.7811% |
| AMZN | 79,975,000,000 | 12,205,000,000 | MISS | 84.7390% |
| NVDA | 130,387,000,000 | 46,253,000,000 | MISS | 64.5264% |
| JPM | null | null | OK | — |
| KO | 13,762,000,000 | 26,914,000,000 | MISS | 95.5675% |
| JNJ | null | null | OK | — |
| WMT | 29,825,000,000 | 17,310,000,000 | MISS | 41.9614% |

### `total_assets` — accuracy 0.0% (0/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 359,241,000,000 | null | MISS | — |
| MSFT | 619,003,000,000 | null | MISS | — |
| GOOGL | 595,281,000,000 | null | MISS | — |
| META | 366,021,000,000 | null | MISS | — |
| AMZN | 818,042,000,000 | 342,530,000,000 | MISS | 58.1281% |
| NVDA | 206,803,000,000 | null | MISS | — |
| JPM | 4,424,900,000,000 | null | MISS | — |
| KO | 104,816,000,000 | 138,281,000,000 | MISS | 31.9274% |
| JNJ | 199,210,000,000 | null | MISS | — |
| WMT | 284,668,000,000 | 422,200,000,000 | MISS | 48.3131% |

### `total_equity` — accuracy 0.0% (0/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 73,733,000,000 | null | MISS | — |
| MSFT | 343,479,000,000 | null | MISS | — |
| GOOGL | 415,265,000,000 | null | MISS | — |
| META | 217,243,000,000 | null | MISS | — |
| AMZN | 411,065,000,000 | 219,770,000,000 | MISS | 46.5364% |
| NVDA | 157,293,000,000 | null | MISS | — |
| JPM | 362,438,000,000 | null | MISS | — |
| KO | 34,275,000,000 | 56,857,000,000 | MISS | 65.8848% |
| JNJ | 81,544,000,000 | null | MISS | — |
| WMT | 105,887,000,000 | 196,500,000,000 | MISS | 85.5752% |

### `cash` — accuracy 0.0% (0/0)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|

### `long_term_debt` — accuracy 0.0% (0/0)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|

### `eps_diluted` — accuracy 0.0% (0/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 7.46 | 6.13 | MISS | 17.8284% |
| MSFT | 13.64 | null | MISS | — |
| GOOGL | 10.81 | 6.13 | MISS | 43.2932% |
| META | 23.49 | 6.13 | MISS | 73.9038% |
| AMZN | 7.17 | 6.13 | MISS | 14.5049% |
| NVDA | 4.9 | 18.9 | MISS | 285.7143% |
| JPM | 20.02 | null | MISS | — |
| KO | 3.04 | null | MISS | — |
| JNJ | 11.03 | 6.13 | MISS | 44.4243% |
| WMT | 2.73 | null | MISS | — |

## Breakdown por empresa

### AAPL — accuracy 0.0% (0/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 416,161,000,000 | null | MISS |
| net_income | 112,010,000,000 | null | MISS |
| operating_income | 133,050,000,000 | null | MISS |
| total_assets | 359,241,000,000 | null | MISS |
| total_equity | 73,733,000,000 | null | MISS |
| eps_diluted | 7.46 | 6.13 | MISS |

### MSFT — accuracy 0.0% (0/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 281,724,000,000 | null | MISS |
| net_income | 101,832,000,000 | null | MISS |
| operating_income | 128,528,000,000 | null | MISS |
| total_assets | 619,003,000,000 | null | MISS |
| total_equity | 343,479,000,000 | null | MISS |
| eps_diluted | 13.64 | null | MISS |

### GOOGL — accuracy 0.0% (0/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 402,836,000,000 | 231,860,000,000 | MISS |
| net_income | 132,170,000,000 | 47,920,000,000 | MISS |
| operating_income | 129,039,000,000 | 58,830,000,000 | MISS |
| total_assets | 595,281,000,000 | null | MISS |
| total_equity | 415,265,000,000 | null | MISS |
| eps_diluted | 10.81 | 6.13 | MISS |

### META — accuracy 0.0% (0/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 200,966,000,000 | 279,800,000,000 | MISS |
| net_income | 60,458,000,000 | 34,610,000,000 | MISS |
| operating_income | 83,276,000,000 | 56,810,000,000 | MISS |
| total_assets | 366,021,000,000 | null | MISS |
| total_equity | 217,243,000,000 | null | MISS |
| eps_diluted | 23.49 | 6.13 | MISS |

### AMZN — accuracy 0.0% (0/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 716,924,000,000 | 391,035,000,000 | MISS |
| net_income | 77,670,000,000 | 26,748,000,000 | MISS |
| operating_income | 79,975,000,000 | 12,205,000,000 | MISS |
| total_assets | 818,042,000,000 | 342,530,000,000 | MISS |
| total_equity | 411,065,000,000 | 219,770,000,000 | MISS |
| eps_diluted | 7.17 | 6.13 | MISS |

### NVDA — accuracy 0.0% (0/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 215,938,000,000 | 102,869,000,000 | MISS |
| net_income | 120,067,000,000 | 34,755,000,000 | MISS |
| operating_income | 130,387,000,000 | 46,253,000,000 | MISS |
| total_assets | 206,803,000,000 | null | MISS |
| total_equity | 157,293,000,000 | null | MISS |
| eps_diluted | 4.9 | 18.9 | MISS |

### JPM — accuracy 16.7% (1/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 182,447,000,000 | null | MISS |
| net_income | 57,048,000,000 | null | MISS |
| operating_income | null | null | OK |
| total_assets | 4,424,900,000,000 | null | MISS |
| total_equity | 362,438,000,000 | null | MISS |
| eps_diluted | 20.02 | null | MISS |

### KO — accuracy 0.0% (0/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 47,941,000,000 | 391,035,000,000 | MISS |
| net_income | 13,107,000,000 | 24,876,000,000 | MISS |
| operating_income | 13,762,000,000 | 26,914,000,000 | MISS |
| total_assets | 104,816,000,000 | 138,281,000,000 | MISS |
| total_equity | 34,275,000,000 | 56,857,000,000 | MISS |
| eps_diluted | 3.04 | null | MISS |

### JNJ — accuracy 16.7% (1/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 94,193,000,000 | null | MISS |
| net_income | 26,804,000,000 | null | MISS |
| operating_income | null | null | OK |
| total_assets | 199,210,000,000 | null | MISS |
| total_equity | 81,544,000,000 | null | MISS |
| eps_diluted | 11.03 | 6.13 | MISS |

### WMT — accuracy 0.0% (0/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 713,163,000,000 | 568,900,000,000 | MISS |
| net_income | 21,893,000,000 | 32,410,000,000 | MISS |
| operating_income | 29,825,000,000 | 17,310,000,000 | MISS |
| total_assets | 284,668,000,000 | 422,200,000,000 | MISS |
| total_equity | 105,887,000,000 | 196,500,000,000 | MISS |
| eps_diluted | 2.73 | null | MISS |

## Distribución de tipos de respuesta

| categoría | n |
|---|---:|
| miss_wrong_value | 30 |
| miss_predicted_null | 28 |
| match | 2 |
