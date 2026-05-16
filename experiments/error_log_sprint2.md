# Sprint 2 — error log

Bitácora de incidencias detectadas mientras se construye L4 (Qualitative
Extractor) y L5 (Analyst). Cada entrada lleva timestamp ISO, tarea
origen, fixture o tag involucrado, y la hipótesis de causa, siguiendo
la convención de `experiments/error_log_sprint1.md`.

---

## 2026-05-16 — T2.2 — JPM — Ventana fija de 500 chars no detecta el Risk Factor Summary

- **Fixture:** `data/cache/JPM_0001628280-26-008131.html` (FY 2025).
- **Síntoma:** el smoke del chunker (`agents/agent4_qualitative/chunker.py`)
  devolvía `summary_present=False` y `summary_chunks=[]` para JPM, violando
  el criterio de cierre "JPM `len(summary_chunks) >= 8`" del spec
  (`docs/architecture/T2_2_chunker_spec.md`).
- **Hipótesis:** los bullets de JPM (un párrafo cada uno enumerando
  sub-riesgos) miden 300–1 000 chars; dentro de la ventana fija
  `pos + 500` solo cabía 1 bullet (delta del segundo bullet = 1 121
  chars). La ventana estaba calibrada sobre una intuición no validada
  contra el filing real.
- **Acción:** spec amendment `ed77a8c` reemplazó la ventana fija por
  "rango desde el header corto hasta el siguiente anchor L2 (o
  `item1a_start + 10000` como bound defensivo)". JPM ahora detecta los
  12 bullets reales (Legal and Regulatory … People) + 1 intro chunk =
  13 summary chunks. AAPL/WMT siguen sin disparar summary (no tienen
  `•` en Item 1A → bullet count = 0).

---

## 2026-05-16 — T2.2 — WMT — `item1a_start` cayó en una cross-reference

- **Fixture:** `data/cache/WMT_0000104169-26-000055.html` (FY 2026).
- **Síntoma:** la primera versión de `find_item1a_range` usaba
  detección bold-leading; WMT (que sí renderiza "ITEM 1A. RISK FACTORS"
  como anchor) funcionaba, pero JPM falló (JPM inlinea el header en el
  primer párrafo, no lo marca como bold). Al cambiar a búsqueda por
  texto, WMT empezó a fallar de otra manera: caía en la cross-reference
  `" Item 1A. Risk Factors " under the sub-caption "Legal, Tax, ..."`
  dentro de Item 1 ("Our Business"), recortando el rango con 14 000
  chars sobrantes al inicio.
- **Hipótesis:** los 10-K mezclan tres patrones para "Item 1A. Risk
  Factors": entrada de TOC (seguida de número de página), referencia
  cruzada (envuelta en comillas dobles), y header de cuerpo (seguido de
  prosa sustancial). La regex naive (`item\s+1a[\.\s]+risk\s+factors`,
  case insensitive) los iguala a todos.
- **Acción:** `find_item1a_range` final filtra (a) ocurrencias
  precedidas por comilla en los 5 chars previos (cross-reference), y
  (b) ocurrencias seguidas por un patrón de página/dígito en los 15
  chars siguientes (TOC entry). Los 3 fixtures resuelven al header de
  cuerpo correcto: AAPL 38 421, JPM 279 186, WMT 76 942.

---

## 2026-05-16 — T2.2 — JPM — Coverage <100 % por intro pre-Summary no asignado a ningún chunk

- **Fixture:** `data/cache/JPM_0001628280-26-008131.html` (FY 2025).
- **Síntoma:** integration test `test_chunker_jpm` falló en
  `_assert_full_coverage`: el primer chunk empezaba en 279 908 (primer
  bullet del Summary) pero `item1a_start` era 279 186. Gap de 722 chars
  no cubierto = el header "Item 1A. Risk Factors." más el párrafo
  introductorio de Item 1A.
- **Hipótesis:** el spec describe `summary_chunks` (bullets
  pre-clasificados del Summary) y `body_chunks` (cuerpo post-Summary)
  pero no define explícitamente qué chunk debe cubrir el rango
  `[item1a_start, summary_start]` cuando hay Summary. La implementación
  original empezaba `body_chunks` directamente en `summary_end`,
  dejando huérfano el tramo previo.
- **Acción:** `bc6f520` añade tres garantías:
  1. Si hay Summary y `summary_start > item1a_start`, se emite un chunk
     pre-Summary con `anchor_text=None`, `anchor_level=3`,
     `in_summary=False`.
  2. `_extract_summary_chunks` ahora emite un primer chunk
     "summary intro" para `[summary_start, primer •]`
     (`anchor_text = short_header_text`, `in_summary=True`).
  3. Post-pass de gap-filling en `chunk_item1a`: ordena todos los
     chunks por `char_start` y rellena cualquier hueco residual con un
     chunk orfan; renumera IDs en una sola pasada conservando los
     sufijos `_NNNa/b` de los sub-chunks del fallback por longitud.
  Los 3 fixtures alcanzan coverage 100 %.
