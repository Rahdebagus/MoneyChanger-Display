"""Admin and staff view of displays: approve pairing, rename, refresh, revoke."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    accessible_branch_ids,
    ensure_branch_access,
    ensure_display_access,
    get_current_user,
    require_admin,
)
from app.api.serializers import serialize_display, serialize_displays
from app.db.session import get_db
from app.models import CommandType, Display, DisplayCommand, User
from app.schemas.common import Message
from app.schemas.displays import DisplayOut, DisplayUpdate, PairingApproveRequest
from app.services import audit, events, pairing

logger = logging.getLogger(__name__)
router = APIRouter(tags=["displays"])


def _load_display(db: Session, display_id: int, user: User) -> Display:
    display = db.get(Display, display_id)
    if display is None:
        raise HTTPException(status_code=404, detail="Display tidak ditemukan.")
    ensure_display_access(db, user, display)
    return display


@router.get("/displays", response_model=List[DisplayOut])
def list_displays(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    branch_id: Optional[int] = Query(None),
):
    stmt = select(Display).order_by(Display.name)

    allowed = accessible_branch_ids(db, user)
    if allowed is not None:
        if not allowed:
            return []
        stmt = stmt.where(Display.branch_id.in_(list(allowed)))

    if branch_id is not None:
        ensure_branch_access(db, user, branch_id)
        stmt = stmt.where(Display.branch_id == branch_id)

    rows = list(db.execute(stmt).scalars())
    return serialize_displays(db, rows)


@router.get("/displays/{display_id}", response_model=DisplayOut)
def get_display(
    display_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    display = _load_display(db, display_id, user)
    return serialize_display(db, display)


@router.post("/displays/pair", response_model=DisplayOut, status_code=201)
def approve_pairing(
    payload: PairingApproveRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin types the code shown on the TV and names the display.

    No credential is returned here. The TV claims its own credential on its
    next poll, so an admin laptop never carries a device secret.
    """
    if payload.branch_id is not None:
        ensure_branch_access(db, admin, payload.branch_id)

    code = payload.code.strip().upper()
    try:
        display = pairing.approve(
            db,
            code=code,
            name=payload.name,
            branch_id=payload.branch_id,
            approved_by=admin.id,
        )
    except pairing.PairingError as exc:
        pairing.register_failed_attempt(db, code)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc))

    audit.record(
        db,
        action="display.pairing_approved",
        actor_user_id=admin.id,
        actor_label=admin.username,
        target_type="display",
        target_id=display.id,
        branch_id=display.branch_id,
        details={"name": display.name},
    )
    db.commit()
    return serialize_display(db, display)


@router.patch("/displays/{display_id}", response_model=DisplayOut)
def update_display(
    display_id: int,
    payload: DisplayUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    display = _load_display(db, display_id, admin)
    changes = {}

    if payload.name is not None:
        display.name = payload.name
        changes["name"] = payload.name

    if payload.branch_id is not None:
        ensure_branch_access(db, admin, payload.branch_id)
        display.branch_id = payload.branch_id
        changes["branch_id"] = payload.branch_id

    if payload.is_active is not None:
        display.is_active = payload.is_active
        changes["is_active"] = payload.is_active

    audit.record(
        db,
        action="display.updated",
        actor_user_id=admin.id,
        actor_label=admin.username,
        target_type="display",
        target_id=display.id,
        branch_id=display.branch_id,
        details=changes,
    )
    db.commit()
    return serialize_display(db, display)


@router.post("/displays/{display_id}/refresh", response_model=Message)
def refresh_display(
    display_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Queue a one-shot refresh.

    The command carries an id and is only cleared by an acknowledgement, so a
    player cannot read it twice and spin in a reload loop. This reloads the
    browser page; it does not power on a TV or restart its operating system.
    """
    display = _load_display(db, display_id, admin)

    existing = db.execute(
        select(DisplayCommand.id).where(
            DisplayCommand.display_id == display.id,
            DisplayCommand.acknowledged_at.is_(None),
        )
    ).scalar()
    if existing:
        return Message(message="Perintah refresh sudah menunggu di antrean.")

    command = DisplayCommand(
        display_id=display.id,
        command=CommandType.REFRESH.value,
        issued_by=admin.id,
    )
    db.add(command)
    db.flush()

    events.emit(
        db,
        events.TOPIC_COMMAND,
        display_id=display.id,
        payload={"command_id": command.id, "command": command.command},
    )
    audit.record(
        db,
        action="display.refresh_requested",
        actor_user_id=admin.id,
        actor_label=admin.username,
        target_type="display",
        target_id=display.id,
        branch_id=display.branch_id,
        details={"command_id": command.id},
    )
    db.commit()
    return Message(message="Perintah refresh dikirim.")


@router.post("/displays/{display_id}/revoke", response_model=DisplayOut)
def revoke_display(
    display_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Revoke a device credential.

    Effective the moment the device next contacts the server. A TV that is
    offline right now keeps showing its last media until it reconnects - the
    server cannot reach a disconnected device, and no API can pretend it can.
    """
    display = _load_display(db, display_id, admin)
    pairing.revoke(db, display)

    events.emit(db, events.TOPIC_REVOKED, display_id=display.id, payload={})
    audit.record(
        db,
        action="display.revoked",
        actor_user_id=admin.id,
        actor_label=admin.username,
        target_type="display",
        target_id=display.id,
        branch_id=display.branch_id,
    )
    db.commit()
    return serialize_display(db, display)


@router.delete("/displays/{display_id}", response_model=Message)
def delete_display(
    display_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    display = _load_display(db, display_id, admin)

    # Break the self-reference first so the publication_targets rows can go.
    display.desired_target_id = None
    db.flush()

    audit.record(
        db,
        action="display.deleted",
        actor_user_id=admin.id,
        actor_label=admin.username,
        target_type="display",
        target_id=display.id,
        branch_id=display.branch_id,
        details={"name": display.name},
    )
    db.delete(display)
    db.commit()
    return Message(message="Display dihapus.")
