# Agno-Python
Agno Framework

An Agno agent that reads insurance PDFs and stores what it finds in a local Postgres
database, behind a small FastAPI app. The first agent is an insurance document parser;
the project is laid out so the next agents can be added next to it.

## What it does

1. `POST /documents` receives a PDF.
2. `app/tools/pdf_tools.py` extracts the text locally with **pdfplumber** — no cloud OCR,
   no external service. The same function is registered as an **Agno tool**, so the agent
   can read the file itself when it needs to; the service also calls it once before the
   agent so the raw text is always stored exactly as it came out of the PDF.
3. The **`insurance-pdf-parser`** agent (`app/agents/insurance_parser.py`) reads that text
   with the OpenAI model named in `MODEL_NAME` and answers with a single JSON object of
   fields.
4. `app/services/ingest.py` reads that JSON leniently (`app/schemas.py`) and writes one
   row to Postgres.

Nothing fails because a field is missing. Every field is optional, and a value that cannot
be read (a date like "end of March", an amount like "as per schedule") is stored as `NULL`
while the rest of the document is kept.

## Quickstart with Docker Compose

```bash
cp .env.example .env          # then put your real OPENAI_API_KEY in .env
docker compose up --build
```

- API and interactive docs: <http://localhost:8000/docs>
- Postgres: `localhost:5432` (host port; container port is always 5432)
- Named volume `pgdata` holds the data, so it survives `docker compose down`
  (use `docker compose down -v` to wipe it)

The app waits until the database healthcheck passes, and also retries the connection on
startup, then creates any missing tables (safe to run repeatedly).

Upload a PDF and see the result:

```bash
curl -X POST http://localhost:8000/documents \
  -F "file=@/path/to/policy.pdf"
```

## Running without Docker

Compose is still the easy way to get Postgres; run only the database in compose and the
app in your shell:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d db
cp .env.example .env          # set OPENAI_API_KEY
uvicorn app.main:app --reload
```

Python 3.12 is what the Docker image uses.

## Endpoints

| Method | Path               | What it does                                                    |
| ------ | ------------------ | --------------------------------------------------------------- |
| `POST` | `/documents`       | Upload one PDF (max 25 MB), run the agent, store the result. Returns the stored document with its extracted fields. |
| `GET`  | `/documents`       | List stored documents, newest first. `limit` (1–200, default 50) and `offset` (default 0). No raw text in the list. |
| `GET`  | `/documents/{id}`  | One stored document, including the full raw text. `404` if there is no such id. |
| `GET`  | `/health`          | `{"status", "database", "agents"}`. `503` if Postgres is unreachable. |

Use the **Try it out** buttons on <http://localhost:8000/docs> for all of these.

Status codes on upload: `201` stored, `415` not a PDF, `422` empty or unreadable PDF,
`502` the model call failed (nothing is stored in that case).

## What is stored

One row per uploaded document in the table `insurance_documents`:

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | integer, primary key | Row id, used in `/documents/{id}`. |
| `filename` | text | Original filename of the upload. |
| `content_hash` | text, indexed | SHA-256 of the uploaded bytes. |
| `ingested_at` | timestamptz | When the row was written (database default `now()`). |
| `raw_text` | text | All text extracted from the PDF. |
| `policy_number` | text | Policy number as printed. |
| `insurer` | text | Insurance company. |
| `insured_name` | text | Insured person or company. |
| `policy_start_date` | date | Policy period start. |
| `policy_end_date` | date | Policy period end. |
| `premium_amount` | numeric(14,2) | Premium, without currency symbols or separators. |
| `premium_currency` | text | ISO 4217 code of the premium (INR, USD, …). |
| `coverage_amount` | numeric(18,2) | Coverage / sum insured. |
| `document_type` | text | Short label, e.g. `policy schedule`, `certificate of insurance`, `invoice`, `endorsement`. |

Every extracted field is nullable: `NULL` means "not found in this PDF", not an error.

## Configuration

All settings come from environment variables, and `.env` is read when present.
`.env` is git-ignored and `.dockerignore`d — never commit a real key.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AGNO_MODEL_PROVIDER` | `openai` | Model provider. Only `openai` is wired up today; an unknown value fails with a clear message. |
| `MODEL_NAME` | `gpt-4o-mini` | Model name passed to the provider. |
| `OPENAI_API_KEY` | — | Required. The key itself, never in the repository. |
| `OPENAI_BASE_URL` | — | Optional, for an OpenAI-compatible gateway. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `agno` | Database credentials, used by both the app and the Postgres container. |
| `POSTGRES_HOST` | `localhost` | Compose sets this to `db` for the app container. |
| `POSTGRES_PORT` | `5432` | Host port Postgres is published on, and the port the app dials. |
| `DATABASE_URL` | — | Optional full SQLAlchemy URL; overrides the `POSTGRES_*` parts. |

## Project layout

```
app/
  main.py                    FastAPI app and the endpoints
  config.py                  Settings from environment variables
  db.py                      Engine, session dependency, startup table creation
  models.py                  SQLAlchemy models (insurance_documents)
  schemas.py                 Agent output shape + API responses, lenient coercion
  agents/
    __init__.py              AGENTS registry (name -> factory)
    model.py                 Builds the Agno model from settings
    insurance_parser.py      The first agent + turning its reply into fields
  tools/
    pdf_tools.py             pdfplumber text extraction (the agent's tool)
  services/
    ingest.py                Upload -> validate -> extract -> agent -> store
Dockerfile                   Python 3.12 image running uvicorn on port 8000
docker-compose.yml           app + Postgres 16 with a healthcheck and named volume
```

## Adding the next agent

1. Put the new agent in `app/agents/`, for example `claims_extractor.py`, with a
   `build_claims_agent()` that returns an `agno.agent.Agent`. Build its model with
   `app.agents.model.build_model()` so it follows the same environment variables.
2. Give it a name constant and register it in the `AGENTS` dict in
   `app/agents/__init__.py`. `GET /health` then lists it, and `get_agent(name)` builds a
   fresh instance per request.
3. Reuse `app/tools/pdf_tools.py`, and put any new tool functions in `app/tools/` — a
   plain typed function with a docstring is all Agno needs.
4. For new storage: a model in `app/models.py` (tables are created on startup), a response
   model in `app/schemas.py`, and an endpoint in `app/main.py` — or a new router module
   next to it if the API grows.

## Limitations, on purpose

- **Scanned PDFs** with no text layer are stored with their metadata and empty fields, and
a warning is logged. There is no OCR.
- **A failed model call stores nothing** and returns `502`, so a half-parsed row can never
end up in the table.
- **Re-uploading the same file creates a second row.** `content_hash` is stored and indexed
so duplicates are easy to find, but nothing de-duplicates yet.
- **No migrations and no auth**; tables are created on startup, and the API is meant for
localhost.
- Nothing here has been run yet: the image was not built and no real PDF was processed.
