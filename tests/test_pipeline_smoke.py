"""Smoke test E2E mockeado para el tramo L1 → L2 del pipeline LUCA.

Verifica que la salida de L1 (construida con fixtures locales, sin red real)
pasa correctamente por L2 y produce el shape de output esperado según el
contrato de ARCHITECTURE.md.

No se realiza ninguna llamada a EDGAR ni a Ollama.
"""

from __future__ import annotations

from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXPECTED_L1_KEYS = {
    "company",
    "ticker",
    "cik",
    "filing_date",
    "accession_number",
    "html_content",
    "xbrl_data",
    "source_urls",
}

_EXPECTED_L2_KEYS = {
    "company",
    "ticker",
    "filing_date",
    "item_1",
    "item_1a",
    "item_7",
    "item_8",
    "raw_tables",
}


def _build_l1_output(
    html_content: str,
    xbrl_data: dict[str, Any],
) -> dict[str, Any]:
    """Construye un dict de salida de L1 completamente mockeado.

    No llama a EDGAR ni a ninguna red. Usa datos de fixtures pasados como
    argumentos para que cada test pueda controlar el contenido exacto.

    Args:
        html_content: HTML del 10-K (puede ser vacío para el caso de fallback).
        xbrl_data: Datos XBRL (companyfacts). Puede ser el fixture real de AAPL
            o un dict vacío para tests que no necesitan métricas.

    Returns:
        Dict que cumple el contrato de L1 según ARCHITECTURE.md, con la clave
        adicional ``accession_number`` presente en la implementación real.
    """
    return {
        "company": "Apple Inc.",
        "ticker": "AAPL",
        "cik": "0000320193",
        "filing_date": "2023-11-03",
        "accession_number": "0000320193-23-000106",
        "html_content": html_content,
        "xbrl_data": xbrl_data,
        "source_urls": {
            "companyfacts": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            "submissions": "https://data.sec.gov/submissions/CIK0000320193.json",
            "filing_index": None,
        },
    }


# ---------------------------------------------------------------------------
# Tests de shape del output de L2
# ---------------------------------------------------------------------------


class TestL2OutputShape:
    """Verifica que el output de L2 tiene las claves y tipos correctos."""

    def test_l2_output_has_required_keys(self, sample_10k_html, companyfacts_aapl):
        """parse() debe devolver exactamente las claves del contrato de L2."""
        from agents.agent2_parser import parse

        l1_out = _build_l1_output(
            html_content=sample_10k_html,
            xbrl_data=companyfacts_aapl,
        )
        result = parse(l1_out)

        assert _EXPECTED_L2_KEYS.issubset(result.keys()), (
            f"Faltan claves en el output de L2: {_EXPECTED_L2_KEYS - result.keys()}"
        )

    def test_l2_item_fields_are_strings(self, sample_10k_html, companyfacts_aapl):
        """Los campos item_* deben ser str."""
        from agents.agent2_parser import parse

        l1_out = _build_l1_output(
            html_content=sample_10k_html,
            xbrl_data=companyfacts_aapl,
        )
        result = parse(l1_out)

        for key in ("item_1", "item_1a", "item_7", "item_8"):
            assert isinstance(result[key], str), (
                f"{key} debe ser str, obtenido: {type(result[key])}"
            )

    def test_l2_raw_tables_is_list(self, sample_10k_html, companyfacts_aapl):
        """raw_tables debe ser una lista."""
        from agents.agent2_parser import parse

        l1_out = _build_l1_output(
            html_content=sample_10k_html,
            xbrl_data=companyfacts_aapl,
        )
        result = parse(l1_out)

        assert isinstance(result["raw_tables"], list), (
            f"raw_tables debe ser list, obtenido: {type(result['raw_tables'])}"
        )

    def test_l2_metadata_passthrough(self, sample_10k_html, companyfacts_aapl):
        """company, ticker y filing_date deben propagarse sin modificación."""
        from agents.agent2_parser import parse

        l1_out = _build_l1_output(
            html_content=sample_10k_html,
            xbrl_data=companyfacts_aapl,
        )
        result = parse(l1_out)

        assert result["company"] == "Apple Inc."
        assert result["ticker"] == "AAPL"
        assert result["filing_date"] == "2023-11-03"


