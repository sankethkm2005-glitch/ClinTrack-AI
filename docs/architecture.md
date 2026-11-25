# ClinTrace AI Architecture
# ClinTrace AI — System Architecture

## 1. Project Overview

ClinTrace AI is an AI-powered clinical intelligence platform that reconstructs a patient's medical history from scattered medical documents.

It helps patients organize their medical records and enables authorized doctors to review reconstructed medical histories, medication discrepancies, laboratory findings, and missing information.

**Important:** ClinTrace AI is a decision-support prototype, not an autonomous diagnostic or prescribing system.

## 2. Architecture Style

We will use a **Modular Monolithic Architecture**.

The application will have separate frontend, backend, database, AI, and document-processing modules while remaining one deployable application.

This approach is suitable for our 24-hour hackathon and allows future expansion.

## 3. Technology Stack

| Layer | Technology |
|---|---|
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Backend | Python, FastAPI |
| Database | SQLite |
| ORM | SQLAlchemy |
| Validation | Pydantic |
| Migrations | Alembic |
| AI Provider | Grok API initially |
| PDF Extraction | PyMuPDF |
| OCR | Tesseract |
| Authentication | Secure password hashing and HTTP-only cookies |
| Version Control | Git and GitHub |

The AI provider must be replaceable through a provider adapter without rewriting the application.

## 4. High-Level Architecture

```text
                 PATIENT / DOCTOR
                        |
                        v
              FRONTEND (HTML/CSS/JS)
                        |
                        v
                 FASTAPI BACKEND
                        |
        +---------------+---------------+
        |               |               |
        v               v               v
   AUTH MODULE     DOCUMENT MODULE   CONSENT MODULE
        |               |               |
        |               v               |
        |        DOCUMENT PROCESSING    |
        |        PDF EXTRACTION/OCR      |
        |               |               |
        |               v               |
        |         AI ANALYSIS ENGINE    |
        |               |               |
        |        +------+-------+       |
        |        |      |       |       |
        |      History Medication Labs |
        |      Reconstruction Review   |
        |        |      |       |       |
        |        +------+-------+       |
        |               |               |
        +---------------+---------------+
                        |
                        v
                  SQLITE DATABASE
                        |
                        v
                 AUDIT LOGGING
```

## 5. User Roles

### Patient
- Register and log in.
- Upload medical documents.
- View medical timeline and AI-generated summary.
- Manage doctor access requests.
- Approve, reject, and revoke access.
- View access history.

### Doctor
- Register and submit verification information.
- Find patients using their unique patient ID.
- Request patient consent.
- View authorized patient records.
- Review AI-generated findings.
- Accept, reject, or request clarification on findings.

Doctor verification in the prototype is provisional. Certificate OCR alone does not establish medical registration authenticity.

## 6. Authentication and Authorization

- One common authentication system for patients and doctors.
- Role-based access control.
- Passwords stored using secure hashing.
- Patient and doctor profiles maintained separately.
- Patient records isolated through backend authorization.
- Knowing a patient ID must never grant access to medical records.

## 7. Consent Management

Normal access flow:

1. Doctor searches for a patient.
2. Doctor sends an access request.
3. Patient receives a notification.
4. Patient approves or rejects the request.
5. Approved access creates a scoped, time-limited grant.
6. Patient can revoke access.
7. Important actions are recorded in audit logs.

Emergency access must require a documented reason, restricted authorization, audit logging, and patient notification when possible. It must never be a silent bypass.

## 8. Document Processing Pipeline

1. Patient uploads PDF, PNG, or JPG files.
2. Backend validates the file.
3. File is stored privately.
4. PyMuPDF extracts text from text-based PDFs.
5. Tesseract performs OCR on supported printed text in scanned documents.
6. Extracted content is classified by document type.
7. Structured information is extracted with source references.
8. Data is stored in the database.
9. The AI analysis pipeline is triggered.

**Handwritten prescriptions:** Automatic handwritten medicine interpretation is excluded from the MVP. The original document is preserved and marked for manual doctor review. The system must never guess medicine names or dosages.

## 9. AI Analysis Engine

The AI engine has four primary modules.

### A. Medical History Reconstruction
- Reconstructs a chronological medical timeline.
- Organizes conditions, procedures, visits, and relevant findings.
- Links information to source documents.

### B. Medication Reconciliation
- Identifies medication names, dosages, and dates when clearly available.
- Detects possible medication discrepancies.
- Highlights conflicting information for doctor review.

### C. Laboratory Analysis
- Organizes laboratory test results.
- Displays available values, units, dates, and reference ranges.
- Highlights missing
