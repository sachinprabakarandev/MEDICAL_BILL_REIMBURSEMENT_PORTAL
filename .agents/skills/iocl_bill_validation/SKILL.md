---
name: "iocl_medical_bill_validation"
description: "Instructions and context for validating IOCL medical claims, prescriptions, and pharmacy bills."
---

# IOCL Medical Bill Validation Skill

This skill contains instructions and domain knowledge for validating IOCL medical claims, prescriptions, and bills.

## Project Architecture
- **Backend**: FastAPI web service running on port 8000.
- **Frontend**: Tailwind-styled HTML/JS templates (`templates/claim_verification.html`, `templates/dashboard.html`).
- **Database**: SQLite database stored at `backend/app/data/medical_verification.db`.
- **OCR Engine**: Located at `backend/app/ocr_engine.py` (uses Native Swift OCR and pdfplumber with selective Gemma Vision fallback).
