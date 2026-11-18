"""Turn an uploaded PDF into a stored ``InsuranceDocument``."""

from __future__ import annotations

import hashlib
import logging
import tempfile
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents import get_agent
from app.agents.insurance_parser import AGENT_NAME, parse_insurance_fields
from app.models import InsuranceDocument
from app.schemas import InsuranceFields
from app.tools.pdf_tools import PdfReadError, read_pdf_text

logger = logging.getLogger(__name__)

_PDF_MAGIC = b"%PDF"


class IngestError(Exception):
    """An upload that cannot be ingested, with the HTTP status to answer with."""

    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


def ingest_pdf(session: Session, filename: str, data: bytes) -> InsuranceDocument:
    """Validate, extract, run the agent and store one document.

    Raises ``IngestError``; nothing is written to the database in that case.
    """
    if not data:
        raise IngestError("the uploaded file is empty")
    # Some PDFs start with a little whitespace or junk before the header.
    if _PDF_MAGIC not in data[:1024]:
        raise IngestError("the uploaded file is not a PDF", status_code=415)

    content_hash = hashlib.sha256(data).hexdigest()

    with tempfile.TemporaryDirectory(prefix="agno-ingest-") as workdir:
        path = Path(workdir) / filename
        path.write_bytes(data)

        try:
            raw_text = read_pdf_text(str(path))
        except PdfReadError as exc:
            raise IngestError(f"could not read the PDF: {exc}") from exc

        if raw_text.strip():
            try:
                agent = get_agent(AGENT_NAME)
                fields = parse_insurance_fields(agent, str(path), raw_text)
            except IngestError:
                raise
            except Exception as exc:
                # Model/provider trouble: say so instead of storing empty fields.
                logger.exception("the agent failed on %s", filename)
                raise IngestError(
                    f"the agent could not process this document: {exc}", status_code=502
                ) from exc
        else:
            # A scan with no text layer: keep the record, but do not spend a
            # model call on an empty string.
            logger.warning(
                "%s has no extractable text (a scanned PDF?); storing it without fields",
                filename,
            )
            fields = InsuranceFields()

    document = InsuranceDocument(
        filename=filename,
        content_hash=content_hash,
        raw_text=raw_text,
        **fields.model_dump(),
    )
    session.add(document)
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception("could not store %s", filename)
        raise IngestError("the document could not be stored", status_code=500) from exc

    session.refresh(document)
    logger.info(
        "stored %s as document %s (agent found %s fields)",
        filename,
        document.id,
        sum(1 for value in fields.model_dump().values() if value is not None),
    )
    return document
