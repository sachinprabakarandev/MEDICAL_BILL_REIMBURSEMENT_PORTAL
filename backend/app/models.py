import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    role = Column(String, default="employee")  # employee, reviewer, admin
    department = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    claims = relationship("Claim", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")

class Claim(Base):
    __tablename__ = "claims"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date_submitted = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String, default="Pending")  # Pending, Approved, Rejected, Action Required
    total_claimed_amount = Column(Float, default=0.0)
    approved_amount = Column(Float, default=0.0)
    rejected_amount = Column(Float, default=0.0)
    reason = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    
    user = relationship("User", back_populates="claims")
    uploaded_files = relationship("UploadedFile", back_populates="claim", cascade="all, delete-orphan")
    prescription_medicines = relationship("PrescriptionMedicine", back_populates="claim", cascade="all, delete-orphan")
    bill_medicines = relationship("BillMedicine", back_populates="claim", cascade="all, delete-orphan")
    validation_results = relationship("ValidationResult", back_populates="claim", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="claim", cascade="all, delete-orphan")
    reviewer_comments = relationship("ReviewerComment", back_populates="claim", cascade="all, delete-orphan")

class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # prescription, bill, other
    content_type = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    claim = relationship("Claim", back_populates="uploaded_files")
    ocr_results = relationship("OCRResult", back_populates="file", cascade="all, delete-orphan")

class OCRResult(Base):
    __tablename__ = "ocr_results"
    
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False)
    file_id = Column(Integer, ForeignKey("uploaded_files.id"), nullable=False)
    page_number = Column(Integer, default=1)
    raw_text = Column(Text, nullable=True)
    confidence_metrics = Column(Text, nullable=True)  # JSON string of confidence details
    status = Column(String, default="Success")  # Success, Fail
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    file = relationship("UploadedFile", back_populates="ocr_results")

class PrescriptionMedicine(Base):
    __tablename__ = "prescription_medicines"
    
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False)
    medicine_name = Column(String, nullable=False)
    normalized_name = Column(String, nullable=True)
    dosage = Column(String, nullable=True)  # e.g., 1-0-1, TDS, BD
    strength = Column(String, nullable=True)  # e.g., 650 mg, 40 mg
    frequency = Column(String, nullable=True)
    duration_days = Column(Integer, nullable=True)
    quantity = Column(Integer, nullable=True)
    confidence_score = Column(Float, default=100.0)
    
    claim = relationship("Claim", back_populates="prescription_medicines")

class BillMedicine(Base):
    __tablename__ = "bill_medicines"
    
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False)
    medicine_name = Column(String, nullable=False)
    brand_name = Column(String, nullable=True)
    normalized_name = Column(String, nullable=True)
    strength = Column(String, nullable=True)
    quantity = Column(Integer, nullable=True)
    unit_price = Column(Float, default=0.0)
    total_price = Column(Float, default=0.0)
    confidence_score = Column(Float, default=100.0)
    
    claim = relationship("Claim", back_populates="bill_medicines")

class DrugMaster(Base):
    __tablename__ = "drug_master"
    
    id = Column(Integer, primary_key=True, index=True)
    generic_name = Column(String, unique=True, index=True, nullable=False)
    drug_category = Column(String, nullable=True)  # e.g., Analgesic, Antibiotic, Cosmetic, OTC
    notes = Column(Text, nullable=True)

class DrugSynonyms(Base):
    __tablename__ = "drug_synonyms"
    
    id = Column(Integer, primary_key=True, index=True)
    drug_id = Column(Integer, ForeignKey("drug_master.id"), nullable=False)
    synonym_name = Column(String, unique=True, index=True, nullable=False)

class DrugBrandMapping(Base):
    __tablename__ = "drug_brand_mapping"
    
    id = Column(Integer, primary_key=True, index=True)
    drug_id = Column(Integer, ForeignKey("drug_master.id"), nullable=False)
    brand_name = Column(String, index=True, nullable=False)
    strength_standardized = Column(String, nullable=True)

class ValidationResult(Base):
    __tablename__ = "validation_results"
    
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False)
    prescribed_item_id = Column(Integer, ForeignKey("prescription_medicines.id"), nullable=True)
    billed_item_id = Column(Integer, ForeignKey("bill_medicines.id"), nullable=True)
    prescribed_name = Column(String, nullable=True)
    billed_name = Column(String, nullable=True)
    match_score = Column(Float, default=0.0)
    match_status = Column(String, default="Rejected")  # Approved, Rejected, Pending Review
    match_reason = Column(Text, nullable=True)
    decision_type = Column(String, default="System")  # System, Override
    
    claim = relationship("Claim", back_populates="validation_results")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    action_type = Column(String, nullable=False)  # Login, Submit, AI_Validation, Override, Export
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=True)
    description = Column(Text, nullable=False)
    details = Column(Text, nullable=True)  # JSON string or additional log info
    
    user = relationship("User", back_populates="audit_logs")
    claim = relationship("Claim", back_populates="audit_logs")

class ReviewerComment(Base):
    __tablename__ = "reviewer_comments"
    
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    comment = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    claim = relationship("Claim", back_populates="reviewer_comments")
