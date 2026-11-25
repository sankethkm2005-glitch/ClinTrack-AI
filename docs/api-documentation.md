# ClinTrace AI — API Documentation

## 1. Overview

The ClinTrace AI backend uses FastAPI and exposes REST API endpoints.

Base URL during local development:

`http://127.0.0.1:8000`

API prefix:

`/api`

All protected endpoints require an authenticated user. The backend must enforce role-based authorization and patient-level access control.

### GET `/api/health`

Health-check endpoint verifying backend availability and SQLite database connectivity.

## 2. Authentication APIs

### GET `/api/auth/me`

Returns the currently authenticated user's session summary and role.

### POST `/api/auth/register`

Registers a patient or doctor.

Request fields:
- email
- password
- role
- profile information

Returns account creation status.

### POST `/api/auth/login`

Authenticates a user.

Request fields:
- email
- password

Returns authentication status and establishes a secure session.

### POST `/api/auth/logout`

Ends the current authenticated session.

## 3. Patient APIs

### GET `/api/patients/me`

Returns the authenticated patient's profile.

### GET `/api/patients/search/{patient_id}`

Allows an authorized doctor to find a patient by unique patient ID.

Finding a patient does not automatically grant access to medical records.

## 4. Doctor APIs

### GET `/api/doctors/me`

Returns the authenticated doctor's profile.

### GET `/api/doctors/patients`

Returns the list of patients for whom the authenticated doctor holds an active, non-expired consent grant.

### POST `/api/doctors/verification`

Submits doctor verification information and supporting certificate.

Verification must not be considered successful merely because OCR extracted matching text.

## 5. Document APIs

### POST `/api/documents/upload`

Uploads one or more medical documents.

Supported formats:
- PDF
- PNG
- JPG
- JPEG

The backend validates and stores files privately.

### GET `/api/documents`

Returns documents belonging to the authenticated patient or documents accessible through an active authorization grant.

### GET `/api/documents/{document_id}/view`

Provides authorized access to a document.

### PATCH `/api/documents/{document_id}`

Allows manual category correction for an authorized patient document.

### POST `/api/documents/{document_id}/retry`

Retries text extraction/processing for a failed document.

### DELETE `/api/documents/{document_id}`

Requests deletion of a patient's document.

Deletion must invalidate affected analysis and trigger reconstruction from remaining documents. Audit history must be retained.

## 6. AI Analysis APIs

### POST `/api/analysis/patients/{patient_id}/run`

Starts a new AI analysis for an authorized patient record.

### GET `/api/analysis/patients/{patient_id}/latest`

Returns the latest analysis version.

### GET `/api/analysis/patients/{patient_id}/history`

Returns previous analysis versions.

Previous versions must remain available and must not be silently overwritten.

## 7. Consent APIs

### GET `/api/consent/requests`

Lists pending and historical access requests for the authenticated patient or doctor.

### POST `/api/consent/requests`

Allows a doctor to request patient record access.

### PATCH `/api/consent/requests/{request_id}`

Allows the patient to approve or reject a request.

### GET `/api/consent/grants`

Lists active and historical access grants for the authenticated patient or doctor.

### DELETE `/api/consent/grants/{grant_id}`

Allows the patient to revoke an access grant.

### POST `/api/consent/emergency-access`

Initiates a separate, restricted, reason-required, audited emergency access workflow and notifies the patient.

Access grants must be scoped and time-limited.

Emergency access must use a separate restricted and audited authorization flow.

## 8. Doctor Review APIs

### PATCH `/api/reviews/findings/{finding_id}`

Allows an authorized doctor to review an AI finding.

Supported actions:
- accept
- reject
- flag for clarification
- resolve with explanation

Every review must record the doctor, timestamp, action, and explanation where applicable.

## 9. Audit & Notification APIs

### GET `/api/audit/history`

Returns access and security events available to the authenticated user according to authorization rules.

### GET `/api/notifications`

Returns notifications for the authenticated user.

### PATCH `/api/notifications/{notification_id}/read`

Marks a notification as read.

## 10. API Security Rules

- Require authentication for protected endpoints.
- Enforce role-based authorization in the backend.
- Verify patient ownership or active access grants.
- Never trust patient IDs supplied by the frontend without authorization checks.
- Validate request bodies using Pydantic.
- Validate uploaded file type and size.
- Use secure session cookies and CSRF protection where applicable.
- Never expose private storage paths.
- Log sensitive access and consent actions.
- Return appropriate HTTP status codes.
- Do not expose passwords, API keys, or sensitive internal errors.

## 11. Important Implementation Note

These endpoints define the planned API contract. They are not implemented yet.

The implementation may refine request and response schemas while preserving the architecture and security requirements.

FastAPI's interactive API documentation will be available at:

`http://127.0.0.1:8000/docs`
