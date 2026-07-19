# IOCL Medical Claim Validation System

A web application that validates employee medical reimbursement claims by extracting data
from uploaded prescriptions and bills (OCR), matching prescribed medicines against billed
items, and applying a configurable rules engine. Includes role-based dashboards for
employees, reviewers, and admins, plus audit logging and exportable reports.

## Tech Stack

- **Backend:** FastAPI, SQLAlchemy (SQLite), python-jose (JWT auth)
- **Frontend:** Jinja2 server-rendered templates + static CSS
- **OCR / parsing:** Gemma vision model via Ollama (handwriting), Apple Vision Swift helper, pdfplumber, Pillow
- **Reports:** openpyxl (Excel), reportlab (PDF), CSV

## Project Structure

```
backend/
  app/
    main.py            # FastAPI app, routes, template wiring
    auth.py            # JWT auth & password hashing
    database.py        # SQLAlchemy engine/session
    models.py          # ORM models
    ocr_engine.py      # Document text extraction (gateway + regex parsing + fallbacks)
    gemma_ocr.py       # Vision LLM extraction (Gemma via Ollama) for handwriting
    intelligence.py    # Prescription <-> bill matching
    rules.py           # Claim validation rules engine
    reports.py         # CSV / Excel / PDF report generation
    seed.py            # Creates tables + seeds demo users & drug master
    data/              # SQLite DB + uploads (git-ignored, created at runtime)
  test_pipeline.py     # Pipeline test
  requirements.txt
frontend/
  templates/           # Jinja2 HTML templates
  static/css/          # Stylesheets
```

## Setup

Requires Python 3.10+.

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create and seed the SQLite database (users, drug master data)
python app/seed.py

# Run the app (from the backend/ directory)
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000

### Handwriting OCR (Gemma vision model)

Handwritten doctor prescriptions are read by a local **Gemma** multimodal model
served through [Ollama](https://ollama.com). This is optional — if Ollama or the
model isn't available, extraction automatically falls back to the Apple Vision
Swift helper / pdfplumber + regex path.

```bash
brew install ollama            # macOS
ollama serve                   # start the local server (or: brew services start ollama)
ollama pull gemma3:4b          # vision-capable model (~3.3 GB)
```

Configurable via environment variables (all optional):

| Variable        | Default                  | Purpose                          |
|-----------------|--------------------------|----------------------------------|
| `OLLAMA_URL`    | `http://localhost:11434` | Ollama server address            |
| `GEMMA_MODEL`   | `gemma3:4b`              | Model tag (e.g. `gemma3:12b`)    |
| `GEMMA_TIMEOUT` | `180`                    | Per-page request timeout (secs)  |

Larger tags (`gemma3:12b`, `gemma3:27b`) read messy handwriting more accurately
at the cost of speed and memory.

## Demo Accounts

All seeded accounts use the password `password123`:

| Username    | Role     |
|-------------|----------|
| `emp1`      | Employee |
| `emp2`      | Employee |
| `reviewer1` | Reviewer |
| `admin1`    | Admin    |

## Notes

- The SQLite database (`backend/app/data/medical_verification.db`) and uploaded files
  (`backend/app/data/uploads/`) are intentionally git-ignored. The database is regenerated
  by running `python app/seed.py`.
- `backend/app/auth.py` contains a hardcoded `SECRET_KEY` for local development. **Set this
  from an environment variable and rotate it before any non-local / public deployment.**
