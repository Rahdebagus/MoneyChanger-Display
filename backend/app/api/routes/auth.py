"""Login, logout and the current-user endpoint.

There is no public registration. Accounts are created by an admin or by the
bootstrap script.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.ratelimit import RateLimiter
from app.core.security import create_access_token, hash_password, verify_password
from app.core.timeutils import utcnow
from app.db.session import get_db
from app.models import Branch, User, UserBranch
from app.schemas.auth import (
    BranchSummary,
    LoginRequest,
    LoginResponse,
    PasswordChange,
    UserOut,
)
from app.schemas.common import Message
from app.services import audit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

_settings = get_settings()
_login_limiter = RateLimiter(
    _settings.login_rate_limit_attempts,
    _settings.login_rate_limit_window_seconds,
)


def serialize_user(db: Session, user: User) -> UserOut:
    branches = list(
        db.execute(
            select(Branch)
            .join(UserBranch, UserBranch.branch_id == Branch.id)
            .where(UserBranch.user_id == user.id)
            .order_by(Branch.name)
        ).scalars()
    )
    return UserOut(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
        branches=[BranchSummary.model_validate(b) for b in branches],
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    limiter_key = f"{client_ip}:{payload.username.lower()}"

    if not _login_limiter.check(limiter_key):
        retry = _login_limiter.retry_after(limiter_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak percobaan login. Coba lagi nanti.",
            headers={"Retry-After": str(retry)},
        )

    user = db.execute(
        select(User).where(User.username == payload.username.strip().lower())
    ).scalar_one_or_none()

    # One message for every failure mode. Whether the account exists, is
    # disabled, or the password is wrong must not be distinguishable.
    if user is None or not verify_password(payload.password, user.password_hash):
        if user is not None:
            user.failed_login_count += 1
            db.commit()
        logger.info("Failed login for username=%s from %s", payload.username, client_ip)
        raise HTTPException(status_code=401, detail="Username atau password salah.")

    if not user.is_active:
        logger.info("Login attempt on inactive account id=%s", user.id)
        raise HTTPException(status_code=401, detail="Username atau password salah.")

    token, expires_at = create_access_token(
        user_id=user.id, role=user.role, token_version=user.token_version
    )

    user.last_login_at = utcnow().replace(tzinfo=None)
    user.failed_login_count = 0
    audit.record(
        db,
        action="auth.login",
        actor_user_id=user.id,
        actor_label=user.username,
        target_type="user",
        target_id=user.id,
        details={"ip": client_ip},
    )
    db.commit()
    _login_limiter.reset(limiter_key)

    return LoginResponse(
        access_token=token,
        expires_at=expires_at,
        user=serialize_user(db, user),
    )


@router.post("/logout", response_model=Message)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Logout is client-side for a bearer token.

    The browser drops the token. The server does not keep a blacklist; tokens
    are short lived and token_version gives a hard revoke when it matters
    (password change or deactivation).
    """
    audit.record(
        db,
        action="auth.logout",
        actor_user_id=user.id,
        actor_label=user.username,
        target_type="user",
        target_id=user.id,
    )
    db.commit()
    return Message(message="Logout berhasil.")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return serialize_user(db, user)


@router.post("/change-password", response_model=Message)
def change_password(
    payload: PasswordChange,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Password saat ini salah.")

    user.password_hash = hash_password(payload.new_password)
    # Invalidate every other session that still holds an old token.
    user.token_version += 1
    audit.record(
        db,
        action="auth.password_changed",
        actor_user_id=user.id,
        actor_label=user.username,
        target_type="user",
        target_id=user.id,
    )
    db.commit()
    return Message(message="Password diperbarui. Silakan login ulang di perangkat lain.")
