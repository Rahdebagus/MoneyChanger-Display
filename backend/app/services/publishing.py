"""Publishing a version to displays, plus scheduling and rollback.

Ordering guarantees:

* Each display has a monotonic revision counter. A publish takes the next
  number under a row lock, so two admins publishing at once get distinct,
  ordered revisions and the unique (display_id, revision) index is a backstop.
* A player only ever moves forward: an acknowledgement for a revision lower
  than what the display already reports is ignored rather than applied. That
  is what stops a slow old update from replacing a newer one.
* Re-sending the same publish request with the same idempotency key returns
  the original publication instead of creating a second one.
"""

from datetime import datetime
from typing import Iterable, List, Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.timeutils import to_naive_utc, utcnow
from app.models import (
    Display,
    Publication,
    PublicationState,
    PublicationTarget,
    RateVersion,
    TargetState,
    VersionStatus,
)
from app.services import events, storage


class PublishError(ValueError):
    """Message is safe to show a user."""


def resolve_branch_displays(db: Session, branch_id: int) -> List[Display]:
    """Displays of a branch, resolved once at publish time.

    A display paired after this call does not inherit the publication; it must
    be targeted explicitly. Leaving that ambiguous would mean a newly paired
    TV silently waking up with stale rates.
    """
    stmt = (
        select(Display)
        .where(
            Display.branch_id == branch_id,
            Display.is_active.is_(True),
            Display.revoked_at.is_(None),
        )
        .order_by(Display.id)
    )
    return list(db.execute(stmt).scalars())


def _lock_display(db: Session, display_id: int) -> Optional[Display]:
    """Row-lock a display so revision assignment cannot interleave."""
    stmt = select(Display).where(Display.id == display_id)
    if db.bind is not None and db.bind.dialect.name != "sqlite":
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def ensure_publishable(version: Optional[RateVersion]) -> RateVersion:
    if version is None:
        raise PublishError("Versi rate tidak ditemukan.")
    if version.status != VersionStatus.READY:
        raise PublishError(
            "Hanya versi berstatus ready yang bisa ditayangkan. "
            "Status versi ini: " + str(version.status) + "."
        )
    if version.png_asset_id is None or version.png_asset is None or not storage.asset_exists(version.png_asset):
        raise PublishError("Versi ini belum memiliki media board.")
    return version


def find_by_idempotency_key(db: Session, key: Optional[str]) -> Optional[Publication]:
    if not key:
        return None
    return db.execute(
        select(Publication).where(Publication.idempotency_key == key)
    ).scalar_one_or_none()


def create_publication(
    db: Session,
    *,
    version: RateVersion,
    displays: Sequence[Display],
    created_by: Optional[int],
    scope: str = "display",
    scope_branch_id: Optional[int] = None,
    scheduled_at: Optional[datetime] = None,
    valid_until: Optional[datetime] = None,
    idempotency_key: Optional[str] = None,
    rollback_of_id: Optional[int] = None,
    note: Optional[str] = None,
) -> Publication:
    version = db.execute(
        select(RateVersion).where(RateVersion.id == version.id)
        .with_for_update().execution_options(populate_existing=True)
    ).scalar_one_or_none()
    ensure_publishable(version)
    if not displays:
        raise PublishError("Tidak ada display yang menjadi tujuan publikasi.")

    now = utcnow()
    is_scheduled = scheduled_at is not None and to_naive_utc(scheduled_at) > to_naive_utc(now)

    publication = Publication(
        version_id=version.id,
        created_by=created_by,
        state=(PublicationState.SCHEDULED if is_scheduled else PublicationState.ACTIVE).value,
        scope=scope,
        scope_branch_id=scope_branch_id,
        scheduled_at=to_naive_utc(scheduled_at),
        effective_at=None if is_scheduled else to_naive_utc(now),
        valid_until=to_naive_utc(valid_until),
        idempotency_key=idempotency_key,
        rollback_of_id=rollback_of_id,
        note=note,
    )
    db.add(publication)
    db.flush()

    if is_scheduled:
        # Remember the intended displays so the scheduler fires at exactly the
        # set the admin chose, without re-resolving a branch later.
        _record_scheduled_targets(db, publication, displays)
    else:
        activate(db, publication, displays=displays)

    return publication


