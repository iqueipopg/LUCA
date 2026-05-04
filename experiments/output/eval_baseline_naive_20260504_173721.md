# T1.9 — Baseline LLM (naive) vs gold standard

Generado: 2026-05-04T17:37:21

CSV detallado: `eval_baseline_naive_20260504_173721.csv`

Prompt: `config/prompts/baseline_extraction.txt`


## Modo de input

- Modo: **naive**
- Tickers evaluados: **10**
- Llamadas LLM con respuesta: **10/10**
- Tamaño medio de contenido: **40,007 chars** (~10,002 tokens estimados)
- Tiempo medio por llamada: **8.8 s**

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
| GOOGL | 350,018,000,000 | 216,890,000,000 | MISS | 38.0346% |
| META | 164,501,000,000 | 391,035,000,000 | MISS | 137.7098% |
| AMZN | 637,959,000,000 | 391,035,000,000 | MISS | 38.7053% |
| NVDA | 215,938,000,000 | 102,639,000,000 | MISS | 52.4683% |
| JPM | 182,447,000,000 | null | MISS | — |
| KO | 47,941,000,000 | 391,035,000,000 | MISS | 715.6588% |
| JNJ | 94,193,000,000 | null | MISS | — |
| WMT | 713,163,000,000 | 601,839,000,000 | MISS | 15.6099% |

### `net_income` — accuracy 0.0% (0/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 112,010,000,000 | null | MISS | — |
| MSFT | 101,832,000,000 | null | MISS | — |
| GOOGL | 100,118,000,000 | 34,720,000,000 | MISS | 65.3209% |
| META | 62,360,000,000 | 24,768,000,000 | MISS | 60.2822% |
| AMZN | 59,248,000,000 | 26,784,000,000 | MISS | 54.7934% |
| NVDA | 120,067,000,000 | 27,842,000,000 | MISS | 76.8113% |
| JPM | 57,048,000,000 | null | MISS | — |
| KO | 13,137,000,000 | 24,768,000,000 | MISS | 88.5362% |
| JNJ | 26,804,000,000 | null | MISS | — |
| WMT | 22,270,000,000 | 24,729,000,000 | MISS | 11.0418% |

### `operating_income` — accuracy 20.0% (2/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 133,050,000,000 | null | MISS | — |
| MSFT | 128,528,000,000 | null | MISS | — |
| GOOGL | 112,390,000,000 | 51,850,000,000 | MISS | 53.8660% |
| META | 69,380,000,000 | 29,468,000,000 | MISS | 57.5267% |
| AMZN | 68,593,000,000 | 13,483,000,000 | MISS | 80.3435% |
| NVDA | 130,387,000,000 | 35,827,000,000 | MISS | 72.5226% |
| JPM | null | null | OK | — |
| KO | 13,762,000,000 | 28,022,000,000 | MISS | 103.6187% |
| JNJ | null | null | OK | — |
| WMT | 29,825,000,000 | 159,920,000,000 | MISS | 436.1945% |

### `total_assets` — accuracy 0.0% (0/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 359,241,000,000 | null | MISS | — |
| MSFT | 619,003,000,000 | null | MISS | — |
| GOOGL | 450,256,000,000 | null | MISS | — |
| META | 276,054,000,000 | null | MISS | — |
| AMZN | 624,894,000,000 | null | MISS | — |
| NVDA | 206,803,000,000 | 126,642,000,000 | MISS | 38.7620% |
| JPM | 4,424,900,000,000 | null | MISS | — |
| KO | 104,816,000,000 | 152,551,000,000 | MISS | 45.5417% |
| JNJ | 199,210,000,000 | null | MISS | — |
| WMT | 284,668,000,000 | 422,891,000,000 | MISS | 48.5559% |

