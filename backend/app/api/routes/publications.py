"""Publishing, scheduling, rollback and the activity log."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import (
    accessible_branch_ids,
    ensure_branch_access,
    ensure_display_access,
    get_current_user,
    require_admin,
)
from app.api.serializers import serialize_publication
from app.db.session import get_db
from app.models import (
    AuditLog,
    Display,
    Publication,
    PublicationState,
    PublicationTarget,
    RateVersion,
    User,
)
from app.schemas.common import Message, Page
from app.schemas.displays import AuditOut, PublicationOut, PublishRequest, RollbackRequest
from app.services import audit, publishing

logger = logging.getLogger(__name__)
router = APIRouter(tags=["publications"])


def _resolve_targets(
    db: Session, user: User, payload_display_ids: List[int], branch_id: Optional[int]
):
    """Turn the request into a concrete, authorized list of displays."""
    if branch_id is not None and payload_display_ids:
        raise HTTPException(
            status_code=400,
            detail="Pilih display spesifik atau satu cabang, bukan keduanya.",
        )

    if branch_id is not None:
        ensure_branch_access(db, user, branch_id)
        displays = publishing.resolve_branch_displays(db, branch_id)
        if not displays:
            raise HTTPException(
                status_code=400, detail="Cabang ini belum memiliki display aktif."
            )
        return displays, "branch", branch_id

    if not payload_display_ids:
        raise HTTPException(status_code=400, detail="Pilih minimal satu display.")

    displays = []
    for display_id in dict.fromkeys(payload_display_ids):
        display = db.get(Display, display_id)
        if display is None:
            raise HTTPException(
                status_code=404, detail=f"Display {display_id} tidak ditemukan."
            )
        ensure_display_access(db, user, display)
        if not display.is_active or display.revoked_at is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Display {display.name} tidak aktif atau sudah dicabut.",
            )
        displays.append(display)

    return displays, "display", None


@router.post("/publications", response_model=PublicationOut, status_code=201)
def create_publication(
    payload: PublishRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Publish a ready version to displays, now or on a schedule.

    Staff cannot reach this route at all: it depends on require_admin.
    """
    existing = publishing.find_by_idempotency_key(db, payload.idempotency_key)
    if existing is not None:
        # Same request, same result. Retrying must not publish twice.
        return serialize_publication(db, existing)

    version = db.get(RateVersion, payload.version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Versi tidak ditemukan.")
    ensure_branch_access(db, admin, version.branch_id)

    displays, scope, scope_branch_id = _resolve_targets(
        db, admin, payload.display_ids, payload.branch_id
    )

    try:
        publication = publishing.create_publication(
            db,
            version=version,
            displays=displays,
            created_by=admin.id,
            scope=scope,
            scope_branch_id=scope_branch_id,
            scheduled_at=payload.scheduled_at,
            valid_until=payload.valid_until,
            idempotency_key=payload.idempotency_key,
            note=payload.note,
        )
    except publishing.PublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    audit.record(
        db,
        action="publication.scheduled" if publication.scheduled_at else "publication.created",
        actor_user_id=admin.id,
        actor_label=admin.username,
        target_type="publication",
        target_id=publication.id,
        branch_id=scope_branch_id or version.branch_id,
        details={
            "version_id": version.id,
            "display_ids": [d.id for d in displays],
            "scheduled_at": payload.scheduled_at.isoformat() if payload.scheduled_at else None,
        },
    )
    db.commit()
    return serialize_publication(db, publication)


@router.get("/publications", response_model=Page[PublicationOut])
def list_publications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    state: Optional[str] = Query(None),
):
    stmt = select(Publication)
    count_stmt = select(func.count(Publication.id))

    allowed = accessible_branch_ids(db, user)
    if allowed is not None:
        if not allowed:
            return Page[PublicationOut](items=[], total=0, page=page, page_size=page_size)
        scoped = (
            select(PublicationTarget.publication_id)
            .join(Display, Display.id == PublicationTarget.display_id)
            .where(Display.branch_id.in_(list(allowed)))
        )
        stmt = stmt.where(Publication.id.in_(scoped))
        count_stmt = count_stmt.where(Publication.id.in_(scoped))

    if state:
        stmt = stmt.where(Publication.state == state)
        count_stmt = count_stmt.where(Publication.state == state)

    total = int(db.execute(count_stmt).scalar() or 0)
    rows = list(
        db.execute(
            stmt.order_by(Publication.created_at.desc(), Publication.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars()
    )

    return Page[PublicationOut](
        items=[serialize_publication(db, p) for p in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/publications/{publication_id}", response_model=PublicationOut)
def get_publication(
    publication_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise HTTPException(status_code=404, detail="Publikasi tidak ditemukan.")

    allowed = accessible_branch_ids(db, user)
    if allowed is not None:
        visible = db.execute(
            select(PublicationTarget.id)
            .join(Display, Display.id == PublicationTarget.display_id)
            .where(
                PublicationTarget.publication_id == publication.id,
                Display.branch_id.in_(list(allowed) or [-1]),
            )
            .limit(1)
        ).scalar()
        if not visible:
            raise HTTPException(status_code=404, detail="Publikasi tidak ditemukan.")

    return serialize_publication(db, publication)


@router.post("/publications/{publication_id}/cancel", response_model=PublicationOut)
def cancel_publication(
    publication_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Cancel a schedule that has not fired yet.

    An already-active publication cannot be cancelled - use rollback, which
    creates a new publication and leaves the history intact.
    """
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise HTTPException(status_code=404, detail="Publikasi tidak ditemukan.")

    try:
        publishing.cancel_schedule(db, publication)
    except publishing.PublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    audit.record(
        db,
        action="publication.cancelled",
        actor_user_id=admin.id,
        actor_label=admin.username,
        target_type="publication",
        target_id=publication.id,
    )
    db.commit()
    return serialize_publication(db, publication)


@router.post("/displays/{display_id}/rollback", response_model=PublicationOut)
def rollback_display(
    display_id: int,
    payload: RollbackRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Put a display back on the previous ready version it successfully showed.

    This creates a new publication with a new revision; it never rewinds the
    log or reuses an old revision number.
    """
    display = db.get(Display, display_id)
    if display is None:
        raise HTTPException(status_code=404, detail="Display tidak ditemukan.")
    ensure_display_access(db, admin, display)

    current = publishing.current_target(db, display)
    current_version_id = current.version_id if current else None

    previous = db.execute(
        select(PublicationTarget)
        .join(RateVersion, RateVersion.id == PublicationTarget.version_id)
        .where(
            PublicationTarget.display_id == display.id,
            PublicationTarget.version_id != current_version_id,
            RateVersion.status == "ready",
        )
        .order_by(PublicationTarget.revision.desc())
        .limit(1)
    ).scalar_one_or_none()

    if previous is None:
        raise HTTPException(
            status_code=409, detail="Tidak ada versi sebelumnya yang bisa dikembalikan."
        )

    version = db.get(RateVersion, previous.version_id)

    existing = publishing.find_by_idempotency_key(db, payload.idempotency_key)
    if existing is not None:
        return serialize_publication(db, existing)

    try:
        publication = publishing.create_publication(
            db,
            version=version,
            displays=[display],
            created_by=admin.id,
            scope="display",
            idempotency_key=payload.idempotency_key,
            rollback_of_id=previous.publication_id,
            note="rollback",
        )
    except publishing.PublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    audit.record(
        db,
        action="publication.rollback",
        actor_user_id=admin.id,
        actor_label=admin.username,
        target_type="publication",
        target_id=publication.id,
        branch_id=display.branch_id,
        details={
            "display_id": display.id,
            "from_version_id": current_version_id,
            "to_version_id": version.id,
        },
    )
    db.commit()
    return serialize_publication(db, publication)


@router.get("/audit", response_model=Page[AuditOut])
def list_audit(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    action: Optional[str] = Query(None),
):
    stmt = select(AuditLog)
    count_stmt = select(func.count(AuditLog.id))

    allowed = accessible_branch_ids(db, user)
    if allowed is not None:
        scope = list(allowed)
        # Staff see entries for their branches plus entries they performed.
        condition = AuditLog.branch_id.in_(scope) if scope else AuditLog.id < 0
        condition = condition | (AuditLog.actor_user_id == user.id)
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    if action:
        stmt = stmt.where(AuditLog.action == action)
        count_stmt = count_stmt.where(AuditLog.action == action)

    total = int(db.execute(count_stmt).scalar() or 0)
    rows = list(
        db.execute(
            stmt.order_by(AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars()
    )

    return Page[AuditOut](
        items=[AuditOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
