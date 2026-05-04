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

        Note (T2.0b): the recency guard rejects facts older than 730d
        relative to ``filing_date``. The fact under test has
        ``end=2015-09-26``, so the ingest must be dated within the
        2015–2017 window for the fallback to be exercised — otherwise
        the guard correctly drops it as stale. We use the actual filing
        date of Apple's 10-K FY2015 (2015-10-28).
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

        ingest = _make_ingest(xbrl_data=xbrl)
        ingest["filing_date"] = "2015-10-28"
        result = extract(ingest)

        revenue = result["metrics"]["revenue"]
        assert revenue is not None
        assert revenue["tag_used"] == "SalesRevenueNet"
        assert revenue["fiscal_year"] == 2015

    def test_revenue_falls_back_to_bank_interest_income_for_jpm_like_filer(
        self,
    ):
        """JPM-like commercial-bank scenario (SIC 6022).

        The first three candidates in the ``revenue`` chain
        (``Revenues``, ``RevenueFromContractWithCustomerExcludingAssessedTax``,
        ``SalesRevenueNet``) are typically absent or non-recent for
        commercial banks. The last candidate,
        ``InterestAndDividendIncomeOperating``, must be picked up so we
        capture the interest-income component of net revenue (~60–65%
        for JPM). The residual under-estimation is documented in T1.10.

        Cadena actualizada por review  (2026-04-27).
        """
        from agents.agent3_extractor import extract

        xbrl = _wrap_us_gaap(
            {
                "InterestAndDividendIncomeOperating": {
                    "USD": [
                        _annual_usd_fact(
                            start="2023-01-01",
                            end="2023-12-31",
                            val=89_267_000_000,
                            fy=2023,
                            accn="0000019617-24-000123",
                        ),
                    ],
                },
            }
        )

        result = extract(
            _make_ingest(
                xbrl_data=xbrl,
                company="JPMorgan Chase & Co.",
                ticker="JPM",
            )
        )

        revenue = result["metrics"]["revenue"]
        assert revenue is not None
        assert revenue["tag_used"] == "InterestAndDividendIncomeOperating"
        assert revenue["value"] == 89_267_000_000.0
        assert revenue["fiscal_year"] == 2023
        assert revenue["unit"] == "USD"

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


# ---------------------------------------------------------------------------
# T1.6 — Fixtures reales multi-empresa (MSFT, JPM)
# ---------------------------------------------------------------------------


