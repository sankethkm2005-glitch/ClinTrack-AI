"""Security utilities for password hashing (Argon2), tokens, and session management."""

import secrets
from datetime import datetime, timedelta, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
import hmac
import hashlib
import json
import base64

from app.config import settings

ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash password using Argon2."""
    return ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against Argon2 hash."""
    try:
        return ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError):
        return False


def generate_patient_id(seq_number: int) -> str:
    """Generate human-readable unique patient ID e.g. CLN-PAT-1001."""
    return f"CLN-PAT-{seq_number:04d}"


def generate_csrf_token() -> str:
    """Generate a cryptographically secure random token for CSRF protection."""
    return secrets.token_urlsafe(32)


def create_session_token(user_id: int, role: str, csrf_token: str) -> str:
    """Create a signed session token containing user_id, role, csrf_token, and expiry."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.SESSION_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "role": role,
        "csrf": csrf_token,
        "exp": int(expire.timestamp()),
    }
    raw = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    b64_payload = base64.urlsafe_b64encode(raw).decode('utf-8')
    signature = hmac.new(settings.SECRET_KEY.encode('utf-8'), b64_payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{b64_payload}.{signature}"


def verify_session_token(token: str) -> dict | None:
    """Verify session token signature and expiration, returning decoded payload or None."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        b64_payload, signature = parts
        expected_sig = hmac.new(settings.SECRET_KEY.encode('utf-8'), b64_payload.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        raw = base64.urlsafe_b64decode(b64_payload.encode('utf-8'))
        payload = json.loads(raw.decode('utf-8'))
        
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if payload.get("exp", 0) < now_ts:
            return None
        return payload
    except Exception:
        return None
