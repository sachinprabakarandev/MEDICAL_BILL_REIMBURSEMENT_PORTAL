import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ocr_engine import process_and_extract_document
from app.intelligence import match_prescription_and_bill, normalize_text
from app.rules import evaluate_rules, parse_frequency
from app.database import SessionLocal
from app.models import Claim, PrescriptionMedicine, BillMedicine, User
from datetime import datetime

db = SessionLocal()

# 1. OCR
presc_extracted = process_and_extract_document("/Users/sachinswazer/Desktop/IOCL_MEDICAL_BILL_VALIDATION/backend/scratch/Dr.Hariharan_OPD.pdf", "prescription")
bill_extracted = process_and_extract_document("/Users/sachinswazer/Desktop/IOCL_MEDICAL_BILL_VALIDATION/backend/scratch/MGM_Healthcare_Bill.pdf", "bill")

print("=== RAW PRESCRIPTION TEXT ===")
print(repr(presc_extracted["raw_text"]))

print("\n=== OCR EXTRACTED PRESCRIPTION MEDICINES ===")
for m in presc_extracted["parsed_data"]["medicines"]:
    print(m)

print("\n=== OCR EXTRACTED BILL MEDICINES ===")
for m in bill_extracted["parsed_data"]["medicines"]:
    print(m)

# Build models
p_meds = []
for m in presc_extracted["parsed_data"]["medicines"]:
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
for m in bill_extracted["parsed_data"]["medicines"]:
    bm = BillMedicine(
        medicine_name=m["medicine_name"],
        strength=m.get("strength"),
        quantity=m.get("quantity"),
        unit_price=m.get("unit_price", 0.0),
        total_price=m.get("total_price", 0.0)
    )
    bm.normalized_name = normalize_text(bm.medicine_name)
    b_meds.append(bm)

# Match
matched_results = match_prescription_and_bill(db, p_meds, b_meds)

# Run rules
temp_claim = Claim(
    user_id=1,
    status="Pending",
    total_claimed_amount=430.0,
    date_submitted=datetime.now()
)
evaluated_results = evaluate_rules(db, temp_claim, matched_results)

print("\n=== EVALUATED RESULTS FROM RULES ===")
for item in evaluated_results:
    pm = item["prescribed_item"]
    bm = item["billed_item"]
    status = item["match_status"]
    reason = item["reason"]
    
    p_name = pm.medicine_name if pm else "— Not prescribed —"
    b_name = bm.medicine_name if bm else "— Not purchased —"
    print(f"P: {p_name} | B: {b_name} | Status: {status} | Reason: {reason}")
    
    # Calculate pro-rata / warnings as done in main.py
    if status == "Pending Review" or status == "Approved" or status == "Warning":
        if pm and bm:
            duration = pm.duration_days or 0
            freq_mult = parse_frequency(pm.dosage or pm.frequency or "")
            expected_qty = duration * freq_mult
            billed_qty = bm.quantity or 1
            print(f"  Debug: pm.dosage={pm.dosage} | pm.frequency={pm.frequency} | freq_mult={freq_mult} | expected_qty={expected_qty} | billed_qty={billed_qty}")
