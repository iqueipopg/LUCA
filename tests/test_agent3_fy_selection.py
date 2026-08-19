"""Unit tests for agents.agent3_extractor.extract_for_fiscal_year (T5.0).

The FY-targeted selector powers the corpus scale-up run. No mocks are
needed — like ``extract``, it is a pure function over the L1 ingest
dict. The synthetic fixture models the EDGAR companyfacts quirk that
matters here: the same fiscal period appears once in its own 10-K
(``fy == Y``) and again as a comparative in the following filings
(``fy == Y+1``, possibly restated).
"""

from __future__ import annotations

from typing import Any

from agents._gold_schema import GOLD_METRICS

_ACCN_2022 = "0000000000-23-000001"
_ACCN_2023 = "0000000000-24-000001"
_ACCN_2024 = "0000000000-25-000001"


def _fact(
    val: float,
    fy: int,
    accn: str,
    end: str,
    start: str | None = None,
) -> dict[str, Any]:
    fact: dict[str, Any] = {
        "val": val,
        "fy": fy,
        "fp": "FY",
        "form": "10-K",
        "end": end,
        "accn": accn,
    }
    if start is not None:
        fact["start"] = start
    return fact


def _synthetic_facts() -> dict[str, Any]:
    """Three fiscal years of a calendar-year filer, with one restatement.

    * FY2022 revenue is 100.0 as originally reported (accn 2022) and was
      restated to 105.0 in the FY2023 filing's comparative.
    * FY2022 net income only survives as a comparative in the FY2023
      filing (no original instance) — comparative fallback case.
    * Assets (instant) repeat identically across filings — must NOT be
      logged as a restatement.
    * OperatingIncomeLoss is absent entirely.
    """
    return {
        "Revenues": {
            "units": {
                "USD": [
                    _fact(100.0, 2022, _ACCN_2022, "2022-12-31", "2022-01-01"),
                    _fact(105.0, 2023, _ACCN_2023, "2022-12-31", "2022-01-01"),
                    _fact(110.0, 2023, _ACCN_2023, "2023-12-31", "2023-01-01"),
                    _fact(110.0, 2024, _ACCN_2024, "2023-12-31", "2023-01-01"),
                    _fact(120.0, 2024, _ACCN_2024, "2024-12-31", "2024-01-01"),
                ],
            },
        },
        "NetIncomeLoss": {
            "units": {
                "USD": [
                    # No fy==2022 instance: only the FY2023 comparative.
                    _fact(9.0, 2023, _ACCN_2023, "2022-12-31", "2022-01-01"),
                    _fact(11.0, 2023, _ACCN_2023, "2023-12-31", "2023-01-01"),
                    _fact(12.0, 2024, _ACCN_2024, "2024-12-31", "2024-01-01"),
                ],
            },
        },
        "Assets": {
            "units": {
                "USD": [
                    _fact(500.0, 2022, _ACCN_2022, "2022-12-31"),
                    _fact(500.0, 2023, _ACCN_2023, "2022-12-31"),
                    _fact(550.0, 2023, _ACCN_2023, "2023-12-31"),
                    _fact(600.0, 2024, _ACCN_2024, "2024-12-31"),
                ],
            },
        },
    }


def _make_ingest(us_gaap: dict[str, Any]) -> dict[str, Any]:
    return {
        "company": "Synthetic Corp",
        "ticker": "SYN",
        "xbrl_data": {"facts": {"us-gaap": us_gaap}},
    }


class TestOriginalPreferred:
    def test_fy2022_revenue_keeps_as_originally_reported(self):
        """The restated comparative (105.0) must lose to the original (100.0)."""
        from agents.agent3_extractor import extract_for_fiscal_year

        result = extract_for_fiscal_year(_make_ingest(_synthetic_facts()), 2022)

        revenue = result["metrics"]["revenue"]
        assert revenue is not None
        assert revenue["value"] == 100.0
        assert revenue["source"] == "original"
        assert revenue["source_fy"] == 2022
        assert revenue["accession"] == _ACCN_2022
        assert revenue["period_end"] == "2022-12-31"

    def test_fy2022_restatement_is_logged(self):
        """The 105.0 restated comparative must appear under restatements."""
        from agents.agent3_extractor import extract_for_fiscal_year

        result = extract_for_fiscal_year(_make_ingest(_synthetic_facts()), 2022)

        revenue_restatements = [
            r for r in result["restatements"] if r["metric"] == "revenue"
        ]
        assert len(revenue_restatements) == 1
        entry = revenue_restatements[0]
        assert entry["original_value"] == 100.0
        assert entry["restated_value"] == 105.0
        assert entry["restated_fy"] == 2023
        assert entry["restated_accession"] == _ACCN_2023

    def test_identical_comparative_is_not_a_restatement(self):
        """Assets repeat with the same value in the next filing — no log entry."""
        from agents.agent3_extractor import extract_for_fiscal_year

        result = extract_for_fiscal_year(_make_ingest(_synthetic_facts()), 2022)

        assert not [
            r for r in result["restatements"] if r["metric"] == "total_assets"
        ]


class TestComparativeFallback:
    def test_fy2022_net_income_falls_back_to_comparative(self):
        """With no fy==2022 instance, the FY2023 comparative is used and marked."""
        from agents.agent3_extractor import extract_for_fiscal_year

        result = extract_for_fiscal_year(_make_ingest(_synthetic_facts()), 2022)

        net_income = result["metrics"]["net_income"]
        assert net_income is not None
        assert net_income["value"] == 9.0
        assert net_income["source"] == "comparative"
        assert net_income["source_fy"] == 2023


class TestAbsentAndAnchor:
    def test_absent_metric_is_none(self):
        """OperatingIncomeLoss is missing from the fixture entirely."""
        from agents.agent3_extractor import extract_for_fiscal_year

        result = extract_for_fiscal_year(_make_ingest(_synthetic_facts()), 2022)

        assert result["metrics"]["operating_income"] is None

    def test_filing_accession_matches_fy_own_10k(self):
        """Top-level accession must be the fiscal year's own 10-K."""
        from agents.agent3_extractor import extract_for_fiscal_year

        result = extract_for_fiscal_year(_make_ingest(_synthetic_facts()), 2024)

        assert result["accession"] == _ACCN_2024
        assert result["period_end"] == "2024-12-31"

    def test_unavailable_fiscal_year_yields_all_none(self):
        """A fiscal year with no 10-K facts returns None for everything."""
        from agents.agent3_extractor import extract_for_fiscal_year

        result = extract_for_fiscal_year(_make_ingest(_synthetic_facts()), 2019)

        assert result["period_end"] is None
        assert result["accession"] is None
        assert all(v is None for v in result["metrics"].values())
        assert result["restatements"] == []

    def test_default_metric_set_is_gold_metrics(self):
        """Without an explicit metrics arg the GOLD_METRICS set is used."""
        from agents.agent3_extractor import extract_for_fiscal_year

        result = extract_for_fiscal_year(_make_ingest(_synthetic_facts()), 2023)

        assert set(result["metrics"].keys()) == set(GOLD_METRICS)

    def test_custom_metric_subset(self):
        """An explicit metrics tuple restricts the output keys."""
        from agents.agent3_extractor import extract_for_fiscal_year

        result = extract_for_fiscal_year(
            _make_ingest(_synthetic_facts()), 2023, metrics=("revenue",),
        )

        assert set(result["metrics"].keys()) == {"revenue"}
        assert result["metrics"]["revenue"]["value"] == 110.0
