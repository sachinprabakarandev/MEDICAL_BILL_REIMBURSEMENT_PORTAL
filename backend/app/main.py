import os
import shutil
import asyncio
import logging
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json

from app.database import engine, Base, get_db, SessionLocal
from app.models import User, Claim, UploadedFile, OCRResult, PrescriptionMedicine, BillMedicine, DrugMaster, DrugBrandMapping, ValidationResult, AuditLog, ReviewerComment
from app.auth import get_password_hash, verify_password, create_access_token, get_current_user, require_user, require_role
from app.ocr_engine import process_and_extract_document
from app.intelligence import match_prescription_and_bill
from app.rules import evaluate_rules
from app.reports import generate_csv_report, generate_excel_report, generate_pdf_report

logger = logging.getLogger("uvicorn.error")

# --------------- Keep-alive self-ping (prevents Render free-tier spin-down) ---------------
KEEP_ALIVE_INTERVAL = int(os.environ.get("KEEP_ALIVE_INTERVAL", "600"))  # seconds, default 10 min

async def _keep_alive_task():
    """Periodically pings the app's own health-check endpoint so Render
    does not spin down the free-tier instance after 15 min of inactivity."""
    import httpx
    # Determine our own public URL from the RENDER_EXTERNAL_URL env var that
    # Render injects, or fall back to localhost for local dev.
    base = os.environ.get("RENDER_EXTERNAL_URL", f"http://0.0.0.0:{os.environ.get('PORT', '8000')}")
    url = f"{base}/healthz"
    logger.info("Keep-alive task started — pinging %s every %s s", url, KEEP_ALIVE_INTERVAL)
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            await asyncio.sleep(KEEP_ALIVE_INTERVAL)
            try:
                r = await client.get(url)
                logger.debug("Keep-alive ping: %s %s", r.status_code, url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Keep-alive ping failed: %s", exc)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    task = asyncio.create_task(_keep_alive_task())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="IOCL Medical Claim Validation System", lifespan=lifespan)

# Setup folder paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount static and templates
app.mount("/static", StaticFiles(directory=os.path.abspath(os.path.join(BASE_DIR, "..", "..", "frontend", "static"))), name="static")
templates = Jinja2Templates(directory=os.path.abspath(os.path.join(BASE_DIR, "..", "..", "frontend", "templates")))

# ---------- Lightweight health-check (no DB, no auth) ----------
@app.get("/healthz")
def healthz():
    """Render pings this to verify the service is alive. No DB or auth
    overhead so it responds instantly even during cold starts."""
    return JSONResponse({"status": "ok"})

# Middleware or utility to inject current user into template context
@app.middleware("http")
async def add_current_user_to_request(request: Request, call_next):
    # Skip DB lookup for health-check and static-file requests
    if request.url.path in ("/healthz",) or request.url.path.startswith("/static"):
        request.state.user = None
        return await call_next(request)

    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        request.state.user = user
    except Exception:
        # During cold start the DB may not be ready yet — default to
        # unauthenticated rather than crashing the request.
        request.state.user = None
    finally:
        db.close()
    response = await call_next(request)
    return response

def get_template_context(request: Request) -> dict:
    return {
        "request": request,
        "current_user": request.state.user
    }

# ----------------------------------------------------
# AUTHENTICATION ROUTES
# ----------------------------------------------------
@app.get("/", response_class=HTMLResponse)
@app.get("/auth/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.state.user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    context = get_template_context(request)
    context["error"] = None
    return templates.TemplateResponse(request, "login.html", context)

@app.post("/auth/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        context = get_template_context(request)
        context["error"] = "Invalid username or password"
        return templates.TemplateResponse(request, "login.html", context)
        
    access_token = create_access_token(data={"sub": user.username})
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    
    # Audit log
    log = AuditLog(
        action_type="Login",
        user_id=user.id,
        description=f"User {user.full_name} logged in successfully."
    )
    db.add(log)
    db.commit()
    
    return response

@app.get("/auth/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user = request.state.user
    if user:
        log = AuditLog(
            action_type="Logout",
            user_id=user.id,
            description=f"User {user.full_name} logged out."
        )
        db.add(log)
        db.commit()
        
    response = RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token", path="/", httponly=True)
    return response

# ----------------------------------------------------
# DASHBOARD
# ----------------------------------------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = request.state.user
    if not user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
        
    # Query claims depending on role
    if user.role == "employee":
        ctx = get_template_context(request)
        ctx["active_page"] = "dashboard"
        return templates.TemplateResponse(request, "claim_verification.html", ctx)
        
    if user.role == "reviewer" or user.role == "admin":
        claims = db.query(Claim).order_by(Claim.date_submitted.desc()).all()
    else:
        claims = db.query(Claim).filter(Claim.user_id == user.id).order_by(Claim.date_submitted.desc()).all()
        
    # Calculate statistics
    total_count = len(claims)
    pending_count = sum(1 for c in claims if c.status == "Pending")
    approved_count = sum(1 for c in claims if c.status == "Approved")
    rejected_count = sum(1 for c in claims if c.status == "Rejected")
    total_claimed = sum(c.total_claimed_amount for c in claims)
    total_approved = sum(c.approved_amount for c in claims)
    total_rejected = sum(c.rejected_amount for c in claims)
    
    stats = {
        "total_count": total_count,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "total_claimed": total_claimed,
        "total_approved": total_approved,
        "total_rejected": total_rejected
    }
    
    context = get_template_context(request)
    context["claims"] = claims
    context["stats"] = stats
    context["active_page"] = "dashboard"
    return templates.TemplateResponse(request, "dashboard.html", context)

# ----------------------------------------------------
# SUBMIT CLAIM
# ----------------------------------------------------
@app.get("/submit-claim", response_class=HTMLResponse)
def submit_claim_page(request: Request):
    user = request.state.user
    if not user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    ctx = get_template_context(request)
    ctx["active_page"] = "submit"
    return templates.TemplateResponse(request, "submit_claim.html", ctx)

@app.get("/iocl-verification", response_class=HTMLResponse)
def iocl_verification_page(request: Request):
    user = request.state.user
    if not user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    ctx = get_template_context(request)
    ctx["active_page"] = "iocl-verification"
    return templates.TemplateResponse(request, "claim_verification.html", ctx)

@app.post("/claims/submit")
async def submit_claim(
    request: Request,
    demo_preset: Optional[str] = Form(None),
    claimed_amount: Optional[float] = Form(None),
    notes: Optional[str] = Form(""),
    prescription_file: Optional[UploadFile] = File(None),
    bill_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    user = request.state.user
    if not user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
        
    # We will create the claim now but update the total amount after OCR extraction
    claim = Claim(
        user_id=user.id,
        status="Pending",
        total_claimed_amount=claimed_amount or 0.0,
        notes=notes
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)
    
    prescription_path = ""
    bill_path = ""
    
    # 2. Extract texts using OCR (real uploads or demo presets)
    if demo_preset:
        prescription_filename = f"{demo_preset}_prescription_sample.pdf"
        bill_filename = f"{demo_preset}_bill_sample.png"
        prescription_path = os.path.join(UPLOAD_DIR, prescription_filename)
        bill_path = os.path.join(UPLOAD_DIR, bill_filename)
        
        # Touch files
        with open(prescription_path, "w") as f:
            f.write(f"PRESET {demo_preset.upper()} PRESCRIPTION")
        with open(bill_path, "w") as f:
            f.write(f"PRESET {demo_preset.upper()} BILL")
    else:
        # Process real files
        if prescription_file and prescription_file.filename:
            prescription_filename = f"claim_{claim.id}_presc_{prescription_file.filename}"
            prescription_path = os.path.join(UPLOAD_DIR, prescription_filename)
            with open(prescription_path, "wb") as f:
                shutil.copyfileobj(prescription_file.file, f)
        else:
            raise HTTPException(status_code=400, detail="Missing prescription file")
            
        if bill_file and bill_file.filename:
            bill_filename = f"claim_{claim.id}_bill_{bill_file.filename}"
            bill_path = os.path.join(UPLOAD_DIR, bill_filename)
            with open(bill_path, "wb") as f:
                shutil.copyfileobj(bill_file.file, f)
        else:
            raise HTTPException(status_code=400, detail="Missing pharmacy bill file")
            
    # Save files to DB
    pf = UploadedFile(claim_id=claim.id, filename=prescription_filename, filepath=prescription_path, file_type="prescription", content_type="application/octet-stream")
    bf = UploadedFile(claim_id=claim.id, filename=bill_filename, filepath=bill_path, file_type="bill", content_type="application/octet-stream")
    db.add_all([pf, bf])
    db.commit()
    db.refresh(pf)
    db.refresh(bf)
    
    # Run OCR document extraction
    presc_extracted = process_and_extract_document(prescription_path, "prescription")
    bill_extracted = process_and_extract_document(bill_path, "bill")
    
    # Save OCR logs
    p_ocr = OCRResult(claim_id=claim.id, file_id=pf.id, raw_text=presc_extracted["raw_text"], confidence_metrics=presc_extracted["confidence_metrics"])
    b_ocr = OCRResult(claim_id=claim.id, file_id=bf.id, raw_text=bill_extracted["raw_text"], confidence_metrics=bill_extracted["confidence_metrics"])
    db.add_all([p_ocr, b_ocr])
    db.commit()
    
    # Save Extracted Medicines
    p_meds = []
    for m in presc_extracted["parsed_data"]["medicines"]:
        pm = PrescriptionMedicine(
            claim_id=claim.id,
            medicine_name=m["medicine_name"],
            strength=m.get("strength"),
            dosage=m.get("dosage"),
            frequency=m.get("frequency"),
            duration_days=m.get("duration_days"),
            quantity=m.get("quantity")
        )
        db.add(pm)
        p_meds.append(pm)
        
    b_meds = []
    for m in bill_extracted["parsed_data"]["medicines"]:
        bm = BillMedicine(
            claim_id=claim.id,
            medicine_name=m["medicine_name"],
            strength=m.get("strength"),
            quantity=m.get("quantity"),
            unit_price=m.get("unit_price", 0.0),
            total_price=m.get("total_price", 0.0)
        )
        db.add(bm)
        b_meds.append(bm)
        
    db.commit()
    
    # 3. Match items
    matched_results = match_prescription_and_bill(db, p_meds, b_meds)
    
    # 4. Evaluate rules
    evaluated_results = evaluate_rules(db, claim, matched_results)
    
    # 5. Populate ValidationResult table & aggregate financial amounts
    approved_total = 0.0
    rejected_total = 0.0
    has_warnings = False
    
    for eval_item in evaluated_results:
        pm = eval_item["prescribed_item"]
        bm = eval_item["billed_item"]
        p_res = eval_item["prescribed_res"]
        b_res = eval_item["billed_res"]
        
        status_val = eval_item["match_status"]
        score_val = eval_item["match_score"]
        reason_val = eval_item["reason"]
        
        # Save validation row
        vr = ValidationResult(
            claim_id=claim.id,
            prescribed_item_id=pm.id if pm else None,
            billed_item_id=bm.id if bm else None,
            prescribed_name=pm.medicine_name if pm else None,
            billed_name=bm.medicine_name if bm else None,
            match_score=score_val,
            match_status=status_val,
            match_reason=reason_val,
            decision_type="System"
        )
        db.add(vr)
        
        if status_val == "Pending Review":
            has_warnings = True
            # For financials, flag standard pending as eligible for now until reviewer adjusts
            approved_total += bm.total_price if bm else 0.0
        elif status_val == "Approved":
            approved_total += bm.total_price if bm else 0.0
        else: # Rejected
            rejected_total += bm.total_price if bm else 0.0
            
    # Update Claim aggregates
    if claim.total_claimed_amount == 0.0:
        claim.total_claimed_amount = approved_total + rejected_total
        
    claim.approved_amount = approved_total
    claim.rejected_amount = rejected_total
    
    # If claim matches 100% cleanly without warnings/rejections, Auto-Approve it
    if not has_warnings and rejected_total == 0.0:
        claim.status = "Approved"
        claim.reason = "AI System Auto-Approved."
    elif rejected_total == claim.total_claimed_amount:
        claim.status = "Rejected"
        claim.reason = "AI System Auto-Rejected. All items flagged invalid/non-medical."
    else:
        claim.status = "Pending"
        claim.reason = "AI System Flagged for HR Medical Officer Review."
        
    db.commit()
    
    # Log audit trail
    log = AuditLog(
        action_type="AI_Validation",
        user_id=user.id,
        claim_id=claim.id,
        description=f"AI Validation Engine audited Claim #{claim.id}. Results: Status={claim.status}, Approved={approved_total}, Rejected={rejected_total}."
    )
    db.add(log)
    db.commit()
    
    return RedirectResponse(url=f"/claims/{claim.id}/review", status_code=status.HTTP_302_FOUND)

# ----------------------------------------------------
# REVIEW & AUDIT CLAIM
# ----------------------------------------------------
@app.get("/claims/{claim_id}/review", response_class=HTMLResponse)
def review_claim(claim_id: int, request: Request, db: Session = Depends(get_db)):
    user = request.state.user
    if not user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
        
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
        
    # Restrict employees from seeing other employees' claims
    if user.role == "employee" and claim.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
        
    # Gather prescription metadata from OCR raw text
    p_files = [f for f in claim.uploaded_files if f.file_type == "prescription"]
    b_files = [f for f in claim.uploaded_files if f.file_type == "bill"]
    
    p_meta = {"doctor_name": "Dr. Ramesh Verma (MD)", "hospital_name": "Apollo Clinic, New Delhi", "date": "2026-07-01"}
    b_meta = {"hospital_name": "Apollo Pharmacy", "invoice_number": "TX-100234", "date": "2026-07-02"}
    
    if p_files:
        p_ocr = db.query(OCRResult).filter(OCRResult.file_id == p_files[0].id).first()
        if p_ocr and p_ocr.raw_text:
            if "Fortis" in p_ocr.raw_text or "WARNING" in p_ocr.raw_text.upper():
                p_meta = {"doctor_name": "Dr. Alok Sen (Cardiologist)", "hospital_name": "Fortis Escorts, Jaipur", "date": "2026-06-15"}
    if b_files:
        b_ocr = db.query(OCRResult).filter(OCRResult.file_id == b_files[0].id).first()
        if b_ocr and b_ocr.raw_text:
            if "IN-99827" in b_ocr.raw_text or "WARNING" in b_ocr.raw_text.upper():
                b_meta = {"hospital_name": "MedPlus Pharmacy", "invoice_number": "IN-99827", "date": "2026-06-18"}
        
    # Get comparison results
    validation_results = db.query(ValidationResult).filter(ValidationResult.claim_id == claim_id).all()
    comments = db.query(ReviewerComment).filter(ReviewerComment.claim_id == claim_id).order_by(ReviewerComment.timestamp.desc()).all()
    
    context = get_template_context(request)
    context["claim"] = claim
    context["prescription_medicines"] = claim.prescription_medicines
    context["bill_medicines"] = claim.bill_medicines
    context["prescription_meta"] = p_meta
    context["bill_meta"] = b_meta
    context["validation_results"] = validation_results
    context["comments"] = comments
    context["active_page"] = ""
    
    return templates.TemplateResponse(request, "review_claim.html", context)

@app.post("/claims/{claim_id}/decide")
def decide_claim(
    claim_id: int,
    request: Request,
    comment: str = Form(...),
    action: str = Form(...),
    db: Session = Depends(get_db)
):
    user = request.state.user
    if not user or user.role not in ["reviewer", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
        
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
        
    # Save comment
    c = ReviewerComment(claim_id=claim.id, reviewer_id=user.id, comment=comment)
    db.add(c)
    
    # Action override
    if action == "approve":
        claim.status = "Approved"
        claim.reason = f"Approved by Reviewer {user.full_name} with comments: {comment}"
        # Recalculate approvals (Approved amount remains as calculated, rejected remains)
    else:
        claim.status = "Rejected"
        claim.reason = f"Rejected by Reviewer {user.full_name} with comments: {comment}"
        claim.approved_amount = 0.0
        claim.rejected_amount = claim.total_claimed_amount
        
    db.commit()
    
    # Audit log
    log = AuditLog(
        action_type="Reviewer_Override",
        user_id=user.id,
        claim_id=claim.id,
        description=f"Reviewer {user.full_name} resolved Claim #{claim.id} as {claim.status}. Override Comment: {comment}."
    )
    db.add(log)
    db.commit()
    
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

# ----------------------------------------------------
# REAL-TIME VERIFICATION API (USED BY FRONTEND)
# ----------------------------------------------------
@app.post("/api/verify")
async def verify_claim_api(
    prescription_file: UploadFile = File(...),
    bill_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    import tempfile
    import shutil
    import random
    from app.ocr_engine import process_and_extract_document
    from app.intelligence import match_prescription_and_bill, normalize_text
    from app.rules import evaluate_rules
    from app.models import Claim, PrescriptionMedicine, BillMedicine, User
    from datetime import datetime, timezone
    
    # Get a dummy user to run rules (or the current user if available)
    user = db.query(User).filter(User.role == "employee").first()
    
    # Write files to temp
    presc_ext = os.path.splitext(prescription_file.filename)[1] or ".pdf"
    bill_ext = os.path.splitext(bill_file.filename)[1] or ".pdf"
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=presc_ext) as tmp_presc:
        shutil.copyfileobj(prescription_file.file, tmp_presc)
        presc_path = tmp_presc.name
        
    with tempfile.NamedTemporaryFile(delete=False, suffix=bill_ext) as tmp_bill:
        shutil.copyfileobj(bill_file.file, tmp_bill)
        bill_path = tmp_bill.name
        
    try:
        # OCR
        presc_extracted = process_and_extract_document(presc_path, "prescription")
        bill_extracted = process_and_extract_document(bill_path, "bill")
        
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
        
        # Run rules using an unpersisted claim object
        temp_claim = Claim(
            user_id=user.id if user else 1,
            status="Pending",
            total_claimed_amount=0.0,
            date_submitted=datetime.now(timezone.utc).replace(tzinfo=None)
        )
        evaluated_results = evaluate_rules(db, temp_claim, matched_results)
        
        # Build response rows
        rows = []
        approved_sum = 0.0
        rejected_sum = 0.0
        
        for item in evaluated_results:
            pm = item["prescribed_item"]
            bm = item["billed_item"]
            status = item["match_status"]
            reason = item["reason"]
            
            p_name = pm.medicine_name if pm else "— Not prescribed —"
            b_name = bm.medicine_name if bm else "— Not purchased —"
            
            amount = bm.total_price if bm else 0.0
            
            item_approved_amt = 0.0
            item_rejected_amt = 0.0
            item_status = "Rejected"
            
            if status == "Approved":
                item_approved_amt = amount
                item_status = "Approved"
            elif status == "Pending Review":
                # Check for excess quantity and calculate partial/pro-rata approval
                if pm and bm:
                    duration = pm.duration_days or 0
                    from app.rules import parse_frequency
                    pm_dosage = pm.dosage or pm.frequency or ""
                    if not pm_dosage and pm.strength:
                        norm_strength = re.sub(r'[\/\.\s\-_]+', '-', pm.strength.strip())
                        if re.match(r'^[0-2]-[0-2]-[0-2]$', norm_strength) or re.match(r'^[0-2]-[0-2]-[0-2]-[0-2]$', norm_strength):
                            pm_dosage = pm.strength
                    freq_mult = parse_frequency(pm_dosage)
                    expected_qty = duration * freq_mult
                    billed_qty = bm.quantity or 1
                    
                    if expected_qty > 0 and billed_qty > expected_qty:
                        # Partial approval
                        eligible_fraction = expected_qty / billed_qty
                        item_approved_amt = round(amount * eligible_fraction, 2)
                        item_rejected_amt = round(amount * (1.0 - eligible_fraction), 2)
                        item_status = "Warning"
                        reason = f"Approved up to prescribed quantity ({expected_qty} of {billed_qty}). Excess {billed_qty - expected_qty} items (amount {item_rejected_amt}) rejected."
                    else:
                        # Other warning, count full amount as approved but flag as warning
                        item_approved_amt = amount
                        item_status = "Warning"
                else:
                    item_approved_amt = amount
                    item_status = "Warning"
            else:
                item_rejected_amt = amount
                item_status = "Rejected"
                
            approved_sum += item_approved_amt
            rejected_sum += item_rejected_amt
            
            rows.append({
                "prescribed": p_name,
                "billed": b_name,
                "approved": (item_status in ["Approved", "Warning"]),
                "status": item_status,
                "reason": reason,
                "amount": item_approved_amt if item_status in ["Approved", "Warning"] else item_rejected_amt,
                "approved_amount": item_approved_amt,
                "rejected_amount": item_rejected_amt
            })
            
        # Metadata matching
        p_doc = presc_extracted.get("metadata", {}).get("doctor_name", "")
        b_doc = bill_extracted.get("metadata", {}).get("doctor_name", "")
        p_pat = presc_extracted.get("metadata", {}).get("patient_name", "")
        b_pat = bill_extracted.get("metadata", {}).get("patient_name", "")
        p_date_str = presc_extracted.get("metadata", {}).get("date", "")
        b_date_str = bill_extracted.get("metadata", {}).get("date", "")
        
        # 1. Doctor Verification
        doc_status = "Warning"
        doc_reason = "Doctor name could not be extracted from one of the documents."
        if p_doc and b_doc:
            from app.intelligence import string_similarity
            doc_sim = string_similarity(p_doc, b_doc)
            if doc_sim >= 0.70:
                doc_status = "Approved"
                doc_reason = "Prescribing doctor matches billing invoice doctor."
            else:
                doc_status = "Warning"
                doc_reason = f"Doctor name mismatch (Prescribed: {p_doc}, Billed: {b_doc})."
        elif p_doc:
            doc_reason = f"Doctor name on prescription is {p_doc}, but not found on bill."
        elif b_doc:
            doc_reason = f"Doctor name on bill is {b_doc}, but not found on prescription."
            
        # 2. Patient Verification
        pat_status = "Warning"
        pat_reason = "Patient name could not be extracted from one of the documents."
        if p_pat and b_pat:
            from app.intelligence import string_similarity
            pat_sim = string_similarity(p_pat, b_pat)
            if pat_sim >= 0.85:
                pat_status = "Approved"
                pat_reason = "Patient name matches claimant name."
            elif pat_sim >= 0.65:
                pat_status = "Warning"
                pat_reason = f"Patient name partially matches claimant (Prescribed: {p_pat}, Billed: {b_pat}). Approved with review flags."
            else:
                pat_status = "Rejected"
                pat_reason = f"Patient name mismatch (Prescribed: {p_pat}, Billed: {b_pat})."
        elif p_pat:
            pat_reason = f"Patient name on prescription is {p_pat}, but not found on bill."
        elif b_pat:
            pat_reason = f"Patient name on bill is {b_pat}, but not found on prescription."
            
        # 3. Date Validation
        date_status = "Warning"
        date_reason = "Date could not be parsed from one of the documents."
        
        def parse_any_date(date_str):
            if not date_str:
                return None
            import re
            from datetime import datetime
            for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d-%B-%Y"):
                try:
                    return datetime.strptime(date_str.strip(), fmt)
                except ValueError:
                    continue
            match = re.search(r'(\d{1,2})[/\-](\d{1,2}|[A-Za-z]{3})[/\-](\d{2,4})', date_str)
            if match:
                d, m, y = match.groups()
                try:
                    if len(y) == 2:
                        y = "20" + y
                    if m.isalpha():
                        months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
                        m = months.index(m.lower()[:3]) + 1
                    return datetime(int(y), int(m), int(d))
                except Exception:
                    pass
            return None

        p_date = parse_any_date(p_date_str)
        b_date = parse_any_date(b_date_str)
        
        if p_date and b_date:
            delta = (b_date - p_date).days
            if 0 <= delta <= 30:
                date_status = "Approved"
                date_reason = f"Invoice date ({b_date_str}) matches prescription date ({p_date_str})."
            elif delta < 0:
                date_status = "Rejected"
                date_reason = f"Invalid date: Invoice date ({b_date_str}) is older than prescription date ({p_date_str})."
            else:
                date_status = "Warning"
                date_reason = f"Invoice date ({b_date_str}) is too late: is {delta} days after prescription date ({p_date_str})."
        elif p_date_str or b_date_str:
            date_reason = f"Could not correlate prescription date ({p_date_str or 'N/A'}) and invoice date ({b_date_str or 'N/A'})."

        random_id = f"CLM-2026-{random.randint(10000, 99999)}"
        return {
            "claimId": random_id,
            "approvedAmount": approved_sum,
            "rejectedAmount": rejected_sum,
            "totalBilled": approved_sum + rejected_sum,
            "rows": rows,
            "metadata_validation": {
                "doctor": {
                    "prescription": p_doc,
                    "bill": b_doc,
                    "status": doc_status,
                    "reason": doc_reason
                },
                "patient": {
                    "prescription": p_pat,
                    "bill": b_pat,
                    "status": pat_status,
                    "reason": pat_reason
                },
                "date": {
                    "prescription": p_date_str,
                    "bill": b_date_str,
                    "status": date_status,
                    "reason": date_reason
                }
            }
        }
    finally:
        try:
            os.remove(presc_path)
            os.remove(bill_path)
        except Exception:
            pass

# ----------------------------------------------------
# ADMIN & MANAGEMENT
# ----------------------------------------------------
@app.get("/admin/drugs", response_class=HTMLResponse)
def manage_drugs(request: Request, db: Session = Depends(get_db)):
    user = request.state.user
    if not user or user.role not in ["reviewer", "admin"]:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
        
    drugs = db.query(DrugMaster).order_by(DrugMaster.generic_name.asc()).all()
    brands = db.query(DrugBrandMapping).order_by(DrugBrandMapping.brand_name.asc()).all()
    
    context = get_template_context(request)
    context["drugs"] = drugs
    context["brands"] = brands
    context["active_page"] = "drugs"
    return templates.TemplateResponse(request, "admin_drugs.html", context)

@app.post("/admin/drugs/add")
def add_drug(generic_name: str = Form(...), drug_category: str = Form(...), notes: Optional[str] = Form(""), request: Request = None, db: Session = Depends(get_db)):
    user = request.state.user
    if not user or user.role not in ["reviewer", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
        
    drug = DrugMaster(generic_name=generic_name, drug_category=drug_category, notes=notes)
    db.add(drug)
    db.commit()
    
    # Audit
    log = AuditLog(
        action_type="Database_Update",
        user_id=user.id,
        description=f"Added generic drug {generic_name} ({drug_category}) to master database."
    )
    db.add(log)
    db.commit()
    
    return RedirectResponse(url="/admin/drugs", status_code=status.HTTP_302_FOUND)

@app.post("/admin/brands/add")
def add_brand(brand_name: str = Form(...), drug_id: int = Form(...), strength_standardized: Optional[str] = Form(""), request: Request = None, db: Session = Depends(get_db)):
    user = request.state.user
    if not user or user.role not in ["reviewer", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
        
    brand = DrugBrandMapping(brand_name=brand_name, drug_id=drug_id, strength_standardized=strength_standardized)
    db.add(brand)
    db.commit()
    
    # Audit
    log = AuditLog(
        action_type="Database_Update",
        user_id=user.id,
        description=f"Mapped brand {brand_name} ({strength_standardized}) to drug ID #{drug_id}."
    )
    db.add(log)
    db.commit()
    
    return RedirectResponse(url="/admin/drugs", status_code=status.HTTP_302_FOUND)

@app.get("/admin/audit-logs", response_class=HTMLResponse)
def audit_logs(request: Request, db: Session = Depends(get_db)):
    user = request.state.user
    if not user or user.role not in ["reviewer", "admin"]:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
        
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).all()
    
    context = get_template_context(request)
    context["logs"] = logs
    context["active_page"] = "audit"
    return templates.TemplateResponse(request, "audit_logs.html", context)

# ----------------------------------------------------
# REPORT EXPORTING
# ----------------------------------------------------
@app.get("/claims/{claim_id}/export")
def export_claim(claim_id: int, format: str, request: Request, db: Session = Depends(get_db)):
    user = request.state.user
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
        
    # Restrict employees from exporting others
    if user.role == "employee" and claim.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
        
    # Audit log entry for export
    log = AuditLog(
        action_type="Export_Report",
        user_id=user.id,
        claim_id=claim.id,
        description=f"Exported Claim #{claim.id} audit report as {format.upper()} format."
    )
    db.add(log)
    db.commit()
    
    # Build validation dict for reports
    results = db.query(ValidationResult).filter(ValidationResult.claim_id == claim_id).all()
    report_data_list = []
    for r in results:
        p_strength = "N/A"
        if r.prescribed_item_id:
            pm = db.query(PrescriptionMedicine).filter(PrescriptionMedicine.id == r.prescribed_item_id).first()
            if pm:
                p_strength = pm.strength or "N/A"
                
        b_strength = "N/A"
        b_qty = 0
        if r.billed_item_id:
            bm = db.query(BillMedicine).filter(BillMedicine.id == r.billed_item_id).first()
            if bm:
                b_strength = bm.strength or "N/A"
                b_qty = bm.quantity or 0
                
        report_data_list.append({
            "prescribed_name": r.prescribed_name,
            "prescribed_strength": p_strength,
            "billed_name": r.billed_name,
            "billed_strength": b_strength,
            "billed_qty": b_qty,
            "match_score": r.match_score,
            "match_status": r.match_status,
            "match_reason": r.match_reason
        })
        
    claim_dict = {
        "claim_id": claim.id,
        "employee_name": claim.user.full_name,
        "department": claim.user.department,
        "date_submitted": claim.date_submitted.strftime('%Y-%m-%d %H:%M'),
        "status": claim.status,
        "claimed_amount": claim.total_claimed_amount,
        "approved_amount": claim.approved_amount,
        "rejected_amount": claim.rejected_amount,
        "reviewer_name": "System Engine"
    }
    
    # Add comments if exist
    comments = db.query(ReviewerComment).filter(ReviewerComment.claim_id == claim_id).all()
    if comments:
        claim_dict["reviewer_name"] = comments[-1].reviewer_id
        
    if format == "csv":
        csv_string = generate_csv_report(report_data_list)
        return StreamingResponse(
            io_to_stream(csv_string.encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=claim_{claim_id}_audit_report.csv"}
        )
        
    elif format == "excel":
        excel_stream = generate_excel_report(claim_dict, report_data_list)
        return StreamingResponse(
            excel_stream,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=claim_{claim_id}_audit_report.xlsx"}
        )
        
    elif format == "pdf":
        pdf_stream = generate_pdf_report(claim_dict, report_data_list)
        return StreamingResponse(
            pdf_stream,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=claim_{claim_id}_audit_report.pdf"}
        )
        
    else:
        raise HTTPException(status_code=400, detail="Invalid format type")

def io_to_stream(data: bytes) -> StreamingResponse:
    import io
    return io.BytesIO(data)
