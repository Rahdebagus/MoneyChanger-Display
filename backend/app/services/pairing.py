"""Device pairing.

The flow deliberately keeps the TV from ever holding an admin credential:

1. The TV asks for a pairing code and gets back a short code plus a private
   device-session secret that only it knows.
2. An admin types the code into the dashboard and picks a name and branch.
   This creates the display row but hands nothing back to the TV.
3. The TV, polling with its device-session secret, claims the credential
   exactly once. The code is consumed in the same transaction.

A code is single use, expires, and is rate limited per attempt. Only hashes
are stored, so a database dump contains no usable code or credential.
"""

from datetime import timedelta
from typing import Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    generate_device_secret,
    generate_pairing_code,
    hash_secret,
)
from app.core.timeutils import utcnow
from app.models import Display, PairingCode

MAX_CODE_ATTEMPTS = 10


class PairingError(ValueError):
    """Message is safe to show a user."""


def create_code(db: Session) -> Tuple[str, str, int]:
    """Mint a pairing code. Returns (code, device_session, ttl_seconds)."""
    settings = get_settings()

    for _ in range(10):
        code = generate_pairing_code()
        code_hash = hash_secret(code)
        exists = db.execute(
            select(PairingCode.id).where(
                PairingCode.code_hash == code_hash,
                PairingCode.consumed_at.is_(None),
            )
        ).scalar()
        if not exists:
            break
    else:
        raise PairingError("Tidak dapat membuat kode pairing. Coba lagi.")

    device_session = generate_device_secret()
    ttl = settings.pairing_code_ttl_seconds

    db.add(
        PairingCode(
            code_hash=code_hash,
            device_session_hash=hash_secret(device_session),
            expires_at=(utcnow() + timedelta(seconds=ttl)).replace(tzinfo=None),
        )
    )
    db.flush()
    return code, device_session, ttl


def _lookup_active(db: Session, code: str) -> Optional[PairingCode]:
    now = utcnow().replace(tzinfo=None)
    return db.execute(
        select(PairingCode).where(
            PairingCode.code_hash == hash_secret(code),
            PairingCode.consumed_at.is_(None),
            PairingCode.expires_at > now,
        )
    ).scalar_one_or_none()


def approve(
    db: Session,
    *,
    code: str,
    name: str,
    branch_id: Optional[int],
    approved_by: Optional[int],
) -> Display:
    """Admin approves a code and creates the display row.

    The credential itself is not minted here - the TV claims it next - so an
    admin approving on their laptop never transports a device secret.
    """
    entry = _lookup_active(db, code)
    if entry is None:
        # Deliberately one message for expired, consumed, wrong and unknown:
        # a typo should not reveal whether a code exists.
        raise PairingError("Kode pairing tidak valid atau sudah kedaluwarsa.")

    if entry.attempts >= MAX_CODE_ATTEMPTS:
        raise PairingError("Kode pairing tidak valid atau sudah kedaluwarsa.")

    if entry.approved_display_id is not None:
        raise PairingError("Kode pairing sudah dipakai.")

    display = Display(
        name=name.strip()[:128] or "Display",
        branch_id=branch_id,
        is_active=True,
    )
    db.add(display)
    db.flush()

    now = utcnow().replace(tzinfo=None)
    entry.approved_display_id = display.id
    entry.approved_by = approved_by
    entry.approved_at = now
    db.flush()
    return display


def register_failed_attempt(db: Session, code: str) -> None:
    """Count a bad guess against the code so brute force runs out of room."""
    db.execute(
        update(PairingCode)
        .where(PairingCode.code_hash == hash_secret(code))
        .values(attempts=PairingCode.attempts + 1)
    )


def claim(db: Session, device_session: str) -> Tuple[Display, str]:
    """TV exchanges its device session for a real device credential.

    The code is consumed inside this transaction, so a replay of the same
    claim finds nothing to consume and fails.
    """
    now = utcnow().replace(tzinfo=None)
    session_hash = hash_secret(device_session)

    entry = db.execute(
        select(PairingCode).where(
            PairingCode.device_session_hash == session_hash,
            PairingCode.consumed_at.is_(None),
            PairingCode.approved_display_id.is_not(None),
            PairingCode.expires_at > now,
        )
    ).scalar_one_or_none()

    if entry is None:
        raise PairingError("Pairing belum disetujui atau sudah kedaluwarsa.")

    # Guarded consume: only the first caller gets rowcount 1.
    consumed = db.execute(
        update(PairingCode)
        .where(PairingCode.id == entry.id, PairingCode.consumed_at.is_(None))
        .values(consumed_at=now, claimed_at=now)
    )
    if consumed.rowcount != 1:
        raise PairingError("Pairing sudah dipakai.")

    display = db.get(Display, entry.approved_display_id)
    if display is None:
        raise PairingError("Display tidak ditemukan.")

    secret = generate_device_secret()
    display.credential_hash = hash_secret(secret)
    display.credential_issued_at = now
    display.is_active = True
    display.revoked_at = None
    db.flush()

    return display, secret


def pairing_state(db: Session, device_session: str) -> str:
    """What a waiting TV should be told: pending, approved, or expired."""
    now = utcnow().replace(tzinfo=None)
    entry = db.execute(
        select(PairingCode).where(PairingCode.device_session_hash == hash_secret(device_session))
    ).scalar_one_or_none()

    if entry is None:
        return "expired"
    if entry.consumed_at is not None:
        return "claimed"
    if entry.expires_at <= now:
        return "expired"
    if entry.approved_display_id is not None:
        return "approved"
    return "pending"


def authenticate_device(db: Session, secret: str) -> Optional[Display]:
    """Resolve a device credential to a live display, or None."""
    if not secret:
        return None
    display = db.execute(
        select(Display).where(Display.credential_hash == hash_secret(secret))
    ).scalar_one_or_none()

    if display is None:
        return None
    if not display.is_active or display.revoked_at is not None:
        return None
    return display


def revoke(db: Session, display: Display) -> None:
    """Kill a device credential.

    This stops the device the moment it next reaches the server. A TV that is
    currently offline keeps showing its last media until it reconnects - the
    server cannot reach into a disconnected device.
    """
    display.credential_hash = None
    display.revoked_at = utcnow().replace(tzinfo=None)
    display.is_active = False
    db.flush()


def purge_expired_codes(db: Session) -> int:
    """Expired, unconsumed codes are noise; drop them."""
    from sqlalchemy import delete

    cutoff = (utcnow() - timedelta(days=1)).replace(tzinfo=None)
    result = db.execute(
        delete(PairingCode).where(
            PairingCode.expires_at < cutoff,
            PairingCode.consumed_at.is_(None),
        )
    )
    return int(result.rowcount or 0)
