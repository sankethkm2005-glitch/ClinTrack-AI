# ClinTrace AI
### The Clinical Record That Cannot Be Trusted
**Agentic Clinical Intelligence for Patient Reconstruction, Medical Reconciliation & Safe Decision Support**

> ClinTrace AI reconstructs a patient's medical history from scattered medical documents, identifies medication discrepancies, cross-references laboratory trends, detects diagnostic contradictions, and provides an evidence-linked clinical workspace for authorized doctors.

---

## 1. Clinical Prototype Disclaimer

**Important Notice:** ClinTrace AI is a clinical decision-support prototype. It does **not** independently diagnose diseases, prescribe medication, or autonomously alter treatment plans. Every finding links to its original source document and page number for qualified clinician verification.

---

## 2. Locked Technology Stack

- **Frontend:** HTML5, CSS3, Vanilla JavaScript, Lucide icons (No React, Node.js, Tailwind, Vite, or Bootstrap).
- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic.
- **Database:** SQLite with foreign keys enforced (`PRAGMA foreign_keys=ON`).
- **Document Processing:** PyMuPDF (`fitz`) for PDF text extraction; Tesseract OCR for image/scan processing.
- **AI Layer:** Provider-independent interface with Grok API (`x.ai`) adapter and deterministic offline fallback.

---

## 3. High-Level Architecture

```text
               Patient Browser                     Doctor Browser
                     │                                   │
                     └─────────────────┬─────────────────┘
                                       │
                              HTML5 / CSS3 / Vanilla JS
                                       │
                              FastAPI REST Backend
                                       │
     ┌──────────────────┬──────────────┴─────┬──────────────────┐
     ▼                  ▼                    ▼                  ▼
Auth & Sessions   Consent & Grants     Documents Module   Clinical Engine
(Argon2, Cookies) (Timed & Emergency) (Private Storage)   (Reconciliation)
     │                  │                    │                  │
     └──────────────────┴──────────────┬─────┴──────────────────┘
                                       ▼
                              SQLite Database (12 Tables)
```

---

## 4. Key Capabilities Implemented

1. **Authentication & Identity:**
   - Role separation between patients and doctors.
   - Argon2 password hashing.
   - Secure HTTP-only cookies with HMAC-SHA256 signatures and CSRF protection (`X-CSRF-Token`).
   - Unique patient ID generation (e.g. `CLN-PAT-1001`).
   - Doctor provisional verification tracking.

2. **Private Document Management:**
   - Multi-file upload (PDF, PNG, JPG, JPEG up to 10MB).
   - Private storage outside the public web root (`storage/uploads/`).
   - Categorization (Prescriptions, Lab Reports, Discharge Summaries, Medical Histories, Other).
   - Conservative handwritten prescription detection requiring manual clinician review.
   - Soft-deletion preserving immutable audit history.

3. **Clinical Intelligence & Multi-Document Reconciliation:**
   - **Chronological Timeline:** Synthesized across all documents with source document names and page numbers.
   - **Medication Reconciliation:** Cross-compares dosages and frequencies across records to surface conflicting prescriptions.
   - **Laboratory Analysis:** Organizes lab tests chronologically, flags abnormal values, and notes missing units.
   - **Contradiction Detection:** Surfaces conflicting documented diagnoses (e.g. Type 1 vs Type 2 diabetes).
   - **Missing Information:** Identifies missing medication dosages or absent glycemic lab panels.
   - **Completeness Indicator (0–100%):** Measures documentation breadth only (not patient health or risk).
   - **Analysis Versioning (V1, V2, ...):** Re-runs increment version numbers, mark previous versions `outdated`, and preserve past doctor reviews.

4. **Patient Consent & 3-Panel Doctor Clinical Workspace:**
   - Patient ID lookup without exposing medical records.
   - Scoped, time-limited access grants (24h, 48h, 7d).
   - Immediate patient revocation.
   - Restricted, audited **Emergency Access** requiring mandatory justification.
   - **3-Panel Doctor Workspace:**
     - *Left Panel:* Chronological timeline + original document inspector.
     - *Centre Panel:* Objective AI health summary, completeness score dial, and version badge.
     - *Right Panel:* Discrepancies and doctor review actions (`accept`, `reject`, `clarification`, `resolve`).
   - In-app notifications and immutable-style audit logs.

---

## 5. Quickstart & Local Setup Instructions

### Prerequisites
- Python 3.12 (or `uv`)
- Git

### Step 1: Clone Repository & Enter Directory
```bash
git clone https://github.com/sankethkm2005-glitch/ClinTrack-AI.git
cd ClinTrack-AI
```

### Step 2: Set Up Python Virtual Environment & Install Dependencies
```powershell
# Using uv (fastest):
uv venv backend/.venv --python 3.12
uv pip install --python backend/.venv/Scripts/python.exe -r backend/requirements.txt

# Or using standard python:
python -m venv backend/.venv
.\backend\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

### Step 3: Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```
*(Optional: add your `AI_API_KEY=xai-...` if using live Grok API; otherwise leave blank to use the built-in deterministic offline fallback).*

### Step 4: Apply Database Migrations
```powershell
cd backend
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe -m alembic upgrade head
```

### Step 5: Seed Synthetic Demonstration Data
```powershell
.\.venv\Scripts\python.exe app/utils/seed_demo.py
```

### Step 6: Start the Local Application
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open your browser at:
- **Application Portal:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive OpenAPI Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 6. Synthetic Demo Credentials

| Role | Email | Password | Details |
|---|---|---|---|
| **Patient 1** | `patient.alice@clintrace.demo` | `DemoPatient123!` | Alice M. Walker (`CLN-DEMO-0001`) — Has 3 documents, conflicting Metformin dosages (500mg vs 1000mg), abnormal HbA1c (7.8%), and an active grant to Dr. Chen. |
| **Patient 2** | `patient.bob@clintrace.demo` | `DemoPatient123!` | Bob J. Reynolds (`CLN-DEMO-0002`) — Has a pending consent request from Dr. Morales. |
| **Doctor 1** | `dr.chen@clintrace.demo` | `DemoDoctor123!` | Dr. Sarah Chen, MD (Cardiologist) — Holds active consent for Alice; reviewed finding. |
| **Doctor 2** | `dr.morales@clintrace.demo` | `DemoDoctor123!` | Dr. Marcus Morales, DO (Endocrinologist) — Requested access to Bob. |

---

## 7. Automated Test Suite

Run all automated unit, integration, and end-to-end tests:
```powershell
cd backend
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe -m pytest -v
```
All **35/35 automated tests** pass covering registration, document upload, extraction, clinical intelligence, consent, emergency access, and doctor workspace.
