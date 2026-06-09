"""Generate paper figures and the results LaTeX table from REAL eval CSVs.

Reads the timestamped CSVs in ``experiments/output/`` (the same files that back
``docs/eval/results_real.md``) and emits, into ``docs/paper/figures/``:

* ``fig_l3_accuracy_by_metric.{pdf,png}`` — L3 accuracy per core metric.
* ``fig_approach_comparison.{pdf,png}`` — L3 vs structured vs naive baselines.

and, into ``docs/paper/``:

* ``results.tex`` — a ``booktabs`` accuracy table (per metric + overall).

All numbers come from the CSVs; nothing is hard-coded. By default the most
recent CSV per prefix is used; ``--extraction-csv/--structured-csv/--naive-csv``
pin a specific run for reproducible paper builds.

Usage:
    venv/bin/python experiments/make_figures.py
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless (WSL)
import matplotlib.pyplot as plt  # noqa: E402

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from agents._gold_schema import GOLD_METRICS  # noqa: E402

_OUTPUT_DIR = _PROJECT_ROOT / "experiments" / "output"
_FIG_DIR = _PROJECT_ROOT / "docs" / "paper" / "figures"
_RESULTS_TEX = _PROJECT_ROOT / "docs" / "paper" / "results.tex"

#: The 6 annotated core metrics (cash/long_term_debt are unannotated future work).
_CORE_METRICS: tuple[str, ...] = tuple(
    m for m in GOLD_METRICS if m not in ("cash", "long_term_debt")
)

_METRIC_LABEL: dict[str, str] = {
    "revenue": "Ingresos",
    "net_income": "Bº neto",
    "operating_income": "Bº op.",
    "total_assets": "Activos tot.",
    "total_equity": "Patrim. neto",
    "eps_diluted": "BPA diluido",
}


def _latest_csv(prefix: str, output_dir: Path = _OUTPUT_DIR) -> Path:
    """Return the most recent ``{prefix}_YYYYMMDD_HHMMSS.csv`` (lexicographic)."""
    matches = sorted(output_dir.glob(f"{prefix}_*.csv"))
    if not matches:
        raise FileNotFoundError(f"No CSV matching {prefix}_*.csv in {output_dir}")
    return matches[-1]


def load_accuracy_by_metric(csv_path: Path) -> dict[str, tuple[int, int]]:
    """Return ``metric -> (matches, total)`` for the core metrics in the CSV."""
    counts: dict[str, list[int]] = {m: [0, 0] for m in _CORE_METRICS}
    with csv_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            metric = row["metric"]
            if metric not in counts:
                continue
            counts[metric][1] += 1
            if row["match"] == "True":
                counts[metric][0] += 1
    return {m: (c[0], c[1]) for m, c in counts.items()}


def load_overall_accuracy(csv_path: Path) -> float:
    by_metric = load_accuracy_by_metric(csv_path)
    matches = sum(m for m, _ in by_metric.values())
    total = sum(t for _, t in by_metric.values())
    return matches / total if total else 0.0


def _acc_pct(matches: int, total: int) -> float:
    return 100.0 * matches / total if total else 0.0


def fig_accuracy_by_metric(extraction_csv: Path, out_dir: Path) -> Path:
    """Figure 1: L3 accuracy per core metric."""
    by_metric = load_accuracy_by_metric(extraction_csv)
    labels = [_METRIC_LABEL[m] for m in _CORE_METRICS]
    accs = [_acc_pct(*by_metric[m]) for m in _CORE_METRICS]

    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(labels, accs, color="#2a6f97")
    ax.set_ylim(0, 105)
    ax.set_ylabel("Precisión (%)")
    ax.set_title("L3 (XBRL) — precisión por métrica (N=60)")
    for bar, m in zip(bars, _CORE_METRICS):
        mt, tot = by_metric[m]
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{mt}/{tot}", ha="center", va="bottom", fontsize=8)
    plt.xticks(rotation=20, ha="right")
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / "fig_l3_accuracy_by_metric.pdf"
    fig.savefig(pdf, bbox_inches="tight")
    fig.savefig(out_dir / "fig_l3_accuracy_by_metric.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return pdf


def fig_approach_comparison(extraction_csv: Path, structured_csv: Path,
                            naive_csv: Path, out_dir: Path) -> Path:
    """Figure 2: grouped bars, L3 vs structured vs naive, per metric + overall."""
    l3 = load_accuracy_by_metric(extraction_csv)
    st = load_accuracy_by_metric(structured_csv)
    na = load_accuracy_by_metric(naive_csv)

    labels = [_METRIC_LABEL[m] for m in _CORE_METRICS] + ["GLOBAL"]
    l3_vals = [_acc_pct(*l3[m]) for m in _CORE_METRICS] + [100 * load_overall_accuracy(extraction_csv)]
    st_vals = [_acc_pct(*st[m]) for m in _CORE_METRICS] + [100 * load_overall_accuracy(structured_csv)]
    na_vals = [_acc_pct(*na[m]) for m in _CORE_METRICS] + [100 * load_overall_accuracy(naive_csv)]

    x = range(len(labels))
    w = 0.27
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar([i - w for i in x], l3_vals, w, label="L3 (XBRL)", color="#2a6f97")
    ax.bar(list(x), st_vals, w, label="LLM structured", color="#e9a23b")
    ax.bar([i + w for i in x], na_vals, w, label="LLM naive", color="#c1666b")
    ax.set_ylim(0, 105)
    ax.set_ylabel("Precisión (%)")
    ax.set_title("Precisión por enfoque (N=60)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.legend()
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / "fig_approach_comparison.pdf"
    fig.savefig(pdf, bbox_inches="tight")
    fig.savefig(out_dir / "fig_approach_comparison.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return pdf


def write_results_tex(extraction_csv: Path, structured_csv: Path,
                      naive_csv: Path, out_path: Path = _RESULTS_TEX) -> Path:
    """Emit a booktabs accuracy table sourced from the CSVs."""
    l3 = load_accuracy_by_metric(extraction_csv)
    st = load_accuracy_by_metric(structured_csv)
    na = load_accuracy_by_metric(naive_csv)

    lines = [
        "% AUTO-GENERATED by experiments/make_figures.py — do not edit by hand.",
        f"% Sources: {extraction_csv.name}, {structured_csv.name}, {naive_csv.name}",
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{Precisión de extracción por métrica (N=60): XBRL híbrido (L3) "
        "frente a baselines LLM-only, en una ejecución representativa. L3 es "
        "totalmente determinista (XBRL, sin LLM); los baselines LLM no son "
        "deterministas por seed y varían $\\pm1$--2 filas entre ejecuciones "
        "(structured observado en 50.0--51.7\\%), por lo que la brecha "
        "L3$-$structured es $\\approx$48--50\\,pp según la ejecución. Cifras "
        "regeneradas desde los CSV de evaluación.}",
        "\\label{tab:accuracy}",
        "\\begin{tabular}{lrrr}",
        "\\toprule",
        "Métrica & L3 (XBRL) & LLM structured & LLM naive \\\\",
        "\\midrule",
    ]
    for m in _CORE_METRICS:
        label = _METRIC_LABEL[m].replace("&", "\\&")
        lines.append(
            f"{label} & {_acc_pct(*l3[m]):.1f}\\% & "
            f"{_acc_pct(*st[m]):.1f}\\% & {_acc_pct(*na[m]):.1f}\\% \\\\"
        )
    lines += [
        "\\midrule",
        f"\\textbf{{Global}} & \\textbf{{{100 * load_overall_accuracy(extraction_csv):.1f}\\%}} & "
        f"\\textbf{{{100 * load_overall_accuracy(structured_csv):.1f}\\%}} & "
        f"\\textbf{{{100 * load_overall_accuracy(naive_csv):.1f}\\%}} \\\\",
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Non-data-driven paper figures (architecture diagram + qualitative finding).
# These use the SAME matplotlib palette/typography as the data figures so the
# paper is visually coherent. Numbers in the over-extraction figure are
# HUMAN-VALIDATED constants (see docs/review/l4_risk_audit.md), not CSV-derived.
# ---------------------------------------------------------------------------

_C_DET = "#2a6f97"   # deterministic (XBRL / arithmetic)
_C_LLM = "#c1666b"   # local 7B (Qwen)
_C_MIX = "#e9a23b"   # mixed (deterministic + LLM)
_C_INFRA = "#8d99ae"  # infrastructure / parsing


def fig_architecture(out_dir: Path) -> Path:
    """Pipeline L1->L7 box-and-arrow diagram, colour-coded by compute type."""
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    stages = [
        ("L1 · Ingestion", "Descarga 10-K + XBRL\n(SEC EDGAR)", _C_INFRA),
        ("L2 · Parser", "Segmenta Items 1/1A/7/8\n+ chunker Item 1A", _C_INFRA),
        ("L3 · Structured", "Métricas numéricas vía XBRL\n(sin LLM, determinista)", _C_DET),
        ("L4 · Qualitative", "Extracción de riesgos\n(Qwen 2.5 7B)", _C_LLM),
        ("L5 · Analyst", "Márgenes/ratios/YoY (det.)\n+ clasificación (7B)", _C_MIX),
        ("L7 · Writer", "Investment memo\n(Qwen 2.5 7B)", _C_LLM),
    ]
    fig, ax = plt.subplots(figsize=(3.4, 5.4))
    ax.set_xlim(0, 10); ax.set_ylim(-2.2, len(stages) * 2 + 0.5)
    ax.axis("off")
    box_w, box_h = 8.4, 1.45
    x0 = 0.8
    # L1 at top, L7 at bottom. centers[i] corresponds to reversed order
    # (i=0 -> bottom box L7, i=last -> top box L1).
    centers = []
    for i, (title, desc, color) in enumerate(reversed(stages)):
        y = 0.6 + i * 2
        box = FancyBboxPatch((x0, y), box_w, box_h,
                             boxstyle="round,pad=0.08,rounding_size=0.12",
                             linewidth=1.2, edgecolor="#333333",
                             facecolor=color, alpha=0.92)
        ax.add_patch(box)
        cx, cy = x0 + box_w / 2, y + box_h / 2
        centers.append((cx, y + box_h, y))  # (centre x, box top y, box bottom y)
        ax.text(cx, cy + 0.30, title, ha="center", va="center",
                fontsize=9.5, fontweight="bold", color="white")
        ax.text(cx, cy - 0.30, desc, ha="center", va="center",
                fontsize=7.0, color="white")
    # Data flows L1 -> ... -> L7, i.e. top box DOWN to the box below it.
    for i in range(len(stages) - 1):
        upper = centers[i + 1]   # higher box
        lower = centers[i]       # box right below
        cx = upper[0]
        ax.add_patch(FancyArrowPatch((cx, upper[2] - 0.02), (cx, lower[1] + 0.02),
                     arrowstyle="-|>", mutation_scale=12, linewidth=1.3,
                     color="#333333"))
    # legend in the reserved space below the lowest box
    from matplotlib.patches import Patch
    handles = [
        Patch(facecolor=_C_DET, label="Determinista (XBRL)"),
        Patch(facecolor=_C_LLM, label="Qwen 2.5 7B local"),
        Patch(facecolor=_C_MIX, label="Mixto"),
        Patch(facecolor=_C_INFRA, label="Ingesta/parsing"),
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.085),
              ncol=2, fontsize=6.5, frameon=False, handlelength=1.1)
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / "fig_architecture.pdf"
    fig.savefig(pdf, bbox_inches="tight")
    fig.savefig(out_dir / "fig_architecture.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return pdf


def fig_overextraction(out_dir: Path) -> Path:
    """Qualitative finding: raw L4 risk count over-states real risk factors.

    HUMAN-VALIDATED constants (docs/review/l4_risk_audit.md):
      AAPL: 27 real factors -> 68 raw sub-aspects (~2.5x), no Risk Factor Summary.
      JPM : 43 real body factors; 105 raw incl. ~16 summary-derived duplicates.
    """
    import numpy as np

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.6))

    # --- AAPL: pure body fragmentation ---
    ax = axes[0]
    bars = ax.bar(["Factores\nreales", "Sub-aspectos\ncrudos (L4)"], [27, 68],
                  color=[_C_DET, _C_LLM], width=0.6)
    ax.set_ylim(0, 80); ax.set_ylabel("Conteo")
    ax.set_title("AAPL FY2025\n(sin Risk Factor Summary)", fontsize=9)
    for b, v in zip(bars, [27, 68]):
        ax.text(b.get_x() + b.get_width() / 2, v + 1.5, str(v),
                ha="center", fontsize=9, fontweight="bold")
    ax.annotate("fragmentación\n$\\approx$2.5$\\times$", xy=(1, 68), xytext=(0.5, 50),
                ha="center", fontsize=8, color="#333333",
                arrowprops=dict(arrowstyle="->", color="#333333"))

    # --- JPM: body + summary contamination ---
    ax = axes[1]
    # raw 105 = 43 body-derived (approx) split is illustrative; show real anchors:
    # body factors (43) vs raw extracted (105) with summary-duplication slice.
    ax.bar(["Factores\nbody reales"], [43], color=_C_DET, width=0.5)
    ax.text(0, 44.5, "43", ha="center", fontsize=9, fontweight="bold")
    ax.bar(["Sub-aspectos\ncrudos (L4)"], [105 - 16], color=_C_LLM, width=0.5)
    ax.bar(["Sub-aspectos\ncrudos (L4)"], [16], bottom=[105 - 16], color=_C_MIX, width=0.5,
           label="≈ 16 del summary\n(duplican body)")
    ax.text(1, 106.5, "105", ha="center", fontsize=9, fontweight="bold")
    ax.set_ylim(0, 122); ax.set_ylabel("Conteo")
    ax.set_title("JPM FY2026\n(con Risk Factor Summary)", fontsize=9)
    ax.legend(loc="upper left", fontsize=6.5, frameon=False)

    fig.suptitle("Sobre-extracción cualitativa: el conteo crudo de L4 infla los factores reales",
                 fontsize=9.5, y=1.02)
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / "fig_overextraction.pdf"
    fig.savefig(pdf, bbox_inches="tight")
    fig.savefig(out_dir / "fig_overextraction.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return pdf


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate paper figures + results.tex from eval CSVs.")
    p.add_argument("--extraction-csv", type=Path, default=None)
    p.add_argument("--structured-csv", type=Path, default=None)
    p.add_argument("--naive-csv", type=Path, default=None)
    p.add_argument("--fig-dir", type=Path, default=_FIG_DIR)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    extraction = args.extraction_csv or _latest_csv("eval_extraction")
    structured = args.structured_csv or _latest_csv("eval_baseline_structured")
    naive = args.naive_csv or _latest_csv("eval_baseline_naive")

    print(f"extraction : {extraction.name}")
    print(f"structured : {structured.name}")
    print(f"naive      : {naive.name}")

    f1 = fig_accuracy_by_metric(extraction, args.fig_dir)
    f2 = fig_approach_comparison(extraction, structured, naive, args.fig_dir)
    f3 = fig_architecture(args.fig_dir)
    f4 = fig_overextraction(args.fig_dir)
    tex = write_results_tex(extraction, structured, naive)
    print(f"Figura 1   : {f1}")
    print(f"Figura 2   : {f2}")
    print(f"Figura 3   : {f3}")
    print(f"Figura 4   : {f4}")
    print(f"results.tex: {tex}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
