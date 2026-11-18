"""Pydantic models: the agent's output shape and the API's response shapes.

The coercion helpers below never raise. Anything that cannot be read becomes
``None`` (a NULL column) so a single odd value can never fail a whole upload.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, field_validator

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
)

_CURRENCY_SYMBOLS = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "₹": "INR",
    "¥": "JPY",
}

_EMPTY_STRINGS = {"", "null", "none", "nil", "n/a", "na", "unknown", "not found", "-", "--"}


class HealthResponse(BaseModel):
    """Answer of ``GET /health``."""

    status: str
    database: str
    agents: list[str]


class InsuranceFields(BaseModel):
    """The fields the agent tries to pull out of an insurance PDF.

    All optional: ``None`` means "not present (or not readable) in this PDF".
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    policy_number: str | None = None
    insurer: str | None = None
    insured_name: str | None = None
    policy_start_date: date | None = None
    policy_end_date: date | None = None
    premium_amount: Decimal | None = None
    premium_currency: str | None = None
    coverage_amount: Decimal | None = None
    document_type: str | None = None

    @field_validator("policy_number", "insurer", "insured_name", "document_type", mode="before")
    @classmethod
    def _clean_text(cls, value: object) -> str | None:
        # Limits match the column lengths in app/models.py.
        limit = {"policy_number": 128, "document_type": 64}.get("", 256)
        return _as_text(value, limit=limit)

    @field_validator("policy_start_date", "policy_end_date", mode="before")
    @classmethod
    def _clean_date(cls, value: object) -> date | None:
        return _as_date(value)

    @field_validator("premium_amount", "coverage_amount", mode="before")
    @classmethod
    def _clean_amount(cls, value: object) -> Decimal | None:
        return _as_decimal(value)

    @field_validator("premium_currency", mode="before")
    @classmethod
    def _clean_currency(cls, value: object) -> str | None:
        return _as_currency(value)


class DocumentSummary(InsuranceFields):
    """List view: metadata plus the extracted fields, without the raw text."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content_hash: str
    ingested_at: datetime


class DocumentDetail(DocumentSummary):
    """Single-document view: everything that is stored, raw text included."""

    raw_text: str


def _as_text(value: object, limit: int | None = None) -> str | None:
    """Trim a value to text, or ``None`` when it is empty or clearly not a value."""
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in _EMPTY_STRINGS:
        return None
    if limit is not None and len(text) > limit:
        text = text[:limit].strip()
    return text or None


def _as_date(value: object) -> date | None:
    """Read the common date spellings a PDF or a model might use."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _as_text(value)
    if text is None:
        return None
    # Try the whole string first ("12 March 2025"), then the date part of an
    # ISO timestamp ("2025-03-12T00:00:00").
    for candidate in (text, text.split("T")[0].strip()):
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def _as_decimal(value: object) -> Decimal | None:
    """Read an amount such as 1250, 1,250.00 or \u20b91,250.00."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    text = _as_text(value)
    if text is None:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", text.replace(",", ""))
    if cleaned in {"", "-", ".", "-."}:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _as_currency(value: object) -> str | None:
    """Read a currency as a short code, mapping the usual symbols."""
    text = _as_text(value)
    if text is None:
        return None
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    code = text.upper()
    # Longer strings are prose, not a currency code; drop them rather than
    # overflowing the column.
    return code if 2 <= len(code) <= 8 else None
