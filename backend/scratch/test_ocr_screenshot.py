import sys
import os

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ocr_engine import parse_extracted_text
from app.database import SessionLocal
from app.seed import seed_db

# Make sure DB is seeded
db = SessionLocal()

raw_text = """
Dr Hariharan M MBBS, MS Ortho, DNB Ortho, FRCS Ed (T&O)
Regn No: TNMC - 100926
Consultant
Department of Orthopedics
MGM HEALTHCARE
25/5/24 MR. MUNNAM PAVAN KUMAR 32/M
c/o (R) Shoulder pain - 2 weeks.
No h/o Trauma / dislocation / instability symptoms.
O/E: Full ROM, Jobes $\\ominus$, Impingement $\\ominus$.
MRI: Small anterior paralabral cyst, labral tear (4-6 o clock).
Supraspinatus tendinitis
R.
- Physio: Cuff strengthening exercises / ER/IR isometric exercises
- Likely to need arthroscopic labral repair with cyst drainage if
with physio.
- Rx.
Tab. Celebrex 200mg 1-0-0 x 5 days.
Tab. Enzymex Forte 1-1-1 x 5 days.
Volitra APS Spray.
MGM HEALTHCARE
72, Nelson Manickam Road, Aminjikarai, Chennai - 600029
* mgmhealthcare.in Book an appointment: 044 4524 2424
"""

result = parse_extracted_text(raw_text, "prescription")

print("=== PRESCRIPTION PARSING RESULT ===")
print("--- OCR Metadata ---")
for k, v in result["metadata"].items():
    print(f"{k}: {v}")

print("\n--- Extracted Medicines ---")
for med in result["medicines"]:
    print(med)

raw_bill_text = """
MGM Healthcare Pharmacy
Bill No: INV-48201
Date: 25/5/24
Patient Name: Mr. Munnam Pavan Kumar

Items:
1. Celebrex 200mg   Qty 5   Rate 20.00   Amount 100.00
2. Enzymex Forte    Qty 15  Rate 12.00   Amount 180.00
3. Volitra APS Spray Qty 1   Rate 150.00  Amount 150.00
Gross Total: 430.00
"""

bill_result = parse_extracted_text(raw_bill_text, "bill")

print("\n=== BILL PARSING RESULT ===")
print("--- OCR Metadata ---")
for k, v in bill_result["metadata"].items():
    print(f"{k}: {v}")

print("\n--- Extracted Medicines ---")
for med in bill_result["medicines"]:
    print(med)
