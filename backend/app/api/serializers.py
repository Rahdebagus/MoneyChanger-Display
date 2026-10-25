"""Model to response-schema mapping shared by several routers."""

from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import display_connection_state
from app.models import (
    Branch,
    Display,
    Job,
    JobStatus,
    MediaAsset,
    Publication,
    PublicationState,
    PublicationTarget,
    RateVersion,
    TargetState,
    User,
)
from app.schemas.displays import DisplayOut, PublicationOut, PublicationTargetOut
from app.schemas.rates import RateItemOut, VersionDetail, VersionSummary
from app.services.rates import rates_as_strings


def media_url(asset_id: Optional[int]) -> Optional[str]:
    """Immutable media URL.

    An asset is written once and never rewritten, and a new version gets a new
    asset id, so this URL can be cached hard by the player and the browser.
    """
    if asset_id is None:
        return None
    return f"/api/media/{asset_id}"


def version_label(version: Optional[RateVersion]) -> Optional[str]:
    if version is None:
        return None
    return f"v{version.version}"


def _names(db: Session, user_ids: Iterable[Optional[int]]) -> Dict[int, str]:
    ids = {uid for uid in user_ids if uid}
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.username).where(User.id.in_(ids))).all()
    return {row[0]: row[1] for row in rows}


def _branch_names(db: Session, branch_ids: Iterable[Optional[int]]) -> Dict[int, str]:
    ids = {bid for bid in branch_ids if bid}
    if not ids:
        return {}
    rows = db.execute(select(Branch.id, Branch.name).where(Branch.id.in_(ids))).all()
    return {row[0]: row[1] for row in rows}


def live_version_ids(db: Session, version_ids=None) -> set:
    """Versions assigned to, or still reported by, a display."""
    desired = select(PublicationTarget.version_id).join(
        Display, Display.desired_target_id == PublicationTarget.id
    )
    reported = select(Display.reported_version_id).where(Display.reported_version_id.is_not(None))
    if version_ids is not None:
        desired = desired.where(PublicationTarget.version_id.in_(version_ids))
        reported = reported.where(Display.reported_version_id.in_(version_ids))
    return set(db.execute(desired.union(reported)).scalars())


def deletion_blocks(db: Session, version_ids, live_ids: set) -> dict:
    reasons = {key: "Versi masih dipakai display." for key in live_ids}
    for key in db.execute(
        select(Publication.version_id).where(
            Publication.version_id.in_(version_ids),
            Publication.state == PublicationState.SCHEDULED.value,
        )
    ).scalars():
        reasons[key] = "Versi masih dipakai jadwal tayang."
    for key in db.execute(
        select(Job.version_id).where(
            Job.version_id.in_(version_ids),
            Job.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
        )
    ).scalars():
        reasons[key] = "Versi masih diproses."
    return reasons


def serialize_version(
    db: Session,
    version: RateVersion,
    *,
    detail: bool = False,
    live_ids: Optional[set] = None,
    user_names: Optional[Dict[int, str]] = None,
    branch_names: Optional[Dict[int, str]] = None,
    blocked_reasons: Optional[dict] = None,
):
    if live_ids is None:
        live_ids = live_version_ids(db, [version.id])
    if blocked_reasons is None:
        blocked_reasons = deletion_blocks(db, [version.id], live_ids)
    if user_names is None:
        user_names = _names(db, [version.created_by])
    if branch_names is None:
        branch_names = _branch_names(db, [version.branch_id])

    common = dict(
        id=version.id,
        board_id=version.board_id,
        version=version.version,
        status=version.status,
        board_title=version.board_title,
        board_subtitle=version.board_subtitle,
        created_at=version.created_at,
        generated_at=version.generated_at,
        created_by=version.created_by,
        created_by_name=user_names.get(version.created_by) if version.created_by else None,
        branch_id=version.branch_id,
        branch_name=branch_names.get(version.branch_id) if version.branch_id else None,
        source_version_id=version.source_version_id,
        thumbnail_url=media_url(version.thumbnail_asset_id),
        png_url=media_url(version.png_asset_id),
        mp4_url=None,  # Deprecated compatibility field; only PNG is served.
        is_live=version.id in live_ids,
        delete_blocked_reason=("Versi masih diproses." if version.status == "generating" else blocked_reasons.get(version.id)),
        error_message=version.error_message,
    )

    if not detail:
        return VersionSummary(**common)

    return VersionDetail(
        **common,
        items=[
            RateItemOut(
                currency=item.currency,
                denomination=item.denomination,
                value=None if item.value is None else format(item.value.normalize(), "f"),
                column_side=item.column_side,
                sort_order=item.sort_order,
            )
            for item in version.items
        ],
        rates=rates_as_strings(version.items),
        config_snapshot=version.config_snapshot or {},
    )


