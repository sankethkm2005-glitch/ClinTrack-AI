"""Seeds the SQLite database with realistic, clearly labeled synthetic demo data.

Includes:
- Pre-verified Demo Doctor: Dr. Sarah Demo (demo.doctor@clintrace.test)
- Two synthetic demo patients: Alice M. Walker (CLN-DEMO-0001) & Bob J. Reynolds (CLN-DEMO-0002)
- Reconstructed clinical documents, extractions, AI analyses, findings, and lab trends
- Active time-limited consent grants linking the demo doctor to both demo patients
- Audit log trails and notifications
- Idempotent and restricted to non-production environments
"""

import io
from datetime import date, datetime, timedelta, timezone
import fitz
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.user import User, PatientProfile, DoctorProfile
from app.models.document import Document, ExtractedData
from app.models.analysis import AIAnalysis, AIFinding
from app.models.consent import AccessRequest, AccessGrant, FindingReview, Notification, AuditLog
from app.utils.security import hash_password
from app.services.clinical_intelligence import ClinicalIntelligenceEngine

DEMO_DOCTOR_EMAIL = "demo.doctor@clintrace.test"
DEMO_DOCTOR_PASSWORD = "ClinTrace2026!DemoDoc"
DEMO_PATIENT_PASSWORD = "DemoPatient123!"


def create_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    b = doc.tobytes()
    doc.close()
    return b


