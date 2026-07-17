import sys
import os
import unittest
from sqlalchemy.orm import Session

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import engine, Base, SessionLocal
from app.models import User, Claim, PrescriptionMedicine, BillMedicine, DrugMaster, DrugBrandMapping
from app.intelligence import resolve_medicine, match_prescription_and_bill
from app.rules import evaluate_rules
from app.reports import generate_csv_report

class TestMedicalValidationPipeline(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Build test tables
        Base.metadata.create_all(bind=engine)
        cls.db = SessionLocal()
        
    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_01_drug_resolution(self):
        print("\n[TEST] Testing drug brand mapping resolution...")
        
        # Test exact generic match
        res_para = resolve_medicine(self.db, "Paracetamol")
        self.assertTrue(res_para["resolved"])
        self.assertEqual(res_para["generic_name"], "Paracetamol")
        
        # Test brand-to-generic mapping (Dolo 650 -> Paracetamol)
        res_dolo = resolve_medicine(self.db, "Dolo 650")
        self.assertTrue(res_dolo["resolved"])
        self.assertEqual(res_dolo["generic_name"], "Paracetamol")
        self.assertEqual(res_dolo["match_type"], "Brand Mapping")
        
        # Test complex brand-to-generic mapping (Augmentin 625 -> Amoxicillin + Clavulanic Acid)
        res_aug = resolve_medicine(self.db, "Augmentin 625")
        self.assertTrue(res_aug["resolved"])
        self.assertEqual(res_aug["generic_name"], "Amoxicillin + Clavulanic Acid")

    def test_02_rejection_categories(self):
        print("\n[TEST] Testing OTC/Non-medical rejection resolution...")
        
        # Test personal hygiene items (Pears Soap -> Soap/Bodywash)
        res_soap = resolve_medicine(self.db, "Pears Soap")
        self.assertTrue(res_soap["resolved"])
        self.assertEqual(res_soap["generic_name"], "Soap/Bodywash")
        self.assertTrue(res_soap["drug_id"] >= 100)
        
        # Test FMCG/Food items (Horlicks -> Protein Supplement)
        res_horlicks = resolve_medicine(self.db, "Horlicks")
        self.assertTrue(res_horlicks["resolved"])
        self.assertEqual(res_horlicks["generic_name"], "Protein Supplement")
        self.assertTrue(res_horlicks["drug_id"] >= 100)

    def test_03_matching_engine(self):
        print("\n[TEST] Testing drug matching loop...")
        
        # Mock prescription
        pm1 = PrescriptionMedicine(medicine_name="Paracetamol", strength="650 mg", dosage="1-0-1", duration_days=5)
        pm2 = PrescriptionMedicine(medicine_name="Pantoprazole", strength="40 mg", dosage="1-0-0", duration_days=10)
        
        # Mock bill
        bm1 = BillMedicine(medicine_name="Dolo 650", strength="650 mg", quantity=10, total_price=25.0)
        bm2 = BillMedicine(medicine_name="Pantocid", strength="40 mg", quantity=10, total_price=120.0)
        
        matches = match_prescription_and_bill(self.db, [pm1, pm2], [bm1, bm2])
        
        self.assertEqual(len(matches), 2)
        # Check first match (Paracetamol <-> Dolo 650)
        self.assertEqual(matches[0]["prescribed_item"].medicine_name, "Paracetamol")
        self.assertEqual(matches[0]["billed_item"].medicine_name, "Dolo 650")
        self.assertEqual(matches[0]["match_status"], "Approved")

    def test_04_rule_engine_validations(self):
        print("\n[TEST] Testing business and medical rules evaluation...")
        
        # 1. Test quantity warning: expected (1-0-1 for 5 days = 10 tablets), billed = 60 tablets
        pm = PrescriptionMedicine(medicine_name="Paracetamol", strength="650 mg", dosage="1-0-1", duration_days=5)
        bm = BillMedicine(medicine_name="Dolo 650", strength="650 mg", quantity=60, total_price=150.0)
        
        matches = match_prescription_and_bill(self.db, [pm], [bm])
        claim = Claim(user_id=1, status="Pending", total_claimed_amount=150.0)
        
        evaluated = evaluate_rules(self.db, claim, matches)
        self.assertEqual(evaluated[0]["match_status"], "Pending Review")
        self.assertIn("Excess quantity", evaluated[0]["reason"])
        
        # 2. Test strength mismatch warning: prescribed 500 mg, billed 650 mg
        pm_str = PrescriptionMedicine(medicine_name="Paracetamol", strength="500 mg", dosage="1-0-1", duration_days=5)
        bm_str = BillMedicine(medicine_name="Dolo 650", strength="650 mg", quantity=10, total_price=25.0)
        
        matches_str = match_prescription_and_bill(self.db, [pm_str], [bm_str])
        evaluated_str = evaluate_rules(self.db, claim, matches_str)
        self.assertEqual(evaluated_str[0]["match_status"], "Pending Review")
        self.assertIn("Strength mismatch", evaluated_str[0]["reason"])

if __name__ == "__main__":
    unittest.main()
