"""Stage 1: Extract.

Pull raw text and tables out of a merchant processing statement PDF using
pdfplumber, and flatten everything into one raw text blob to hand to stage 2.

Statements vary wildly by processor (Fiserv, TSYS, Elavon, Paysafe, ...), so we
deliberately do NOT try to understand layout here. We just get every word and
every table cell out of the PDF and let the model in stage 2 make sense of it.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber


def extract_raw(pdf_path: str | Path) -> str:
    """Return a single raw text blob containing all text and tables in the PDF.

    The blob is organized page by page. For each page we emit the plain text,
    then any tables rendered as pipe-delimited rows. This keeps tabular numbers
    (the fee schedules we care about) legible to the model even when the flat
    text mangles their alignment.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Statement PDF not found: {pdf_path}")

    parts: list[str] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            parts.append(f"\n===== PAGE {page_number} =====")

            text = page.extract_text() or ""
            if text.strip():
                parts.append("--- TEXT ---")
                parts.append(text)

            tables = page.extract_tables() or []
            for table_index, table in enumerate(tables, start=1):
                parts.append(f"--- TABLE {page_number}.{table_index} ---")
                for row in table:
                    cells = ["" if cell is None else str(cell).strip() for cell in row]
                    parts.append(" | ".join(cells))

    blob = "\n".join(parts).strip()
    if not blob:
        raise ValueError(
            f"No text or tables could be extracted from {pdf_path}. "
            "The PDF may be a scanned image (OCR not yet supported in milestone 1)."
        )
    return blob
