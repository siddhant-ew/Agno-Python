"""FastAPI app: upload insurance PDFs, list and fetch what was stored."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents import AGENTS
from app.db import get_session, init_db
from app.models import InsuranceDocument
from app.schemas import DocumentDetail, DocumentSummary, HealthResponse
from app.services.ingest import IngestError, ingest_pdf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

# One upload is read into memory before extraction, so keep the cap modest.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Wait for Postgres and create the tables before serving requests."""
    init_db()
    yield


app = FastAPI(
    title="Agno Insurance Ingest API",
    version="0.1.0",
    summary="Run the insurance parser agent over uploaded PDFs and store the result.",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": "Agno Insurance Ingest API", "docs": "/docs"}


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health(session: Session = Depends(get_session)):
    """Report the app, the database and the registered agents."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("health check: database unreachable: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "database": "unreachable", "agents": sorted(AGENTS)},
        )
    return HealthResponse(status="ok", database="reachable", agents=sorted(AGENTS))


@app.post(
    "/documents",
    response_model=DocumentDetail,
    status_code=status.HTTP_201_CREATED,
    tags=["documents"],
    summary="Upload insurance PDFs",
    description=(
        "Store one PDF: extract its text, run the insurance parser agent over it and "
        "save the fields it finds. Missing fields are stored as NULL, not as an error."
    ),
)
async def upload_document(
    file: UploadFile = File(..., description="The insurance PDF to ingest"),
    session: Session = Depends(get_session),
):
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"the file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )

    # Keep only the base name: the upload's own path is not ours to trust.
    filename = Path(file.filename or "upload.pdf").name or "upload.pdf"

    try:
        document = ingest_pdf(session, filename=filename, data=data)
    except IngestError as exc:
        logger.info("upload of %s rejected: %s", filename, exc)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return document


@app.get(
    "/documents",
    response_model=list[DocumentSummary],
    tags=["documents"],
    summary="List stored documents",
    description="Newest first. The list leaves out the raw text; fetch one document for that.",
)
def list_documents(
    limit: int = Query(50, ge=1, le=200, description="How many documents to return"),
    offset: int = Query(0, ge=0, description="How many documents to skip"),
    session: Session = Depends(get_session),
):
    statement = (
        select(InsuranceDocument)
        .order_by(InsuranceDocument.ingested_at.desc(), InsuranceDocument.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


@app.get(
    "/documents/{document_id}",
    response_model=DocumentDetail,
    tags=["documents"],
    summary="Fetch one stored document",
    description="Everything stored for the document, including the full extracted text.",
)
def get_document(document_id: int, session: Session = Depends(get_session)):
    document = session.get(InsuranceDocument, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no document with id {document_id}",
        )
    return document