def _record_scheduled_targets(
    db: Session, publication: Publication, displays: Sequence[Display]
) -> None:
    publication.scheduled_display_ids = [d.id for d in displays]
    db.flush()


def _scheduled_display_ids(publication: Publication) -> List[int]:
    return [int(x) for x in (publication.scheduled_display_ids or [])]


def activate(
    db: Session,
    publication: Publication,
    *,
    displays: Optional[Sequence[Display]] = None,
) -> List[PublicationTarget]:
    """Assign the publication to its displays and make it the desired state."""
    version = db.execute(
        select(RateVersion).where(RateVersion.id == publication.version_id)
        .with_for_update().execution_options(populate_existing=True)
    ).scalar_one_or_none()
    ensure_publishable(version)
    if displays is None:
        displays = _displays_for_scheduled(db, publication)

    targets: List[PublicationTarget] = []
    now = utcnow().replace(tzinfo=None)

    for display in displays:
        locked = _lock_display(db, display.id)
        if locked is None or not locked.is_active or locked.revoked_at is not None:
            continue

        revision = locked.current_revision + 1

        # Anything still outstanding for this display is now stale.
        db.execute(
            update(PublicationTarget)
            .where(
                PublicationTarget.display_id == locked.id,
                PublicationTarget.state.in_(
                    [
                        TargetState.PENDING.value,
                        TargetState.DOWNLOADING.value,
                        TargetState.LOADING.value,
                    ]
                ),
            )
            .values(state=TargetState.SUPERSEDED.value)
        )

        target = PublicationTarget(
            publication_id=publication.id,
            display_id=locked.id,
            version_id=publication.version_id,
            revision=revision,
            state=TargetState.PENDING.value,
            valid_until=publication.valid_until,
        )
        db.add(target)
        db.flush()

        locked.current_revision = revision
        locked.desired_target_id = target.id
        targets.append(target)

        events.emit(
            db,
            events.TOPIC_ASSIGNMENT,
            display_id=locked.id,
            payload={"revision": revision, "version_id": publication.version_id},
        )

    publication.state = PublicationState.ACTIVE.value
    publication.effective_at = publication.effective_at or now
    db.flush()

    _supersede_previous(db, publication, [t.display_id for t in targets])
    return targets


def _displays_for_scheduled(db: Session, publication: Publication) -> List[Display]:
    """Targets of a scheduled publication, resolved when it actually fires."""
    if publication.scope == "branch" and publication.scope_branch_id:
        return resolve_branch_displays(db, publication.scope_branch_id)

    ids = _scheduled_display_ids(publication)
    if not ids:
        return []

    stmt = (
        select(Display)
        .where(
            Display.id.in_(ids),
            Display.is_active.is_(True),
            Display.revoked_at.is_(None),
        )
        .order_by(Display.id)
    )
    return list(db.execute(stmt).scalars())


def _supersede_previous(db: Session, publication: Publication, display_ids: Iterable[int]) -> None:
    ids = list(display_ids)
    if not ids:
        return

    stale_ids = list(
        db.execute(
            select(Publication.id)
            .join(PublicationTarget, PublicationTarget.publication_id == Publication.id)
            .where(
                PublicationTarget.display_id.in_(ids),
                Publication.id != publication.id,
                Publication.state == PublicationState.ACTIVE.value,
            )
        ).scalars()
    )
    if not stale_ids:
        return

    # A publication is only superseded once none of its targets are current.
    still_current = set(
        db.execute(
            select(PublicationTarget.publication_id)
            .join(Display, Display.desired_target_id == PublicationTarget.id)
            .where(PublicationTarget.publication_id.in_(stale_ids))
        ).scalars()
    )
    obsolete = [pid for pid in set(stale_ids) if pid not in still_current]
    if obsolete:
        db.execute(
            update(Publication)
            .where(Publication.id.in_(obsolete))
            .values(state=PublicationState.SUPERSEDED.value)
        )


