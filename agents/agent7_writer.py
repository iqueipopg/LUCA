"""L7 Writer agent (T3.1) — investment memo in Spanish prose.

Generates a 6-section memo from the structured upstream outputs. Numbers are
rendered deterministically (Financial Highlights table + Appendix); Qwen only
writes prose around those fixed figures, so the model never emits a financial
number. This keeps the memo factually correct even when the 7B model's prose
quality is limited (a documented, valid result on consumer hardware).

Sections (``config/agents.json::L7_writer.sections``):
    1. Resumen ejecutivo      — LLM, factual temp
    2. Visión general         — LLM, factual temp (from L2 item_1)
    3. Aspectos financieros   — deterministic table + LLM comment
    4. Análisis de riesgos    — LLM, factual temp (from L4/L5 risks)
    5. Perspectivas y guidance— LLM, outlook temp + explicit limitation note
    6. Apéndice               — deterministic, NO LLM

``forward_looking`` and ``management_tone`` are out of scope this session, so
the Outlook section carries an explicit limitation note rather than fabricated
guidance.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from agents._config import PROJECT_ROOT, get_agent_config
from agents._llm_client import LLMClient
from agents._logging import get_logger
from agents.agent5_analyst import compute_margins, compute_ratios, compute_yoy

_LOGGER = get_logger(__name__)

#: Char budget for the L2 business text fed into Company Overview (~1.5k tokens).
_BUSINESS_TEXT_BUDGET: int = 6000

_OUTLOOK_LIMITATION = (
    "_Nota de limitación: esta sección no incorpora forward-looking statements "
    "ni análisis de tono directivo (trabajo futuro); se deriva únicamente de "
    "los riesgos declarados y de las métricas extraídas._"
)

_METRIC_LABELS: dict[str, str] = {
    "revenue": "Ingresos",
    "net_income": "Beneficio neto",
    "operating_income": "Beneficio operativo",
    "total_assets": "Activos totales",
    "total_equity": "Patrimonio neto",
    "eps_diluted": "BPA diluido",
}


# ---------------------------------------------------------------------------
# Deterministic formatting
# ---------------------------------------------------------------------------


def _mval(metrics: dict[str, Any], name: str) -> float | None:
    entry = metrics.get(name)
    if isinstance(entry, dict):
        v = entry.get("value")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return None


def _fmt_money(value: float | None) -> str:
    """Format a USD figure: millions with thousands separators, EPS as-is."""
    if value is None:
        return "n/d"
    if abs(value) >= 1e6:
        return f"{value / 1e6:,.0f} M USD"
    return f"{value:,.2f} USD"


def _fmt_pct(value: float | None) -> str:
    return "n/d" if value is None else f"{value * 100:.1f}%"


def _markdown_metrics_table(metrics: dict[str, Any], margins: dict, yoy: dict) -> str:
    rows = ["| Métrica | Valor | YoY |", "|---|---|---|"]
    for key in ("revenue", "net_income", "operating_income", "total_assets",
                "total_equity", "eps_diluted"):
        label = _METRIC_LABELS[key]
        if key == "eps_diluted":
            val = _mval(metrics, key)
            value_str = "n/d" if val is None else f"{val:,.2f} USD/acción"
        else:
            value_str = _fmt_money(_mval(metrics, key))
        yoy_str = _fmt_pct(yoy.get(key, {}).get("yoy_pct")) if key in yoy else "—"
        rows.append(f"| {label} | {value_str} | {yoy_str} |")
    rows.append(f"| Margen neto | {_fmt_pct(margins.get('net_margin'))} | — |")
    rows.append(f"| Margen operativo | {_fmt_pct(margins.get('operating_margin'))} | — |")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _llm_section(client: LLMClient, system: str, user: str, *, temperature: float,
                 max_tokens: int) -> str:
    """Call Qwen for one section; degrade to a placeholder on failure."""
    try:
        return client.chat(system=system, user=user, temperature=temperature,
                            num_ctx=8192, max_tokens=max_tokens).strip()
    except Exception as exc:  # noqa: BLE001 — a failed section must not abort the memo
        _LOGGER.warning("L7 sección falló (%s)", exc)
        return "_(Sección no generada: error del modelo.)_"


_SYS_FACTUAL = (
    "Eres un analista financiero que redacta UNA sección de un investment memo "
    "en español. Usa EXCLUSIVAMENTE los datos que se te proporcionan. NUNCA "
    "inventes cifras ni datos. Devuelve prosa en Markdown, sin encabezados."
)


def write_memo(
    l3_output: dict[str, Any],
    l5_output: dict[str, Any] | None = None,
    l4_output: dict[str, Any] | None = None,
    l2_output: dict[str, Any] | None = None,
    *,
    llm_client: LLMClient | None = None,
    output_dir: Path | None = None,
    risk_factor_note: str | None = None,
) -> str:
    """Generate the investment memo, write it to disk, and return the Markdown.

    Args:
        l3_output: L3 metrics dict.
        l5_output: L5 analysis dict (derived metrics + classified risks). If
            ``None``, derived metrics are computed from L3 and risks come from
            ``l4_output``.
        l4_output: L4 dict (risks); used when ``l5_output`` is absent.
        l2_output: L2 parse dict (``item_1`` business text for the overview).
        llm_client: Injectable client (tests mock it).
        output_dir: Override for ``outputs/memos``.
        risk_factor_note: Optional human-validated risk-factor count line,
            rendered deterministically at the top of the risk-analysis section.
            The raw L4 risk count is NOT a reliable factor count (it is
            over-fragmented and, for filers with a Risk Factor Summary, inflated
            by summary↔body duplication; see docs/review/l4_risk_audit.md), so
            the count is only shown when a human passes a validated string here.
            The LLM never emits a risk count.

    Returns:
        The memo as a Markdown string.
    """
    cfg = get_agent_config("L7_writer")
    t_factual = float(cfg.get("temperature_factual", 0.2))
    t_outlook = float(cfg.get("temperature_outlook", 0.5))
    max_tok = int(cfg.get("max_output_tokens_per_section", 800))

    client = llm_client if llm_client is not None else LLMClient()

    ticker = l3_output.get("ticker", "")
    company = l3_output.get("company") or (l2_output or {}).get("company") or ticker
    fiscal_year = l3_output.get("fiscal_year")
    metrics = l3_output.get("metrics", {}) or {}
    filing_date = (l2_output or {}).get("filing_date")

    # Derived metrics: prefer L5, else compute deterministically from L3.
    if l5_output and l5_output.get("derived_metrics"):
        dm = l5_output["derived_metrics"]
        margins = dm.get("margins", {})
        ratios = dm.get("ratios", {})
        yoy = dm.get("yoy", {})
    else:
        margins = compute_margins(metrics)
        ratios = compute_ratios(metrics)
        yoy = compute_yoy(metrics, None, None)

    if l5_output and l5_output.get("risks_classified") is not None:
        risks = l5_output["risks_classified"]
    else:
        risks = (l4_output or {}).get("risks", []) or []

    # Compact fact block reused across factual sections.
    facts = (
        f"Empresa: {company} ({ticker}). Ejercicio fiscal: {fiscal_year}.\n"
        f"Ingresos: {_fmt_money(_mval(metrics, 'revenue'))}.\n"
        f"Beneficio neto: {_fmt_money(_mval(metrics, 'net_income'))}.\n"
        f"Margen neto: {_fmt_pct(margins.get('net_margin'))}; "
        f"margen operativo: {_fmt_pct(margins.get('operating_margin'))}.\n"
        f"Crecimiento YoY ingresos: {_fmt_pct(yoy.get('revenue', {}).get('yoy_pct'))}; "
        f"YoY beneficio neto: {_fmt_pct(yoy.get('net_income', {}).get('yoy_pct'))}.\n"
        # El conteo de riesgos NO se cita como dato: está pendiente de validación
        # humana (posible fragmentación por solape de chunks; ver
        # docs/review/l4_risk_audit.md). No inyectamos un número en la prosa.
        "Riesgos: la empresa declara una amplia gama de factores de riesgo "
        "(NO menciones un número total; el conteo está pendiente de validación)."
    )

    parts: list[str] = []
    parts.append(f"# Investment memo — {company} ({ticker})")
    parts.append(
        f"*Generado por LUCA (Qwen 2.5 7B local). Ejercicio fiscal {fiscal_year}. "
        f"Fecha de filing: {filing_date or 'n/d'}.*"
    )

    # 1. Resumen ejecutivo
    parts.append("## Resumen ejecutivo")
    parts.append(_llm_section(
        client, _SYS_FACTUAL,
        "Redacta un resumen ejecutivo (3-5 frases) a partir de estos datos. NO "
        f"menciones un número total de riesgos:\n{facts}",
        temperature=t_factual, max_tokens=max_tok))

    # 2. Visión general
    parts.append("## Visión general")
    business = ((l2_output or {}).get("item_1") or "").strip()
    if business:
        if len(business) > _BUSINESS_TEXT_BUDGET:
            business = business[:_BUSINESS_TEXT_BUDGET]
            _LOGGER.info("L7 %s: item_1 truncado a %d chars", ticker, _BUSINESS_TEXT_BUDGET)
        parts.append(_llm_section(
            client, _SYS_FACTUAL,
            "Resume en 3-4 frases el negocio de la empresa según este texto "
            f"(Item 1 del 10-K):\n\n{business}",
            temperature=t_factual, max_tokens=max_tok))
    else:
        parts.append("_No se dispone del texto de Item 1 (negocio) en esta ejecución._")

    # 3. Aspectos financieros (deterministic table + LLM comment)
    parts.append("## Aspectos financieros")
    table = _markdown_metrics_table(metrics, margins, yoy)
    parts.append(table)
    parts.append(_llm_section(
        client, _SYS_FACTUAL,
        "Comenta en 2-4 frases la siguiente tabla financiera. No introduzcas "
        f"cifras nuevas; interpreta solo las dadas:\n\n{table}",
        temperature=t_factual, max_tokens=max(300, max_tok // 2)))

    # 4. Análisis de riesgos
    parts.append("## Análisis de riesgos")
    if risk_factor_note:
        # Conteo validado a mano contra el filing (determinista, no del LLM).
        parts.append(risk_factor_note)
    if risks:
        risk_lines = []
        for r in risks[:12]:
            cat = r.get("category")
            cat_str = f" [{cat}]" if cat else ""
            risk_lines.append(f"- {r.get('title', '')}{cat_str}: {r.get('summary', '')}")
        risk_block = "\n".join(risk_lines)
        parts.append(_llm_section(
            client, _SYS_FACTUAL,
            "Agrupa y prioriza estos riesgos en un análisis de 4-6 frases. No "
            f"inventes riesgos nuevos:\n\n{risk_block}",
            temperature=t_factual, max_tokens=max_tok))
    else:
        parts.append("_No se ejecutó la extracción de riesgos (L4) en esta configuración._")

    # 5. Perspectivas y guidance
    parts.append("## Perspectivas y guidance")
    if risks or margins.get("net_margin") is not None:
        parts.append(_llm_section(
            client, _SYS_FACTUAL,
            "Redacta unas perspectivas prudentes (3-4 frases) basadas SOLO en "
            "los riesgos declarados y en las métricas. No inventes guidance "
            "numérica ni previsiones que no estén en los datos. NO menciones un "
            f"número total de riesgos:\n{facts}",
            temperature=t_outlook, max_tokens=max_tok))
    parts.append(_OUTLOOK_LIMITATION)

    # 6. Apéndice (deterministic, no LLM)
    parts.append("## Apéndice — métricas y trazabilidad")
    app = ["| Métrica | Valor | Tag XBRL | Período | Accession |",
           "|---|---|---|---|---|"]
    # Solo las 6 métricas core (las evaluadas contra gold, N=60). cash y
    # long_term_debt las extrae L3 a nivel de código pero NO están anotadas ni
    # evaluadas en este sprint (future work), así que no se muestran en el memo
    # para no contradecir el scope del paper.
    for key in ("revenue", "net_income", "operating_income", "total_assets",
                "total_equity", "eps_diluted"):
        entry = metrics.get(key)
        if isinstance(entry, dict):
            app.append(
                f"| {key} | {entry.get('value')} | {entry.get('tag_used')} | "
                f"{entry.get('period_end')} | {entry.get('accession')} |"
            )
        else:
            app.append(f"| {key} | n/d | — | — | — |")
    parts.append("\n".join(app))

    memo = "\n\n".join(parts) + "\n"

    out_dir = output_dir or (PROJECT_ROOT / "outputs" / "memos")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = filing_date or date.today().isoformat()
    (out_dir / f"{ticker}_{stamp}.md").write_text(memo, encoding="utf-8")
    _LOGGER.info("L7 %s: memo escrito (%d chars)", ticker, len(memo))
    return memo


__all__ = ["write_memo"]
