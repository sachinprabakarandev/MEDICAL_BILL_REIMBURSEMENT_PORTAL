"""
Vision-based extraction using a local Gemma multimodal model served by Ollama.

Apple Vision / plain OCR reads printed text well but fails on handwritten
doctor prescriptions. A vision LLM reads the image directly and returns
structured data, which is far more robust for messy handwriting.

Requirements at runtime:
  - Ollama running locally (default http://localhost:11434)
  - A vision-capable Gemma model pulled, e.g. `ollama pull gemma3:4b`

Configuration via environment variables (all optional):
  - OLLAMA_URL   (default: http://localhost:11434)
  - GEMMA_MODEL  (default: gemma3:4b)
  - GEMMA_TIMEOUT (seconds, default: 180)
"""
import os
import io
import re
import json
import base64
import urllib.request
import urllib.error

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
GEMMA_MODEL = os.environ.get("GEMMA_MODEL", "gemma3:4b")
GEMMA_TIMEOUT = int(os.environ.get("GEMMA_TIMEOUT", "30"))

# Longest-edge cap for pages sent to the model (keeps requests fast/bounded).
MAX_IMAGE_EDGE = 2000
# Render resolution for PDF pages (higher = crisper handwriting, slower).
PDF_RENDER_SCALE = 3.0  # ~216 DPI


def is_available() -> bool:
    """Return True if the Ollama server responds and the model is present."""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = {m.get("name", "") for m in data.get("models", [])}
        # Match with or without an explicit tag (gemma3:4b vs gemma3).
        base = GEMMA_MODEL.split(":")[0]
        return any(n == GEMMA_MODEL or n.split(":")[0] == base for n in names)
    except Exception as e:
        print(f"[Gemma] Ollama not available: {e}")
        return False


def _pil_to_b64_png(img, max_edge: int = MAX_IMAGE_EDGE) -> str:
    from PIL import Image

    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    scale = max_edge / float(max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _file_to_b64_images(file_path: str) -> list:
    """Convert an image or PDF into a list of base64-encoded PNG pages."""
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
                images.append(_pil_to_b64_png(pil_img))
        except Exception as e:
            print(f"[Gemma] PDF render failed: {e}")
    else:
        try:
            img = Image.open(file_path)
            images.append(_pil_to_b64_png(img))
        except Exception as e:
            print(f"[Gemma] Image open failed: {e}")
    return images


def _prompt_for(doc_type: str) -> str:
    if doc_type == "prescription":
        return (
            "You are a careful medical data extractor. The attached image is a "
            "doctor's PRESCRIPTION, often HANDWRITTEN. Read it carefully, including "
            "messy handwriting, and extract the information.\n\n"
            "Return ONLY a JSON object (no markdown, no commentary) with this exact shape:\n"
            "{\n"
            '  "metadata": {\n'
            '    "doctor_name": "", "hospital_name": "", "patient_name": "",\n'
            '    "date": "", "invoice_number": "", "total_amount": 0.0, "gst_amount": 0.0\n'
            "  },\n"
            '  "medicines": [\n'
            '    {"medicine_name": "", "strength": "", "dosage": "", "frequency": "",\n'
            '     "duration_days": 0, "quantity": 0}\n'
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- medicine_name: the drug/brand name only (no dose form words if avoidable).\n"
            "- strength: e.g. '650 mg', '40 mg', '5 ml'. Empty string if unknown.\n"
            "- dosage/frequency: e.g. '1-0-1', '1-1-1', 'BD', 'TDS', 'OD', 'HS', 'SOS'.\n"
            "- duration_days: integer number of days if written (e.g. 'x 5 days' -> 5), else 0.\n"
            "- quantity: total units if derivable, else 0.\n"
            "- Include every medicine you can read. Do not invent items.\n"
            "- Use empty string / 0 for anything not present. Output must be valid JSON."
        )
    return (
        "You are a careful medical data extractor. The attached image is a PHARMACY "
        "BILL / TAX INVOICE. Read it carefully and extract the billed line items.\n\n"
        "Return ONLY a JSON object (no markdown, no commentary) with this exact shape:\n"
        "{\n"
        '  "metadata": {\n'
        '    "doctor_name": "", "hospital_name": "", "patient_name": "",\n'
        '    "date": "", "invoice_number": "", "total_amount": 0.0, "gst_amount": 0.0\n'
        "  },\n"
        '  "medicines": [\n'
        '    {"medicine_name": "", "strength": "", "quantity": 0,\n'
        '     "unit_price": 0.0, "total_price": 0.0}\n'
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- medicine_name: the product name as printed.\n"
        "- strength: e.g. '650 mg', '500 mg'. Empty string if none.\n"
        "- quantity: integer quantity billed.\n"
        "- unit_price / total_price: numbers only (no currency symbols).\n"
        "- total_amount: the final payable/gross amount of the bill.\n"
        "- Include every line item you can read. Do not invent items.\n"
        "- Use empty string / 0 for anything not present. Output must be valid JSON."
    )


def _call_ollama(prompt: str, images_b64: list) -> str:
    payload = {
        "model": GEMMA_MODEL,
        "prompt": prompt,
        "images": images_b64,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0, "num_ctx": 8192},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=GEMMA_TIMEOUT) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body.get("response", "")


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


