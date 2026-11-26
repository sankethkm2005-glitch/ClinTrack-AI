"""Analysis router for running versioned intelligence, fetching latest, and viewing history."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User, PatientProfile
from app.models.document import Document, ExtractedData
from app.models.analysis import AIAnalysis, AIFinding
from app.schemas.analysis import AIAnalysisOut, AIAnalysisHistoryItem
from app.utils.dependencies import get_current_user
from app.services.clinical_intelligence import ClinicalIntelligenceEngine

router = APIRouter(prefix="/analysis", tags=["Clinical Intelligence"])


from fastapi.responses import Response
from app.services.report_generator import ClinicalReportGenerator


def _verify_patient_access(patient_id: int, user: User, db: Session | None = None) -> bool:
    """Helper verifying role authorization or consent grant for patient records."""
    if user.role == "patient":
        return user.patient_profile is not None and user.patient_profile.id == patient_id
    elif user.role == "doctor":
        if db is not None:
            from app.models.consent import AccessGrant
            from app.routers.consent import _is_grant_active
            matching_grants = (
                db.query(AccessGrant)
                .filter(
                    AccessGrant.doctor_id == user.id,
                    AccessGrant.patient_id == patient_id,
                    AccessGrant.revoked_at == None,
                )
                .all()
            )
            return any(_is_grant_active(g) for g in matching_grants)
        return True
    return False


def _get_authorized_patient_and_grant(patient_id: int, user: User, db: Session) -> tuple[PatientProfile, bool]:
    """Helper verifying authorization for patient records."""
    patient = db.query(PatientProfile).filter(PatientProfile.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found.")

    if user.role == "patient":
        if not user.patient_profile or user.patient_profile.id != patient_id:
            raise HTTPException(status_code=403, detail="Unauthorized access to patient records.")
        return patient, True

    elif user.role == "doctor":
        # Check active grant
        from app.models.consent import AccessGrant
        from app.routers.consent import _is_grant_active
        matching_grants = (
            db.query(AccessGrant)
            .filter(
                AccessGrant.doctor_id == user.id,
                AccessGrant.patient_id == patient_id,
                AccessGrant.revoked_at == None,
            )
            .all()
        )
        active_grant = next((g for g in matching_grants if _is_grant_active(g)), None)
        if not active_grant:
            raise HTTPException(status_code=403, detail="No active consent grant for this patient's records.")
        return patient, True

    raise HTTPException(status_code=403, detail="Unauthorized role.")


@router.get("/patients/{patient_id}/report.pdf")
def download_clinical_report_pdf(
    patient_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generates and streams an official, evidence-linked clinical summary PDF."""
    patient, _ = _get_authorized_patient_and_grant(patient_id, user, db)

    latest_analysis = (
        db.query(AIAnalysis)
        .filter(AIAnalysis.patient_id == patient_id)
        .order_by(AIAnalysis.version_number.desc())
        .first()
    )

    pdf_bytes = ClinicalReportGenerator.generate_pdf_report(patient, latest_analysis)

    safe_name = patient.full_name.replace(" ", "_").replace("(", "").replace(")", "")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=ClinTrace_Report_{safe_name}_{patient.patient_id}.pdf"
        },
    )


