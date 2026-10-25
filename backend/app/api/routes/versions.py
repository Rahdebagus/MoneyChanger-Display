"""Rate versions: create, list, inspect, duplicate, archive, generate media.

Saving a version never changes what a TV shows. Publishing is a separate,
explicit action in publications.py.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

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
    RateBoard,
    RateVersion,
    User,
    VersionStatus,
)
from app.schemas.common import Message, Page
from app.schemas.rates import GenerateResponse, JobOut, VersionCreate, VersionDetail, VersionSummary
from app.services import audit, direct_save, publishing, rates as rates_service, version_cleanup
from app.services.access import BranchAccessDenied
from app.services.rates import RateValidationError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rates"])

def _load_version(db: Session, version_id: int, user: User, *, lock: bool = False) -> RateVersion:
    stmt = select(RateVersion).where(RateVersion.id == version_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    version = db.execute(stmt).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Versi tidak ditemukan.")
    ensure_branch_access(db, user, version.branch_id)
    return version


@router.post("/versions", response_model=GenerateResponse, status_code=201)
def create_version(
    payload: VersionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Persist rates, render PNG in-process, then return the ready version."""
    try:
        version = direct_save.save(db, user, payload)
    except BranchAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RateValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except direct_save.SaveError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database failure saving rate board")
        raise HTTPException(status_code=503, detail="Penyimpanan belum dapat dikonfirmasi. Coba ulang dengan data yang sama.") from exc
    return GenerateResponse(version=serialize_version(db, version), job=None)


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

    if version.status == VersionStatus.GENERATING.value:
        raise HTTPException(status_code=409, detail="Versi masih dibuat. Tunggu proses selesai.")
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
