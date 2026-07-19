"""
Vision-based extraction using Gemini multimodal model.
"""
import os
import re
import json
import google.generativeai as genai
from PIL import Image

PDF_RENDER_SCALE = 3.0  # ~216 DPI

def is_available() -> bool:
    """Return True if the Gemini API Key is configured."""
    return bool(os.environ.get("GEMINI_API_KEY"))

def _file_to_pil_images(file_path: str) -> list:
    from PIL import Image
    lower = file_path.lower()
    images = []
    if lower.endswith(".pdf"):
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(file_path)
            for i in range(len(pdf)):
                page = pdf[i]
                bitmap = page.render(scale=PDF_RENDER_SCALE)
                pil_img = bitmap.to_pil()
                images.append(pil_img)
        except Exception as e:
            print(f"[Gemini] PDF render failed: {e}")
    else:
        try:
            img = Image.open(file_path)
            img.load()
            images.append(img)
        except Exception as e:
            print(f"[Gemini] Image open failed: {e}")
    return images

def _coerce_float(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"\d+(?:,\d{3})*(?:\.\d+)?", v.replace(" ", ""))
        if m:
            try:
                return float(m.group(0).replace(",", ""))
            except ValueError:
                return 0.0
    return 0.0

def _coerce_int(v) -> int:
    if isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        m = re.search(r"\d+", v)
        if m:
            return int(m.group(0))
    return 0

def _normalize_gemini_response(parsed: dict) -> dict:
    meta_in = parsed.get("metadata", {}) or {}
    metadata = {
        "doctor_name": str(meta_in.get("doctor_name", "") or "").strip(),
        "hospital_name": str(meta_in.get("hospital_name", "") or "").strip(),
        "patient_name": str(meta_in.get("patient_name", "") or "").strip(),
        "date": str(meta_in.get("date", "") or "").strip(),
        "invoice_number": str(meta_in.get("invoice_number", "") or "").strip(),
        "total_amount": _coerce_float(meta_in.get("total_amount", 0.0)),
    }
    
    medicines = []
    for m in parsed.get("medicines", []) or []:
        if not isinstance(m, dict):
            continue
        name = str(m.get("medicine_name", "") or "").strip()
        if len(name) < 2:
            continue
        
        dosage = str(m.get("dosage", "") or m.get("frequency", "") or "").strip()
        
        medicines.append({
            "medicine_name": name,
            "strength": str(m.get("strength", "") or "").strip(),
            "dosage": dosage,
            "frequency": str(m.get("frequency", "") or dosage).strip(),
            "duration_days": _coerce_int(m.get("duration_days", 0)),
            "quantity": _coerce_int(m.get("quantity", 0)),
            "unit_price": _coerce_float(m.get("unit_price", 0.0)),
            "total_price": _coerce_float(m.get("total_price", 0.0)),
        })
    return {"metadata": metadata, "medicines": medicines}

def extract_with_gemma(file_path: str, doc_type: str):
    """
    Run Gemini vision extraction. Returns a dict compatible with
    process_and_extract_document, or None if the model is unavailable or
    produced nothing usable.
    """
    if not is_available():
        print("[Gemini] API Key not set.")
        return None

    try:
        # Load images
        pil_images = _file_to_pil_images(file_path)
        if not pil_images:
            print("[Gemini] No images to process.")
            return None

        # System prompt and rules
        prompt = (
            "You are an expert medical document parser for IOCL claims. Extract information from the text/image and return strictly valid JSON.\n"
            "RULES:\n"
            "1. Extract metadata: doctor_name, hospital_name, patient_name, date (YYYY-MM-DD), invoice_number, total_amount.\n"
            "2. Extract medicines: medicine_name, strength, dosage, duration_days, quantity, unit_price, total_price.\n"
            "3. CALCULATIONS (Prescriptions): Calculate `quantity`. Example: '1-1-1 x 5 days' = 15. '1-0-0 x 5 days' = 5. Sprays/Ointments default to 1.\n"
            "4. CALCULATIONS (Bills): Ensure `unit_price` * `quantity` = `total_price`.\n"
            "5. Output ONLY JSON. Do not include markdown formatting (like ```json).\n\n"
            "SCHEMA TO MATCH:\n"
            '{"metadata": {"doctor_name": "", "hospital_name": "", "patient_name": "", "date": "", "invoice_number": "", "total_amount": 0.0}, '
            '"medicines": [{"medicine_name": "", "strength": "", "dosage": "", "frequency": "", "duration_days": 0, "quantity": 0, "unit_price": 0.0, "total_price": 0.0}]}'
        )

        # Configure SDK
        api_key = os.environ.get("GEMINI_API_KEY")
        genai.configure(api_key=api_key)
        
        # Instantiate model
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        # Build contents
        contents = [prompt] + pil_images
        
        # Call API
        response = model.generate_content(contents)
        text_response = response.text
        
        # Strip out any hallucinated markdown blocks
        cleaned_text = re.sub(r'```(?:json)?', '', text_response).strip()
        
        parsed_dict = json.loads(cleaned_text)
        normalized_data = _normalize_gemini_response(parsed_dict)
        
        # Status determination
        status = "Success" if normalized_data["medicines"] else "Warning"
        
        # Confidence score mapping
        overall = 90.0
        confidence_dict = {
            "overall_confidence": overall,
            "fields": {m["medicine_name"]: overall for m in normalized_data["medicines"]}
        }
        
        return {
            "status": status,
            "raw_text": "Extracted via LLM",
            "confidence_metrics": json.dumps(confidence_dict),
            "parsed_data": normalized_data
        }
        
    except Exception as e:
        print(f"[Gemini] Extraction failed: {e}")
        return None