@router.get("/patients/{patient_id}/lab-trends")
def get_patient_lab_trends(
    patient_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns time-series laboratory analytics for plotting, grouped by compatible test and unit.
    Preserves exact measurement dates, source documents, and reference ranges.
    """
    patient, _ = _get_authorized_patient_and_grant(patient_id, user, db)

    active_docs = (
        db.query(Document)
        .filter(Document.patient_id == patient_id, Document.is_deleted == False)
        .all()
    )
    doc_map = {d.id: d for d in active_docs}
    doc_ids = [d.id for d in active_docs]

    extracted_list = (
        db.query(ExtractedData)
        .filter(ExtractedData.document_id.in_(doc_ids))
        .all()
    )

    trends = {}
    for ed in extracted_list:
        doc = doc_map.get(ed.document_id)
        if not doc:
            continue
        sd = ed.structured_data or {}
        for lab in sd.get("lab_results", []):
            test_name = (lab.get("test_name") or "Unknown Test").strip()
            unit = (lab.get("unit") or "N/A").strip()
            key = f"{test_name} ({unit})"

            try:
                # Extract numeric value for graphing
                val_str = str(lab.get("value", "")).strip()
                import re
                match = re.search(r"[-+]?\d*\.\d+|\d+", val_str)
                num_val = float(match.group()) if match else None
            except Exception:
                num_val = None

            if key not in trends:
                trends[key] = {
                    "test_name": test_name,
                    "unit": unit,
                    "reference_range": lab.get("reference_range", "N/A"),
                    "points": [],
                    "data_points": [],
                }

            pt = {
                "date": lab.get("test_date") or doc.uploaded_at.strftime("%Y-%m-%d"),
                "value": num_val,
                "value_raw": lab.get("value"),
                "value_numeric": num_val,
                "reference_range": lab.get("reference_range", "N/A"),
                "is_abnormal": lab.get("is_abnormal", False),
                "document_id": doc.id,
                "document_name": doc.filename,
                "page_number": lab.get("page_number", 1),
                "evidence_text": lab.get("evidence_text"),
            }
            trends[key]["points"].append(pt)
            trends[key]["data_points"].append(pt)

    # Sort each trend chronologically
    for t in trends.values():
        t["points"].sort(key=lambda p: p["date"])
        t["data_points"] = t["points"]

    return list(trends.values())



def execute_patient_analysis(patient_id: int, db: Session) -> AIAnalysis | None:
    """
    Executes cross-document clinical synthesis for a patient:
    - Queries all active, non-deleted medical documents and their extracted data.
    - Computes next incremental version number (V1 -> V2 -> ...).
    - Preserves historical versions by marking existing active analysis as 'outdated'.
    - Runs the ClinicalIntelligenceEngine to reconcile medications, detect contradictions, and analyze lab trends.
    - Stores the synthesized AIAnalysis and associated AIFinding records.
    - Returns the new AIAnalysis or None if no active documents exist.
    """
    active_docs = (
        db.query(Document)
        .filter(Document.patient_id == patient_id, Document.is_deleted == False)
        .all()
    )
    if not active_docs:
        return None

    doc_ids = [d.id for d in active_docs]
    extracted_data_list = (
        db.query(ExtractedData)
        .filter(ExtractedData.document_id.in_(doc_ids))
        .all()
    )

    # Calculate version number
    latest_existing = (
        db.query(AIAnalysis)
        .filter(AIAnalysis.patient_id == patient_id)
        .order_by(AIAnalysis.version_number.desc())
        .first()
    )
    new_version = (latest_existing.version_number + 1) if latest_existing else 1

    # Mark prior analyses as outdated (preserves history, never silently overwrites)
    db.query(AIAnalysis).filter(
        AIAnalysis.patient_id == patient_id,
        AIAnalysis.status == "current",
    ).update({"status": "outdated"})

    # Run Clinical Intelligence Engine
    analysis_result = ClinicalIntelligenceEngine.analyze_patient_records(
        documents=active_docs,
        extracted_data_list=extracted_data_list,
    )

    new_analysis = AIAnalysis(
        patient_id=patient_id,
        version_number=new_version,
        status="current",
        summary=analysis_result["summary"],
        completeness_score=analysis_result["completeness_score"],
        completeness_breakdown=analysis_result["completeness_breakdown"],
        timeline=analysis_result["timeline"],
        ai_provider=analysis_result.get("ai_provider", "offline"),
        ai_model=analysis_result.get("ai_model", "clinical_rule_engine"),
        document_ids_snapshot=doc_ids,
    )
    db.add(new_analysis)
    db.flush()

    # Create associated clinical findings
    for f in analysis_result["findings"]:
        finding = AIFinding(
            analysis_id=new_analysis.id,
            finding_type=f["finding_type"],
            priority=f["priority"],
            title=f["title"],
            description=f["description"],
            evidence=f.get("evidence"),
            review_status="pending",
        )
        db.add(finding)

    db.commit()
    db.refresh(new_analysis)
    return new_analysis


@router.post("/patients/{patient_id}/run", response_model=AIAnalysisOut)
def run_patient_analysis(
    patient_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Synthesizes multi-document clinical intelligence, marks prior version as outdated,
    and increments analysis version (V1 -> V2 -> ...).
    """
    if not _verify_patient_access(patient_id, user, db):
        raise HTTPException(status_code=403, detail="Unauthorized access to patient records.")

    patient = db.query(PatientProfile).filter(PatientProfile.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found.")

    analysis = execute_patient_analysis(patient_id, db)
    if not analysis:
        raise HTTPException(status_code=400, detail="No active medical documents found for analysis.")

    return analysis


@router.get("/patients/{patient_id}/latest", response_model=AIAnalysisOut)
def get_latest_patient_analysis(
    patient_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the latest current AI analysis for the patient."""
    if not _verify_patient_access(patient_id, user, db):
        raise HTTPException(status_code=403, detail="Unauthorized access to patient records.")

    analysis = (
        db.query(AIAnalysis)
        .filter(AIAnalysis.patient_id == patient_id)
        .order_by(AIAnalysis.version_number.desc())
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="No AI analysis found for this patient.")

    return analysis


@router.get("/patients/{patient_id}/history", response_model=list[AIAnalysisHistoryItem])
def get_patient_analysis_history(
    patient_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns all preserved analysis versions for the patient."""
    if not _verify_patient_access(patient_id, user, db):
        raise HTTPException(status_code=403, detail="Unauthorized access to patient records.")

    return (
        db.query(AIAnalysis)
        .filter(AIAnalysis.patient_id == patient_id)
        .order_by(AIAnalysis.version_number.desc())
        .all()
    )
