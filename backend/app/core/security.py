"""Password hashing, JWT issuing, and opaque device-token helpers.

Two different credential styles are used on purpose:

* **Humans (admin/staff)** get a signed JWT. It carries a ``tv`` (token
  version) claim copied from the user row, so deactivating a user or changing
  their password revokes every outstanding token immediately.
* **Devices (TVs)** get an opaque random secret. Only its hash is stored, and
  revoking the row kills the credential on the next request. A device secret
  is never a JWT, so it can never be mistaken for a user token.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"

AUDIENCE_USER = "pam:user"


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
def hash_password(password: str) -> str:
    settings = get_settings()
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    """Constant-ish time check that never raises on malformed input.

    When *password_hash* is missing we still run a bcrypt comparison against a
    dummy hash so a non-existent user costs the same as an existing one.
    """
    candidate = password.encode("utf-8")
    if not password_hash:
        bcrypt.checkpw(candidate, _DUMMY_HASH)
        return False
    try:
        return bcrypt.checkpw(candidate, password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# Pre-computed so the dummy path does not pay for gensalt on every call.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt(rounds=12))


# --------------------------------------------------------------------------
# User JWTs
# --------------------------------------------------------------------------
def create_access_token(
    *,
    user_id: int,
    role: str,
    token_version: int,
    expires_minutes: Optional[int] = None,
) -> tuple[str, datetime]:
    settings = get_settings()
    ttl = expires_minutes if expires_minutes is not None else settings.access_token_ttl_minutes
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=ttl)

    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "tv": token_version,
        "aud": AUDIENCE_USER,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": secrets.token_urlsafe(8),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
    return token, expires_at


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            audience=AUDIENCE_USER,
        )
    except jwt.PyJWTError:
        return None


# --------------------------------------------------------------------------
# Opaque secrets (device credentials, pairing codes)
# --------------------------------------------------------------------------
def generate_device_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_secret(secret: str) -> str:
    """SHA-256 of a high-entropy secret.

    bcrypt is deliberately *not* used here: these secrets are 256-bit random
    values, not user-chosen passwords, so there is nothing to brute-force and
    a device heartbeat must stay cheap. The hash still means a database leak
    does not hand over usable credentials.
    """
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_secret(secret: str, secret_hash: Optional[str]) -> bool:
    if not secret_hash:
        return False
    return hmac.compare_digest(hash_secret(secret), secret_hash)


def generate_pairing_code(length: int = 6) -> str:
    """Human-readable pairing code shown on a TV.

    The alphabet drops characters that are easy to misread across a room
    (0/O, 1/I, 5/S, 8/B) because somebody has to type this off a screen.
    """
    alphabet = "ACDEFGHJKLMNPQRTUVWXY2346789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def checksum_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
