# Item 1A — Structural Scouting (AAPL / JPM / WMT)

**Tarea:** T2.2-prep (data sobre la mesa para diseñar la heurística de chunking).
**Fecha:** 2026-05-05
**Inputs:** 10-K más reciente cacheado en `data/cache/` para AAPL, JPM, WMT.
**Scope:** Solo medición. NO implementa chunking — el diseño se hace mañana en chat humano.

## Resumen ejecutivo

Los tres 10-K son **Inline XBRL** sin un solo `<h1-h6>`, `<p>`, `<b>` ni `<strong>`: toda la jerarquía visual está en `<div>` + `<span>` con `font-weight:700` como marca de "bold". Bajo la heurística H3 tal y como está escrita (≥3 palabras, ≤120 chars), AAPL detecta 8 sub-headers y JPM 12, pero **WMT colapsa a 2** porque la mayoría de sus sub-headers son frases-completas en bold de ≥130 chars (rechazadas por la cota superior) o etiquetas de 2 palabras como "Strategic Risks" (rechazadas por la cota inferior). H1 y H2 dan 0 en los tres tickers (no hay heading-tags y no hay líneas all-caps en los bodies de Item 1A modernos). El tamaño de Item 1A va de **~17k tokens (AAPL)** a **~28k tokens (JPM)**: ninguno cabe en una sola ventana de Qwen 7B (8k). JPM, único con >15k palabras, lleva un Risk Factor Summary etiquetado simplemente "Summary" con bullets `•` listando 11 categorías de riesgo pre-clasificadas — material directo para T2.6.

## A. Estructura HTML del Item 1A

Conteo de **instancias únicas** de cada tag dentro del bloque Item 1A (descendientes y ancestros del tramo entre el header de Item 1A y el header de Item 1B/Item 2):

| tag | AAPL | JPM | WMT |
|---|---:|---:|---:|
| `<h1>` | 0 | 0 | 0 |
| `<h2>` | 0 | 0 | 0 |
| `<h3>` | 0 | 0 | 0 |
| `<h4>` | 0 | 0 | 0 |
| `<h5>` | 0 | 0 | 0 |
| `<h6>` | 0 | 0 | 0 |
| `<b>` | 0 | 0 | 0 |
| `<strong>` | 0 | 0 | 0 |
| `<p>` | 0 | 0 | 0 |
| `<div>` | 143 | 818 | 158 |
| `<span>` | 124 | 1070 | 146 |
| `<table>` | 0 | 23 | 1 |
| `<ul>` / `<ol>` / `<li>` | 0 | 0 | 0 |

**Hallazgo dominante:** los tres documentos son iXBRL puro sin tags semánticos. La marca de bold vive en el atributo `style` (`font-weight:700` o `font-weight:bold`) sobre `<span>`. Los "párrafos" son `<div>` con `margin-top` / `text-align:justify`. Las listas con bullets se renderizan como caracteres `•` literales dentro de spans, no como `<ul><li>`.

**Tablas:** AAPL y WMT casi no usan tablas en Item 1A (0 y 1 respectivamente). JPM mete 23 tablas — corresponden mayoritariamente a footers/page-breaks ("Parts I and II", "31") y al tooling iXBRL, no a contenido financiero del Item 1A.

**Item 1A — tamaño absoluto:**

| Ticker | chars | palabras | tokens (chars/4) | leaves de texto |
|---|---:|---:|---:|---:|
| AAPL | 68 044 | 9 784 | ~17 011 | 124 |
| JPM | 112 517 | 15 906 | ~28 129 | 1 070 |
| WMT | 93 182 | 13 566 | ~23 295 | 247 |

JPM es el único que cruza el umbral SEC de 15 000 palabras que activa el Risk Factor Summary obligatorio.

## B. Heurísticas de sub-headers

### Conteos por ticker

H3 se generaliza a iXBRL como "el primer leaf de un bloque (`<div>`-paragraph) está dentro de un span con `font-weight ≥ 600`". Cotas de la spec original conservadas: ≥3 palabras y ≤120 chars en el texto bold del prefijo.

| Heurística | AAPL | JPM | WMT |
|---|---:|---:|---:|
| H1 (heading explícito h1-h6) | 0 | 0 | 0 |
| H2 (all-caps line) | 0 | 0 | 0 |
| H3 (bold-leading block, spec strict) | 8 | 12 | 2 |
| **Unión** | **8** | **12** | **2** |

H1 = 0 porque no hay tags `h1-h6` en iXBRL. H2 = 0 porque las líneas-cabecera no se renderizan en mayúsculas dentro del cuerpo (solo en el título "ITEM 1A. RISK FACTORS" del propio Item 1A, que excluimos por construcción). H3 hace todo el trabajo, y queda muy condicionada por las cotas.

