import re
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import Claim, PrescriptionMedicine, BillMedicine

def _utcnow():
    """Naive UTC timestamp (replacement for deprecated datetime.utcnow)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

def evaluate_rules(db: Session, claim: Claim, matches: list) -> list:
    """
    Evaluates business and medical claims validation rules on matched items.
    Updates the match_status and reason of matches based on rules.
    """
    updated_matches = []
    
    # We could query previous claims to check for duplicates
    # Let's check for duplicate claims from the same employee
    existing_claims = db.query(Claim).filter(
        Claim.user_id == claim.user_id,
        Claim.id != claim.id,
        Claim.status == "Approved"
    ).all()
    
    # Basic claim-level checks
    # (e.g., date checks, duplicates, limits)
    for match in matches:
        pm = match["prescribed_item"]
        bm = match["billed_item"]
        p_res = match["prescribed_res"]
        b_res = match["billed_res"]
        
        status = match["match_status"]
        reason = match["reason"]
        score = match["match_score"]
        
        # Rule 1: Non-medical consumables (e.g., Soap, Snacks, Horlicks)
        if bm and b_res and b_res["resolved"] and b_res["drug_id"] >= 100:
            status = "Rejected"
            reason = f"Automatically rejected: Non-medical consumable ({b_res['category']})."
            
        # Rule 2: Purchased but not prescribed
        elif bm and not pm:
            if b_res and b_res["resolved"] and b_res["drug_id"] >= 100:
                status = "Rejected"
                reason = f"Automatically rejected: Non-medical consumable ({b_res['category']})."
            else:
                status = "Rejected"
                reason = "Not approved: Purchased item is not present in doctor's prescription."
                
        # Rule 3: Prescribed but not purchased
        elif pm and not bm:
            status = "Rejected"
            reason = "Not approved: Prescribed medicine was not purchased."
            
        # Rule 4: Match checks (both pm and bm exist)
        elif pm and bm:
            # Check Strength matching
            pm_strength = extract_numerical_strength(pm.strength or pm.medicine_name)
            bm_strength = extract_numerical_strength(bm.strength or bm.medicine_name)
            
            strength_warning = False
            if pm_strength and bm_strength and pm_strength != bm_strength:
                strength_warning = True
                
            # Check Quantity matching
            # Expected quantity = duration * frequency_multiplier
            # If no duration/frequency is extracted, we can try to find from text or default
            duration = pm.duration_days or 0
            freq_mult = parse_frequency(pm.dosage or pm.frequency or "")
            
            expected_qty = duration * freq_mult
            billed_qty = bm.quantity or 0
            
            qty_warning = False
            if expected_qty > 0 and billed_qty > (expected_qty * 1.2): # 20% buffer
                qty_warning = True
                
            # Combine warnings into decision
            reasons = []
            if strength_warning:
                reasons.append(f"Strength mismatch (Prescribed: {pm.strength or pm_strength}, Billed: {bm.strength or bm_strength})")
            if qty_warning:
                reasons.append(f"Excess quantity purchased (Expected: {expected_qty}, Billed: {billed_qty})")
                
            # Duplicate medicine check within same claim
            # (already aggregated in matches, but let's check historical)
            for prev_claim in existing_claims:
                # Check if this medicine was already approved in another claim recently (e.g., last 15 days)
                # For simplicity, we just flag it if there is a match
                claim_date = claim.date_submitted or _utcnow()
                prev_date = prev_claim.date_submitted or _utcnow()
                days_diff = (claim_date - prev_date).days
                if days_diff <= 15:
                    prev_medicines = [m.normalized_name for m in prev_claim.bill_medicines]
                    if bm.normalized_name in prev_medicines:
                        reasons.append(f"Duplicate purchase (Same medicine was approved in Claim #{prev_claim.id} {days_diff} days ago)")
                        
            if reasons:
                status = "Pending Review"
                reason = "Warning flags: " + "; ".join(reasons)
            else:
                if status == "Approved":
                    reason = f"Approved brand equivalent: {pm.medicine_name} -> {bm.medicine_name}."
                        
        updated_matches.append({
            "prescribed_item": pm,
            "billed_item": bm,
            "prescribed_res": p_res,
            "billed_res": b_res,
            "match_score": score,
            "match_status": status,
            "reason": reason
        })
        
    return updated_matches

def extract_numerical_strength(text: str) -> str:
    """Helper to pull numerical parts and units of strength"""
    if not text:
        return ""
    # Matches patterns like 650 mg, 650mg, 40mg, 40 mg, 500
    match = re.search(r'\b(\d+)\s*(mg|g|mcg|ml)?\b', text, re.IGNORECASE)
    if match:
        num = match.group(1)
        unit = match.group(2) or "mg"
        return f"{num} {unit.lower()}"
    return ""

def parse_frequency(dosage: str) -> int:
    """
    Parses common frequency codes (TDS, BD, OD, 1-0-1, etc.) into daily multiplier.
    """
    clean_dosage = dosage.upper().strip()
    
    # 1-0-1 or 1-1-1 patterns
    if re.match(r'^\d\-\d\-\d$', clean_dosage):
        parts = [int(p) for p in clean_dosage.split('-')]
        return sum(parts)
    if re.match(r'^\d\-\d\-\d\-\d$', clean_dosage):
        parts = [int(p) for p in clean_dosage.split('-')]
        return sum(parts)
        
    # Standard Latin abbreviations
    freq_map = {
        "OD": 1,       # Once daily
        "BD": 2,       # Twice daily
        "TDS": 3,      # Thrice daily
        "QDS": 4,      # Four times daily
        "HS": 1,       # At bedtime
        "SOS": 1,      # As needed (default to 1)
        "ONCE": 1,
        "TWICE": 2,
        "THRICE": 3,
        "DAILY": 1
    }
    
    for key, val in freq_map.items():
        if key in clean_dosage:
            return val
            
    # If it is a direct number like "twice a day" or "2 times"
    match = re.search(r'\b(\d+)\s*(?:times|daily|day)\b', clean_dosage, re.IGNORECASE)
    if match:
        return int(match.group(1))
        
    # Default fallback
    return 1
