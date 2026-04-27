"""Unit tests for agents.agent3_extractor.extract.

T1.3 covers the primary US-GAAP mapping; T1.4 adds tests for the ordered
fallback chain. T1.5 covers most-recent-across-chain selection,
period/currency handling and accession propagation. No mocks are needed
here — the extractor is a pure function over the L1 ingest dict.
"""

from __future__ import annotations

from typing import Any

from agents._gold_schema import GOLD_METRICS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ingest(
    xbrl_data: dict[str, Any] | None = None,
    *,
    company: str = "Apple Inc.",
    ticker: str = "AAPL",
) -> dict[str, Any]:
    """Build a minimal ingest_output dict for extract()."""
    return {
        "company": company,
        "ticker": ticker,
        "filing_date": "2025-10-31",
        "html_content": "",
        "xbrl_data": xbrl_data if xbrl_data is not None else {},
        "accession_number": None,
        "cik": "0000320193",
        "source_urls": {},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExtractAaplFixture:
    def test_extract_returns_all_six_metrics_with_numeric_value(
        self, companyfacts_aapl
    ):
        """extract() with the AAPL fixture must populate every gold metric
        with a numeric value via its primary US-GAAP tag.
        """
        from agents.agent3_extractor import extract

        result = extract(_make_ingest(xbrl_data=companyfacts_aapl))

        assert set(result["metrics"].keys()) == set(GOLD_METRICS)
        for metric in GOLD_METRICS:
            entry = result["metrics"][metric]
            assert entry is not None, f"{metric} should not be None for AAPL fixture"
            assert isinstance(entry["value"], float), (
                f"{metric} value must be float, got {type(entry['value']).__name__}"
            )
            assert entry["tag_used"], f"{metric} must record the tag used"
            assert entry["period_end"], f"{metric} must record period_end"
            assert entry["unit"] in {"USD", "USD/shares"}

    def test_extract_top_level_fiscal_year_is_int(self, companyfacts_aapl):
        """Top-level fiscal_year must be an int when at least one metric was
        extracted from the AAPL fixture.
        """
        from agents.agent3_extractor import extract

        result = extract(_make_ingest(xbrl_data=companyfacts_aapl))

        assert isinstance(result["fiscal_year"], int)


class TestExtractEmptyXbrl:
    def test_extract_empty_xbrl_returns_all_none(self):
        """extract() with xbrl_data={} must return every metric as None and
        not raise.
        """
        from agents.agent3_extractor import extract

        result = extract(_make_ingest(xbrl_data={}))

        assert set(result["metrics"].keys()) == set(GOLD_METRICS)
        for metric in GOLD_METRICS:
            assert result["metrics"][metric] is None
        assert result["fiscal_year"] is None

    def test_extract_missing_xbrl_key_returns_all_none(self):
        """extract() with no xbrl_data key at all must still degrade
        gracefully and return all metrics as None.
        """
        from agents.agent3_extractor import extract

        ingest = _make_ingest()
        ingest.pop("xbrl_data", None)
        result = extract(ingest)

        for metric in GOLD_METRICS:
            assert result["metrics"][metric] is None


class TestExtractWrongCurrency:
    def test_extract_returns_none_when_unit_is_not_usd(self):
        """A tag present only in EUR (not USD) must yield None for that
        metric — currency filtering is part of the T1.3 contract.
        """
        from agents.agent3_extractor import extract

        eur_only_xbrl = {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "EUR": [
                                {
                                    "start": "2024-01-01",
                                    "end": "2024-12-31",
                                    "val": 100_000_000,
                                    "fy": 2024,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "accn": "0000000000-00-000000",
                                },
                            ],
                        },
                    },
                },
            },
        }

        result = extract(_make_ingest(xbrl_data=eur_only_xbrl))

        assert result["metrics"]["revenue"] is None


class TestExtractPropagatesMetadata:
    def test_extract_propagates_company_and_ticker(self, companyfacts_aapl):
        """company and ticker on the output must mirror those on the
        ingest_output input.
        """
        from agents.agent3_extractor import extract

        result = extract(
            _make_ingest(
                xbrl_data=companyfacts_aapl,
                company="Apple Inc.",
                ticker="AAPL",
            )
        )

        assert result["company"] == "Apple Inc."
        assert result["ticker"] == "AAPL"


# ---------------------------------------------------------------------------
# T1.4 — fallback chain tests
# ---------------------------------------------------------------------------


