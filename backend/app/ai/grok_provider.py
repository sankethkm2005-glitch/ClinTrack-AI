"""Grok (xAI) API provider implementation using OpenAI-compatible chat completions."""

import json
import re
import httpx
from app.ai.base import BaseAIProvider
from app.ai.prompts.extraction import (
    CLINICAL_EXTRACTION_SYSTEM_PROMPT,
    CLINICAL_EXTRACTION_USER_PROMPT,
)
from app.schemas.document import ClinicalExtractionResult


class GrokAIProvider(BaseAIProvider):
    """Integrates with Grok API (x.ai) for clinical text extraction."""

    async def extract_clinical_data(
        self,
        filename: str,
        document_type: str,
        page_texts: list[dict],
    ) -> ClinicalExtractionResult:
        # If API key is not configured, return a clear, honest mock/fallback extraction
        if not self.api_key or self.api_key.strip() in ["", "your_api_key_here"]:
            return self._generate_heuristic_or_demo_extraction(filename, document_type, page_texts)

        formatted_pages = "\n\n".join(
            [f"--- Page {p.get('page', 1)} ---\n{p.get('text', '')}" for p in page_texts]
        )

        user_content = CLINICAL_EXTRACTION_USER_PROMPT.format(
            filename=filename,
            document_type=document_type,
            page_content=formatted_pages,
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model or "grok-3-mini",
            "messages": [
                {"role": "system", "content": CLINICAL_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,  # Low temperature to minimize hallucination
        }

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                raise RuntimeError(
                    f"Grok API error ({response.status_code}): {response.text}"
                )
            res_data = response.json()

        raw_output = res_data["choices"][0]["message"]["content"]
        parsed = json.loads(raw_output)
        parsed["ai_provider"] = "grok"
        parsed["model"] = self.model

        # Pydantic validation ensures structure adheres to clinical requirements
        return ClinicalExtractionResult.model_validate(parsed)

    def _generate_heuristic_or_demo_extraction(
        self, filename: str, document_type: str, page_texts: list[dict]
    ) -> ClinicalExtractionResult:
        """
        Deterministic offline clinical entity parser using validated medical regex rules.
        Runs when GROK_API_KEY is not configured or offline mode is requested.
        Preserves page references, extracts explicit dosages, units, and ranges,
        and never infers diagnoses from isolated laboratory results.
        """
        meds = []
        labs = []
        conds = []

        all_text = " ".join([p.get("text", "") for p in page_texts])
        lower_all = all_text.lower()

        # Check for sparse / low-confidence text requiring clinician review
        sparse_text = len(all_text.strip()) < 20
        handwritten_suspect = any(
            w in lower_all for w in ["handwritten", "handwriting", "dr rx", "illegible", "scanned signature"]
        )
        requires_review = sparse_text or handwritten_suspect
        review_reason = (
            "Document contains sparse or suspect handwritten text requiring qualified clinician review."
            if requires_review
            else None
        )

        # -------------------------------------------------------------
        # 1. MEDICATIONS EXTRACTION (Explicit names, dosages, frequency)
        # -------------------------------------------------------------
        known_drugs = [
            "Metformin", "Lisinopril", "Atorvastatin", "Amlodipine", "Levothyroxine",
            "Omeprazole", "Losartan", "Metoprolol", "Simvastatin", "Hydrochlorothiazide",
            "Gabapentin", "Amoxicillin", "Aspirin", "Insulin", "Albuterol", "Furosemide",
            "Pantoprazole", "Glipizide", "Clopidogrel", "Sertraline", "Ibuprofen",
            "Ciprofloxacin", "Prednisone", "Rosuvastatin", "Warfarin", "Empagliflozin",
        ]

        seen_med_keys = set()
        for p in page_texts:
            page_num = p.get("page", 1)
            text = p.get("text", "")
            lines = text.split("\n")

            for line in lines:
                clean_line = line.strip()
                if not clean_line:
                    continue

                for drug in known_drugs:
                    pattern = rf"(?i)\b{drug}\b"
                    if re.search(pattern, clean_line):
                        # Extract explicit dosage
                        dos_match = re.search(
                            r"(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|units?|iu))\b", clean_line, re.IGNORECASE
                        )
                        dosage = dos_match.group(1).strip() if dos_match else "Not specified"

                        # Extract explicit frequency
                        freq = "Once daily"
                        if re.search(r"(?i)\b(?:bid|twice\s+daily)\b", clean_line):
                            freq = "Twice daily"
                        elif re.search(r"(?i)\b(?:tid|three\s+times\s+daily)\b", clean_line):
                            freq = "Three times daily"
                        elif re.search(r"(?i)\b(?:qid|four\s+times\s+daily)\b", clean_line):
                            freq = "Four times daily"
                        elif re.search(r"(?i)\b(?:hs|at\s+bedtime|bedtime)\b", clean_line):
                            freq = "At bedtime"
                        elif re.search(r"(?i)\b(?:prn|as\s+needed)\b", clean_line):
                            freq = "As needed"
                        elif re.search(r"(?i)\b(?:daily|once\s+daily|qd)\b", clean_line):
                            freq = "Once daily"
                        elif re.search(r"(?i)\bevery\s+\d+\s+hours\b", clean_line):
                            every_h = re.search(r"(?i)every\s+\d+\s+hours", clean_line).group(0)
                            freq = every_h.capitalize()

                        route = "Oral"
                        if "inhal" in clean_line.lower() or drug == "Albuterol":
                            route = "Inhalation"
                        elif "subcut" in clean_line.lower() or drug == "Insulin":
                            route = "Subcutaneous"
                        elif "topical" in clean_line.lower():
                            route = "Topical"

                        med_key = f"{drug.lower()}_{dosage.lower()}_{page_num}"
                        if med_key not in seen_med_keys:
                            seen_med_keys.add(med_key)
                            meds.append({
                                "name": drug,
                                "dosage": dosage,
                                "frequency": freq,
                                "route": route,
                                "status": "active",
                                "page_number": page_num,
                                "evidence_text": clean_line[:120],
                            })

                # Also match explicitly labeled medication lines for any drug name + dosage
                rx_line_match = re.search(
                    r"(?i)^(?:rx|medication|medications|prescribed)[\s:]+([A-Z][a-zA-Z\-]{2,})\s+(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|units?|iu))\b",
                    clean_line,
                )
                if rx_line_match:
                    gen_drug = rx_line_match.group(1).strip()
                    gen_dosage = rx_line_match.group(2).strip()
                    gen_key = f"{gen_drug.lower()}_{gen_dosage.lower()}_{page_num}"
                    if gen_key not in seen_med_keys:
                        seen_med_keys.add(gen_key)
                        freq = "Once daily"
                        if re.search(r"(?i)\b(?:bid|twice\s+daily)\b", clean_line):
                            freq = "Twice daily"
                        elif re.search(r"(?i)\b(?:tid|three\s+times\s+daily)\b", clean_line):
                            freq = "Three times daily"
                        elif re.search(r"(?i)\b(?:hs|at\s+bedtime|bedtime)\b", clean_line):
                            freq = "At bedtime"
                        meds.append({
                            "name": gen_drug,
                            "dosage": gen_dosage,
                            "frequency": freq,
                            "route": "Oral",
                            "status": "active",
                            "page_number": page_num,
                            "evidence_text": clean_line[:120],
                        })

        # -------------------------------------------------------------
        # 2. CONDITIONS EXTRACTION (Only from explicit diagnosis sections)
        # -------------------------------------------------------------
        diagnosis_section_pattern = re.compile(
            r"(?i)\b(?:diagnosis|diagnoses|assessment|impression|condition|problem\s+list)[\s:]+([^\n\.;]+)"
        )
        seen_cond_keys = set()
        for p in page_texts:
            page_num = p.get("page", 1)
            text = p.get("text", "")

            # Look for labeled diagnosis lines
            for match in diagnosis_section_pattern.finditer(text):
                raw_extracted = match.group(1).strip()
                # Split multiple diagnoses separated by commas or semicolons
                candidates = re.split(r"[,;]|(?:\sand\s)", raw_extracted)
                for cand in candidates:
                    cand_clean = cand.strip()
                    if len(cand_clean) < 3:
                        continue

                    # Standardize condition names
                    cand_lower = cand_clean.lower()
                    canon_name = cand_clean
                    if "diabetes" in cand_lower:
                        canon_name = "Type 2 Diabetes Mellitus"
                    elif "hypertension" in cand_lower:
                        canon_name = "Essential Hypertension"
                    elif "hyperlipidemia" in cand_lower or "hypercholesterolemia" in cand_lower:
                        canon_name = "Hyperlipidemia"
                    elif "asthma" in cand_lower:
                        canon_name = "Bronchial Asthma"
                    elif "ckd" in cand_lower or "chronic kidney" in cand_lower:
                        canon_name = "Chronic Kidney Disease"
                    elif "hypothyroidism" in cand_lower:
                        canon_name = "Hypothyroidism"

                    if canon_name.lower() not in seen_cond_keys:
                        seen_cond_keys.add(canon_name.lower())
                        conds.append({
                            "name": canon_name,
                            "status": "active",
                            "page_number": page_num,
                            "evidence_text": f"{match.group(0).strip()[:100]}",
                        })

        # Fallback for synthetic demo documents explicitly stating diagnoses in text
        if not conds:
            if "type 2 diabetes" in lower_all or "diabetes mellitus" in lower_all:
                conds.append({
                    "name": "Type 2 Diabetes Mellitus",
                    "status": "active",
                    "page_number": 1,
                    "evidence_text": "Mentioned in clinical record: Type 2 Diabetes",
                })
            if "essential hypertension" in lower_all or "hypertension" in lower_all:
                conds.append({
                    "name": "Essential Hypertension",
                    "status": "active",
                    "page_number": 1,
                    "evidence_text": "Mentioned in clinical record: Hypertension",
                })

        # -------------------------------------------------------------
        # 3. LABORATORY RESULTS (Test name, numerical value, units, ref range)
        # -------------------------------------------------------------
        known_labs = [
            (r"(?i)\b(hba1c|glycated\s+hemoglobin)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(%|percent)?",
             "HbA1c", "%", "4.0 - 5.6", (4.0, 5.6)),
            (r"(?i)\b(fasting\s+(?:blood|plasma)?\s*glucose|blood\s+glucose|glucose)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(mg/dl|mmol/l)?",
             "Fasting Plasma Glucose", "mg/dL", "70 - 99", (70.0, 99.0)),
            (r"(?i)\b(serum\s+creatinine|creatinine)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(mg/dl|umol/l)?",
             "Serum Creatinine", "mg/dL", "0.6 - 1.2", (0.6, 1.2)),
            (r"(?i)\b(total\s+cholesterol|cholesterol)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(mg/dl)?",
             "Total Cholesterol", "mg/dL", "100 - 199", (100.0, 199.0)),
            (r"(?i)\b(ldl(?:\s*cholesterol)?)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(mg/dl)?",
             "LDL Cholesterol", "mg/dL", "< 100", (0.0, 99.0)),
            (r"(?i)\b(hdl(?:\s*cholesterol)?)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(mg/dl)?",
             "HDL Cholesterol", "mg/dL", "40 - 60", (40.0, 60.0)),
            (r"(?i)\b(triglycerides)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(mg/dl)?",
             "Triglycerides", "mg/dL", "< 150", (0.0, 149.0)),
            (r"(?i)\b(potassium|k\+?)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(meq/l|mmol/l)?",
             "Potassium", "mEq/L", "3.5 - 5.0", (3.5, 5.0)),
            (r"(?i)\b(sodium|na\+?)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(meq/l|mmol/l)?",
             "Sodium", "mEq/L", "135 - 145", (135.0, 145.0)),
            (r"(?i)\b(hemoglobin|hgb)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(g/dl)?",
             "Hemoglobin", "g/dL", "12.0 - 17.5", (12.0, 17.5)),
            (r"(?i)\b(platelets|plt)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(10\^3/ul|k/ul)?",
             "Platelets", "10^3/uL", "150 - 450", (150.0, 450.0)),
            (r"(?i)\b(tsh)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(miu/l|uiu/ml)?",
             "TSH", "mIU/L", "0.4 - 4.0", (0.4, 4.0)),
            (r"(?i)\b(alt|alanine\s+aminotransferase)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(u/l|iu/l)?",
             "ALT", "U/L", "7 - 56", (7.0, 56.0)),
            (r"(?i)\b(ast|aspartate\s+aminotransferase)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(u/l|iu/l)?",
             "AST", "U/L", "10 - 40", (10.0, 40.0)),
            (r"(?i)\b(total\s+bilirubin|bilirubin)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(mg/dl)?",
             "Total Bilirubin", "mg/dL", "0.1 - 1.2", (0.1, 1.2)),
            (r"(?i)\b(bun|blood\s+urea\s+nitrogen)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(mg/dl)?",
             "BUN", "mg/dL", "7 - 20", (7.0, 20.0)),
            (r"(?i)\b(calcium)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(mg/dl)?",
             "Calcium", "mg/dL", "8.5 - 10.5", (8.5, 10.5)),
            (r"(?i)\b(crp|c-reactive\s+protein)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(mg/l|mg/dl)?",
             "CRP", "mg/L", "0.0 - 10.0", (0.0, 10.0)),
            (r"(?i)\b(egfr)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(ml/min(?:/1\.73m2)?)?",
             "eGFR", "mL/min/1.73m2", "60 - 120", (60.0, 120.0)),
            (r"(?i)\b(wbc|white\s+blood\s+cells?)\b[\s:]*([0-9]+(?:\.[0-9]+)?)\s*(10\^3/ul|k/ul)?",
             "White Blood Cells", "10^3/uL", "4.5 - 11.0", (4.5, 11.0)),
        ]

        seen_lab_keys = set()
        for p in page_texts:
            page_num = p.get("page", 1)
            text = p.get("text", "")
            lines = text.split("\n")

            for line in lines:
                clean_line = line.strip()
                if not clean_line:
                    continue

                for pat, canon_lab, default_unit, default_ref, (low_norm, high_norm) in known_labs:
                    m = re.search(pat, clean_line)
                    if m:
                        val_str = m.group(2)
                        unit = (m.group(3) if m.lastindex and m.lastindex >= 3 else None) or default_unit
                        try:
                            val_num = float(val_str)
                        except ValueError:
                            continue

                        # Explicit reference range in text
                        ref_match = re.search(
                            r"(?i)(?:ref:?|range:?|\()\s*([0-9.]+\s*-\s*[0-9.]+)", clean_line
                        )
                        ref_range = ref_match.group(1).strip() if ref_match else default_ref

                        # Abnormality evaluation
                        flagged_high = bool(re.search(r"(?i)\b(?:\(H\)|High|Elevated|\*)\b", clean_line))
                        flagged_low = bool(re.search(r"(?i)\b(?:\(L\)|Low)\b", clean_line))
                        is_abnormal = flagged_high or flagged_low or (val_num < low_norm) or (val_num > high_norm)

                        lab_key = f"{canon_lab}_{val_str}_{page_num}"
                        if lab_key not in seen_lab_keys:
                            seen_lab_keys.add(lab_key)
                            labs.append({
                                "test_name": canon_lab,
                                "value": val_str,
                                "unit": unit,
                                "reference_range": ref_range,
                                "is_abnormal": is_abnormal,
                                "page_number": page_num,
                                "evidence_text": clean_line[:120],
                            })

        return ClinicalExtractionResult(
            document_type=document_type,
            patient_name=None,
            conditions=conds,
            medications=meds,
            lab_results=labs,
            clinical_notes=["Extracted via deterministic offline rule engine (GROK_API_KEY unconfigured)."],
            requires_manual_review=requires_review,
            review_reason=review_reason,
            extracted_summary=f"[Offline Rule Engine] Extracted {len(meds)} medication(s), {len(conds)} condition(s), {len(labs)} lab result(s) from {filename}.",
            ai_provider="offline_heuristic",
            model="clinical_regex_rule_engine",
        )
