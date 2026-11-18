"""PDF text extraction with pdfplumber, local and dependency-free beyond pip."""

from __future__ import annotations

import logging
from pathlib import Path

import pdfplumber

logger = logging.getLogger(__name__)


class PdfReadError(RuntimeError):
    """The file is not a PDF we can read."""


def read_pdf_text(file_path: str) -> str:
    """Return the text of every page, separated by blank lines.

    Raises ``PdfReadError`` when the file cannot be read at all. A page without
    a text layer (for example a scan) contributes nothing instead of failing.
    """
    path = Path(file_path)
    if not path.is_file():
        raise PdfReadError(f"no file at {file_path}")

    try:
        with pdfplumber.open(path) as pdf:
            pages = [(page.extract_text() or "").strip() for page in pdf.pages]
    except Exception as exc:  # pdfplumber raises several unrelated error types
        logger.warning("could not read PDF %s: %s", file_path, exc)
        raise PdfReadError(f"could not read the PDF: {exc}") from exc

    return "\n\n".join(text for text in pages if text)


def extract_pdf_text(file_path: str) -> str:
    """Extract the text of a PDF file, page by page.

    Args:
        file_path: Path to the PDF file on disk.

    Returns:
        The text of the document, pages separated by blank lines, or a string
        starting with "ERROR:" explaining why the file could not be read.
    """
    try:
        return read_pdf_text(file_path)
    except PdfReadError as exc:
        return f"ERROR: {exc}"