def _annual_usd_fact(
    *,
    start: str,
    end: str,
    val: float,
    fy: int,
    accn: str = "0000000000-00-000000",
) -> dict[str, Any]:
    """Build a minimal annual 10-K USD fact for a duration tag."""
    return {
        "start": start,
        "end": end,
        "val": val,
        "accn": accn,
        "fy": fy,
        "fp": "FY",
        "form": "10-K",
        "filed": end,
    }


def _wrap_us_gaap(tag_units: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Wrap a ``{tag: {unit: [facts]}}`` dict into the full xbrl_data shape."""
    us_gaap = {
        tag: {"label": tag, "units": units}
        for tag, units in tag_units.items()
    }
    return {"facts": {"us-gaap": us_gaap}}


class TestExtractFallbackChain:
    def test_revenue_falls_back_to_asc606_tag_when_primary_missing(self):
        """When the primary tag (``Revenues``) has no facts but the ASC-606
        fallback (``RevenueFromContractWithCustomerExcludingAssessedTax``)
        does, ``extract`` must use the fallback and record it in
        ``tag_used``. This is the exact scenario for AAPL FY25.
        """
        from agents.agent3_extractor import extract

        xbrl = _wrap_us_gaap(
            {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "USD": [
                        _annual_usd_fact(
                            start="2024-09-29",
                            end="2025-09-27",
                            val=416_161_000_000,
                            fy=2025,
                        ),
                    ],
                },
            }
        )

        result = extract(_make_ingest(xbrl_data=xbrl))

        revenue = result["metrics"]["revenue"]
        assert revenue is not None
        assert revenue["value"] == 416_161_000_000.0
        assert revenue["tag_used"] == (
            "RevenueFromContractWithCustomerExcludingAssessedTax"
        )
        assert revenue["fiscal_year"] == 2025
        assert revenue["unit"] == "USD"

    def test_primary_tag_wins_on_tie_when_both_have_same_end_date(self):
        """Under T1.5, the most recent fact across the *whole* candidate
        chain wins. Ties on ``end`` are broken by tag priority — the
        primary tag (earliest in ``_TAG_CANDIDATES``) wins. This test
        replaces the T1.4 behaviour where the primary always won.
        """
        from agents.agent3_extractor import extract

        # Both tags expose a fact with the same end date. Primary must
        # win the tie-break.
        xbrl = _wrap_us_gaap(
            {
                "Revenues": {
                    "USD": [
                        _annual_usd_fact(
                            start="2024-09-29",
                            end="2025-09-27",
                            val=391_035_000_000,
                            fy=2025,
                        ),
                    ],
                },
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "USD": [
                        _annual_usd_fact(
                            start="2024-09-29",
                            end="2025-09-27",
                            val=416_161_000_000,
                            fy=2025,
                        ),
                    ],
                },
            }
        )

        result = extract(_make_ingest(xbrl_data=xbrl))

        revenue = result["metrics"]["revenue"]
        assert revenue is not None
        assert revenue["tag_used"] == "Revenues"
        assert revenue["value"] == 391_035_000_000.0

    def test_returns_none_when_no_candidate_tag_resolves(self):
        """If neither the primary nor any fallback tag has a usable annual
        USD fact, the metric must be ``None`` and other metrics must remain
        unaffected.
        """
        from agents.agent3_extractor import extract

        # Only an unrelated tag is present; nothing in the ``revenue``
        # candidate chain (Revenues, RevenueFromContract..., SalesRevenueNet)
        # is there.
        xbrl = _wrap_us_gaap(
            {
                "Assets": {
                    "USD": [
                        {
                            "end": "2025-09-27",
                            "val": 359_241_000_000,
                            "accn": "0000000000-00-000000",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2025-10-31",
                        },
                    ],
                },
            }
        )

        result = extract(_make_ingest(xbrl_data=xbrl))

        assert result["metrics"]["revenue"] is None
        # Sanity: assets should still resolve from its own (single) tag.
        assert result["metrics"]["total_assets"] is not None

    def test_revenue_uses_third_fallback_when_only_sales_revenue_net_present(
        self,
    ):
        """Pre-2018 filings sometimes only carry the deprecated
        ``SalesRevenueNet`` tag. The third fallback in the chain must
        resolve them.
        """
        from agents.agent3_extractor import extract

        xbrl = _wrap_us_gaap(
            {
                "SalesRevenueNet": {
                    "USD": [
                        _annual_usd_fact(
                            start="2014-09-28",
                            end="2015-09-26",
                            val=233_715_000_000,
                            fy=2015,
                        ),
                    ],
                },
            }
        )

        result = extract(_make_ingest(xbrl_data=xbrl))

        revenue = result["metrics"]["revenue"]
        assert revenue is not None
        assert revenue["tag_used"] == "SalesRevenueNet"
        assert revenue["fiscal_year"] == 2015

    def test_aapl_fixture_revenue_resolves_to_asc606_fy2025_under_t15(
        self, companyfacts_aapl
    ):
        """End-to-end on the AAPL fixture under T1.5 selection.

        The fixture carries valid annual facts in three revenue
        candidates: ``Revenues`` (FY2017, end 2017-09-30),
        ``RevenueFromContractWithCustomerExcludingAssessedTax`` (FY2025,
        end 2025-09-27) and ``SalesRevenueNet`` (FY2015, end
        2015-09-26). T1.5's selection rule — *"most recent fact across
        the whole candidate chain wins"* — must pick the ASC-606 FY2025
        fact at 416.161B USD.

        This test replaces the T1.4 pin
        (``test_aapl_fixture_revenue_still_resolves_with_legacy_revenues_tag``)
        which captured the old "first candidate wins" semantics. The
        T1.4 entry in ``experiments/error_log_sprint1.md`` documents the
        rationale for the change.
        """
        from agents.agent3_extractor import extract

        result = extract(_make_ingest(xbrl_data=companyfacts_aapl))

        revenue = result["metrics"]["revenue"]
        assert revenue is not None
        assert revenue["tag_used"] == (
            "RevenueFromContractWithCustomerExcludingAssessedTax"
        )
        assert revenue["period_end"] == "2025-09-27"
        assert revenue["fiscal_year"] == 2025
        assert revenue["value"] == 416_161_000_000.0


# ---------------------------------------------------------------------------
# T1.5 — period + currency handling
# ---------------------------------------------------------------------------


class TestExtractMostRecentAcrossChain:
    def test_fallback_wins_when_more_recent_than_primary(self):
        """Critical T1.5 scenario (the AAPL bug from T1.4):

        ``Revenues`` carries a FY2017 fact and
        ``RevenueFromContractWithCustomerExcludingAssessedTax`` carries
        a FY2024 fact. The fallback must win because its ``end`` date
        is more recent across the whole candidate chain.
        """
        from agents.agent3_extractor import extract

        xbrl = _wrap_us_gaap(
            {
                "Revenues": {
                    "USD": [
                        _annual_usd_fact(
                            start="2016-09-25",
                            end="2017-09-30",
                            val=229_234_000_000,
                            fy=2017,
                            accn="0000320193-18-000145",
                        ),
                    ],
                },
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "USD": [
                        _annual_usd_fact(
                            start="2023-10-01",
                            end="2024-09-28",
                            val=391_035_000_000,
                            fy=2024,
                            accn="0000320193-24-000123",
                        ),
                    ],
                },
            }
        )

        result = extract(_make_ingest(xbrl_data=xbrl))

        revenue = result["metrics"]["revenue"]
        assert revenue is not None
        assert revenue["tag_used"] == (
            "RevenueFromContractWithCustomerExcludingAssessedTax"
        )
        assert revenue["fiscal_year"] == 2024
        assert revenue["value"] == 391_035_000_000.0
        assert revenue["period_end"] == "2024-09-28"

    def test_primary_wins_tie_break_when_end_dates_match(self):
        """When two candidates expose facts with the **same** ``end``
        date, the primary tag (earliest in the candidate chain) wins.
        """
        from agents.agent3_extractor import extract

        same_end = "2024-12-31"
        xbrl = _wrap_us_gaap(
            {
                "Revenues": {
                    "USD": [
                        _annual_usd_fact(
                            start="2024-01-01",
                            end=same_end,
                            val=100_000_000,
                            fy=2024,
                            accn="primary-accn",
                        ),
                    ],
                },
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "USD": [
                        _annual_usd_fact(
                            start="2024-01-01",
                            end=same_end,
                            val=200_000_000,
                            fy=2024,
                            accn="fallback-accn",
                        ),
                    ],
                },
            }
        )

        result = extract(_make_ingest(xbrl_data=xbrl))

        revenue = result["metrics"]["revenue"]
        assert revenue is not None
        assert revenue["tag_used"] == "Revenues"
        assert revenue["value"] == 100_000_000.0
        assert revenue["accession"] == "primary-accn"


class TestExtractCurrencyOnlyUsd:
    def test_eur_only_metric_returns_none_no_conversion(self):
        """A metric that only appears in EUR (across every candidate
        tag) must yield ``None``. Sprint 1 is USD-only and does not
        attempt FX conversion.
        """
        from agents.agent3_extractor import extract

        eur_fact = _annual_usd_fact(
            start="2024-01-01",
            end="2024-12-31",
            val=100_000_000,
            fy=2024,
        )
        xbrl = {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "label": "Revenues",
                        "units": {"EUR": [eur_fact]},
                    },
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "label": "RevenueFromContractWithCustomerExcludingAssessedTax",
                        "units": {"EUR": [eur_fact]},
                    },
                    "SalesRevenueNet": {
                        "label": "SalesRevenueNet",
                        "units": {"EUR": [eur_fact]},
                    },
                },
            },
        }

        result = extract(_make_ingest(xbrl_data=xbrl))

        assert result["metrics"]["revenue"] is None


class TestExtractDurationGuard:
    def test_stub_year_under_320_days_is_rejected(self):
        """A 250-day period (e.g. a fiscal-year-change stub) must be
        rejected by the duration guard, even if it is labelled
        ``form=10-K`` and ``fp=FY``.
        """
        from agents.agent3_extractor import extract

        xbrl = _wrap_us_gaap(
            {
                "Revenues": {
                    "USD": [
                        _annual_usd_fact(
                            start="2024-01-01",
                            # 250 days later — a "stub" year, not a full FY.
                            end="2024-09-07",
                            val=50_000_000,
                            fy=2024,
                        ),
                    ],
                },
            }
        )

        result = extract(_make_ingest(xbrl_data=xbrl))

        assert result["metrics"]["revenue"] is None

    def test_full_52_week_year_is_accepted(self):
        """A 364-day period (canonical 52-week fiscal year, e.g. Apple)
        must pass the duration guard.
        """
        from agents.agent3_extractor import extract

        xbrl = _wrap_us_gaap(
            {
                "Revenues": {
                    "USD": [
                        _annual_usd_fact(
                            start="2023-09-25",
                            # exactly 364 days later (52 weeks).
                            end="2024-09-23",
                            val=100_000_000,
                            fy=2024,
                        ),
                    ],
                },
            }
        )

        result = extract(_make_ingest(xbrl_data=xbrl))

        revenue = result["metrics"]["revenue"]
        assert revenue is not None
        assert revenue["fiscal_year"] == 2024


class TestExtractAccessionPropagation:
    def test_extracted_metric_includes_accession(self):
        """The output dict for a resolved metric must carry the
        ``accession`` field (string accn from the source fact). T1.10
        relies on this for traceability when reconciling against the
        gold standard.
        """
        from agents.agent3_extractor import extract

        xbrl = _wrap_us_gaap(
            {
                "Revenues": {
                    "USD": [
                        _annual_usd_fact(
                            start="2023-10-01",
                            end="2024-09-28",
                            val=391_035_000_000,
                            fy=2024,
                            accn="0000320193-24-000123",
                        ),
                    ],
                },
            }
        )

        result = extract(_make_ingest(xbrl_data=xbrl))

        revenue = result["metrics"]["revenue"]
        assert revenue is not None
        assert revenue["accession"] == "0000320193-24-000123"

    def test_extracted_metric_accession_is_none_when_absent_in_fact(self):
        """If the source fact does not carry an ``accn`` field, the
        output should expose ``accession=None`` rather than raise.
        """
        from agents.agent3_extractor import extract

        fact_without_accn = {
            "start": "2023-10-01",
            "end": "2024-09-28",
            "val": 391_035_000_000,
            "fy": 2024,
            "fp": "FY",
            "form": "10-K",
            "filed": "2024-10-31",
        }
        xbrl = _wrap_us_gaap(
            {
                "Revenues": {"USD": [fact_without_accn]},
            }
        )

        result = extract(_make_ingest(xbrl_data=xbrl))

        revenue = result["metrics"]["revenue"]
        assert revenue is not None
        assert revenue["accession"] is None
