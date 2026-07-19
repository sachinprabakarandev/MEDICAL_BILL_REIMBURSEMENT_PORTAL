import sys
import os

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ocr_engine import parse_extracted_text
from app.database import SessionLocal
from app.models import Claim, PrescriptionMedicine, BillMedicine, User
from app.intelligence import match_prescription_and_bill, normalize_text
from app.rules import evaluate_rules
from datetime import datetime

# Initialize Session
db = SessionLocal()

# Set up test inputs
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
- Rx.
Tab. Celebrex 200mg 1-0-0 x 5 days.
Tab. Enzymex Forte 1-1-1 x 5 days.
Volitra APS Spray.
"""

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

# Extract
presc_extracted = parse_extracted_text(raw_text, "prescription")
bill_extracted = parse_extracted_text(raw_bill_text, "bill")

# Models mapping (as done in /api/verify)
p_meds = []
for m in presc_extracted["medicines"]:
    pm = PrescriptionMedicine(
        medicine_name=m["medicine_name"],
        strength=m.get("strength"),
        dosage=m.get("dosage"),
        frequency=m.get("frequency"),
        duration_days=m.get("duration_days"),
        quantity=m.get("quantity")
    )
    pm.normalized_name = normalize_text(pm.medicine_name)
    p_meds.append(pm)
    
b_meds = []
for m in bill_extracted["medicines"]:
    bm = BillMedicine(
        medicine_name=m["medicine_name"],
        strength=m.get("strength"),
        quantity=m.get("quantity"),
        unit_price=m.get("unit_price", 0.0),
        total_price=m.get("total_price", 0.0)
    )
    bm.normalized_name = normalize_text(bm.medicine_name)
    b_meds.append(bm)

# Run match
matches = match_prescription_and_bill(db, p_meds, b_meds)

# Create a mock Claim
user = db.query(User).filter(User.role == "employee").first()
claim = Claim(
    user_id=user.id if user else 1,
    status="Pending",
    total_claimed_amount=430.0,
    date_submitted=datetime.now()
)

# Run rules
evaluated = evaluate_rules(db, claim, matches)

print("=== PIPELINE MATCH & DECISION RESULTS ===")
for item in evaluated:
    pm = item["prescribed_item"]
    bm = item["billed_item"]
    p_name = pm.medicine_name if pm else "N/A"
    b_name = bm.medicine_name if bm else "N/A"
    status = item["match_status"]
    reason = item["reason"]
    print(f"Prescribed: {p_name} | Billed: {b_name} | Status: {status} | Reason: {reason}")
