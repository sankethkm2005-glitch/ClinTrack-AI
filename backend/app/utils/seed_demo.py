"""Seeds the SQLite database with realistic, clearly labeled synthetic demo data."""

import io
from datetime import date, datetime, timedelta, timezone
import fitz
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, Base
from app.models.user import User, PatientProfile, DoctorProfile
from app.models.document import Document, ExtractedData
from app.models.analysis import AIAnalysis, AIFinding
from app.models.consent import AccessRequest, AccessGrant, FindingReview, Notification, AuditLog
from app.utils.security import hash_password
from app.services.clinical_intelligence import ClinicalIntelligenceEngine


def create_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    b = doc.tobytes()
    doc.close()
    return b


def seed_demo_data():
    db: Session = SessionLocal()
    try:
        # Check if already seeded
        if db.query(User).filter(User.email == "patient.alice@clintrace.demo").first():
            print("Demo data already seeded. Skipping...")
            return

        print("Seeding synthetic demonstration data...")

        # 1. Patients
        p1_user = User(
            email="patient.alice@clintrace.demo",
            password_hash=hash_password("DemoPatient123!"),
            role="patient",
            is_active=True,
        )
        db.add(p1_user)
        db.flush()

        p1_profile = PatientProfile(
            user_id=p1_user.id,
            patient_id="CLN-DEMO-0001",
            full_name="Alice M. Walker (Synthetic Demo)",
            date_of_birth=date(1982, 4, 18),
            gender="Female",
        )
        db.add(p1_profile)

        p2_user = User(
            email="patient.bob@clintrace.demo",
            password_hash=hash_password("DemoPatient123!"),
            role="patient",
            is_active=True,
        )
        db.add(p2_user)
        db.flush()

        p2_profile = PatientProfile(
            user_id=p2_user.id,
            patient_id="CLN-DEMO-0002",
            full_name="Bob J. Reynolds (Synthetic Demo)",
            date_of_birth=date(1975, 9, 30),
            gender="Male",
        )
        db.add(p2_profile)

        # 2. Doctors
        d1_user = User(
            email="dr.chen@clintrace.demo",
            password_hash=hash_password("DemoDoctor123!"),
            role="doctor",
            is_active=True,
        )
        db.add(d1_user)
        db.flush()

        d1_profile = DoctorProfile(
            user_id=d1_user.id,
            full_name="Dr. Sarah Chen, MD",
            registration_number="MED-CARDIO-88219",
            medical_council="State Medical Council",
            specialization="Cardiology & Internal Medicine",
            verification_status="verified",
        )
        db.add(d1_profile)

        d2_user = User(
            email="dr.morales@clintrace.demo",
            password_hash=hash_password("DemoDoctor123!"),
            role="doctor",
            is_active=True,
        )
        db.add(d2_user)
        db.flush()

        d2_profile = DoctorProfile(
            user_id=d2_user.id,
            full_name="Dr. Marcus Morales, DO",
            registration_number="MED-ENDO-44102",
            medical_council="National Medical Commission",
            specialization="Endocrinology",
            verification_status="provisional",
        )
        db.add(d2_profile)
        db.commit()

        # 3. Documents for Alice (Demonstrating Discrepancies & Contradictions)
        # Doc 1: Prescription
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
                "model": "clinical_regex_rule_engine",
            },
            extraction_method="pdf_text",
        )
        db.add(ed1)

        # Doc 2: Subsequent clinic visit with conflicting Metformin dosage (1000mg)
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
                "model": "clinical_regex_rule_engine",
            },
            extraction_method="pdf_text",
        )
        db.add(ed2)

        # Doc 3: Lab report with abnormal HbA1c
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
                "model": "clinical_regex_rule_engine",
            },
            extraction_method="pdf_text",
        )
        db.add(ed3)
        db.commit()

        # 4. Generate Clinical Intelligence Analysis (V1) for Alice
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

        created_findings = []
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
            created_findings.append(finding)
        db.commit()

        # 5. Access Grant: Alice -> Dr. Sarah Chen
        grant = AccessGrant(
            doctor_id=d1_user.id,
            patient_id=p1_profile.id,
            scope="full_records",
            is_emergency=False,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(grant)

        # 6. Doctor Review: Dr. Chen reviews the Metformin discrepancy finding
        if created_findings:
            review = FindingReview(
                finding_id=created_findings[0].id,
                doctor_id=d1_user.id,
                action="accept",
                explanation="Clinically confirmed dosage adjustment from 500mg to 1000mg BID based on elevated HbA1c (7.8%). Patient tolerating increased dose well.",
            )
            created_findings[0].review_status = "reviewed"
            db.add(review)

        # 7. Access Request: Dr. Marcus Morales requested access to Bob Reynolds (Pending)
        req = AccessRequest(
            doctor_id=d2_user.id,
            patient_id=p2_profile.id,
            reason="Endocrine consultation and diabetes management review.",
            is_emergency=False,
            status="pending",
        )
        db.add(req)

        # 8. Notifications & Audit Logs
        notif1 = Notification(
            user_id=p1_user.id,
            title="Access Granted to Dr. Sarah Chen",
            message="Dr. Sarah Chen was granted full clinical review access for 7 days.",
            notification_type="consent",
            is_read=True,
        )
        notif2 = Notification(
            user_id=p2_user.id,
            title="New Access Request from Dr. Marcus Morales",
            message="Dr. Marcus Morales requested access to your medical records for 'Endocrine consultation and diabetes management review.'",
            notification_type="consent",
            is_read=False,
        )
        db.add(notif1)
        db.add(notif2)

        audit1 = AuditLog(
            user_id=d1_user.id,
            action="access_granted",
            resource_type="patient_record",
            resource_id=str(p1_profile.id),
            details={"doctor_name": "Dr. Sarah Chen", "patient_id_str": p1_profile.patient_id},
        )
        audit2 = AuditLog(
            user_id=d2_user.id,
            action="access_requested",
            resource_type="patient_record",
            resource_id=str(p2_profile.id),
            details={"doctor_name": "Dr. Marcus Morales", "patient_id_str": p2_profile.patient_id},
        )
        db.add(audit1)
        db.add(audit2)

        db.commit()
        print("Demo data seeded successfully!")

    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_data()