**H3 candidatos rechazados por las cotas (diagnóstico):**

| Ticker | rechazados <3 palabras | rechazados >120 chars | total candidatos H3 brutos |
|---|---:|---:|---:|
| AAPL | 3 | 21 | 8 + 24 = **32** |
| JPM | 23 | 33 | 12 + 56 = **68** |
| WMT | 3 | 23 | 2 + 26 = **28** |

Es decir: en WMT y AAPL el detector "bold-leading" encuentra ~3-4× más bloques de los que la spec acepta. Las cotas filtran sub-headers reales.

Ejemplos verbatim de candidatos rechazados (cortos, <3 palabras):

- AAPL: "Business Risks", "Financial Risks", "General Risks"
- JPM: "Summary", "Part I", "Political"
- WMT: "Strategic Risks", "Operational Risks", "Financial Risks"

Ejemplos verbatim de candidatos rechazados (largos, >120 chars), primer fragmento ≤200 chars:

- AAPL: "The Company's operations and performance depend significantly on global and regional economic conditions and adverse eco…"
- JPM: "JPMorganChase's businesses are highly regulated and are significantly affected by applicable law and supervisory expecta…"
- WMT: "Failure to successfully execute our omnichannel strategy and the cost of our investments in eCommerce and technology may…"

### Solapamiento

Como solo H3 dispara, el solapamiento es trivial:

| Detectado por | AAPL | JPM | WMT |
|---|---:|---:|---:|
| Las 3 heurísticas | 0 | 0 | 0 |
| H1 + H2 | 0 | 0 | 0 |
| H1 + H3 | 0 | 0 | 0 |
| H2 + H3 | 0 | 0 | 0 |
| Solo H1 | 0 | 0 | 0 |
| Solo H2 | 0 | 0 | 0 |
| Solo H3 | 8 | 12 | 2 |

## C. Longitud entre sub-headers

Sobre la unión (= H3 strict). Cada gap = chars desde un sub-header hasta el siguiente; el último gap llega hasta el final de Item 1A. Tokens estimados = chars / 4.

| Ticker | mediana (chars) | P25 | P75 | max | min | mediana (toks) | max (toks) |
|---|---:|---:|---:|---:|---:|---:|---:|
| AAPL | 5 860 | 1 423 | 6 875 | 25 325 | 1 285 | 1 465 | 6 331 |
| JPM | 9 131 | 1 301 | 11 283 | 29 441 | 14 | 2 282 | 7 360 |
| WMT | 39 717 | 32 717 | 32 717 | 39 717 | 32 717 | 9 929 | 9 929 |

WMT solo tiene 2 anchors (3 gaps incluyendo el último), lo que hace que sus percentiles sean degenerados — todo el documento está prácticamente sin sub-headers reconocidos. JPM además tiene un min=14 (dos anchors casi pegados; ver casos problemáticos).

### Huecos problemáticos

Los 2-3 huecos más largos por ticker (un anchor → siguiente anchor, sin sub-header detectado en medio):

**AAPL — gap 25 325 chars (~6 331 toks)** entre `"Macroeconomic and Industry Risks"` y `"The Company's future performance depends in part on support from third-party software developers."`:

- first 100 chars: `"Macroeconomic and Industry Risks The Company's operations and performance depend significantly on gl"`
- last 100 chars: `"tation, results of operations, financial condition and stock price. Apple Inc. | 2025 Form 10-K | 9 "`

(Bloque que contiene varios sub-headers de frase-larga rechazados por la cota >120 chars: "The Company's operations and performance depend significantly on global and regional economic conditions…", etc.)

**JPM — gap 29 441 chars (~7 360 toks)** entre `"A successful cyber attack…"` y `"Competition in the financial services industry…"`:

- first 100 chars: `"A successful cyber attack could cause significant harm to JPMorganChase and its clients and customer"`
- last 100 chars: `"erties, or exiting businesses or products could be material to its results of operations. 27 Part I "`

**WMT — gap 39 717 chars (~9 929 toks)** entre `"Risks associated with our suppliers…"` y `"Legal, Tax, Regulatory, Compliance, Reputational and Other Risks"`:

- first 100 chars: `"Risks associated with our suppliers could materially adversely affect our financial performance. The"`
- last 100 chars: `"nge rates have adversely affected, and may continue to adversely affect, our results of operations. "`

(Este hueco contiene la mitad del cuerpo de Item 1A de WMT — ~10K tokens sin un solo anchor reconocido por la spec strict.)