def cancel_schedule(db: Session, publication: Publication) -> None:
    if publication.state != PublicationState.SCHEDULED:
        raise PublishError("Hanya jadwal yang belum berjalan yang bisa dibatalkan.")
    publication.state = PublicationState.CANCELLED.value
    publication.cancelled_at = utcnow().replace(tzinfo=None)
    db.flush()


def due_schedules(db: Session, limit: int = 50) -> List[int]:
    now = utcnow().replace(tzinfo=None)
    stmt = (
        select(Publication.id)
        .where(
            Publication.state == PublicationState.SCHEDULED.value,
            Publication.scheduled_at.is_not(None),
            Publication.scheduled_at <= now,
        )
        .order_by(Publication.scheduled_at, Publication.id)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())


def claim_schedule(db: Session, publication_id: int) -> Optional[Publication]:
    """Guarded transition so two workers cannot fire one schedule twice."""
    result = db.execute(
        update(Publication)
        .where(
            Publication.id == publication_id,
            Publication.state == PublicationState.SCHEDULED.value,
        )
        .values(state=PublicationState.ACTIVE.value, effective_at=utcnow().replace(tzinfo=None))
    )
    if result.rowcount != 1:
        return None
    return db.get(Publication, publication_id)


def acknowledge(
    db: Session,
    *,
    display: Display,
    revision: int,
    version_id: Optional[int],
    state: str,
    error_message: Optional[str] = None,
) -> Optional[PublicationTarget]:
    """Record what a display reports it is actually showing.

    An acknowledgement for an older revision than the display already reports
    is dropped: late packets must not rewind the reported state.
    """
    target = db.execute(
        select(PublicationTarget).where(
            PublicationTarget.display_id == display.id,
            PublicationTarget.revision == revision,
        )
    ).scalar_one_or_none()

    if target is None:
        return None

    if revision < display.reported_revision:
        return target

    if version_id is not None and version_id != target.version_id:
        return None
    # Repeated acknowledgements are normal after reconnects. Do not rewrite
    # the same state or create another outbox event for each retry.
    if target.state == state and (
        state != TargetState.DISPLAYED
        or (display.reported_revision == revision and display.reported_version_id == target.version_id)
    ) and (state != TargetState.FAILED or target.error_message == error_message):
        return target

    now = utcnow().replace(tzinfo=None)
    target.state = state
    target.attempts = target.attempts + 1

    if state == TargetState.DISPLAYED:
        target.acknowledged_at = now
        target.error_message = None
        display.reported_revision = revision
        display.reported_version_id = version_id or target.version_id
        display.reported_at = now
        display.last_error = None
    elif state == TargetState.FAILED:
        target.failed_at = now
        target.error_message = (error_message or "Player melaporkan kegagalan.")[:2000]
        # The display keeps showing whatever it had: a failed load must never
        # advance reported state.
        display.last_error = target.error_message

    db.flush()
    events.emit(
        db,
        events.TOPIC_DISPLAY_STATE,
        display_id=display.id,
        payload={"revision": revision, "state": state},
    )
    return target


def current_target(db: Session, display: Display) -> Optional[PublicationTarget]:
    if display.desired_target_id is None:
        return None
    return db.get(PublicationTarget, display.desired_target_id)


def is_version_referenced(db: Session, version_id: int) -> bool:
    """A version wired to a display or a pending schedule cannot be deleted."""
    referenced = db.execute(
        select(PublicationTarget.id)
        .join(Display, Display.desired_target_id == PublicationTarget.id)
        .where(PublicationTarget.version_id == version_id)
        .limit(1).with_for_update()
    ).scalar()
    if referenced:
        return True

    reported = db.execute(
        select(Display.id).where(Display.reported_version_id == version_id)
        .limit(1).with_for_update()
    ).scalar_one_or_none()
    if reported is not None:
        return True

    scheduled = db.execute(
        select(Publication.id)
        .where(
            Publication.version_id == version_id,
            Publication.state == PublicationState.SCHEDULED.value,
        )
        .limit(1).with_for_update()
    ).scalar()
    return bool(scheduled)
