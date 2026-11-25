"""Clinical intelligence engine for multi-document clinical reconciliation."""

import re
from datetime import datetime
from collections import defaultdict

from app.models.document import Document, ExtractedData


class ClinicalIntelligenceEngine:
    """
    Reconstructs chronological timelines, reconciles medications, analyzes lab trends,
    detects multi-document contradictions, identifies missing info, and computes completeness score.
    """

    @classmethod
    def analyze_patient_records(
        cls,
        documents: list[Document],
        extracted_data_list: list[ExtractedData],
    ) -> dict:
        """
        Executes comprehensive cross-document reconciliation.
        Returns:
            dict containing:
                - summary: str
                - completeness_score: int
                - completeness_breakdown: dict
                - timeline: list[dict]
                - findings: list[dict]
        """
        doc_map = {d.id: d for d in documents}
        
        # Aggregate raw items tagged with source document metadata
        all_conditions = []
        all_medications = []
        all_labs = []
        all_notes = []

        for ed in extracted_data_list:
            doc = doc_map.get(ed.document_id)
            if not doc:
                continue
            sd = ed.structured_data or {}
            
            # Conditions
            for c in sd.get("conditions", []):
                all_conditions.append({
                    **c,
                    "doc_id": doc.id,
                    "doc_name": doc.filename,
                    "doc_type": doc.document_type,
                    "doc_date": doc.uploaded_at.strftime("%Y-%m-%d"),
                })
            
            # Medications
            for m in sd.get("medications", []):
                all_medications.append({
                    **m,
                    "doc_id": doc.id,
                    "doc_name": doc.filename,
                    "doc_type": doc.document_type,
                    "doc_date": doc.uploaded_at.strftime("%Y-%m-%d"),
                })

            # Labs
            for l in sd.get("lab_results", []):
                all_labs.append({
                    **l,
                    "doc_id": doc.id,
                    "doc_name": doc.filename,
                    "doc_type": doc.document_type,
                    "doc_date": doc.uploaded_at.strftime("%Y-%m-%d"),
                })

            # Notes
            for n in sd.get("clinical_notes", []):
                all_notes.append({
                    "note": n,
                    "doc_id": doc.id,
                    "doc_name": doc.filename,
                    "doc_type": doc.document_type,
                    "doc_date": doc.uploaded_at.strftime("%Y-%m-%d"),
                })

        # 1. Timeline Reconstruction
        timeline = cls._reconstruct_timeline(documents, all_conditions, all_medications, all_labs)

        # 2. Medication Reconciliation
        med_findings = cls._reconcile_medications(all_medications)

        # 3. Lab Trend Analysis
        lab_findings = cls._analyze_laboratories(all_labs)

        # 4. Contradiction Detection
        contradiction_findings = cls._detect_contradictions(all_conditions, all_medications, all_labs)

        # 5. Missing Information
        missing_findings = cls._detect_missing_info(documents, all_conditions, all_medications, all_labs)

        # 6. Record Completeness Indicator (0-100)
        completeness_score, breakdown = cls._compute_completeness(
            documents, all_conditions, all_medications, all_labs, missing_findings
        )

        # 7. Summary Narrative
        summary = cls._generate_summary(
            documents, all_conditions, all_medications, all_labs, contradiction_findings
        )

        all_findings = med_findings + lab_findings + contradiction_findings + missing_findings

        return {
            "summary": summary,
            "completeness_score": completeness_score,
            "completeness_breakdown": breakdown,
            "timeline": timeline,
            "findings": all_findings,
        }

    @classmethod
    def _reconstruct_timeline(cls, docs, conditions, medications, labs) -> list[dict]:
        """Builds chronological events linked to source document, page, and evidence quote."""
        events = []

        # Conditions events
        for c in conditions:
            date_val = c.get("onset_date") or c.get("doc_date")
            events.append({
                "date": date_val,
                "event_type": "condition",
                "title": f"Documented Condition: {c.get('name')}",
                "description": f"Status: {c.get('status', 'documented')}",
                "document_id": c.get("doc_id"),
                "document_name": c.get("doc_name"),
                "page_number": c.get("page_number", 1),
                "evidence_text": c.get("evidence_text"),
            })

        # Medication events
        for m in medications:
            date_val = m.get("start_date") or m.get("doc_date")
            events.append({
                "date": date_val,
                "event_type": "medication",
                "title": f"Prescribed / Mentioned: {m.get('name')}",
                "description": f"Dosage: {m.get('dosage', 'Not specified')}, Freq: {m.get('frequency', 'Not specified')}",
                "document_id": m.get("doc_id"),
                "document_name": m.get("doc_name"),
                "page_number": m.get("page_number", 1),
                "evidence_text": m.get("evidence_text"),
            })

        # Lab events
        for l in labs:
            date_val = l.get("test_date") or l.get("doc_date")
            events.append({
                "date": date_val,
                "event_type": "lab",
                "title": f"Lab Result: {l.get('test_name')}",
                "description": f"Value: {l.get('value')} {l.get('unit', '')} (Ref: {l.get('reference_range', 'N/A')})",
                "document_id": l.get("doc_id"),
                "document_name": l.get("doc_name"),
                "page_number": l.get("page_number", 1),
                "evidence_text": l.get("evidence_text"),
            })

        # Sort chronologically (oldest to newest, placing known dates first)
        def sort_key(item):
            d = item.get("date")
            return (0, d) if d else (1, "9999-99-99")

        events.sort(key=sort_key)
        return events

    @classmethod
    def _reconcile_medications(cls, medications) -> list[dict]:
        """Detects discrepancies in dosage, frequency, or duplicates across prescriptions."""
        findings = []
        by_name = defaultdict(list)

        for m in medications:
            norm_name = m.get("name", "").strip().lower()
            if norm_name:
                by_name[norm_name].append(m)

        for name, occurrences in by_name.items():
            if len(occurrences) > 1:
                # Compare dosages across occurrences
                dosages = {o.get("dosage") for o in occurrences if o.get("dosage")}
                frequencies = {o.get("frequency") for o in occurrences if o.get("frequency")}

                if len(dosages) > 1:
                    evidence_list = [
                        {
                            "document_id": o["doc_id"],
                            "document_name": o["doc_name"],
                            "page": o.get("page_number", 1),
                            "dosage": o.get("dosage"),
                            "frequency": o.get("frequency"),
                            "quote": o.get("evidence_text"),
                        }
                        for o in occurrences
                    ]
                    findings.append({
                        "finding_type": "medication",
                        "priority": "critical",
                        "title": f"Medication Dosage Discrepancy: {occurrences[0]['name'].title()}",
                        "description": (
                            f"Multiple conflicting dosages recorded for {occurrences[0]['name'].title()}: "
                            f"{', '.join(dosages)}. Requires clinician reconciliation."
                        ),
                        "evidence": evidence_list,
                    })
                elif len(frequencies) > 1:
                    evidence_list = [
                        {
                            "document_id": o["doc_id"],
                            "document_name": o["doc_name"],
                            "page": o.get("page_number", 1),
                            "frequency": o.get("frequency"),
                            "quote": o.get("evidence_text"),
                        }
                        for o in occurrences
                    ]
                    findings.append({
                        "finding_type": "medication",
                        "priority": "needs_review",
                        "title": f"Medication Frequency Variation: {occurrences[0]['name'].title()}",
                        "description": (
                            f"Different dosing frequencies observed: {', '.join(frequencies)} across documents."
                        ),
                        "evidence": evidence_list,
                    })

        return findings

    @classmethod
    def _analyze_laboratories(cls, labs) -> list[dict]:
        """Organizes tests and highlights abnormal findings and missing units."""
        findings = []
        for l in labs:
            if l.get("is_abnormal"):
                findings.append({
                    "finding_type": "lab",
                    "priority": "critical" if "high" in str(l.get("value")).lower() or "h" in str(l.get("evidence_text", "")).lower() else "needs_review",
                    "title": f"Abnormal Lab Value: {l.get('test_name')}",
                    "description": (
                        f"Reported value {l.get('value')} {l.get('unit', '')} falls outside standard reference range "
                        f"({l.get('reference_range', 'Not specified')})."
                    ),
                    "evidence": [{
                        "document_id": l["doc_id"],
                        "document_name": l["doc_name"],
                        "page": l.get("page_number", 1),
                        "value": l.get("value"),
                        "unit": l.get("unit"),
                        "quote": l.get("evidence_text"),
                    }],
                })
            elif not l.get("unit") or l.get("unit").strip() == "":
                findings.append({
                    "finding_type": "lab",
                    "priority": "informational",
                    "title": f"Missing Unit for Lab Test: {l.get('test_name')}",
                    "description": f"Test result has value '{l.get('value')}' but no measurement unit was explicitly documented.",
                    "evidence": [{
                        "document_id": l["doc_id"],
                        "document_name": l["doc_name"],
                        "page": l.get("page_number", 1),
                        "quote": l.get("evidence_text"),
                    }],
                })
        return findings

    @classmethod
    def _detect_contradictions(cls, conditions, medications, labs) -> list[dict]:
        """Detects conflicting diagnoses or mutually incompatible documented facts."""
        findings = []
        
        # Check for condition conflicts (e.g. Type 1 vs Type 2 diabetes, or Active vs Resolved conflict)
        by_name = defaultdict(list)
        for c in conditions:
            base = c.get("name", "").lower()
            if "diabetes" in base:
                by_name["diabetes"].append(c)
            elif "hypertension" in base:
                by_name["hypertension"].append(c)

        for cond_key, occurrences in by_name.items():
            names = {o.get("name") for o in occurrences}
            if len(names) > 1:
                findings.append({
                    "finding_type": "contradiction",
                    "priority": "critical",
                    "title": f"Diagnostic Contradiction: {cond_key.title()}",
                    "description": (
                        f"Conflicting classifications found in records: {', '.join(names)}. "
                        f"ClinTrace AI does not resolve diagnostic conflicts autonomously."
                    ),
                    "evidence": [
                        {
                            "document_id": o["doc_id"],
                            "document_name": o["doc_name"],
                            "page": o.get("page_number", 1),
                            "documented_diagnosis": o.get("name"),
                            "quote": o.get("evidence_text"),
                        }
                        for o in occurrences
                    ],
                })

        return findings

    @classmethod
    def _detect_missing_info(cls, docs, conditions, medications, labs) -> list[dict]:
        """Identifies gaps in documentation (e.g. medication without diagnosis, missing dosages)."""
        findings = []

        # Check for medications with unspecified dosages
        for m in medications:
            if not m.get("dosage") or m.get("dosage").strip().lower() in ["none", "unspecified"]:
                findings.append({
                    "finding_type": "missing_information",
                    "priority": "needs_review",
                    "title": f"Missing Dosage: {m.get('name')}",
                    "description": f"Medication '{m.get('name')}' was prescribed without explicit dosage or frequency.",
                    "evidence": [{
                        "document_id": m["doc_id"],
                        "document_name": m["doc_name"],
                        "page": m.get("page_number", 1),
                        "quote": m.get("evidence_text"),
                    }],
                })

        # Check if no laboratory reports are present when chronic conditions exist
        has_diabetes = any("diabetes" in c.get("name", "").lower() for c in conditions)
        has_hba1c = any("hba1c" in l.get("test_name", "").lower() or "glucose" in l.get("test_name", "").lower() for l in labs)
        if has_diabetes and not has_hba1c:
            findings.append({
                "finding_type": "missing_information",
                "priority": "needs_review",
                "title": "Missing Glycemic Lab Records",
                "description": "Patient has documented diabetes mellitus, but no corresponding HbA1c or blood glucose laboratory reports are present in the uploaded records.",
                "evidence": [],
            })

        return findings

    @classmethod
    def _compute_completeness(cls, docs, conditions, medications, labs, missing_findings) -> tuple[int, dict]:
        """
        Calculates a record completeness indicator (0-100%).
        NOTE: Measures documentation completeness only, not patient health or risk.
        """
        if not docs:
            return 0, {"reason": "No documents uploaded"}

        score = 100
        penalties = []

        # Deduct if no conditions identified
        if not conditions:
            score -= 20
            penalties.append("No medical conditions or clinical history documented (-20%)")

        # Deduct if no medications identified
        if not medications:
            score -= 15
            penalties.append("No active or historical medications recorded (-15%)")

        # Deduct for missing info findings
        for mf in missing_findings:
            score -= 10
            penalties.append(f"Missing clinical item: {mf['title']} (-10%)")

        # Deduct if only 1 document type is present
        doc_types = {d.document_type for d in docs}
        if len(doc_types) == 1:
            score -= 15
            penalties.append(f"Only one document category ({list(doc_types)[0]}) available (-15%)")

        score = max(10, min(100, score))
        breakdown = {
            "score": score,
            "document_count": len(docs),
            "categories_covered": list(doc_types),
            "penalties_or_gaps": penalties,
            "disclaimer": "Completeness score evaluates the breadth of provided clinical records only; it does not measure medical safety or health status.",
        }
        return score, breakdown

    @classmethod
    def _generate_summary(cls, docs, conditions, medications, labs, contradictions) -> str:
        """Synthesizes objective medical history narrative without speculative diagnoses."""
        if not docs:
            return "No medical documents available for clinical synthesis."

        cond_names = list({c.get("name") for c in conditions if c.get("name")})
        med_names = list({f"{m.get('name')} ({m.get('dosage') or 'unspecified'})" for m in medications if m.get("name")})
        abnormal_labs = [f"{l.get('test_name')}: {l.get('value')} {l.get('unit', '')}" for l in labs if l.get("is_abnormal")]

        parts = [
            f"Clinical summary synthesized across {len(docs)} uploaded document(s)."
        ]
        if cond_names:
            parts.append(f"Documented conditions include: {', '.join(cond_names)}.")
        if med_names:
            parts.append(f"Current/documented pharmacotherapy includes: {', '.join(med_names)}.")
        if abnormal_labs:
            parts.append(f"Abnormal laboratory values requiring physician attention: {', '.join(abnormal_labs)}.")
        if contradictions:
            parts.append(f"ATTENTION: {len(contradictions)} potential clinical contradiction(s) flagged for doctor review.")

        return " ".join(parts)
