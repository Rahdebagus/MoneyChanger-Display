"""Rate versions: create, list, inspect, duplicate, archive, generate media.

Saving a version never changes what a TV shows. Publishing is a separate,
explicit action in publications.py.
"""

import base64
import binascii
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import (
    accessible_branch_ids,
    ensure_branch_access,
    get_current_user,
    require_admin,
)
from app.api.serializers import serialize_version, serialize_versions
from app.core.timeutils import utcnow
from app.db.session import get_db
from app.models import (
    Job,
    JobStatus,
    JobType,
    MediaKind,
    RateBoard,
    RateVersion,
    User,
    VersionStatus,
)
from app.schemas.common import Message, Page
from app.schemas.rates import GenerateResponse, JobOut, VersionCreate, VersionDetail, VersionSummary
from app.services import audit, jobs, publishing, rates as rates_service, storage, version_cleanup
from app.services.rates import RateValidationError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rates"])

MAX_LOGO_BYTES = 4 * 1024 * 1024


def _decode_logo(raw: Optional[str]) -> Optional[bytes]:
    if not raw:
        return None
    payload = raw.split(",", 1)[1] if "," in raw else raw
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Logo tidak dapat dibaca.")
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(status_code=400, detail="Ukuran logo maksimal 4MB.")
    return data