### `total_equity` — accuracy 0.0% (0/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 73,733,000,000 | null | MISS | — |
| MSFT | 343,479,000,000 | null | MISS | — |
| GOOGL | 325,084,000,000 | null | MISS | — |
| META | 182,637,000,000 | null | MISS | — |
| AMZN | 285,970,000,000 | null | MISS | — |
| NVDA | 157,293,000,000 | 69,084,000,000 | MISS | 56.0794% |
| JPM | 362,438,000,000 | null | MISS | — |
| KO | 34,275,000,000 | 93,975,000,000 | MISS | 174.1794% |
| JNJ | 81,544,000,000 | null | MISS | — |
| WMT | 105,887,000,000 | 366,823,000,000 | MISS | 246.4287% |

### `eps_diluted` — accuracy 0.0% (0/10)

| ticker | gold | predicted | match | rel_error |
|---|---:|---:|:---:|---:|
| AAPL | 7.46 | 6.13 | MISS | 17.8284% |
| MSFT | 13.64 | null | MISS | — |
| GOOGL | 8.04 | 6.13 | MISS | 23.7562% |
| META | 23.86 | 6.13 | MISS | 74.3085% |
| AMZN | 5.53 | 6.13 | MISS | 10.8499% |
| NVDA | 4.9 | 6.13 | MISS | 25.1020% |
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
| revenue | 350,018,000,000 | 216,890,000,000 | MISS |
| net_income | 100,118,000,000 | 34,720,000,000 | MISS |
| operating_income | 112,390,000,000 | 51,850,000,000 | MISS |
| total_assets | 450,256,000,000 | null | MISS |
| total_equity | 325,084,000,000 | null | MISS |
| eps_diluted | 8.04 | 6.13 | MISS |

### META — accuracy 0.0% (0/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 164,501,000,000 | 391,035,000,000 | MISS |
| net_income | 62,360,000,000 | 24,768,000,000 | MISS |
| operating_income | 69,380,000,000 | 29,468,000,000 | MISS |
| total_assets | 276,054,000,000 | null | MISS |
| total_equity | 182,637,000,000 | null | MISS |
| eps_diluted | 23.86 | 6.13 | MISS |

### AMZN — accuracy 0.0% (0/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 637,959,000,000 | 391,035,000,000 | MISS |
| net_income | 59,248,000,000 | 26,784,000,000 | MISS |
| operating_income | 68,593,000,000 | 13,483,000,000 | MISS |
| total_assets | 624,894,000,000 | null | MISS |
| total_equity | 285,970,000,000 | null | MISS |
| eps_diluted | 5.53 | 6.13 | MISS |

### NVDA — accuracy 0.0% (0/6)

| metric | gold | predicted | match |
|---|---:|---:|:---:|
| revenue | 215,938,000,000 | 102,639,000,000 | MISS |
| net_income | 120,067,000,000 | 27,842,000,000 | MISS |
| operating_income | 130,387,000,000 | 35,827,000,000 | MISS |
| total_assets | 206,803,000,000 | 126,642,000,000 | MISS |
| total_equity | 157,293,000,000 | 69,084,000,000 | MISS |
| eps_diluted | 4.9 | 6.13 | MISS |

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
| net_income | 13,137,000,000 | 24,768,000,000 | MISS |
| operating_income | 13,762,000,000 | 28,022,000,000 | MISS |
| total_assets | 104,816,000,000 | 152,551,000,000 | MISS |
| total_equity | 34,275,000,000 | 93,975,000,000 | MISS |
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
| revenue | 713,163,000,000 | 601,839,000,000 | MISS |
| net_income | 22,270,000,000 | 24,729,000,000 | MISS |
| operating_income | 29,825,000,000 | 159,920,000,000 | MISS |
| total_assets | 284,668,000,000 | 422,891,000,000 | MISS |
| total_equity | 105,887,000,000 | 366,823,000,000 | MISS |
| eps_diluted | 2.73 | null | MISS |

## Distribución de tipos de respuesta

| categoría | n |
|---|---:|
| miss_wrong_value | 30 |
| miss_predicted_null | 28 |
| match | 2 |
