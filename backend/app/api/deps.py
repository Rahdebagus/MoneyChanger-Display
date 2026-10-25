"""Authentication and authorization dependencies.

Every protected route resolves its principal here. Authorization is enforced
on the server for each request - hiding a button in the UI is not access
control, and these dependencies are what actually stop a staff account from
touching another branch or a TV from reaching an admin endpoint.

Two principal types exist and they never overlap:

* ``User``   - admin or staff, authenticated with a signed JWT.
* ``Display`` - a paired TV, authenticated with an opaque device secret.

A device token cannot satisfy a user dependency and vice versa, because they
are validated by different code paths against different columns.
"""

from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.core.timeutils import utcnow
from app.db.session import get_db
from app.models import Branch, Display, User, UserRole
from app.services import pairing
from app.services.access import (
    BranchAccessDenied,
    accessible_branch_ids,
    user_branch_ids,  # Re-export for existing API callers.
)
from app.services.access import ensure_branch_access as _ensure_branch_access


def _unauthorized(detail: str = "Tidak terautentikasi.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(detail: str = "Akses ditolak.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def bearer_token(authorization: Optional[str] = Header(None)) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------
def get_current_user(
    token: Optional[str] = Depends(bearer_token),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise _unauthorized()

    payload = decode_access_token(token)
    if not payload:
        raise _unauthorized("Sesi tidak valid atau sudah berakhir.")

    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise _unauthorized()

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("Akun tidak aktif.")

    # token_version invalidates every token issued before a password change
    # or a deactivation, without needing a blacklist.
    if int(payload.get("tv", -1)) != int(user.token_version):
        raise _unauthorized("Sesi sudah tidak berlaku. Silakan login ulang.")

    return user


def get_optional_user(
    token: Optional[str] = Depends(bearer_token),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not token:
        return None
    try:
        return get_current_user(token=token, db=db)
    except HTTPException:
        return None


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise _forbidden("Hanya admin yang boleh melakukan aksi ini.")
    return user


def ensure_branch_access(db: Session, user: User, branch_id: Optional[int]) -> None:
    try:
        _ensure_branch_access(db, user, branch_id)
    except BranchAccessDenied as exc:
        raise _forbidden(str(exc)) from exc


def ensure_display_access(db: Session, user: User, display: Display) -> None:
    allowed = accessible_branch_ids(db, user)
    if allowed is None:
        return
    if display.branch_id is None or display.branch_id not in allowed:
        raise _forbidden("Display ini bukan bagian dari penugasan Anda.")


def load_branch(db: Session, branch_id: int) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Cabang tidak ditemukan.")
    return branch


# --------------------------------------------------------------------------
# Devices
# --------------------------------------------------------------------------
def get_current_device(
    request: Request,
    token: Optional[str] = Depends(bearer_token),
    db: Session = Depends(get_db),
) -> Display:
    if not token:
        raise _unauthorized("Perangkat belum terdaftar.")

    display = pairing.authenticate_device(db, token)
    if display is None:
        raise _unauthorized("Kredensial perangkat tidak berlaku. Lakukan pairing ulang.")

    agent = request.headers.get("user-agent")
    now = utcnow().replace(tzinfo=None)
    # A download and its acknowledgements used to each write the same device
    # row. One liveness write per 15 seconds is sufficient for a 90s timeout.
    if display.last_seen_at is None or (now - display.last_seen_at).total_seconds() >= 15:
        if agent:
            display.user_agent = agent[:255]
        display.last_seen_at = now
        db.commit()
    return display


def display_connection_state(display: Display) -> str:
    """online / offline / never_seen, from the heartbeat clock alone."""
    settings = get_settings()
    if display.last_seen_at is None:
        return "never_seen"
    age = (utcnow().replace(tzinfo=None) - display.last_seen_at).total_seconds()
    return "online" if age <= settings.display_offline_after_seconds else "offline"