def _load_version(db: Session, version_id: int, user: User, *, lock: bool = False) -> RateVersion:
    stmt = select(RateVersion).where(RateVersion.id == version_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    version = db.execute(stmt).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Versi tidak ditemukan.")
    ensure_branch_access(db, user, version.branch_id)
    return version


def _resolve_branch(db: Session, user: User, branch_id: Optional[int]) -> Optional[int]:
    """Pick the branch a new version belongs to, honouring staff scope."""
    allowed = accessible_branch_ids(db, user)

    if branch_id is not None:
        ensure_branch_access(db, user, branch_id)
        return branch_id

    if allowed is None:
        return None
    # A staff member with exactly one branch does not need to pick it.
    if len(allowed) == 1:
        return next(iter(allowed))
    if not allowed:
        raise HTTPException(
            status_code=403, detail="Akun Anda belum ditugaskan ke cabang mana pun."
        )
    raise HTTPException(status_code=400, detail="Pilih cabang untuk versi ini.")


@router.post("/versions", response_model=GenerateResponse, status_code=201)
def create_version(
    payload: VersionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a draft version and queue board generation.

    Returns immediately with a job id. The version only becomes ready - and
    therefore publishable - once the worker has actually written the media.
    """
    try:
        parsed = rates_service.normalise_input(payload.rates)
    except RateValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not rates_service.has_any_value(parsed):
        raise HTTPException(status_code=400, detail="Isi minimal satu nilai rate.")

    branch_id = _resolve_branch(db, user, payload.branch_id)

    source_version = None
    if payload.source_version_id is not None:
        source_version = _load_version(db, payload.source_version_id, user, lock=True)

    logo_asset_id = None
    logo_bytes = _decode_logo(payload.logo_base64)
    if logo_bytes:
        asset = storage.create_asset(
            db,
            kind=MediaKind.LOGO.value,
            storage_key=f"logos/{storage.checksum_name(logo_bytes)}.png",
            data=logo_bytes,
        )
        logo_asset_id = asset.id
    elif source_version is not None:
        logo_asset_id = source_version.logo_asset_id

    board = rates_service.get_or_create_default_board(
        db, owner_id=user.id, branch_id=branch_id, title=payload.title
    )

    version = rates_service.create_version(
        db,
        board=board,
        rates=parsed,
        board_title=payload.title,
        board_subtitle=payload.subtitle,
        created_by=user.id,
        branch_id=branch_id,
        logo_asset_id=logo_asset_id,
        source_version_id=source_version.id if source_version else None,
        config_snapshot={
            "title": payload.title,
            "subtitle": payload.subtitle,
            "has_custom_logo": logo_asset_id is not None,
        },
    )

    version.status = VersionStatus.GENERATING.value
    job = jobs.enqueue(
        db,
        job_type=JobType.GENERATE_BOARD.value,
        payload={"version_id": version.id, "generate_video": bool(payload.generate_video)},
        version_id=version.id,
        created_by=user.id,
    )

    audit.record(
        db,
        action="version.created",
        actor_user_id=user.id,
        actor_label=user.username,
        target_type="rate_version",
        target_id=version.id,
        branch_id=branch_id,
        details={
            "version": version.version,
            "source_version_id": payload.source_version_id,
            "job_id": job.id,
        },
    )
    db.commit()

    return GenerateResponse(
        version=serialize_version(db, version),
        job=JobOut.model_validate(job),
    )


@router.get("/versions", response_model=Page[VersionSummary])
def list_versions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    branch_id: Optional[int] = Query(None),
    include_archived: bool = Query(False),
):
    stmt = select(RateVersion)
    count_stmt = select(func.count(RateVersion.id))

    allowed = accessible_branch_ids(db, user)
    if allowed is not None:
        if not allowed:
            return Page[VersionSummary](items=[], total=0, page=page, page_size=page_size)
        scope = list(allowed)
        stmt = stmt.where(RateVersion.branch_id.in_(scope))
        count_stmt = count_stmt.where(RateVersion.branch_id.in_(scope))

    if branch_id is not None:
        ensure_branch_access(db, user, branch_id)
        stmt = stmt.where(RateVersion.branch_id == branch_id)
        count_stmt = count_stmt.where(RateVersion.branch_id == branch_id)

    if status:
        stmt = stmt.where(RateVersion.status == status)
        count_stmt = count_stmt.where(RateVersion.status == status)
    elif not include_archived:
        stmt = stmt.where(RateVersion.status != VersionStatus.ARCHIVED.value)
        count_stmt = count_stmt.where(RateVersion.status != VersionStatus.ARCHIVED.value)

    total = int(db.execute(count_stmt).scalar() or 0)
    rows = list(
        db.execute(
            stmt.order_by(RateVersion.created_at.desc(), RateVersion.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars()
    )

    return Page[VersionSummary](
        items=serialize_versions(db, rows),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/versions/{version_id}", response_model=VersionDetail)
def get_version(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    version = _load_version(db, version_id, user)
    return serialize_version(db, version, detail=True)


@router.post("/versions/{version_id}/duplicate", response_model=VersionDetail, status_code=201)
def duplicate_version(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Open an existing version as a fresh editable draft.

    The original is untouched, which is what makes editing a version that is
    currently on screen safe.
    """
    source = _load_version(db, version_id, user, lock=True)
    board = db.get(RateBoard, source.board_id)

    draft = rates_service.create_version(
        db,
        board=board,
        rates=rates_service.clone_rates(source),
        board_title=source.board_title,
        board_subtitle=source.board_subtitle,
        created_by=user.id,
        branch_id=source.branch_id,
        logo_asset_id=source.logo_asset_id,
        source_version_id=source.id,
        config_snapshot=dict(source.config_snapshot or {}),
    )

    audit.record(
        db,
        action="version.duplicated",
        actor_user_id=user.id,
        actor_label=user.username,
        target_type="rate_version",
        target_id=draft.id,
        branch_id=draft.branch_id,
        details={"source_version_id": source.id, "new_version": draft.version},
    )
    db.commit()
    return serialize_version(db, draft, detail=True)


@router.post("/versions/{version_id}/video", response_model=JobOut, status_code=202)
def request_video(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    version = _load_version(db, version_id, user, lock=True)
    if version.png_asset_id is None:
        raise HTTPException(status_code=409, detail="Board PNG belum tersedia.")
    if version.mp4_asset_id is not None:
        raise HTTPException(status_code=409, detail="Video sudah tersedia.")

    existing = db.execute(
        select(Job).where(
            Job.version_id == version.id,
            Job.job_type == JobType.GENERATE_VIDEO.value,
            Job.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
        )
    ).scalar_one_or_none()
    if existing is not None:
        return JobOut.model_validate(existing)

    job = jobs.enqueue(
        db,
        job_type=JobType.GENERATE_VIDEO.value,
        payload={"version_id": version.id},
        version_id=version.id,
        created_by=user.id,
    )
    db.commit()
    return JobOut.model_validate(job)


@router.post("/versions/{version_id}/archive", response_model=VersionSummary)
def archive_version(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Archive hides a version from the default history list.

    A version still referenced by a display or a pending schedule cannot be
    archived - the history behind what is on screen stays intact.
    """
    version = _load_version(db, version_id, user, lock=True)

    if publishing.is_version_referenced(db, version.id):
        raise HTTPException(
            status_code=409,
            detail="Versi ini sedang tayang atau dipakai jadwal. Tidak bisa diarsipkan.",
        )

    version.status = VersionStatus.ARCHIVED.value
    version.archived_at = utcnow().replace(tzinfo=None)
    audit.record(
        db,
        action="version.archived",
        actor_user_id=user.id,
        actor_label=user.username,
        target_type="rate_version",
        target_id=version.id,
        branch_id=version.branch_id,
    )
    db.commit()
    db.refresh(version)
    return serialize_version(db, version)


@router.post("/versions/{version_id}/restore", response_model=VersionSummary)
def restore_version(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    version = _load_version(db, version_id, user, lock=True)
    if version.status != VersionStatus.ARCHIVED:
        raise HTTPException(status_code=409, detail="Versi ini tidak sedang diarsipkan.")

    version.status = (
        VersionStatus.READY.value if version.png_asset_id else VersionStatus.DRAFT.value
    )
    version.archived_at = None
    audit.record(
        db,
        action="version.restored",
        actor_user_id=user.id,
        actor_label=user.username,
        target_type="rate_version",
        target_id=version.id,
        branch_id=version.branch_id,
    )
    db.commit()
    db.refresh(version)
    return serialize_version(db, version)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan.")

    if job.version_id is not None:
        version = db.get(RateVersion, job.version_id)
        if version is not None:
            ensure_branch_access(db, user, version.branch_id)

    return JobOut.model_validate(job)


@router.get("/jobs", response_model=List[JobOut])
def list_recent_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    limit: int = Query(20, ge=1, le=100),
):
    rows = list(
        db.execute(select(Job).order_by(Job.id.desc()).limit(limit)).scalars()
    )
    return [JobOut.model_validate(j) for j in rows]


@router.delete("/versions/{version_id}", response_model=Message)
def delete_version(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Delete unused history and queue durable cleanup of its media files."""
    version = _load_version(db, version_id, user, lock=True)
    try:
        version_cleanup.delete_version(db, version, user)
    except version_cleanup.VersionInUse as exc:
        raise HTTPException(
            status_code=409, detail=str(exc),
        ) from exc
    db.commit()
    return Message(message="Versi dihapus. File yang tidak digunakan akan dibersihkan otomatis.")