def seed_demo_data():
    """Idempotently seed synthetic demo patients, pre-verified demo doctor, and consent grants."""
    if settings.APP_ENV == "production":
        print("Production environment detected. Skipping demo data creation.")
        return

    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # ---------------------------------------------------------------------
        # 1. Pre-verified Demo Doctor
        # ---------------------------------------------------------------------
        demo_doc_user = db.query(User).filter(User.email == DEMO_DOCTOR_EMAIL).first()
        if not demo_doc_user:
            demo_doc_user = User(
                email=DEMO_DOCTOR_EMAIL,
                password_hash=hash_password(DEMO_DOCTOR_PASSWORD),
                role="doctor",
                is_active=True,
            )
            db.add(demo_doc_user)
            db.flush()

            demo_doc_profile = DoctorProfile(
                user_id=demo_doc_user.id,
                full_name="Dr. Sarah Demo",
                registration_number="MED-DEMO-001",
                medical_council="National Medical Commission",
                specialization="General Medicine & Clinical Informatics",
                verification_status="verified",
            )
            db.add(demo_doc_profile)
            db.commit()
            print(f"Created pre-verified demo doctor: {DEMO_DOCTOR_EMAIL}")
        else:
            demo_doc_user.is_active = True
            if demo_doc_user.doctor_profile:
                demo_doc_user.doctor_profile.verification_status = "verified"
                demo_doc_user.doctor_profile.full_name = "Dr. Sarah Demo"
            db.commit()

        # ---------------------------------------------------------------------
        # 2. Synthetic Patient 1: Alice M. Walker (CLN-DEMO-0001)
        # ---------------------------------------------------------------------
        p1_user = db.query(User).filter(User.email == "patient.alice@clintrace.demo").first()
        p1_profile = db.query(PatientProfile).filter(PatientProfile.patient_id == "CLN-DEMO-0001").first()

        if not p1_user:
            p1_user = User(
                email="patient.alice@clintrace.demo",
                password_hash=hash_password(DEMO_PATIENT_PASSWORD),
                role="patient",
                is_active=True,
            )
            db.add(p1_user)
            db.flush()

        if not p1_profile:
            p1_profile = PatientProfile(
                user_id=p1_user.id,
                patient_id="CLN-DEMO-0001",
                full_name="Alice M. Walker (Synthetic Demo)",
                date_of_birth=date(1982, 4, 18),
                gender="Female",
            )
            db.add(p1_profile)
            db.commit()

        # Documents & Synthesis for Alice
        if db.query(Document).filter(Document.patient_id == p1_profile.id).count() == 0:
            doc1 = Document(
                patient_id=p1_profile.id,
                filename="Discharge_Prescription_Cardiology.pdf",
                stored_filename="demo_alice_doc1.pdf",
                storage_path="storage/uploads/demo_alice_doc1.pdf",
                document_type="prescription",
                mime_type="application/pdf",
                file_size_bytes=1024 * 18,
                processing_status="processed",
            )
            db.add(doc1)
            db.flush()

            ed1 = ExtractedData(
                document_id=doc1.id,
                raw_text="DISCHARGE PRESCRIPTION: Metformin 500mg BID. Lisinopril 10mg daily oral. Diagnosis: Essential Hypertension, Type 2 Diabetes.",
                page_count=1,
                page_texts=[{"page": 1, "text": "DISCHARGE PRESCRIPTION: Metformin 500mg BID. Lisinopril 10mg daily oral. Diagnosis: Essential Hypertension, Type 2 Diabetes."}],
                structured_data={
                    "document_type": "prescription",
                    "patient_name": "Alice M. Walker",
                    "conditions": [
                        {"name": "Essential Hypertension", "status": "active", "page_number": 1, "evidence_text": "Diagnosis: Essential Hypertension"},
                        {"name": "Type 2 Diabetes Mellitus", "status": "active", "page_number": 1, "evidence_text": "Diagnosis: Type 2 Diabetes"},
                    ],
                    "medications": [
                        {"name": "Metformin", "dosage": "500 mg", "frequency": "Twice daily", "route": "Oral", "status": "active", "page_number": 1, "evidence_text": "Metformin 500mg BID"},
                        {"name": "Lisinopril", "dosage": "10 mg", "frequency": "Daily", "route": "Oral", "status": "active", "page_number": 1, "evidence_text": "Lisinopril 10mg daily oral"},
                    ],
                    "lab_results": [],
                    "requires_manual_review": False,
                    "ai_provider": "offline",
                    "model": "clinical_rule_engine",
                },
                extraction_method="pdf_text",
            )
            db.add(ed1)

            doc2 = Document(
                patient_id=p1_profile.id,
                filename="Followup_Clinic_Note.pdf",
                stored_filename="demo_alice_doc2.pdf",
                storage_path="storage/uploads/demo_alice_doc2.pdf",
                document_type="discharge_summary",
                mime_type="application/pdf",
                file_size_bytes=1024 * 22,
                processing_status="processed",
            )
            db.add(doc2)
            db.flush()

            ed2 = ExtractedData(
                document_id=doc2.id,
                raw_text="CLINICAL FOLLOW-UP NOTE: Metformin 1000mg BID oral. Notes: Increased dosage due to elevated glycemic trend.",
                page_count=1,
                page_texts=[{"page": 1, "text": "CLINICAL FOLLOW-UP NOTE: Metformin 1000mg BID oral. Notes: Increased dosage due to elevated glycemic trend."}],
                structured_data={
                    "document_type": "discharge_summary",
                    "patient_name": "Alice M. Walker",
                    "conditions": [
                        {"name": "Type 2 Diabetes Mellitus", "status": "active", "page_number": 1, "evidence_text": "Type 2 Diabetes"},
                    ],
                    "medications": [
                        {"name": "Metformin", "dosage": "1000 mg", "frequency": "Twice daily", "route": "Oral", "status": "active", "page_number": 1, "evidence_text": "Metformin 1000mg BID oral"},
                    ],
                    "lab_results": [],
                    "requires_manual_review": False,
                    "ai_provider": "offline",
                    "model": "clinical_rule_engine",
                },
                extraction_method="pdf_text",
            )
            db.add(ed2)

            doc3 = Document(
                patient_id=p1_profile.id,
                filename="Comprehensive_Metabolic_Panel.pdf",
                stored_filename="demo_alice_doc3.pdf",
                storage_path="storage/uploads/demo_alice_doc3.pdf",
                document_type="lab_report",
                mime_type="application/pdf",
                file_size_bytes=1024 * 31,
                processing_status="processed",
            )
            db.add(doc3)
            db.flush()

            ed3 = ExtractedData(
                document_id=doc3.id,
                raw_text="LABORATORY REPORT: HbA1c: 7.8% (H) (Reference 4.0-5.6). Fasting Plasma Glucose: 148 mg/dL (Reference 70-99). Serum Creatinine: 0.9 mg/dL.",
                page_count=1,
                page_texts=[{"page": 1, "text": "LABORATORY REPORT: HbA1c: 7.8% (H) (Reference 4.0-5.6). Fasting Plasma Glucose: 148 mg/dL (Reference 70-99). Serum Creatinine: 0.9 mg/dL."}],
                structured_data={
                    "document_type": "lab_report",
                    "patient_name": "Alice M. Walker",
                    "conditions": [],
                    "medications": [],
                    "lab_results": [
                        {"test_name": "HbA1c", "value": "7.8", "unit": "%", "reference_range": "4.0 - 5.6", "is_abnormal": True, "page_number": 1, "evidence_text": "HbA1c: 7.8% (H)"},
                        {"test_name": "Fasting Plasma Glucose", "value": "148", "unit": "mg/dL", "reference_range": "70 - 99", "is_abnormal": True, "page_number": 1, "evidence_text": "Fasting Plasma Glucose: 148 mg/dL"},
                        {"test_name": "Serum Creatinine", "value": "0.9", "unit": "mg/dL", "reference_range": "0.6 - 1.2", "is_abnormal": False, "page_number": 1, "evidence_text": "Serum Creatinine: 0.9 mg/dL"},
                    ],
                    "requires_manual_review": False,
                    "ai_provider": "offline",
                    "model": "clinical_rule_engine",
                },
                extraction_method="pdf_text",
            )
            db.add(ed3)
            db.commit()

            analysis_res = ClinicalIntelligenceEngine.analyze_patient_records(
                documents=[doc1, doc2, doc3],
                extracted_data_list=[ed1, ed2, ed3],
            )
            analysis = AIAnalysis(
                patient_id=p1_profile.id,
                version_number=1,
                status="current",
                summary=analysis_res["summary"],
                completeness_score=analysis_res["completeness_score"],
                completeness_breakdown=analysis_res["completeness_breakdown"],
                timeline=analysis_res["timeline"],
                ai_provider="offline",
                ai_model="clinical_rule_engine",
                document_ids_snapshot=[doc1.id, doc2.id, doc3.id],
            )
            db.add(analysis)
            db.flush()

            for f in analysis_res["findings"]:
                finding = AIFinding(
                    analysis_id=analysis.id,
                    finding_type=f["finding_type"],
                    priority=f["priority"],
                    title=f["title"],
                    description=f["description"],
                    evidence=f.get("evidence"),
                    review_status="pending",
                )
                db.add(finding)
            db.commit()

        # ---------------------------------------------------------------------
        # 3. Synthetic Patient 2: Bob J. Reynolds (CLN-DEMO-0002)
        # ---------------------------------------------------------------------
        p2_user = db.query(User).filter(User.email == "patient.bob@clintrace.demo").first()
        p2_profile = db.query(PatientProfile).filter(PatientProfile.patient_id == "CLN-DEMO-0002").first()

        if not p2_user:
            p2_user = User(
                email="patient.bob@clintrace.demo",
                password_hash=hash_password(DEMO_PATIENT_PASSWORD),
                role="patient",
                is_active=True,
            )
            db.add(p2_user)
            db.flush()

        if not p2_profile:
            p2_profile = PatientProfile(
                user_id=p2_user.id,
                patient_id="CLN-DEMO-0002",
                full_name="Bob J. Reynolds (Synthetic Demo)",
                date_of_birth=date(1975, 9, 30),
                gender="Male",
            )
            db.add(p2_profile)
            db.commit()

        # Documents & Synthesis for Bob
        if db.query(Document).filter(Document.patient_id == p2_profile.id).count() == 0:
            b_doc1 = Document(
                patient_id=p2_profile.id,
                filename="Cardiology_Consultation_Note.pdf",
                stored_filename="demo_bob_doc1.pdf",
                storage_path="storage/uploads/demo_bob_doc1.pdf",
                document_type="medical_history",
                mime_type="application/pdf",
                file_size_bytes=1024 * 24,
                processing_status="processed",
            )
            db.add(b_doc1)
            db.flush()

            b_ed1 = ExtractedData(
                document_id=b_doc1.id,
                raw_text="CARDIOLOGY CONSULTATION: Patient presents for dyslipidemia and primary cardiovascular prevention. Medications: Atorvastatin 20mg daily oral. Amlodipine 5mg daily. Assessment: Hypercholesterolemia, Stage 1 Hypertension.",
                page_count=1,
                page_texts=[{"page": 1, "text": "CARDIOLOGY CONSULTATION: Patient presents for dyslipidemia and primary cardiovascular prevention. Medications: Atorvastatin 20mg daily oral. Amlodipine 5mg daily. Assessment: Hypercholesterolemia, Stage 1 Hypertension."}],
                structured_data={
                    "document_type": "medical_history",
                    "patient_name": "Bob J. Reynolds",
                    "conditions": [
                        {"name": "Hypercholesterolemia", "status": "active", "page_number": 1, "evidence_text": "Assessment: Hypercholesterolemia"},
                        {"name": "Stage 1 Hypertension", "status": "active", "page_number": 1, "evidence_text": "Stage 1 Hypertension"},
                    ],
                    "medications": [
                        {"name": "Atorvastatin", "dosage": "20 mg", "frequency": "Daily", "route": "Oral", "status": "active", "page_number": 1, "evidence_text": "Atorvastatin 20mg daily oral"},
                        {"name": "Amlodipine", "dosage": "5 mg", "frequency": "Daily", "route": "Oral", "status": "active", "page_number": 1, "evidence_text": "Amlodipine 5mg daily"},
                    ],
                    "lab_results": [],
                    "requires_manual_review": False,
                    "ai_provider": "offline",
                    "model": "clinical_rule_engine",
                },
                extraction_method="pdf_text",
            )
            db.add(b_ed1)

            b_doc2 = Document(
                patient_id=p2_profile.id,
                filename="Lipid_Panel_Laboratory.pdf",
                stored_filename="demo_bob_doc2.pdf",
                storage_path="storage/uploads/demo_bob_doc2.pdf",
                document_type="lab_report",
                mime_type="application/pdf",
                file_size_bytes=1024 * 28,
                processing_status="processed",
            )
            db.add(b_doc2)
            db.flush()

            b_ed2 = ExtractedData(
                document_id=b_doc2.id,
                raw_text="LIPID PANEL: Total Cholesterol: 242 mg/dL (H) (Reference < 200). LDL Cholesterol: 165 mg/dL (H) (Reference < 100). HDL Cholesterol: 42 mg/dL. Triglycerides: 175 mg/dL (H).",
                page_count=1,
                page_texts=[{"page": 1, "text": "LIPID PANEL: Total Cholesterol: 242 mg/dL (H) (Reference < 200). LDL Cholesterol: 165 mg/dL (H) (Reference < 100). HDL Cholesterol: 42 mg/dL. Triglycerides: 175 mg/dL (H)."}],
                structured_data={
                    "document_type": "lab_report",
                    "patient_name": "Bob J. Reynolds",
                    "conditions": [],
                    "medications": [],
                    "lab_results": [
                        {"test_name": "Total Cholesterol", "value": "242", "unit": "mg/dL", "reference_range": "< 200", "is_abnormal": True, "page_number": 1, "evidence_text": "Total Cholesterol: 242 mg/dL (H)"},
                        {"test_name": "LDL Cholesterol", "value": "165", "unit": "mg/dL", "reference_range": "< 100", "is_abnormal": True, "page_number": 1, "evidence_text": "LDL Cholesterol: 165 mg/dL (H)"},
                        {"test_name": "HDL Cholesterol", "value": "42", "unit": "mg/dL", "reference_range": "> 40", "is_abnormal": False, "page_number": 1, "evidence_text": "HDL Cholesterol: 42 mg/dL"},
                        {"test_name": "Triglycerides", "value": "175", "unit": "mg/dL", "reference_range": "< 150", "is_abnormal": True, "page_number": 1, "evidence_text": "Triglycerides: 175 mg/dL (H)"},
                    ],
                    "requires_manual_review": False,
                    "ai_provider": "offline",
                    "model": "clinical_rule_engine",
                },
                extraction_method="pdf_text",
            )
            db.add(b_ed2)
            db.commit()

            b_analysis_res = ClinicalIntelligenceEngine.analyze_patient_records(
                documents=[b_doc1, b_doc2],
                extracted_data_list=[b_ed1, b_ed2],
            )
            b_analysis = AIAnalysis(
                patient_id=p2_profile.id,
                version_number=1,
                status="current",
                summary=b_analysis_res["summary"],
                completeness_score=b_analysis_res["completeness_score"],
                completeness_breakdown=b_analysis_res["completeness_breakdown"],
                timeline=b_analysis_res["timeline"],
                ai_provider="offline",
                ai_model="clinical_rule_engine",
                document_ids_snapshot=[b_doc1.id, b_doc2.id],
            )
            db.add(b_analysis)
            db.flush()

            for f in b_analysis_res["findings"]:
                finding = AIFinding(
                    analysis_id=b_analysis.id,
                    finding_type=f["finding_type"],
                    priority=f["priority"],
                    title=f["title"],
                    description=f["description"],
                    evidence=f.get("evidence"),
                    review_status="pending",
                )
                db.add(finding)
            db.commit()

        # ---------------------------------------------------------------------
        # 4. Consent Grants for Demo Doctor (Alice & Bob)
        # ---------------------------------------------------------------------
        # Alice -> Dr. Sarah Demo (Active Grant)
        grant_alice = (
            db.query(AccessGrant)
            .filter(
                AccessGrant.doctor_id == demo_doc_user.id,
                AccessGrant.patient_id == p1_profile.id,
                AccessGrant.expires_at > now,
                AccessGrant.revoked_at == None,
            )
            .first()
        )
        if not grant_alice:
            grant_alice = AccessGrant(
                doctor_id=demo_doc_user.id,
                patient_id=p1_profile.id,
                scope="full_records",
                is_emergency=False,
                expires_at=now + timedelta(days=14),
            )
            db.add(grant_alice)

            db.add(
                AuditLog(
                    user_id=demo_doc_user.id,
                    action="access_granted",
                    resource_type="patient_record",
                    resource_id=str(p1_profile.id),
                    details={"doctor_name": "Dr. Sarah Demo", "patient_id_str": p1_profile.patient_id, "duration_hours": 336},
                )
            )
            db.add(
                Notification(
                    user_id=p1_user.id,
                    title="Access Granted to Dr. Sarah Demo",
                    message="Dr. Sarah Demo was granted consented clinical review access to your records.",
                    notification_type="consent",
                    is_read=True,
                )
            )

        # Bob -> Dr. Sarah Demo (Active Grant)
        grant_bob = (
            db.query(AccessGrant)
            .filter(
                AccessGrant.doctor_id == demo_doc_user.id,
                AccessGrant.patient_id == p2_profile.id,
                AccessGrant.expires_at > now,
                AccessGrant.revoked_at == None,
            )
            .first()
        )
        if not grant_bob:
            grant_bob = AccessGrant(
                doctor_id=demo_doc_user.id,
                patient_id=p2_profile.id,
                scope="full_records",
                is_emergency=False,
                expires_at=now + timedelta(days=14),
            )
            db.add(grant_bob)

            db.add(
                AuditLog(
                    user_id=demo_doc_user.id,
                    action="access_granted",
                    resource_type="patient_record",
                    resource_id=str(p2_profile.id),
                    details={"doctor_name": "Dr. Sarah Demo", "patient_id_str": p2_profile.patient_id, "duration_hours": 336},
                )
            )
            db.add(
                Notification(
                    user_id=p2_user.id,
                    title="Access Granted to Dr. Sarah Demo",
                    message="Dr. Sarah Demo was granted consented clinical review access to your records.",
                    notification_type="consent",
                    is_read=True,
                )
            )

        db.commit()
        print("Demo doctor and synthetic patient consent data seeded successfully!")

    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_data()
