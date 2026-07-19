import re
from sqlalchemy.orm import Session
from app.models import DrugMaster, DrugSynonyms, DrugBrandMapping

def normalize_text(text: str) -> str:
    if not text:
        return ""
    # Lowercase
    normalized = text.lower()
    # Strip strength annotations like "650mg", "650 mg", "625", "40 mg", "10mg + 5mg", etc.
    # Keep the base name clean
    normalized = re.sub(r'\b\d+(?:\s*mg|\s*g|\s*ml|\s*mcg)?\b', '', normalized)
    # Remove symbols and punctuation
    normalized = re.sub(r'[^a-z0-9\s\+]', ' ', normalized)
    # Collapse multiple whitespaces
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized

def extract_strength(text: str) -> str:
    if not text:
        return ""
    # Find patterns like 650mg, 650 mg, 40mg, 10 mg + 5 mg, etc.
    matches = re.findall(r'\b\d+\s*(?:mg|mcg|g|ml)?(?:\s*\+\s*\d+\s*(?:mg|mcg|g|ml)?)?\b', text, re.IGNORECASE)
    if matches:
        return matches[0].strip()
    return ""

def calculate_levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return calculate_levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
        
    return previous_row[-1]

def string_similarity(s1: str, s2: str) -> float:
    import difflib
    # Normalize strings
    ns1 = normalize_text(s1)
    ns2 = normalize_text(s2)
    
    if not ns1 or not ns2:
        return 0.0
        
    # Exact match after normalization
    if ns1 == ns2:
        return 1.0
        
    # Overall character-level similarity
    overall_ratio = difflib.SequenceMatcher(None, ns1, ns2).ratio()
    
    # Token-level fuzzy similarity
    tokens1 = ns1.split()
    tokens2 = ns2.split()
    
    if not tokens1 or not tokens2:
        return overall_ratio
        
    # Match each token in tokens1 to the best matching token in tokens2
    matched_count = 0
    used_indices = set()
    
    for t1 in tokens1:
        best_sim = 0.0
        best_idx = -1
        for idx, t2 in enumerate(tokens2):
            if idx in used_indices:
                continue
            sim = difflib.SequenceMatcher(None, t1, t2).ratio()
            if sim > best_sim:
                best_sim = sim
                best_idx = idx
        
        # If the tokens match with at least 70% similarity, count it as a match
        if best_sim >= 0.70:
            matched_count += 1
            used_indices.add(best_idx)
            
    # Fuzzy Jaccard score
    fuzzy_union = len(tokens1) + len(tokens2) - matched_count
    fuzzy_token_score = (matched_count / fuzzy_union) if fuzzy_union > 0 else 0.0
    
    # Return the maximum of overall similarity and token fuzzy similarity
    return max(overall_ratio, fuzzy_token_score)

def resolve_medicine(db: Session, raw_name: str) -> dict:
    """
    Tries to resolve raw medicine name to a known generic medicine in DrugMaster.
    Returns a dict with resolution details.
    """
    clean_name = raw_name.strip()
    norm_name = normalize_text(clean_name)
    strength = extract_strength(clean_name)
    
    # 1. Check exact/case-insensitive match in DrugMaster (Generic Name)
    generic = db.query(DrugMaster).filter(DrugMaster.generic_name.ilike(clean_name)).first()
    if generic:
        return {
            "resolved": True,
            "drug_id": generic.id,
            "generic_name": generic.generic_name,
            "category": generic.drug_category,
            "match_type": "Generic Direct Match",
            "score": 100.0,
            "original_name": raw_name,
            "strength": strength or "N/A"
        }
        
    # 2. Check brand name mapping
    # Check exact brand name match
    brand_map = db.query(DrugBrandMapping).filter(DrugBrandMapping.brand_name.ilike(norm_name)).first()
    if not brand_map:
        # If not, check brand name starts with or resembles the word
        # (e.g. "Dolo 650" starts with "Dolo")
        # Split tokens and try matching brands
        tokens = norm_name.split()
        for token in tokens:
            if len(token) > 2:
                brand_map = db.query(DrugBrandMapping).filter(DrugBrandMapping.brand_name.ilike(token)).first()
                if brand_map:
                    break
                    
    if brand_map:
        generic = db.query(DrugMaster).filter(DrugMaster.id == brand_map.drug_id).first()
        if generic:
            return {
                "resolved": True,
                "drug_id": generic.id,
                "generic_name": generic.generic_name,
                "category": generic.drug_category,
                "match_type": "Brand Mapping",
                "score": 98.0,
                "original_name": raw_name,
                "brand_matched": brand_map.brand_name,
                "strength": strength or brand_map.strength_standardized or "N/A"
            }
            
    # 3. Check Synonyms
    synonym = db.query(DrugSynonyms).filter(DrugSynonyms.synonym_name.ilike(norm_name)).first()
    if synonym:
        generic = db.query(DrugMaster).filter(DrugMaster.id == synonym.drug_id).first()
        if generic:
            return {
                "resolved": True,
                "drug_id": generic.id,
                "generic_name": generic.generic_name,
                "category": generic.drug_category,
                "match_type": "Synonym Match",
                "score": 95.0,
                "original_name": raw_name,
                "strength": strength or "N/A"
            }
            
    # 4. Fuzzy Similarity Search against DrugMaster
    best_match = None
    best_score = 0.0
    
    # Compare with all generics
    generics = db.query(DrugMaster).all()
    for g in generics:
        score = string_similarity(clean_name, g.generic_name)
        if score > best_score:
            best_score = score
            best_match = g
            
    # Compare with all brands
    brands = db.query(DrugBrandMapping).all()
    best_brand_match = None
    best_brand_score = 0.0
    for b in brands:
        score = string_similarity(clean_name, b.brand_name)
        if score > best_brand_score:
            best_brand_score = score
            best_brand_match = b
            
    # Determine the absolute best fuzzy match
    if best_score >= 0.70 or best_brand_score >= 0.70:
        if best_brand_score > best_score:
            # Map brand to generic
            generic = db.query(DrugMaster).filter(DrugMaster.id == best_brand_match.drug_id).first()
            return {
                "resolved": True,
                "drug_id": generic.id,
                "generic_name": generic.generic_name,
                "category": generic.drug_category,
                "match_type": "Fuzzy Brand Match",
                "score": round(best_brand_score * 100, 1),
                "original_name": raw_name,
                "brand_matched": best_brand_match.brand_name,
                "strength": strength or best_brand_match.strength_standardized or "N/A"
            }
        else:
            return {
                "resolved": True,
                "drug_id": best_match.id,
                "generic_name": best_match.generic_name,
                "category": best_match.drug_category,
                "match_type": "Fuzzy Generic Match",
                "score": round(best_score * 100, 1),
                "original_name": raw_name,
                "strength": strength or "N/A"
            }
            
    # Unresolved
    return {
        "resolved": False,
        "generic_name": None,
        "category": "Unknown",
        "match_type": "None",
        "score": 0.0,
        "original_name": raw_name,
        "strength": strength or "N/A"
    }

