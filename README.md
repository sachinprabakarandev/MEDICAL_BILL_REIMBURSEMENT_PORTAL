# IOCL Medical Claim Validation System

A web application that validates employee medical reimbursement claims by extracting data
from uploaded prescriptions and bills (OCR), matching prescribed medicines against billed
items, and applying a configurable rules engine. Includes role-based dashboards for
employees, reviewers, and admins, plus audit logging and exportable reports.

## Tech Stack

- **Backend:** FastAPI, SQLAlchemy (SQLite), python-jose (JWT auth)
- **Frontend:** Jinja2 server-rendered templates + static CSS
- **OCR / parsing:** pdfplumber, Pillow
- **Reports:** openpyxl (Excel), reportlab (PDF), CSV

## Project Structure

```
backend/
  app/
    main.py            # FastAPI app, routes, template wiring
    auth.py            # JWT auth & password hashing
    database.py        # SQLAlchemy engine/session
    models.py          # ORM models
    ocr_engine.py      # Document text extraction
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
