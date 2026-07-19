import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Claim, PrescriptionMedicine, BillMedicine, ValidationResult

db = SessionLocal()

claim = db.query(Claim).order_by(Claim.id.desc()).first()
if claim:
    print(f"=== Claim #{claim.id} (Status: {claim.status}) ===")
    print(f"Total Claimed: {claim.total_claimed_amount} | Approved: {claim.approved_amount} | Rejected: {claim.rejected_amount}")
    
    print("\n--- Prescription Medicines ---")
    for pm in claim.prescription_medicines:
        print(f"ID: {pm.id} | Name: {pm.medicine_name} | Strength: {pm.strength} | Dosage: {pm.dosage} | Freq: {pm.frequency} | Dur: {pm.duration_days} | Qty: {pm.quantity}")
        
    print("\n--- Bill Medicines ---")
    for bm in claim.bill_medicines:
        print(f"ID: {bm.id} | Name: {bm.medicine_name} | Strength: {bm.strength} | Qty: {bm.quantity} | Unit Price: {bm.unit_price} | Total Price: {bm.total_price}")
        
    print("\n--- Validation Results ---")
    for vr in claim.validation_results:
        print(f"Prescribed: {vr.prescribed_name} | Billed: {vr.billed_name} | Status: {vr.match_status} | Reason: {vr.match_reason}")
else:
    print("No claims found in DB.")
