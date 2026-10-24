"""Admin-only user and branch management."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import load_branch, require_admin
from app.api.routes.auth import serialize_user
from app.core.security import hash_password
from app.db.session import get_db
from app.models import Branch, Display, User, UserBranch
from app.schemas.auth import (
    BranchCreate,
    BranchSummary,
    BranchUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.schemas.common import Message
from app.services import audit

router = APIRouter(tags=["admin"])


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------
@router.get("/users", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    users = list(db.execute(select(User).order_by(User.username)).scalars())
    return [serialize_user(db, u) for u in users]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    exists = db.execute(
        select(User.id).where(User.username == payload.username)
    ).scalar()
    if exists:
        raise HTTPException(status_code=409, detail="Username sudah dipakai.")

    user = User(
        username=payload.username,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.flush()

    _set_branches(db, user, payload.branch_ids)

    audit.record(
        db,
        action="user.created",
        actor_user_id=admin.id,
        actor_label=admin.username,
        target_type="user",
        target_id=user.id,
        details={"role": user.role, "branch_ids": payload.branch_ids},
    )
    db.commit()
    return serialize_user(db, user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User tidak ditemukan.")

    changes = {}

    if payload.full_name is not None:
        user.full_name = payload.full_name
        changes["full_name"] = payload.full_name

    if payload.role is not None and payload.role != user.role:
        if user.id == admin.id:
            raise HTTPException(status_code=400, detail="Tidak bisa mengubah role akun sendiri.")
        user.role = payload.role
        user.token_version += 1
        changes["role"] = payload.role

    if payload.is_active is not None and payload.is_active != user.is_active:
        if user.id == admin.id and not payload.is_active:
            raise HTTPException(status_code=400, detail="Tidak bisa menonaktifkan akun sendiri.")
        if not payload.is_active and _is_last_active_admin(db, user):
            raise HTTPException(
                status_code=400, detail="Minimal satu admin aktif harus tetap ada."
            )
        user.is_active = payload.is_active
        # Deactivating must log the account out everywhere, immediately.
        user.token_version += 1
        changes["is_active"] = payload.is_active

    if payload.password:
        user.password_hash = hash_password(payload.password)
        user.token_version += 1
        changes["password"] = "[redacted]"

    if payload.branch_ids is not None:
        _set_branches(db, user, payload.branch_ids)
        changes["branch_ids"] = payload.branch_ids

    audit.record(
        db,
        action="user.updated",
        actor_user_id=admin.id,
        actor_label=admin.username,
        target_type="user",
        target_id=user.id,
        details=changes,
    )
    db.commit()
    return serialize_user(db, user)


def _is_last_active_admin(db: Session, user: User) -> bool:
    if user.role != "admin":
        return False
    count = db.execute(
        select(User.id).where(User.role == "admin", User.is_active.is_(True))
    ).scalars()
    active = [uid for uid in count]
    return active == [user.id]


def _set_branches(db: Session, user: User, branch_ids: List[int]) -> None:
    db.execute(delete(UserBranch).where(UserBranch.user_id == user.id))
    for branch_id in dict.fromkeys(branch_ids or []):
        if db.get(Branch, branch_id) is None:
            raise HTTPException(status_code=400, detail=f"Cabang {branch_id} tidak ditemukan.")
        db.add(UserBranch(user_id=user.id, branch_id=branch_id))
    db.flush()


# --------------------------------------------------------------------------
# Branches
# --------------------------------------------------------------------------
@router.get("/branches", response_model=List[BranchSummary])
def list_branches(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    branches = list(db.execute(select(Branch).order_by(Branch.name)).scalars())
    return [BranchSummary.model_validate(b) for b in branches]


@router.post("/branches", response_model=BranchSummary, status_code=201)
def create_branch(
    payload: BranchCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    exists = db.execute(select(Branch.id).where(Branch.name == payload.name)).scalar()
    if exists:
        raise HTTPException(status_code=409, detail="Nama cabang sudah dipakai.")

    branch = Branch(name=payload.name, timezone=payload.timezone, is_active=True)
    db.add(branch)
    db.flush()

    audit.record(
        db,
        action="branch.created",
        actor_user_id=admin.id,
        actor_label=admin.username,
        target_type="branch",
        target_id=branch.id,
        branch_id=branch.id,
        details={"name": branch.name, "timezone": branch.timezone},
    )
    db.commit()
    return BranchSummary.model_validate(branch)


@router.patch("/branches/{branch_id}", response_model=BranchSummary)
def update_branch(
    branch_id: int,
    payload: BranchUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    branch = load_branch(db, branch_id)
    changes = {}

    if payload.name is not None:
        clash = db.execute(
            select(Branch.id).where(Branch.name == payload.name, Branch.id != branch.id)
        ).scalar()
        if clash:
            raise HTTPException(status_code=409, detail="Nama cabang sudah dipakai.")
        branch.name = payload.name
        changes["name"] = payload.name

    if payload.timezone is not None:
        branch.timezone = payload.timezone
        changes["timezone"] = payload.timezone

    if payload.is_active is not None:
        branch.is_active = payload.is_active
        changes["is_active"] = payload.is_active

    audit.record(
        db,
        action="branch.updated",
        actor_user_id=admin.id,
        actor_label=admin.username,
        target_type="branch",
        target_id=branch.id,
        branch_id=branch.id,
        details=changes,
    )
    db.commit()
    return BranchSummary.model_validate(branch)


@router.delete("/branches/{branch_id}", response_model=Message)
def delete_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    branch = load_branch(db, branch_id)

    attached = db.execute(
        select(Display.id).where(Display.branch_id == branch.id).limit(1)
    ).scalar()
    if attached:
        raise HTTPException(
            status_code=409,
            detail="Cabang masih memiliki display. Pindahkan display terlebih dahulu.",
        )

    audit.record(
        db,
        action="branch.deleted",
        actor_user_id=admin.id,
        actor_label=admin.username,
        target_type="branch",
        target_id=branch.id,
        details={"name": branch.name},
    )
    db.delete(branch)
    db.commit()
    return Message(message="Cabang dihapus.")
