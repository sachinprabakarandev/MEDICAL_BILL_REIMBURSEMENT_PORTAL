import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ocr_engine import run_swift_ocr

text = run_swift_ocr("/Users/sachinswazer/Desktop/IOCL_MEDICAL_BILL_VALIDATION/backend/scratch/Dr.Hariharan_OPD.pdf")
print("=== Swift OCR Output ===")
print(repr(text))
