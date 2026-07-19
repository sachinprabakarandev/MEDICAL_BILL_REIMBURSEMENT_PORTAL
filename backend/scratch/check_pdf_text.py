import sys
import os
import pdfplumber

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ocr_engine import parse_extracted_text

# Read PDF
with pdfplumber.open("/Users/sachinswazer/Desktop/IOCL_MEDICAL_BILL_VALIDATION/backend/scratch/Dr.Hariharan_OPD.pdf") as pdf:
    text = ""
    for page in pdf.pages:
        text += page.extract_text() + "\n"

print("=== Raw Text in PDF ===")
print(text)

# Parse
result = parse_extracted_text(text, "prescription")
print("\n=== Parsed Medicines ===")
for med in result["medicines"]:
    print(med)
