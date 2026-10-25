"""Transactional history deletion; disk cleanup runs only after commit."""

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Job, JobStatus, JobType, MediaAsset, Publication, PublicationTarget, RateVersion,
)
from app.services import audit, jobs, publishing, storage


class VersionInUse(ValueError):
    """A version must remain available until its consumers release it."""


def delete_version(db: Session, version: RateVersion, user) -> None:
    # The caller holds the version lock. Publishing requests acquire
    # the same lock, so they cannot create a new consumer during this check.
    if version.status == "generating":
        raise VersionInUse("Versi masih diproses. Tunggu proses selesai sebelum menghapus.")
    if publishing.is_version_referenced(db, version.id):
        raise VersionInUse("Versi masih dipakai display atau jadwal. Ganti tayangan atau batalkan jadwal terlebih dahulu.")
    active_job = db.execute(
        select(Job.id).where(
            Job.version_id == version.id,
            Job.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
        ).limit(1).with_for_update()
    ).scalar_one_or_none()
    if active_job is not None:
        raise VersionInUse("Versi masih diproses. Tunggu proses selesai sebelum menghapus.")

    asset_ids = sorted({asset_id for asset_id in (
        version.png_asset_id, version.mp4_asset_id,
        version.thumbnail_asset_id, version.logo_asset_id,
    ) if asset_id is not None})
    audit.record(
        db, action="version.deleted", actor_user_id=user.id,
        actor_label=user.username, target_type="rate_version",
        target_id=version.id, branch_id=version.branch_id,
        details={"version": version.version, "board_id": version.board_id},
    )
    # Historical publication targets restrict deletion in SQL. Current and
    # reported assignments, schedules and active jobs were protected above.
    db.execute(delete(PublicationTarget).where(PublicationTarget.version_id == version.id))
    db.execute(delete(Publication).where(Publication.version_id == version.id))
    jobs.enqueue(
        db, job_type=JobType.CLEANUP_MEDIA.value, created_by=user.id,
        payload={"deleted_version_id": version.id, "asset_ids": asset_ids},
    )
    db.delete(version)
    db.flush()


def cleanup_media(db: Session, payload: dict) -> dict:
    """Idempotent worker task. Preserve logos/media shared by another version."""
    freed = 0
    for asset_id in sorted(set(payload.get("asset_ids", []))):
        asset = db.execute(
            select(MediaAsset).where(MediaAsset.id == asset_id).with_for_update()
        ).scalar_one_or_none()
        if asset is None:
            continue
        referenced = db.execute(
            select(RateVersion.id).where(or_(
                RateVersion.png_asset_id == asset.id,
                RateVersion.mp4_asset_id == asset.id,
                RateVersion.thumbnail_asset_id == asset.id,
                RateVersion.logo_asset_id == asset.id,
            )).limit(1).with_for_update()
        ).scalar_one_or_none()
        if referenced is not None:
            continue
        path = storage.absolute_path(asset)
        try:
            size = path.stat().st_size
            path.unlink()
            freed += size
        except FileNotFoundError:
            pass  # A previous attempt may have removed the file before a crash.
        db.delete(asset)
    db.flush()

    version_id = int(payload["deleted_version_id"])
    prefix = f"versions/{version_id:08d}/"
    remaining = db.execute(
        select(MediaAsset.id).where(MediaAsset.storage_key.startswith(prefix)).limit(1)
    ).scalar_one_or_none()
    if remaining is None and db.get(RateVersion, version_id) is None:
        freed += storage.delete_version_files(version_id)
    return {"bytes_freed": freed}
