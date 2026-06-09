"""LUCA L4 Qualitative Extractor.

Sprint 2 sub-package. T2.2 lands the structural Item 1A chunker
(``chunker.py``) and its Pydantic models (``models.py``); T2.3 (L4-mínimo)
adds risk extraction (``extractor.py``). Forward-looking statements and
management tone (T2.4) remain future work.
"""

from agents.agent4_qualitative.extractor import extract_qualitative

__all__ = ["extract_qualitative"]