## D. Primeros 10 sub-headers detectados

### AAPL

1. (H3) "Macroeconomic and Industry Risks"
2. (H3) "The Company's future performance depends in part on support from third-party software developers."
3. (H3) "The Company depends on the performance of carriers and other resellers."
4. (H3) "The Company's business and reputation are impacted by information technology system failures and network disruptions."
5. (H3) "Legal and Regulatory Compliance Risks"
6. (H3) "The Company's net sales and gross margins are subject to volatility and downward pressure due to a variety of factors."
7. (H3) "The Company is exposed to credit risk and fluctuations in the values of its investment portfolio."
8. (H3) "The price of the Company's stock is subject to volatility."

(Solo 8 detectados: AAPL realmente tiene ~22 sub-headers de párrafo más 4 categorías ("Business Risks", "Financial Risks", "General Risks" + "Macroeconomic"); la cota de 120 chars filtra los párrafos-cabecera largos.)

### JPM

1. (H3) "Legal and Regulatory"
2. (H3) "Holders of JPMorgan Chase & Co.'s debt and equity securities will absorb losses if it were to enter into a resolution."
3. (H3) "Unfavorable market and economic conditions could adversely affect JPMorganChase's wholesale businesses."
4. (H3) "JPMorganChase could suffer losses if the value of collateral declines."
5. (H3) "JPMorganChase could incur significant losses arising from concentrations of credit and market risk."
6. (H3) "JPMorganChase's ability to operate its businesses could be impaired if its liquidity is constrained."
7. (H3) "JPMorganChase's liquidity and cost of funding could be adversely affected by downgrades in its credit ratings."
8. (H3) "A successful cyber attack could cause significant harm to JPMorganChase and its clients and customers."
9. (H3) "Competition in the financial services industry could lead to negative effects on JPMorganChase's results of operations."
10. (H3) "Damage to JPMorganChase's reputation could negatively affect its business, results and prospects."

### WMT

1. (H3) "Risks associated with our suppliers could materially adversely affect our financial performance."
2. (H3) "Legal, Tax, Regulatory, Compliance, Reputational and Other Risks"

(Solo 2 detectados — los reales son ~25 frases-cabecera bold de longitud >120 y 4 etiquetas-categoría de 2 palabras; ambos extremos rechazados por la spec strict.)

## E. Casos problemáticos

### Sub-headers rechazados por las cotas de la spec (más graves en WMT)

Los tres filers usan dos patrones de sub-header que la spec strict deja fuera:

1. **Etiquetas-categoría de 2 palabras** (rechazadas por <3 palabras): "Strategic Risks", "Operational Risks", "Financial Risks", "Business Risks", "General Risks". Suele aparecer una por sección agrupando varios sub-riesgos. Saltarlas hace que el chunker no respete la primera capa de la jerarquía de riesgos del filer.

2. **Frases-cabecera largas** (>120 chars) rechazadas por la cota superior. Es el patrón **dominante en WMT** (donde TODO sub-header es una frase de ~130-200 chars). En AAPL y JPM también ocurre pero coexisten con sub-headers cortos.

### Falsos positivos por bold no-cabecera

JPM mete bullets bold-leading dentro del Risk Factor Summary; cada bullet empieza con una etiqueta en bold ("Legal and Regulatory", "Political", "Market", "Credit", "Liquidity", …) que NO es un sub-header del Item 1A sino un bullet del Summary. Si una heurística H3 corre sin distinguir "estoy dentro del Summary", contamos esos labels como sub-headers fantasma. Hay 10 labels así, todos en los primeros ~5K chars de Item 1A.

JPM también tiene un falso positivo único al cierre del Item 1A: `"Parts I and II"` (offset 112 503), que es el header de página repetido, no un sub-header. La heurística no lo distingue de un sub-header bold legítimo.

### Sub-headers pegados al cuerpo siguiente sin separador (`bold_leading_long_block`)

Cero ocurrencias en los tres tickers. En iXBRL cada sub-header bold vive en su propio `<div>` aislado del siguiente `<div>` de cuerpo. Esto es buena noticia para el chunker: una vez el anchor está localizado, la frontera entre header y cuerpo es nítida (cambio de div), no requiere parsing de "bold prefix" dentro de un párrafo mixto.

### Secciones largas sin sub-header (huecos C)

Resumen ya tabulado en sección C: AAPL tiene un hueco de 25 325 chars tras "Macroeconomic and Industry Risks", JPM 29 441 chars tras "A successful cyber attack…", WMT 39 717 chars (mitad de su Item 1A) tras "Risks associated with our suppliers…". En los tres casos la causa es la misma: dentro del hueco hay varios sub-headers reales que la spec strict rechazó.