def _normalize(parsed: dict, doc_type: str) -> dict:
    meta_in = parsed.get("metadata", {}) or {}
    metadata = {
        "doctor_name": str(meta_in.get("doctor_name", "") or ""),
        "hospital_name": str(meta_in.get("hospital_name", "") or ""),
        "patient_name": str(meta_in.get("patient_name", "") or ""),
        "date": str(meta_in.get("date", "") or ""),
        "invoice_number": str(meta_in.get("invoice_number", "") or ""),
        "total_amount": _coerce_float(meta_in.get("total_amount", 0.0)),
        "gst_amount": _coerce_float(meta_in.get("gst_amount", 0.0)),
    }

    medicines = []
    for m in parsed.get("medicines", []) or []:
        if not isinstance(m, dict):
            continue
        name = str(m.get("medicine_name", "") or "").strip()
        if len(name) < 2:
            continue
        if doc_type == "prescription":
            dosage = str(m.get("dosage", "") or m.get("frequency", "") or "").strip()
            medicines.append({
                "medicine_name": name,
                "strength": str(m.get("strength", "") or "").strip(),
                "dosage": dosage,
                "frequency": str(m.get("frequency", "") or dosage).strip(),
                "duration_days": _coerce_int(m.get("duration_days", 0)),
                "quantity": _coerce_int(m.get("quantity", 0)),
            })
        else:
            medicines.append({
                "medicine_name": name,
                "strength": str(m.get("strength", "") or "").strip(),
                "quantity": _coerce_int(m.get("quantity", 0)),
                "unit_price": _coerce_float(m.get("unit_price", 0.0)),
                "total_price": _coerce_float(m.get("total_price", 0.0)),
            })

    return {"metadata": metadata, "medicines": medicines}


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # Fallback: grab the first {...} block.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return {}
    return {}


def extract_with_gemma(file_path: str, doc_type: str):
    """
    Run Gemma vision extraction. Returns a dict compatible with
    process_and_extract_document, or None if the model is unavailable or
    produced nothing usable (so callers can fall back to the legacy OCR).
    """
    if not is_available():
        return None

    images = _file_to_b64_images(file_path)
    if not images:
        print("[Gemma] No images to process.")
        return None

    prompt = _prompt_for(doc_type)

    merged = {"metadata": {}, "medicines": []}
    raw_chunks = []
    for idx, img_b64 in enumerate(images):
        try:
            response = _call_ollama(prompt, [img_b64])
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"[Gemma] Ollama call failed on page {idx + 1}: {e}")
            continue
        raw_chunks.append(response)
        parsed = _extract_json(response)
        if not parsed:
            continue
        norm = _normalize(parsed, doc_type)
        # Keep first non-empty metadata values.
        for k, v in norm["metadata"].items():
            if not merged["metadata"].get(k) and v:
                merged["metadata"][k] = v
        merged["medicines"].extend(norm["medicines"])

    # Ensure metadata has all keys.
    full = _normalize(merged, doc_type)

    if not full["medicines"]:
        print("[Gemma] No medicines extracted.")
        return None

    overall = 90.0
    return {
        "status": "Success",
        "raw_text": "[Gemma vision extraction]\n" + "\n---\n".join(raw_chunks),
        "confidence_metrics": json.dumps({
            "engine": f"gemma-vision:{GEMMA_MODEL}",
            "overall_confidence": overall,
            "fields": {m["medicine_name"]: overall for m in full["medicines"]},
        }),
        "parsed_data": full,
    }