# ---------------------------------------------------------------------------
# Tests de contenido con HTML de muestra real
# ---------------------------------------------------------------------------


class TestL2ContentWithSampleHtml:
    """Verifica el contenido extraído cuando el HTML tiene los cuatro items."""

    def test_item_1a_not_empty_when_html_has_risk_factors(
        self, sample_10k_html, companyfacts_aapl
    ):
        """item_1a no debe ser vacío si el HTML contiene Item 1A."""
        from agents.agent2_parser import parse

        l1_out = _build_l1_output(
            html_content=sample_10k_html,
            xbrl_data=companyfacts_aapl,
        )
        result = parse(l1_out)

        assert result["item_1a"] != "", (
            "item_1a vacío a pesar de que el HTML contiene Item 1A Risk Factors"
        )

    def test_item_1a_contains_risk_keyword(self, sample_10k_html, companyfacts_aapl):
        """item_1a extraído debe contener la palabra 'Risk' del fixture."""
        from agents.agent2_parser import parse

        l1_out = _build_l1_output(
            html_content=sample_10k_html,
            xbrl_data=companyfacts_aapl,
        )
        result = parse(l1_out)

        assert "Risk" in result["item_1a"] or "risk" in result["item_1a"], (
            "item_1a no contiene la palabra 'risk' del fixture de muestra"
        )

    def test_all_four_items_non_empty(self, sample_10k_html, companyfacts_aapl):
        """Todos los items deben tener contenido con el fixture completo."""
        from agents.agent2_parser import parse

        l1_out = _build_l1_output(
            html_content=sample_10k_html,
            xbrl_data=companyfacts_aapl,
        )
        result = parse(l1_out)

        for key in ("item_1", "item_1a", "item_7", "item_8"):
            assert len(result[key]) > 0, (
                f"{key} está vacío, esperaba contenido del fixture de muestra"
            )

    def test_raw_tables_non_empty_with_sample_html(
        self, sample_10k_html, companyfacts_aapl
    ):
        """raw_tables debe contener al menos una tabla del Item 8 del fixture."""
        from agents.agent2_parser import parse

        l1_out = _build_l1_output(
            html_content=sample_10k_html,
            xbrl_data=companyfacts_aapl,
        )
        result = parse(l1_out)

        assert len(result["raw_tables"]) >= 1, (
            "raw_tables vacío a pesar de que el fixture contiene tablas en Item 8"
        )
        for table_text in result["raw_tables"]:
            assert isinstance(table_text, str) and len(table_text) > 0, (
                "Cada entrada de raw_tables debe ser str no vacía"
            )

    def test_item_7_contains_financial_figures(
        self, sample_10k_html, companyfacts_aapl
    ):
        """item_7 debe contener cifras financieras presentes en el fixture."""
        from agents.agent2_parser import parse

        l1_out = _build_l1_output(
            html_content=sample_10k_html,
            xbrl_data=companyfacts_aapl,
        )
        result = parse(l1_out)

        # El fixture menciona "383.3 billion" en el MD&A
        assert "383" in result["item_7"], (
            "item_7 no contiene la cifra de ventas '383' presente en el fixture"
        )


# ---------------------------------------------------------------------------
# Tests de fallback graceful con html_content vacío
# ---------------------------------------------------------------------------