## F. Risk Factors Summary post-2020

| Ticker | Presente | Posición | Bullets detectados |
|---|:---:|---|---:|
| AAPL | no | — | 0 |
| JPM | sí | Inside Item 1A (offset 678 de 112 517; etiqueta literal `"Summary"`, no `"Risk Factors Summary"`) | 8 (verbatim abajo) |
| WMT | no | — | 0 |

**AAPL** tiene Item 1A de 9 784 palabras (< 15 000), no requiere Summary.
**WMT** tiene Item 1A de 13 566 palabras (< 15 000), no requiere Summary.
**JPM** es el único con 15 906 palabras (> 15 000) y, congruente con la regla SEC, incluye un summary. La etiqueta usada NO es la frase canónica "Risk Factor(s) Summary" sino simplemente `"Summary"` seguida de la frase de transición `"The principal risk factors include:"` — habrá que detectarlo por estructura (header bold-corto + bullets) más que por literal.

### Bullets verbatim del Summary de JPM (extracto, primer fragmento ≤200 chars cada uno)

- "Political risks, including the potential negative effects on JPMorganChase's businesses due to economic uncertainty resulting from political developments."
- "Market risks, including the effects that unfavorable economic and market events and conditions, political developments, changes in interest rates and credit spreads, and market fluctuations could have"
- "Credit risks, including the effects from adverse changes in the financial condition of clients, customers, counterparties, central counterparties and other market participants; the potential for losse"
- "Liquidity risks, including the risk that JPMorganChase's ability to operate could be impaired by constrained liquidity; the dependence of JPMorgan Chase & Co. on its subsidiaries for funding; and the "
- "Capital risks, including the risk that JPMorganChase's ability to distribute capital to shareholders or to support its business activities could be limited if it does not satisfy applicable regulatory"
- "Strategic risks, including the damage to JPMorganChase's competitive standing that could result from ineffective business strategies; risks associated with the significant competition that JPMorganCha"
- "Conduct risks, including the negative impact that could result from misconduct of JPMorganChase's employees."

(El primer bullet "Legal and Regulatory risks…" se inlinea con la frase de apertura `"The principal risk factors include:"` y por eso no aparece como bullet separado en el extracto. Categorías totales en el Summary de JPM: Legal/Regulatory, Political, Market, Credit, Liquidity, Capital, Operational, Strategic, Conduct, Reputation, Country — 11 en total. Útil para T2.6.)

## Hipótesis emergentes para T2.2 (informativas, sin diseño)

1. **El detector estructural prácticamente solo puede apoyarse en bold via `font-weight ≥ 600` sobre `<span>`** (más, opcionalmente, en la sub-pista de `font-size` y `text-decoration:underline` que aparece en algunos category-labels de WMT como `"Strategic Risks"`). H1 y H2 son cero en los tres tickers, así que no aportan al fallback chain en 10-Ks modernos. (Quizá sí relevantes en otros corpus, p.ej. PDFs CNMV.)

2. **Las cotas de longitud de la spec strict son el principal cuello de botella.** Quitar la cota inferior (≥3 palabras) recupera category-labels de 2 palabras tipo "Strategic Risks" / "Financial Risks" en los tres tickers. Quitar/relajar la cota superior (≤120 chars) recupera la mayoría de WMT. La cota es razonable como filtro anti-FP pero la spec final probablemente necesita cotas distintas (p.ej. ≥2 palabras y ≤300 chars) o un esquema de dos pasos: detectar candidatos sin cota y luego segmentar por densidad.

3. **El header del Risk Factor Summary no siempre se etiqueta literalmente "Risk Factor(s) Summary".** JPM lo llama "Summary" a secas. Detectarlo por patrón "header corto bold + bullets `•` densos en los primeros ~3 000 chars de Item 1A" es más robusto que match literal.

4. **El chunker debe distinguir "dentro del Summary" vs "dentro del cuerpo principal".** Los bullet-labels del Summary son bold-leading y van a contar como sub-headers fantasma si no se aísla la zona del Summary primero. Una pasada simple: si hay Summary, recortar [start_summary, end_summary] y procesar el resto como Item 1A "real".

5. **Diferencias por industria a tener en cuenta:** banca (JPM) usa frases-cabecera mixtas (algunas cortas, algunas largas) y mete tablas dentro de Item 1A; tech (AAPL) usa categorías cortas + frases largas en proporción ~30/70; retail (WMT) usa exclusivamente frases largas + 4 categorías cortas. La heurística de chunking debe robustecerse contra el extremo "WMT" o el chunker se queda con bloques de ~10K tokens enteros sin partir.
