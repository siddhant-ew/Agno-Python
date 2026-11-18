"""SQLAlchemy models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class InsuranceDocument(Base):
    """One ingested insurance PDF: its provenance, its text and its fields.

    Every extracted field is nullable on purpose: a PDF that does not carry a
    field (or carries one too unclear to read) stores NULL instead of failing.
    """

    __tablename__ = "insurance_documents"

    id: Mapped[int] = mapped_column(primary_key=True)

    # --- provenance ----------------------------------------------------------
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    # SHA-256 of the uploaded bytes. Indexed, not unique: re-uploads are allowed.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # --- structured fields ---------------------------------------------------
    policy_number: Mapped[str | None] = mapped_column(String(128))
    insurer: Mapped[str | None] = mapped_column(String(256))
    insured_name: Mapped[str | None] = mapped_column(String(256))
    policy_start_date: Mapped[date | None] = mapped_column(Date)
    policy_end_date: Mapped[date | None] = mapped_column(Date)
    premium_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    premium_currency: Mapped[str | None] = mapped_column(String(8))
    coverage_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    document_type: Mapped[str | None] = mapped_column(String(64))

    def __repr__(self) -> str:
        return f"<InsuranceDocument id={self.id} filename={self.filename!r}>"