def serialize_versions(db: Session, versions: List[RateVersion]) -> List[VersionSummary]:
    if not versions:
        return []
    ids = [v.id for v in versions]
    live_ids = live_version_ids(db, ids)
    blocked_reasons = deletion_blocks(db, ids, live_ids)
    user_names = _names(db, [v.created_by for v in versions])
    branch_names = _branch_names(db, [v.branch_id for v in versions])
    return [
        serialize_version(
            db,
            v,
            live_ids=live_ids,
            blocked_reasons=blocked_reasons,
            user_names=user_names,
            branch_names=branch_names,
        )
        for v in versions
    ]


def serialize_display(
    db: Session, display: Display, *, branch_names=None, targets=None, versions=None,
) -> DisplayOut:
    if branch_names is None:
        branch_names = _branch_names(db, [display.branch_id])

    desired_target = None
    desired_version = None
    reported_version = None
    if display.desired_target_id is not None:
        desired_target = (
            targets.get(display.desired_target_id) if targets is not None
            else db.get(PublicationTarget, display.desired_target_id)
        )
    if desired_target is not None:
        desired_version = (
            versions.get(desired_target.version_id) if versions is not None
            else db.get(RateVersion, desired_target.version_id)
        )
    if display.reported_version_id is not None:
        reported_version = (
            versions.get(display.reported_version_id) if versions is not None
            else db.get(RateVersion, display.reported_version_id)
        )

    connection = display_connection_state(display)
    # Stale means: the TV is showing something, but not what we asked for.
    is_stale = bool(
        desired_target is not None
        and display.reported_revision < desired_target.revision
    )

    return DisplayOut(
        id=display.id,
        name=display.name,
        branch_id=display.branch_id,
        branch_name=branch_names.get(display.branch_id) if display.branch_id else None,
        is_active=display.is_active,
        is_paired=display.credential_hash is not None,
        connection=connection,
        last_seen_at=display.last_seen_at,
        desired_revision=desired_target.revision if desired_target else 0,
        desired_version_id=desired_target.version_id if desired_target else None,
        desired_version_label=version_label(desired_version),
        reported_revision=display.reported_revision,
        reported_version_id=display.reported_version_id,
        reported_version_label=version_label(reported_version),
        target_state=desired_target.state if desired_target else None,
        is_stale=is_stale,
        last_error=display.last_error,
        revoked_at=display.revoked_at,
    )


def serialize_displays(db: Session, displays: List[Display]) -> List[DisplayOut]:
    if not displays:
        return []
    branch_names = _branch_names(db, [d.branch_id for d in displays])
    target_ids = {d.desired_target_id for d in displays if d.desired_target_id is not None}
    targets = {}
    if target_ids:
        targets = {target.id: target for target in db.execute(
            select(PublicationTarget).where(PublicationTarget.id.in_(target_ids))
        ).scalars()}
    version_ids = {t.version_id for t in targets.values()} | {
        d.reported_version_id for d in displays if d.reported_version_id is not None
    }
    versions = {}
    if version_ids:
        versions = {version.id: version for version in db.execute(
            select(RateVersion).where(RateVersion.id.in_(version_ids))
        ).scalars()}
    return [
        serialize_display(db, d, branch_names=branch_names, targets=targets, versions=versions)
        for d in displays
    ]


def serialize_publication(db: Session, publication: Publication) -> PublicationOut:
    version = db.get(RateVersion, publication.version_id)
    user_names = _names(db, [publication.created_by])

    targets = list(
        db.execute(
            select(PublicationTarget)
            .where(PublicationTarget.publication_id == publication.id)
            .order_by(PublicationTarget.id)
        ).scalars()
    )
    display_names = {}
    if targets:
        rows = db.execute(
            select(Display.id, Display.name).where(
                Display.id.in_([t.display_id for t in targets])
            )
        ).all()
        display_names = {row[0]: row[1] for row in rows}

    return PublicationOut(
        id=publication.id,
        version_id=publication.version_id,
        version_label=version_label(version),
        state=publication.state,
        scope=publication.scope,
        scope_branch_id=publication.scope_branch_id,
        created_by=publication.created_by,
        created_by_name=user_names.get(publication.created_by)
        if publication.created_by
        else None,
        created_at=publication.created_at,
        scheduled_at=publication.scheduled_at,
        effective_at=publication.effective_at,
        valid_until=publication.valid_until,
        cancelled_at=publication.cancelled_at,
        rollback_of_id=publication.rollback_of_id,
        note=publication.note,
        targets=[
            PublicationTargetOut(
                id=t.id,
                display_id=t.display_id,
                display_name=display_names.get(t.display_id),
                revision=t.revision,
                state=t.state,
                acknowledged_at=t.acknowledged_at,
                error_message=t.error_message,
            )
            for t in targets
        ],
    )


def asset_for(db: Session, asset_id: Optional[int]) -> Optional[MediaAsset]:
    if asset_id is None:
        return None
    return db.get(MediaAsset, asset_id)


__all__ = [
    "asset_for",
    "live_version_ids",
    "media_url",
    "serialize_display",
    "serialize_displays",
    "serialize_publication",
    "serialize_version",
    "serialize_versions",
    "version_label",
    "TargetState",
]
