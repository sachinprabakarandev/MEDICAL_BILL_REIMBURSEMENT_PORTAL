import sys
import os
import hashlib
from sqlalchemy.orm import Session

# Add current directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine, Base, SessionLocal
from app.models import User, DrugMaster, DrugSynonyms, DrugBrandMapping

def get_password_hash(password: str) -> str:
    # Simple, highly reliable PBKDF2 SHA256 hashing to avoid passlib/bcrypt incompatibility bugs
    salt = "iocl_salt_2026"
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()

def seed_db():
    print("Recreating database tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db: Session = SessionLocal()
    try:
        # Check if users already exist
        if db.query(User).count() == 0:
            print("Seeding users...")
            users = [
                User(
                    username="emp1",
                    hashed_password=get_password_hash("password123"),
                    full_name="Sachin",
                    email="sachin@iocl.in",
                    role="employee",
                    department="Refineries division"
                ),
                User(
                    username="emp2",
                    hashed_password=get_password_hash("password123"),
                    full_name="Amit Sharma",
                    email="amit.sharma@iocl.in",
                    role="employee",
                    department="Marketing division"
                ),
                User(
                    username="reviewer1",
                    hashed_password=get_password_hash("password123"),
                    full_name="Dr. Sunita Patel (CMO)",
                    email="sunita.patel@iocl.in",
                    role="reviewer",
                    department="Medical Claims Team"
                ),
                User(
                    username="admin1",
                    hashed_password=get_password_hash("password123"),
                    full_name="System Admin",
                    email="admin@iocl.in",
                    role="admin",
                    department="IT Support"
                )
            ]
            db.add_all(users)
            db.commit()
            print("Users seeded successfully!")
            
        # Check if drugs already exist
        if db.query(DrugMaster).count() == 0:
            print("Seeding drug database...")
            
            # 1. Define Drug Masters
            drug_masters = [
                # Generics
                DrugMaster(id=1, generic_name="Paracetamol", drug_category="Analgesic/Antipyretic", notes="Common fever and pain reducer. Safe limit 4000mg/day."),
                DrugMaster(id=2, generic_name="Pantoprazole", drug_category="Antacid/PPI", notes="Proton pump inhibitor for acidity. Take empty stomach."),
                DrugMaster(id=3, generic_name="Amoxicillin + Clavulanic Acid", drug_category="Antibiotic", notes="Broad-spectrum penicillin antibiotic with beta-lactamase inhibitor."),
                DrugMaster(id=4, generic_name="Calcium + Vitamin D3", drug_category="Supplements", notes="Calcium and Vitamin D3 combination for bone health."),
                DrugMaster(id=5, generic_name="Atorvastatin", drug_category="Cardiovascular", notes="Cholesterol-lowering statin medication."),
                DrugMaster(id=6, generic_name="Metformin", drug_category="Antidiabetic", notes="First-line medication for type 2 diabetes."),
                DrugMaster(id=7, generic_name="Montelukast + Levocetirizine", drug_category="Antihistamine/Antiasthmatic", notes="For allergic rhinitis and asthma control."),
                DrugMaster(id=8, generic_name="Vitamin C", drug_category="Supplements", notes="Ascorbic acid booster."),
                
                # Case study specific drugs
                DrugMaster(id=9, generic_name="Benzonatate", drug_category="Antitussive", notes="Cough suppressant. Do not chew capsule."),
                DrugMaster(id=10, generic_name="Acebrophylline + Acetylcysteine", drug_category="Mucolytic/Bronchodilator", notes="For productive cough and airway clearance."),
                DrugMaster(id=11, generic_name="Celecoxib", drug_category="NSAID (Analgesic)", notes="For pain and inflammatory relief."),
                DrugMaster(id=12, generic_name="Trypsin Chymotrypsin", drug_category="Analgesic/Anti-inflammatory", notes="Enzyme-based pain and swelling reliever."),
                DrugMaster(id=13, generic_name="Diclofenac Spray", drug_category="Topical Analgesic", notes="For localized musculoskeletal pain relief."),
                
                # Non-medical rejections
                DrugMaster(id=100, generic_name="Soap/Bodywash", drug_category="Non-Reimbursable (Cosmetic)", notes="Personal hygiene consumable. Automatically rejected."),
                DrugMaster(id=101, generic_name="Protein Supplement", drug_category="Non-Reimbursable (Nutritional)", notes="Health drinks, powders. Automatically rejected unless special approval."),
                DrugMaster(id=102, generic_name="Cosmetics/Moisturizer", drug_category="Non-Reimbursable (Cosmetic)", notes="Beauty/skin care cosmetics. Automatically rejected."),
                DrugMaster(id=103, generic_name="Snacks/Food items", drug_category="Non-Reimbursable (Food)", notes="FMCG items. Automatically rejected.")
            ]
            db.add_all(drug_masters)
            db.commit()
            
            # 2. Seed Synonyms
            synonyms = [
                # Paracetamol
                DrugSynonyms(drug_id=1, synonym_name="Acetaminophen"),
                DrugSynonyms(drug_id=1, synonym_name="APAP"),
                # Calcium / Vitamin D3
                DrugSynonyms(drug_id=4, synonym_name="Cholecalciferol + Calcium"),
                DrugSynonyms(drug_id=4, synonym_name="Calcium Carbonate + Vitamin D3"),
                # Amoxicillin combinations
                DrugSynonyms(drug_id=3, synonym_name="Co-amoxiclav"),
                # Montelukast combinations
                DrugSynonyms(drug_id=7, synonym_name="Levocetirizine + Montelukast")
            ]
            db.add_all(synonyms)
            
            # 3. Seed Brand Mappings
            brand_mappings = [
                # Paracetamol brands
                DrugBrandMapping(drug_id=1, brand_name="Dolo", strength_standardized="650 mg"),
                DrugBrandMapping(drug_id=1, brand_name="Dolo 650", strength_standardized="650 mg"),
                DrugBrandMapping(drug_id=1, brand_name="Calpol", strength_standardized="500 mg"),
                DrugBrandMapping(drug_id=1, brand_name="Calpol 650", strength_standardized="650 mg"),
                DrugBrandMapping(drug_id=1, brand_name="Crocin", strength_standardized="500 mg"),
                DrugBrandMapping(drug_id=1, brand_name="Pacimol", strength_standardized="650 mg"),
                
                # Pantoprazole brands
                DrugBrandMapping(drug_id=2, brand_name="Pantocid", strength_standardized="40 mg"),
                DrugBrandMapping(drug_id=2, brand_name="Pantocid 40", strength_standardized="40 mg"),
                DrugBrandMapping(drug_id=2, brand_name="Pan 40", strength_standardized="40 mg"),
                DrugBrandMapping(drug_id=2, brand_name="Pantodac", strength_standardized="40 mg"),
                
                # Amoxicillin + Clavulanic Acid brands
                DrugBrandMapping(drug_id=3, brand_name="Augmentin", strength_standardized="625 mg"),
                DrugBrandMapping(drug_id=3, brand_name="Augmentin 625", strength_standardized="625 mg"),
                DrugBrandMapping(drug_id=3, brand_name="Augmentin 375", strength_standardized="375 mg"),
                DrugBrandMapping(drug_id=3, brand_name="Clavam 625", strength_standardized="625 mg"),
                
                # Calcium + Vitamin D3 brands
                DrugBrandMapping(drug_id=4, brand_name="Shelcal", strength_standardized="500 mg"),
                DrugBrandMapping(drug_id=4, brand_name="Shelcal 500", strength_standardized="500 mg"),
                DrugBrandMapping(drug_id=4, brand_name="Shelcal XT", strength_standardized="500 mg"),
                DrugBrandMapping(drug_id=4, brand_name="Gemcal", strength_standardized="500 mg"),
                
                # Atorvastatin brands
                DrugBrandMapping(drug_id=5, brand_name="Atorva", strength_standardized="10 mg"),
                DrugBrandMapping(drug_id=5, brand_name="Atorva 10", strength_standardized="10 mg"),
                DrugBrandMapping(drug_id=5, brand_name="Lipitor", strength_standardized="10 mg"),
                
                # Metformin brands
                DrugBrandMapping(drug_id=6, brand_name="Glycomet", strength_standardized="500 mg"),
                DrugBrandMapping(drug_id=6, brand_name="Glycomet GP1", strength_standardized="500 mg"),
                DrugBrandMapping(drug_id=6, brand_name="Obimet", strength_standardized="500 mg"),
                
                # Montelukast + Levocetirizine brands
                DrugBrandMapping(drug_id=7, brand_name="Montair LC", strength_standardized="10 mg + 5 mg"),
                DrugBrandMapping(drug_id=7, brand_name="Montair-LC", strength_standardized="10 mg + 5 mg"),
                DrugBrandMapping(drug_id=7, brand_name="Montek LC", strength_standardized="10 mg + 5 mg"),
                
                # Vitamin C brands
                DrugBrandMapping(drug_id=8, brand_name="Limcee", strength_standardized="500 mg"),
                DrugBrandMapping(drug_id=8, brand_name="Celin", strength_standardized="500 mg"),
                
                # Case study specific brands
                DrugBrandMapping(drug_id=9, brand_name="Benz Pearls", strength_standardized="100 mg"),
                DrugBrandMapping(drug_id=9, brand_name="Benz Pearls 100mg Caps 10's", strength_standardized="100 mg"),
                DrugBrandMapping(drug_id=10, brand_name="Pulmoclear", strength_standardized="100 mg + 600 mg"),
                DrugBrandMapping(drug_id=10, brand_name="Pulmoclear Tab 15's", strength_standardized="100 mg + 600 mg"),
                # Celecoxib brands & OCR variants
                DrugBrandMapping(drug_id=11, brand_name="Celebrex", strength_standardized="200 mg"),
                DrugBrandMapping(drug_id=11, brand_name="Celethex", strength_standardized="200 mg"),
                
                # Trypsin Chymotrypsin brands & OCR variants
                DrugBrandMapping(drug_id=12, brand_name="Chymoral Forte", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=12, brand_name="Chymoral", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=12, brand_name="Enzymex Forte", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=12, brand_name="Enzymex", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=12, brand_name="Enymeral Forte", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=12, brand_name="Enymeral", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=12, brand_name="Ehymeral Forte", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=12, brand_name="Ehymeral", strength_standardized="N/A"),
                
                # Diclofenac Spray brands & variants
                DrugBrandMapping(drug_id=13, brand_name="Volitra APS Spray", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=13, brand_name="Volitra APS Topical Solution", strength_standardized="N/A"),
                
                # Non-medical rejects (exact brands mapped for auto-detection)
                DrugBrandMapping(drug_id=100, brand_name="Pears Soap", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=100, brand_name="Dettol Soap", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=100, brand_name="Fiama Body Wash", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=101, brand_name="Horlicks", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=101, brand_name="Protinex", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=101, brand_name="Ensure", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=102, brand_name="Nivea Moisturizer", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=102, brand_name="Himalaya Baby Cream", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=103, brand_name="Snacks", strength_standardized="N/A"),
                DrugBrandMapping(drug_id=103, brand_name="Snickers", strength_standardized="N/A")
            ]
            db.add_all(brand_mappings)
            db.commit()
            print("Drug Database seeded successfully!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding DB: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    seed_db()