class TestL2FallbackEmptyHtml:
    """Verifica el comportamiento graceful cuando L1 entrega html_content vacío.

    Sprint 0 deja html_content='' como placeholder hasta T1.7. L2 debe
    tolerar esto sin lanzar excepciones y devolver items vacíos.
    """

    def test_empty_html_returns_empty_items(self, companyfacts_aapl):
        """Con html_content vacío, todos los items deben ser strings vacíos."""
        from agents.agent2_parser import parse

        l1_out = _build_l1_output(html_content="", xbrl_data=companyfacts_aapl)
        result = parse(l1_out)

        assert result["item_1"] == ""
        assert result["item_1a"] == ""
        assert result["item_7"] == ""
        assert result["item_8"] == ""

    def test_empty_html_returns_empty_raw_tables(self, companyfacts_aapl):
        """Con html_content vacío, raw_tables debe ser lista vacía."""
        from agents.agent2_parser import parse

        l1_out = _build_l1_output(html_content="", xbrl_data=companyfacts_aapl)
        result = parse(l1_out)

        assert result["raw_tables"] == []

    def test_empty_html_preserves_metadata(self, companyfacts_aapl):
        """Con html_content vacío, los metadatos deben propagarse igualmente."""
        from agents.agent2_parser import parse

        l1_out = _build_l1_output(html_content="", xbrl_data=companyfacts_aapl)
        result = parse(l1_out)

        assert result["company"] == "Apple Inc."
        assert result["ticker"] == "AAPL"
        assert result["filing_date"] == "2023-11-03"

    def test_empty_html_output_has_required_keys(self, companyfacts_aapl):
        """Con html_content vacío, el shape del output debe seguir siendo correcto."""
        from agents.agent2_parser import parse

        l1_out = _build_l1_output(html_content="", xbrl_data=companyfacts_aapl)
        result = parse(l1_out)

        assert _EXPECTED_L2_KEYS.issubset(result.keys()), (
            f"Faltan claves en el output de L2 (fallback): "
            f"{_EXPECTED_L2_KEYS - result.keys()}"
        )

    def test_empty_html_does_not_raise(self, companyfacts_aapl):
        """parse() con html vacío no debe lanzar ninguna excepción."""
        from agents.agent2_parser import parse

        l1_out = _build_l1_output(html_content="", xbrl_data=companyfacts_aapl)
        # Si lanza, el test falla automáticamente
        parse(l1_out)


# ---------------------------------------------------------------------------
# Test de contrato L1: el mock de L1 tiene las claves esperadas
# ---------------------------------------------------------------------------


class TestL1ContractShape:
    """Verifica que el mock de L1 construido en este smoke test cumple el
    contrato documentado en ARCHITECTURE.md, para detectar desviaciones
    antes de que afecten a tests posteriores."""

    def test_l1_mock_has_required_keys(self, sample_10k_html, companyfacts_aapl):
        """El dict de L1 mockeado debe contener todas las claves del contrato."""
        l1_out = _build_l1_output(
            html_content=sample_10k_html,
            xbrl_data=companyfacts_aapl,
        )

        assert _EXPECTED_L1_KEYS.issubset(l1_out.keys()), (
            f"Faltan claves en el mock de L1: {_EXPECTED_L1_KEYS - l1_out.keys()}"
        )

    def test_l1_xbrl_data_is_dict(self, sample_10k_html, companyfacts_aapl):
        """xbrl_data debe ser un dict (fixture companyfacts_aapl)."""
        l1_out = _build_l1_output(
            html_content=sample_10k_html,
            xbrl_data=companyfacts_aapl,
        )

        assert isinstance(l1_out["xbrl_data"], dict), (
            f"xbrl_data debe ser dict, obtenido: {type(l1_out['xbrl_data'])}"
        )

    def test_l1_xbrl_data_has_entity_name(self, sample_10k_html, companyfacts_aapl):
        """xbrl_data (fixture AAPL) debe contener entityName."""
        l1_out = _build_l1_output(
            html_content=sample_10k_html,
            xbrl_data=companyfacts_aapl,
        )

        assert "entityName" in l1_out["xbrl_data"], (
            "xbrl_data no contiene 'entityName'; ¿fixture companyfacts_AAPL.json correcto?"
        )
