"""The first agent: read an insurance PDF and return its key fields as JSON."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from agno.agent import Agent
from pydantic import ValidationError

from app.agents.model import build_model
from app.schemas import InsuranceFields
from app.tools.pdf_tools import extract_pdf_text

logger = logging.getLogger(__name__)

AGENT_NAME = "insurance-pdf-parser"

# Keep the prompt a sane size for very long documents; the agent can read the
# whole file itself with its tool when the text below looks truncated.
MAX_PROMPT_TEXT_CHARS = 60_000

INSTRUCTIONS = [
    "You extract structured data from insurance documents.",
    "Use the extract_pdf_text tool to read the PDF whenever you need its contents.",
    "Answer with a single JSON object and nothing else: no prose, no markdown fences, no comments.",
    (
        "The JSON object has exactly these keys: policy_number, insurer, insured_name, "
        "policy_start_date, policy_end_date, premium_amount, premium_currency, "
        "coverage_amount, document_type."
    ),
    "policy_start_date and policy_end_date are ISO dates, YYYY-MM-DD.",
    (
        "premium_amount and coverage_amount are plain numbers: no currency symbols, no "
        "thousands separators. coverage_amount is the coverage or sum insured."
    ),
    "premium_currency is an ISO 4217 code such as INR, USD, EUR, GBP.",
    (
        "document_type is a short label such as 'policy schedule', 'certificate of "
        "insurance', 'invoice' or 'endorsement'."
    ),
    "Use null for any field the document does not contain. Never invent or calculate values.",
    (
        "If a value appears more than once, prefer what is printed on the policy "
        "schedule over values derived elsewhere in the document."
    ),
]

_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def build_insurance_agent() -> Agent:
    """Build the insurance document parser agent."""
    return Agent(
        name=AGENT_NAME,
        model=build_model(),
        tools=[extract_pdf_text],
        description="Reads an insurance PDF and returns its policy fields as JSON.",
        instructions=INSTRUCTIONS,
        markdown=False,
    )


def parse_insurance_fields(agent: Agent, pdf_path: str, raw_text: str) -> InsuranceFields:
    """Run the agent over a document and turn its reply into ``InsuranceFields``.

    Odd replies are logged and treated as "no fields found" rather than raising:
    the document itself is still worth storing.
    """
    prompt = _build_prompt(pdf_path, raw_text)
    response = agent.run(prompt)
    content = getattr(response, "content", response)

    data = _load_json_object(content)
    if not data:
        logger.warning(
            "agent reply was not a JSON object; storing the document without fields: %.200s",
            content,
        )
        return InsuranceFields()

    try:
        return InsuranceFields.model_validate(data)
    except ValidationError as exc:
        logger.warning("agent JSON had unusable values: %s", exc)
        return InsuranceFields()


def _build_prompt(pdf_path: str, raw_text: str) -> str:
    text = raw_text.strip()
    note = ""
    if len(text) > MAX_PROMPT_TEXT_CHARS:
        text = text[:MAX_PROMPT_TEXT_CHARS]
        note = (
            "\n(The text below is cut short; call extract_pdf_text with the file path for "
            "the rest of the document.)"
        )
    return (
        f"Extract the insurance fields from this document: {Path(pdf_path).name}\n"
        f"Its text was already extracted for speed.{note}\n\n"
        f"--- BEGIN PDF TEXT ---\n{text}\n--- END PDF TEXT ---"
    )


def _load_json_object(content: Any) -> dict[str, Any]:
    """Find the JSON object in a model reply, tolerating fences and stray prose."""
    if content is None:
        return {}
    text = _JSON_FENCE.sub("", str(content)).strip()
    if not text:
        return {}

    for candidate in (text, _object_slice(text)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def _object_slice(text: str) -> str | None:
    """The widest {...} span in the text, if there is one."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    return text[start : end + 1]
