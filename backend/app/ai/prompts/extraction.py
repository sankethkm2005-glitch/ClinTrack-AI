"""System and extraction prompts for clinical intelligence extraction."""

CLINICAL_EXTRACTION_SYSTEM_PROMPT = """You are ClinTrace AI's clinical information extraction module.
Your role is to strictly extract explicitly stated clinical facts from patient medical documents.

SAFETY GUIDELINES:
1. NEVER independently diagnose a disease or condition. Only extract diagnoses explicitly stated by attending clinicians.
2. NEVER prescribe, change, or recommend medication dosages.
3. NEVER guess unreadable, handwritten, or ambiguous medicine names or dosages.
4. If a value or instruction is uncertain, set requires_manual_review to true and explain in review_reason.
5. Retain exact page numbers and evidence quotes from the source text.
6. Return your findings exclusively in valid JSON matching the required schema.
"""

CLINICAL_EXTRACTION_USER_PROMPT = """Analyze the following extracted medical document text and extract all explicitly stated clinical details.

Source Document Filename: {filename}
Assigned Document Category: {document_type}

Document Content by Page:
{page_content}

Return a valid JSON object matching this structure:
{{
  "document_type": "{document_type}",
  "patient_name": "string or null",
  "patient_dob": "string or null",
  "conditions": [
    {{
      "name": "string",
      "status": "active | historical | suspected",
      "onset_date": "string or null",
      "page_number": 1,
      "evidence_text": "verbatim text quote"
    }}
  ],
  "medications": [
    {{
      "name": "string",
      "dosage": "string or null",
      "frequency": "string or null",
      "route": "string or null",
      "start_date": "string or null",
      "status": "active | discontinued | unknown",
      "page_number": 1,
      "evidence_text": "verbatim text quote"
    }}
  ],
  "lab_results": [
    {{
      "test_name": "string",
      "value": "string",
      "unit": "string or null",
      "reference_range": "string or null",
      "is_abnormal": false,
      "test_date": "string or null",
      "page_number": 1,
      "evidence_text": "verbatim text quote"
    }}
  ],
  "clinical_notes": ["explicit doctor comments or instructions"],
  "requires_manual_review": false,
  "review_reason": null,
  "extracted_summary": "Objective, concise factual summary of the explicit findings without speculation."
}}
"""