def match_prescription_and_bill(db: Session, prescribed_medicines: list, billed_medicines: list) -> list:
    """
    Performs core matching logic between all prescription medicines and bill medicines.
    Returns a list of matching results.
    """
    results = []
    matched_bill_indices = set()
    
    # 1. Resolve all prescribed medicines
    presc_resolved = []
    for idx, pm in enumerate(prescribed_medicines):
        resolution = resolve_medicine(db, pm.medicine_name)
        presc_resolved.append((idx, pm, resolution))
        
    # 2. Resolve all billed medicines
    bill_resolved = []
    for idx, bm in enumerate(billed_medicines):
        resolution = resolve_medicine(db, bm.medicine_name)
        bill_resolved.append((idx, bm, resolution))
        
    # 3. Match loop
    for p_idx, pm, p_res in presc_resolved:
        best_b_match = None
        best_b_score = 0.0
        best_b_idx = -1
        best_b_res = None
        
        # Try matching by resolved drug ID
        if p_res["resolved"]:
            for b_idx, bm, b_res in bill_resolved:
                if b_idx in matched_bill_indices:
                    continue
                if b_res["resolved"] and b_res["drug_id"] == p_res["drug_id"]:
                    # Exact generic match or mapped brand match!
                    best_b_match = bm
                    best_b_score = 100.0 if b_res["match_type"] == p_res["match_type"] else 98.0
                    best_b_idx = b_idx
                    best_b_res = b_res
                    break
                    
        # If no generic ID match, fall back to string fuzzy comparison between original names
        if best_b_idx == -1:
            for b_idx, bm, b_res in bill_resolved:
                if b_idx in matched_bill_indices:
                    continue
                sim = string_similarity(pm.medicine_name, bm.medicine_name)
                if sim > best_b_score and sim >= 0.70:
                    best_b_score = sim * 100.0
                    best_b_match = bm
                    best_b_idx = b_idx
                    best_b_res = b_res
                    
        # If a match was found
        if best_b_idx != -1:
            matched_bill_indices.add(best_b_idx)
            results.append({
                "prescribed_item": pm,
                "billed_item": best_b_match,
                "prescribed_res": p_res,
                "billed_res": best_b_res,
                "match_score": best_b_score,
                "match_status": "Approved" if best_b_score >= 80.0 else "Pending Review",
                "reason": f"Matched via {best_b_res['match_type']} ({p_res['generic_name'] or pm.medicine_name} <-> {best_b_res['generic_name'] or best_b_match.medicine_name})"
            })
        else:
            # Unmatched prescription item
            results.append({
                "prescribed_item": pm,
                "billed_item": None,
                "prescribed_res": p_res,
                "billed_res": None,
                "match_score": 0.0,
                "match_status": "Rejected",
                "reason": "Medicine prescribed but not purchased."
            })
            
    # 4. Handle remaining billed medicines (purchased but not prescribed)
    for b_idx, bm, b_res in bill_resolved:
        if b_idx not in matched_bill_indices:
            # Check if this item is a non-medical reject category in DrugMaster
            is_non_medical = False
            reject_reason = "Medicine purchased but not found in prescription."
            
            if b_res["resolved"] and b_res["drug_id"] >= 100:
                is_non_medical = True
                reject_reason = f"Rejected: Non-medical consumable ({b_res['category']})."
                
            results.append({
                "prescribed_item": None,
                "billed_item": bm,
                "prescribed_res": None,
                "billed_res": b_res,
                "match_score": 0.0,
                "match_status": "Rejected",
                "reason": reject_reason
            })
            
    return results
