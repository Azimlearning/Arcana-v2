# Adapted from Azimlearning/Arcana (v1), api/ingestion/parsers/pdf.py @ 9a3d67f.
# Read in full and adapted for v2 (D-01, D-16): returns a ParsedPdf (adds the PDF's own title) and
# raises v2's IngestFailed.
"""PDF parser: text per page via PyMuPDF, 1-indexed so a chunk can cite the page it starts on.

Text-only. A scanned PDF yields empty pages, which the pipeline reports as a failed document
(OCR is out of scope for P0).
"""

from __future__ import annotations

from typing import cast

import pymupdf

from api.core.errors import IngestFailed
from api.ingestion.types import PageText, ParsedPdf


def parse(raw: bytes) -> ParsedPdf:
    if not raw:
        raise IngestFailed("The uploaded file is empty.")
    try:
        doc = pymupdf.open(stream=raw, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises several unrelated types for a bad file
        raise IngestFailed("The uploaded file could not be opened as a PDF.") from exc
    try:
        pages = [
            PageText(page=i + 1, text=cast(str, doc[i].get_text("text")) or "")
            for i in range(doc.page_count)
        ]
        title = ((doc.metadata or {}).get("title") or "").strip() or None
        return ParsedPdf(title=title, pages=pages)
    finally:
        doc.close()