class TestExtractMsftFixture:
    """Tests sobre el fixture real de Microsoft Corporation (CIK 0000789019).

    Caso "tech moderno" con fiscal year Jul→Jun. Valida:
    - revenue resuelve por RevenueFromContractWithCustomerExcludingAssessedTax
      (ASC 606) porque ese tag tiene el hecho mas reciente (end 2025-06-30)
      aunque Revenues tambien exista con un hecho anual de FY2008.
    - total_equity cae a StockholdersEquity porque el fixture no contiene
      el tag NCI (StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest).
      Microsoft no reporta NCI material; ambos tags publican el mismo valor.
    - fiscal year no-calendario (Juni): period_end termina en -06-30.
    """

    def test_msft_extracts_six_metrics_with_recent_fy(self, companyfacts_msft):
        """extract() con el fixture MSFT debe poblar las 6 metricas con valor
        numerico, todas del mismo FY reciente, y todos los tag_used documentados.

        Valores esperados (FY2025, period_end 2025-06-30):
          revenue     : 281_724_000_000  tag RevenueFromContractWithCustomerExcludingAssessedTax
          net_income  : 101_832_000_000  tag NetIncomeLoss
          operating_income : 128_528_000_000  tag OperatingIncomeLoss
          total_assets: 619_003_000_000  tag Assets
          total_equity: 343_479_000_000  tag StockholdersEquity (no NCI en fixture)
          eps_diluted :          13.64   tag EarningsPerShareDiluted
        """
        from agents.agent3_extractor import extract

        result = extract(
            _make_ingest(
                xbrl_data=companyfacts_msft,
                company="Microsoft Corporation",
                ticker="MSFT",
            )
        )

        assert set(result["metrics"].keys()) == set(GOLD_METRICS)

        for metric in GOLD_METRICS:
            entry = result["metrics"][metric]
            assert entry is not None, f"{metric} no debe ser None para MSFT"
            assert isinstance(entry["value"], float), (
                f"{metric} value debe ser float, fue {type(entry['value']).__name__}"
            )
            assert entry["tag_used"], f"{metric} debe registrar tag_used"
            assert entry["period_end"], f"{metric} debe registrar period_end"
            assert entry["unit"] in {"USD", "USD/shares"}

        # Fiscal year no-calendario: periodo termina en junio
        for metric in GOLD_METRICS:
            assert result["metrics"][metric]["period_end"].endswith("-06-30"), (
                f"MSFT {metric}: period_end debe ser fin de junio (fiscal year Jul-Jun), "
                f"fue {result['metrics'][metric]['period_end']!r}"
            )

        assert isinstance(result["fiscal_year"], int)
        assert result["fiscal_year"] == 2025

        # Valores concretos — leidos del fixture real
        rev = result["metrics"]["revenue"]
        assert rev["value"] == 281_724_000_000.0
        assert rev["fiscal_year"] == 2025

        ni = result["metrics"]["net_income"]
        assert ni["value"] == 101_832_000_000.0

        oi = result["metrics"]["operating_income"]
        assert oi["value"] == 128_528_000_000.0

        ta = result["metrics"]["total_assets"]
        assert ta["value"] == 619_003_000_000.0

        te = result["metrics"]["total_equity"]
        assert te["value"] == 343_479_000_000.0

        eps = result["metrics"]["eps_diluted"]
        assert eps["value"] == 13.64

    def test_msft_revenue_uses_asc606_tag(self, companyfacts_msft):
        """revenue para MSFT debe resolver con el tag ASC 606, no con el
        tag legacy Revenues, aunque este exista en el fixture con un hecho
        anual de FY2008.

        La seleccion T1.5 (mas reciente a lo largo de TODA la cadena) elige
        RevenueFromContractWithCustomerExcludingAssessedTax (end 2025-06-30)
        sobre Revenues (end 2008-06-30). Informacion relevante para T1.10:
        Microsoft es un ejemplo de filer que publica ambos tags en EDGAR,
        con el legacy solo cubriendo el historial pre-ASC-606.
        """
        from agents.agent3_extractor import extract

        result = extract(_make_ingest(xbrl_data=companyfacts_msft, ticker="MSFT"))

        rev = result["metrics"]["revenue"]
        assert rev is not None
        assert rev["tag_used"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
        assert rev["period_end"] == "2025-06-30"
        assert rev["fiscal_year"] == 2025

    def test_msft_total_equity_tag_used(self, companyfacts_msft):
        """total_equity para MSFT debe usar StockholdersEquity (fallback) porque
        el fixture no contiene el tag NCI preferente.

        Informacion relevante para T1.10: Microsoft no tiene subsidiarias
        con participaciones no controladoras (NCI) significativas, por lo que
        EDGAR no etiqueta StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest
        con datos recientes. El extractor degrada al fallback correctamente —
        no es un fallo, es el comportamiento esperado para filers sin NCI.

        El reorden de total_equity (NCI primero segun review 
        2026-04-27) no afecta negativamente a MSFT porque el tag NCI simplemente
        no tiene hechos recientes: el fallback StockholdersEquity gana por
        recencia bajo T1.5.
        """
        from agents.agent3_extractor import extract

        result = extract(_make_ingest(xbrl_data=companyfacts_msft, ticker="MSFT"))

        te = result["metrics"]["total_equity"]
        assert te is not None
        # NCI tag ausente en fixture MSFT -> fallback correcto
        assert te["tag_used"] == "StockholdersEquity"
        assert te["value"] == 343_479_000_000.0
        assert te["period_end"] == "2025-06-30"


class TestExtractJpmFixture:
    """Tests sobre el fixture real de JPMorgan Chase & Co. (CIK 0000019617).

    Caso "banco comercial" (SIC 6022). Valida comportamientos especificos
    de la arquitectura financiera bancaria bajo US-GAAP:
    - operating_income: OperatingIncomeLoss ausente en EDGAR para bancos
      → None. Esto NO es fallo del extractor; es decision de diseño
      documentada y avalada (2026-04-27). Los bancos
      no reportan OperatingIncomeLoss como linea consolidada bajo US-GAAP.
    - revenue: JPM etiqueta la linea de ingresos como Revenues (no solo
      InterestAndDividendIncomeOperating). El tag primario de la cadena
      resuelve con datos recientes (FY2025). El fallback bancario
      InterestAndDividendIncomeOperating esta presente pero solo con
      datos de 2009-2011, por lo que Revenues gana por recencia (T1.5).
    - total_equity: NCI tag presente pero solo con datos hasta 2015;
      StockholdersEquity tiene datos hasta 2025 y gana por recencia.
    """

    def test_jpm_operating_income_is_none_when_tag_absent(self, companyfacts_jpm):
        """operating_income debe ser None para JPM porque OperatingIncomeLoss
        no aparece en el companyfacts de EDGAR para bancos comerciales.

        NOTA: esto NO es un fallo del extractor L3. Es una decision de diseno
        consciente avalada por la revision de  (2026-04-27):
        los bancos bajo US-GAAP no reportan OperatingIncomeLoss como elemento
        XBRL a nivel consolidado; el concepto de "ingreso operativo" en banca
        se calcula de forma diferente (net interest income + non-interest income
        menos provision for credit losses) y no tiene un tag estandarizado en
        la taxonomia FASB. LUCA devuelve None para esta metrica en bancos y lo
        documenta en T1.10 como limitacion conocida del pipeline para SIC 6022.
        """
        from agents.agent3_extractor import extract

        result = extract(
            _make_ingest(
                xbrl_data=companyfacts_jpm,
                company="JPMorgan Chase & Co.",
                ticker="JPM",
            )
        )

        assert result["metrics"]["operating_income"] is None, (
            "operating_income debe ser None para JPM: OperatingIncomeLoss "
            "no existe en EDGAR companyfacts para bancos (SIC 6022)"
        )

        # Las demas metricas si deben resolverse
        for metric in ("revenue", "net_income", "total_assets", "total_equity", "eps_diluted"):
            assert result["metrics"][metric] is not None, (
                f"{metric} no debe ser None para JPM"
            )

    def test_jpm_revenue_uses_revenues_tag_not_bank_fallback(self, companyfacts_jpm):
        """revenue para JPM debe resolver con el tag primario Revenues, NO con
        el fallback bancario InterestAndDividendIncomeOperating.

        El fixture real de JPM muestra que JPM etiqueta sus ingresos totales
        como Revenues en EDGAR (FY2025, end 2025-12-31, val ~182.4B USD).
        El tag InterestAndDividendIncomeOperating tambien existe pero solo con
        datos de 2009-2011 (end maximo 2011-12-31), por lo que pierde por
        recencia bajo T1.5.

        Informacion relevante para T1.10: Revenues en JPM representa el "Net
        Revenue" reportado en el income statement bancario (net interest income
        + non-interest revenue), NO solo los ingresos por intereses. La
        cadena de candidatos funciona correctamente para JPM porque la
        empresa si etiqueta la linea de ingresos como Revenues.

        Si JPM dejara de usar Revenues en el futuro, el fallback bancario
        InterestAndDividendIncomeOperating actuaria como red de seguridad
        con la caveta de subestimacion documentada en el modulo.
        """
        from agents.agent3_extractor import extract

        result = extract(
            _make_ingest(
                xbrl_data=companyfacts_jpm,
                company="JPMorgan Chase & Co.",
                ticker="JPM",
            )
        )

        rev = result["metrics"]["revenue"]
        assert rev is not None
        assert rev["tag_used"] == "Revenues", (
            f"JPM revenue debe usar tag Revenues, fue {rev['tag_used']!r}"
        )
        assert rev["period_end"] == "2025-12-31"
        assert rev["fiscal_year"] == 2025
        assert rev["value"] == 182_447_000_000.0

    def test_jpm_total_equity_falls_back_to_stockholders_equity(self, companyfacts_jpm):
        """total_equity para JPM debe usar StockholdersEquity aunque el tag NCI
        preferente exista en el fixture — porque los datos NCI son de 2015.

        El fixture de JPM contiene
        StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest
        (el preferente) pero solo con hechos hasta end=2015-12-31. El tag
        StockholdersEquity tiene hechos hasta end=2025-12-31. T1.5 elige
        el mas reciente → StockholdersEquity gana.

        Informacion para T1.10: el tag NCI de JPM desaparecio de las 10-K
        post-2015, probablemente porque JPM reorganizo su estructura de NCI.
        El extractor degrada correctamente al fallback sin necesitar logica
        especial para este caso.
        """
        from agents.agent3_extractor import extract

        result = extract(
            _make_ingest(
                xbrl_data=companyfacts_jpm,
                company="JPMorgan Chase & Co.",
                ticker="JPM",
            )
        )

        te = result["metrics"]["total_equity"]
        assert te is not None
        assert te["tag_used"] == "StockholdersEquity", (
            f"JPM total_equity debe usar StockholdersEquity (NCI tag obsoleto), "
            f"fue {te['tag_used']!r}"
        )
        assert te["value"] == 362_438_000_000.0
        assert te["period_end"] == "2025-12-31"


# ---------------------------------------------------------------------------
# T1.6 — Cobertura con fixtures sinteticos (edge cases no cubiertos por AAPL)
# ---------------------------------------------------------------------------


class TestExtractSyntheticEdgeCases:
    """Tests de edge cases con datos sinteticos inline.

    No requieren EDGAR; se construyen con dicts directamente en el test.
    Cubren rutas que AAPL/MSFT/JPM no ejercitan.
    """

    def test_currency_other_than_usd_returns_none(self):
        """Una metrica cuyos hechos estan SOLO en EUR (no USD) debe devolver
        None. LUCA Sprint 1 es USD-only y no intenta conversion FX.

        Distingue del test existente TestExtractWrongCurrency porque ese
        usa el API de alto nivel extract(); este verifica explicitamente
        que la decision se aplica cuando TODOS los candidatos del chain
        estan en EUR (no solo el primario).
        """
        from agents.agent3_extractor import extract

        # Todos los candidatos de revenue en EUR, ninguno en USD
        eur_fact = {
            "start": "2024-01-01",
            "end": "2024-12-31",
            "val": 50_000_000_000,
            "accn": "0099999999-24-000001",
            "fy": 2024,
            "fp": "FY",
            "form": "10-K",
            "filed": "2025-03-01",
        }
        xbrl = {
            "facts": {
                "us-gaap": {
                    tag: {"label": tag, "units": {"EUR": [eur_fact]}}
                    for tag in (
                        "Revenues",
                        "RevenueFromContractWithCustomerExcludingAssessedTax",
                        "SalesRevenueNet",
                        "InterestAndDividendIncomeOperating",
                    )
                },
            },
        }

        result = extract(
            _make_ingest(
                xbrl_data=xbrl,
                company="European Filer S.A.",
                ticker="EURF",
            )
        )

        assert result["metrics"]["revenue"] is None, (
            "revenue debe ser None cuando todos los candidatos estan solo en EUR"
        )

    def test_quarterly_facts_are_excluded_when_only_quarters_exist(self):
        """Una metrica cuyos unicos hechos tienen fp distinto de 'FY' debe
        devolver None aunque form=='10-K'.

        Caso limite: un hecho con fp='Q4' incluido en una 10-K (EDGAR lo
        hace para algunos comparative quarters). El filtro fp=='FY' debe
        rechazarlo. La duracion es suficiente (>320 dias) para descartar
        que sea la duracion quien lo rechace — es el campo fp.
        """
        from agents.agent3_extractor import extract

        q4_fact = {
            "start": "2024-01-01",
            "end": "2024-12-31",  # duracion 365d, no es el problema
            "val": 100_000_000,
            "accn": "0099999999-25-000001",
            "fy": 2024,
            "fp": "Q4",   # <-- no es FY; debe ser filtrado
            "form": "10-K",
            "filed": "2025-02-01",
        }
        xbrl = _wrap_us_gaap({"Revenues": {"USD": [q4_fact]}})

        result = extract(_make_ingest(xbrl_data=xbrl))

        assert result["metrics"]["revenue"] is None, (
            "revenue debe ser None: el unico hecho tiene fp='Q4', no 'FY'"
        )

    def test_metric_with_no_facts_at_all_returns_none(self):
        """Una metrica sin ningun hecho en ningun candidato del chain debe
        devolver None sin lanzar excepciones.

        Verifica que el extractor degrada silenciosamente cuando el
        bloque us-gaap existe pero ninguno de los tags del chain aparece
        en el fixture (ej: empresa que solo reporta SIC-especifico).
        """
        from agents.agent3_extractor import extract

        # Solo tags irrelevantes presentes (no en _TAG_CANDIDATES de revenue)
        xbrl = _wrap_us_gaap(
            {
                "InterestExpense": {
                    "USD": [
                        {
                            "start": "2024-01-01",
                            "end": "2024-12-31",
                            "val": 5_000_000_000,
                            "accn": "0099999999-25-000001",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2025-02-01",
                        },
                    ],
                },
            }
        )

        result = extract(_make_ingest(xbrl_data=xbrl))

        assert result["metrics"]["revenue"] is None
        assert result["metrics"]["net_income"] is None
        assert result["metrics"]["operating_income"] is None
        # total_assets usa Assets — tampoco esta presente
        assert result["metrics"]["total_assets"] is None
        assert result["metrics"]["total_equity"] is None
        assert result["metrics"]["eps_diluted"] is None
        assert result["fiscal_year"] is None


# ---------------------------------------------------------------------------
# T2.0b — Recency guard tests
# ---------------------------------------------------------------------------

import json
from pathlib import Path

_STALE_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "companyfacts_stale.json"


def _load_stale_fixture() -> dict:
    """Load the stale fixture from disk (companyfacts_stale.json)."""
    with _STALE_FIXTURE_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


class TestRecencyGuard:
    """Tests for the T2.0b recency guard in _extract_metric.

    The guard rejects winning facts whose ``(filing_date - end_date).days``
    exceeds ``_MAX_FACT_AGE_DAYS`` (730). When ``filing_date`` is ``None``
    or malformed the guard is disabled and the fact is returned as-is
    (with a WARNING log). All tests in this class use the
    ``companyfacts_stale.json`` fixture (single tag ``OperatingIncomeLoss``,
    single fact ``end=2014-12-31``) unless stated otherwise.
    """

    def test_stale_fact_rejected_when_filing_recent(self):
        """A fact with end=2014-12-31 is stale relative to filing_date=2025-02-01.

        The delta is ~3684 days, far beyond the 730-day threshold, so
        operating_income must be None. The other five metrics are also None
        because the stale fixture only contains OperatingIncomeLoss — that is
        expected and intentional; the test focuses on operating_income.
        """
        from agents.agent3_extractor import extract

        fixture = _load_stale_fixture()
        ingest = {
            "company": "Stale Filer Fixture Inc.",
            "ticker": "STALE",
            "filing_date": "2025-02-01",
            "html_content": "",
            "xbrl_data": fixture,
            "accession_number": None,
            "cik": "9999999999",
            "source_urls": {},
        }

        result = extract(ingest)

        # Primary assertion: stale fact rejected
        assert result["metrics"]["operating_income"] is None, (
            "operating_income debe ser None: fact end=2014-12-31 es stale "
            "respecto a filing_date=2025-02-01 (>730 dias)"
        )
        # The other metrics are also None because the fixture only contains
        # OperatingIncomeLoss — this is expected, not a guard failure.
        assert result["metrics"]["revenue"] is None
        assert result["metrics"]["net_income"] is None
        assert result["metrics"]["total_assets"] is None
        assert result["metrics"]["total_equity"] is None
        assert result["metrics"]["eps_diluted"] is None

    def test_stale_fact_accepted_when_filing_date_is_none(self):
        """Guard is disabled when filing_date is None.

        The stale fact (end=2014-12-31) must be returned as-is because the
        guard cannot fire without a reference date. A WARNING containing
        'filing_date ausente' must be emitted.

        Note: agents._logging uses ``propagate=False`` so pytest caplog
        cannot capture the record via the root logger. We mock _LOGGER.warning
        directly to verify the call without touching infrastructure code.
        """
        from unittest.mock import patch

        from agents.agent3_extractor import extract

        fixture = _load_stale_fixture()
        ingest = {
            "company": "Stale Filer Fixture Inc.",
            "ticker": "STALE",
            "filing_date": None,
            "html_content": "",
            "xbrl_data": fixture,
            "accession_number": None,
            "cik": "9999999999",
            "source_urls": {},
        }

        with patch("agents.agent3_extractor._LOGGER") as mock_logger:
            result = extract(ingest)

        assert result["metrics"]["operating_income"] is not None, (
            "operating_income debe resolverse cuando filing_date=None "
            "(guard desactivado)"
        )
        assert result["metrics"]["operating_income"]["value"] == 21590000000.0
        # Verify that warning was called with a message containing 'filing_date ausente'
        warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
        assert any("filing_date ausente" in c for c in warning_calls), (
            f"Se esperaba un _LOGGER.warning con 'filing_date ausente', "
            f"llamadas recibidas: {warning_calls}"
        )

    def test_stale_fact_accepted_when_filing_date_malformed(self):
        """Guard is disabled when filing_date is an unparseable string.

        The stale fact must be returned (guard cannot fire), and a WARNING
        must be logged — same behaviour as the None case.

        Note: agents._logging uses ``propagate=False`` so pytest caplog
        cannot capture the record via the root logger. We mock _LOGGER.warning
        directly to verify the call without touching infrastructure code.
        """
        from unittest.mock import patch

        from agents.agent3_extractor import extract

        fixture = _load_stale_fixture()
        ingest = {
            "company": "Stale Filer Fixture Inc.",
            "ticker": "STALE",
            "filing_date": "not-a-date",
            "html_content": "",
            "xbrl_data": fixture,
            "accession_number": None,
            "cik": "9999999999",
            "source_urls": {},
        }

        with patch("agents.agent3_extractor._LOGGER") as mock_logger:
            result = extract(ingest)

        assert result["metrics"]["operating_income"] is not None, (
            "operating_income debe resolverse cuando filing_date malformado "
            "(guard desactivado)"
        )
        assert result["metrics"]["operating_income"]["value"] == 21590000000.0
        warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
        assert any("filing_date ausente" in c for c in warning_calls), (
            f"Se esperaba un _LOGGER.warning con 'filing_date ausente', "
            f"llamadas recibidas: {warning_calls}"
        )

    def test_fresh_fact_accepted_under_guard(self, companyfacts_aapl):
        """Happy-path: guard does not reject fresh facts from the AAPL fixture.

        The AAPL fixture's most recent facts end on 2025-09-27. With
        filing_date=2025-10-31 the delta is 34 days, well within the 730-day
        window. At least revenue must be extracted successfully.
        """
        from agents.agent3_extractor import extract

        ingest = _make_ingest(xbrl_data=companyfacts_aapl)
        # _make_ingest already sets filing_date="2025-10-31" which is within window
        result = extract(ingest)

        revenue = result["metrics"]["revenue"]
        assert revenue is not None, (
            "revenue no debe ser None para AAPL con filing_date reciente; "
            "el guard no debe rechazar hechos frescos"
        )
        assert isinstance(revenue["value"], float)
        assert revenue["value"] > 0

    def test_fresh_fact_wins_over_stale_in_same_chain(self):
        """When the revenue chain has a stale Revenues tag and a fresh ASC-606 tag,
        the sort-by-recency puts the fresh fact at position 0, the guard passes it,
        and the stale fact is never even evaluated.

        Chain:
          - Revenues           end=2014-12-31  (stale, >730d from 2025-02-01)
          - RevenueFromContractWithCustomerExcludingAssessedTax  end=2024-12-31  (fresh)

        Expected: tag_used == RevenueFromContractWithCustomerExcludingAssessedTax,
                  value     == 391_035_000_000,
                  period_end == '2024-12-31'.
        """
        from agents.agent3_extractor import extract

        xbrl = _wrap_us_gaap(
            {
                "Revenues": {
                    "USD": [
                        _annual_usd_fact(
                            start="2014-01-01",
                            end="2014-12-31",
                            val=50_000_000_000,
                            fy=2014,
                            accn="stale-accn",
                        ),
                    ],
                },
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "USD": [
                        _annual_usd_fact(
                            start="2024-01-01",
                            end="2024-12-31",
                            val=391_035_000_000,
                            fy=2024,
                            accn="fresh-accn",
                        ),
                    ],
                },
            }
        )

        ingest = _make_ingest(xbrl_data=xbrl)
        ingest["filing_date"] = "2025-02-01"
        result = extract(ingest)

        revenue = result["metrics"]["revenue"]
        assert revenue is not None, (
            "revenue no debe ser None: hay un fact fresco en la cadena aunque "
            "Revenues sea stale"
        )
        assert revenue["tag_used"] == "RevenueFromContractWithCustomerExcludingAssessedTax", (
            f"tag_used incorrecto: {revenue['tag_used']!r}"
        )
        assert revenue["value"] == 391_035_000_000.0
        assert revenue["period_end"] == "2024-12-31"

    def test_just_within_730d_window_accepted(self):
        """A fact whose end_date is exactly 729 days before filing_date is accepted.

        Boundary condition: delta_days == 729 < _MAX_FACT_AGE_DAYS (730).
        The guard must NOT reject this fact.

        Uses _MAX_FACT_AGE_DAYS from the module so the test stays valid if
        the threshold is ever adjusted.
        """
        from datetime import date, timedelta

        from agents.agent3_extractor import _MAX_FACT_AGE_DAYS, extract

        filing = date(2025, 2, 1)
        end = filing - timedelta(days=_MAX_FACT_AGE_DAYS - 1)  # 729 days before
        start = end - timedelta(days=365)

        xbrl = _wrap_us_gaap(
            {
                "Revenues": {
                    "USD": [
                        _annual_usd_fact(
                            start=start.isoformat(),
                            end=end.isoformat(),
                            val=100_000_000_000,
                            fy=end.year,
                        ),
                    ],
                },
            }
        )

        ingest = _make_ingest(xbrl_data=xbrl)
        ingest["filing_date"] = filing.isoformat()
        result = extract(ingest)

        assert result["metrics"]["revenue"] is not None, (
            f"revenue no debe ser None: delta={_MAX_FACT_AGE_DAYS - 1}d < "
            f"_MAX_FACT_AGE_DAYS={_MAX_FACT_AGE_DAYS}"
        )

    def test_just_outside_730d_window_rejected(self):
        """A fact whose end_date is exactly 731 days before filing_date is rejected.

        Boundary condition: delta_days == 731 > _MAX_FACT_AGE_DAYS (730).
        The guard must reject this fact and return None.

        Uses _MAX_FACT_AGE_DAYS from the module so the test stays valid if
        the threshold is ever adjusted.
        """
        from datetime import date, timedelta

        from agents.agent3_extractor import _MAX_FACT_AGE_DAYS, extract

        filing = date(2025, 2, 1)
        end = filing - timedelta(days=_MAX_FACT_AGE_DAYS + 1)  # 731 days before
        start = end - timedelta(days=365)

        xbrl = _wrap_us_gaap(
            {
                "Revenues": {
                    "USD": [
                        _annual_usd_fact(
                            start=start.isoformat(),
                            end=end.isoformat(),
                            val=100_000_000_000,
                            fy=end.year,
                        ),
                    ],
                },
            }
        )

        ingest = _make_ingest(xbrl_data=xbrl)
        ingest["filing_date"] = filing.isoformat()
        result = extract(ingest)

        assert result["metrics"]["revenue"] is None, (
            f"revenue debe ser None: delta={_MAX_FACT_AGE_DAYS + 1}d > "
            f"_MAX_FACT_AGE_DAYS={_MAX_FACT_AGE_DAYS}"
        )
