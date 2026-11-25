"""PDF clinical report generator using PyMuPDF (fitz) without third-party dependencies."""

import fitz
from datetime import datetime, timezone
from app.models.user import PatientProfile
from app.models.analysis import AIAnalysis


class ClinicalReportGenerator:
    """Generates an official, well-formatted clinical summary PDF report."""

    @staticmethod
    def generate_pdf_report(patient: PatientProfile, analysis: AIAnalysis | None) -> bytes:
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)  # Standard Letter size

        # Header Banner
        banner_rect = fitz.Rect(36, 36, 576, 95)
        page.draw_rect(banner_rect, color=(0.04, 0.43, 0.60), fill=(0.04, 0.43, 0.60))
        page.insert_text(
            (48, 65),
            "ClinTrace AI — Clinical Intelligence Summary Report",
            fontsize=16,
            color=(1, 1, 1),
            fontname="helv",
        )
        page.insert_text(
            (48, 83),
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} | Clinical Decision-Support Prototype",
            fontsize=9,
            color=(0.9, 0.9, 0.9),
            fontname="helv",
        )

        y = 120
        # Patient Identification Section
        page.insert_text((36, y), "PATIENT IDENTIFICATION", fontsize=12, color=(0.05, 0.2, 0.4), fontname="helv")
        y += 18
        page.insert_text((36, y), f"Full Name: {patient.full_name}", fontsize=10, fontname="helv")
        page.insert_text((300, y), f"Unique Patient ID: {patient.patient_id}", fontsize=10, fontname="helv")
        y += 16
        page.insert_text((36, y), f"Date of Birth: {patient.date_of_birth}", fontsize=10, fontname="helv")
        page.insert_text((300, y), f"Gender: {patient.gender or 'Not specified'}", fontsize=10, fontname="helv")
        y += 24

        if not analysis:
            page.insert_text((36, y), "No clinical intelligence analysis has been synthesized for this patient record.", fontsize=10, fontname="helv")
            pdf_bytes = doc.tobytes()
            doc.close()
            return pdf_bytes

        # Analysis Metadata
        page.draw_line((36, y), (576, y), color=(0.8, 0.8, 0.8), width=1)
        y += 18
        page.insert_text(
            (36, y),
            f"ANALYSIS VERSION: V{analysis.version_number} ({analysis.status.upper()}) | Completeness Score: {analysis.completeness_score}%",
            fontsize=11,
            color=(0.05, 0.2, 0.4),
            fontname="helv",
        )
        y += 18

        # Summary Paragraph
        page.insert_text((36, y), "Objective Reconstructed Summary:", fontsize=10, color=(0.1, 0.1, 0.1), fontname="helv")
        y += 16
        # Split text simply into lines of max ~85 chars
        words = analysis.summary.split()
        line = ""
        for w in words:
            if len(line) + len(w) + 1 > 85:
                page.insert_text((36, y), line, fontsize=9, fontname="helv")
                y += 14
                line = w
            else:
                line = f"{line} {w}".strip()
        if line:
            page.insert_text((36, y), line, fontsize=9, fontname="helv")
            y += 20

        # AI Findings Section
        page.draw_line((36, y), (576, y), color=(0.8, 0.8, 0.8), width=1)
        y += 18
        page.insert_text((36, y), "KEY CLINICAL FINDINGS & DISCREPANCIES (EVIDENCE-LINKED)", fontsize=11, color=(0.05, 0.2, 0.4), fontname="helv")
        y += 16

        findings = analysis.findings or []
        if not findings:
            page.insert_text((36, y), "No clinical discrepancies, medication conflicts, or laboratory abnormalities identified.", fontsize=9, fontname="helv")
            y += 16
        else:
            for f in findings:
                if y > 720:  # New page if near bottom
                    page = doc.new_page(width=612, height=792)
                    y = 50
                p_tag = f"[{f.priority.upper()}]"
                page.insert_text((36, y), f"• {p_tag} {f.title} (Status: {f.review_status})", fontsize=9, fontname="helv", color=(0.6, 0.1, 0.1) if f.priority == "critical" else (0.1, 0.1, 0.1))
                y += 13
                page.insert_text((48, y), f.description[:110], fontsize=8, fontname="helv", color=(0.3, 0.3, 0.3))
                y += 14

                # Print doctor reviews if present
                for rev in getattr(f, "reviews", []):
                    doc_title = rev.doctor.doctor_profile.full_name if rev.doctor and rev.doctor.doctor_profile else "Doctor"
                    page.insert_text((48, y), f"→ Doctor Decision ({rev.action.upper()} by {doc_title}): {rev.explanation[:95]}", fontsize=8, fontname="helv", color=(0.08, 0.4, 0.2))
                    y += 13

        # Timeline Overview
        y += 12
        if y > 700:
            page = doc.new_page(width=612, height=792)
            y = 50
        page.draw_line((36, y), (576, y), color=(0.8, 0.8, 0.8), width=1)
        y += 18
        page.insert_text((36, y), "RECONSTRUCTED CHRONOLOGICAL TIMELINE", fontsize=11, color=(0.05, 0.2, 0.4), fontname="helv")
        y += 16

        timeline = analysis.timeline or []
        for t in timeline[:8]:
            if y > 740:
                break
            page.insert_text((36, y), f"{t.get('date', 'Undated')}: {t.get('title')} — Ref: {t.get('document_name', 'Doc')} (Page {t.get('page_number', 1)})", fontsize=8, fontname="helv")
            y += 13

        # Footer Disclaimer
        page.draw_rect(fitz.Rect(36, 755, 576, 780), color=(0.95, 0.95, 0.95), fill=(0.95, 0.95, 0.95))
        page.insert_text((42, 770), "ClinTrace AI decision-support prototype. Source evidence must be clinically verified prior to diagnostic or treatment decisions.", fontsize=7, color=(0.4, 0.4, 0.4), fontname="helv")

        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes
