import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def make_pdf(filename, text_content):
    doc = SimpleDocTemplate(filename, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()
    
    body_style = ParagraphStyle(
        name='NormalWithSpacing',
        parent=styles['Normal'],
        fontSize=10,
        leading=14
    )
    
    lines = text_content.strip().split("\n")
    for line in lines:
        if not line.strip():
            story.append(Spacer(1, 10))
        else:
            story.append(Paragraph(line.replace("\n", "<br/>"), body_style))
            story.append(Spacer(1, 4))
            
    doc.build(story)

presc_text = """
Dr Hariharan M MBBS, MS Ortho, DNB Ortho, FRCS Ed (T&O)
Regn No: TNMC - 100926
Consultant
Department of Orthopedics
MGM HEALTHCARE
25/5/24 MR. MUNNAM PAVAN KUMAR 32/M
c/o (R) Shoulder pain - 2 weeks.
No h/o Trauma / dislocation / instability symptoms.
O/E: Full ROM, Jobes negative, Impingement negative.
MRI: Small anterior paralabral cyst, labral tear (4-6 o clock).
Supraspinatus tendinitis
R.
- Physio: Cuff strengthening exercises / ER/IR isometric exercises
- Rx.
Tab. Celebrex 200mg 1-0-0 x 5 days.
Tab. Enzymex Forte 1-1-1 x 5 days.
Volitra APS Spray.
"""

bill_text = """
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

os.makedirs("/Users/sachinswazer/Desktop/IOCL_MEDICAL_BILL_VALIDATION/backend/scratch", exist_ok=True)
make_pdf("/Users/sachinswazer/Desktop/IOCL_MEDICAL_BILL_VALIDATION/backend/scratch/Dr.Hariharan_OPD.pdf", presc_text)
make_pdf("/Users/sachinswazer/Desktop/IOCL_MEDICAL_BILL_VALIDATION/backend/scratch/MGM_Healthcare_Bill.pdf", bill_text)

print("PDFs generated successfully!")
