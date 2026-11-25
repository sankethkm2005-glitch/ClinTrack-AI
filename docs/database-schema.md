# ClinTrace AI — Database Schema

## 1. Database Overview

ClinTrace AI uses SQLite as its database and SQLAlchemy as its ORM.

The database stores user accounts, patient and doctor profiles, medical documents, extracted information, AI analysis versions, clinical findings, doctor reviews, consent records, notifications, and audit logs.

## 2. Database Tables

### 2.1 users

Stores authentication information for all users.

| Column | Type | Description |
|---|---|---|
| id | Integer | Primary key |
| email | String | Unique email |
| password_hash | String | Secure password hash |
| role | String | patient or doctor |
| is_active | Boolean | Account status |
| created_at | DateTime | Registration time |

### 2.2 patient_profiles

Stores patient-specific information.

| Column | Type | Description |
|---|---|---|
| id | Integer | Primary key |
| user_id | Integer | Foreign key to users |
| patient_id | String | Unique patient identifier |
| full_name | String | Patient name |
| date_of_birth | Date | Date of birth |
| gender | String | Optional gender |
| created_at | DateTime | Creation time |

### 2.3 doctor_profiles

Stores doctor information and verification status.

| Column | Type | Description |
|---|---|---|
| id | Integer | Primary key |
| user_id | Integer | Foreign key to users |
| full_name | String | Doctor name |
| registration_number | String | Medical registration number |
| medical_council | String | Council information |
| specialization | String | Medical specialization |
| certificate_path | String | Private certificate storage path |
| verification_status | String | pending, provisional, verified, rejected |

Certificate OCR is not proof of genuine registration.

### 2.4 documents

Stores uploaded medical document metadata.

| Column | Type | Description |
|---|---|---|
| id | Integer | Primary key |
| patient_id | Integer | Patient profile foreign key |
| filename | String | Original filename |
| storage_path | String | Private storage path |
| document_type | String | Prescription, lab report, discharge summary, other |
| mime_type | String | File content type |
| processing_status | String | uploaded, processing, processed, failed |
| uploaded_at | DateTime | Upload time |

### 2.5 extracted_data

Stores information extracted from uploaded documents.

| Column | Type | Description |
|---|---|---|
| id | Integer | Primary key |
| document_id | Integer | Document foreign key |
| extracted_text | Text | Extracted content |
| structured_data | JSON/Text | Validated structured information |
| extraction_method | String | PDF extraction or OCR |
| created_at | DateTime | Extraction time |

### 2.6 ai_analyses

Stores individual AI analysis versions.

| Column | Type | Description |
|---|---|---|
| id | Integer | Primary key |
| patient_id | Integer | Patient profile foreign key |
| version_number | Integer | Analysis version |
| status | String | current, outdated, failed |
| summary | Text | Reconstructed medical summary |
| ai_provider | String | Provider used |
| created_at | DateTime | Analysis time |

### 2.7 ai_findings

Stores AI-generated clinical findings.

| Column | Type | Description |
|---|---|---|
| id | Integer | Primary key |
| analysis_id | Integer | Analysis foreign key |
| finding_type | String | medication, contradiction, lab, missing information |
| priority | String | critical, needs_review, informational |
| description | Text | Finding description |
| evidence | JSON/Text | Source document and page references |
| review_status | String | pending, reviewed |
| created_at | DateTime | Creation time |

Priority indicates review priority, not patient risk or diagnosis.

### 2.8 finding_reviews

Stores doctor review actions separately from AI findings.

| Column | Type | Description |
|---|---|---|
| id | Integer | Primary key |
| finding_id | Integer | Finding foreign key |
| doctor_id | Integer | Doctor user foreign key |
| action | String | accept, reject, clarification, resolve |
| explanation | Text | Doctor explanation |
| created_at | DateTime | Review time |

### 2.9 access_requests

Stores requests made by doctors to access patient records.

| Column | Type | Description |
|---|---|---|
| id | Integer | Primary key |
| doctor_id | Integer | Doctor user foreign key |
| patient_id | Integer | Patient profile foreign key |
| reason | Text | Access reason |
| status | String | pending, approved, rejected |
| created_at | DateTime | Request time |

### 2.10 access_grants

Stores approved, scoped, time-limited access.

| Column | Type | Description |
|---|---|---|
| id | Integer | Primary key |
| doctor_id | Integer | Doctor user foreign key |
| patient_id | Integer | Patient profile foreign key |
| request_id | Integer | Related access request |
| scope | JSON/Text | Authorized access scope |
| expires_at | DateTime | Expiration time |
| revoked_at | DateTime | Revocation time |
| created_at | DateTime | Grant time |

### 2.11 audit_logs

Stores important security and access events.

| Column | Type | Description |
|---|---|---|
| id | Integer | Primary key |
| user_id | Integer | Actor user ID |
| action | String | Event type |
| resource_type | String | Affected resource |
| resource_id | String | Resource identifier |
| details | JSON/Text | Additional event details |
| created_at | DateTime | Event time |

### 2.12 notifications

Stores notifications for patients and doctors.

| Column | Type | Description |
|---|---|---|
| id | Integer | Primary key |
| user_id | Integer | Recipient user ID |
| title | String | Notification title |
| message | Text | Notification message |
| is_read | Boolean | Read status |
| created_at | DateTime | Creation time |

## 3. Important Relationships

- One user has one patient profile or one doctor profile, depending on role.
- One patient can upload multiple documents.
- One document can have extracted data.
- One patient can have multiple AI analysis versions.
- One analysis can contain multiple AI findings.
- One finding can have multiple doctor review records.
- One doctor can request access to multiple patients.
- One patient can approve multiple access grants.
- Important actions generate audit log entries.

## 4. Database Rules

1. Use foreign keys and appropriate relationships.
2. Enforce unique email addresses and patient IDs.
3. Use database transactions for related operations.
4. Store passwords only as secure hashes.
5. Do not store uploaded documents as public URLs.
6. Enforce patient-level access in backend queries.
7. Preserve previous analysis versions.
8. Never overwrite doctor review history.
9. Store timestamps consistently.
10. Use Alembic for future schema migrations.

## 5. Implementation Notes

- Database: SQLite.
- ORM: SQLAlchemy.
- Validation: Pydantic.
- Migrations: Alembic.
- Use JSON columns or serialized JSON text for structured evidence and extracted information where appropriate.
- Add indexes to frequently queried foreign keys and unique identifiers.
- Use explicit relationships and cascade behavior; do not accidentally delete audit history or previous reviews.
- Keep AI-generated data separate from doctor-reviewed data.
