"""Dashboard summary numbers."""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.api.deps import accessible_branch_ids, display_connection_state, get_current_user
from app.db.session import get_db
from app.models import (
    Display,
    Job,
    JobStatus,
    Publication,
    PublicationState,
    PublicationTarget,
    RateVersion,
    User,
    VersionStatus,
)
from app.schemas.displays import DashboardStats

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardStats)
def dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    allowed = accessible_branch_ids(db, user)

    display_stmt = select(Display, PublicationTarget.revision).outerjoin(
        PublicationTarget, Display.desired_target_id == PublicationTarget.id
    )
    version_stmt = select(RateVersion.status, func.count(RateVersion.id)).group_by(RateVersion.status)
    job_stmt = select(Job.status, func.count(Job.id)).group_by(Job.status).where(
        Job.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value, JobStatus.FAILED.value])
    )
    publication_filters = []

    if allowed is not None:
        scope = list(allowed) or [-1]
        display_stmt = display_stmt.where(Display.branch_id.in_(scope))
        version_stmt = version_stmt.where(RateVersion.branch_id.in_(scope))
        job_stmt = job_stmt.join(RateVersion, Job.version_id == RateVersion.id).where(RateVersion.branch_id.in_(scope))
        scoped_publications = select(PublicationTarget.publication_id).join(
            Display, Display.id == PublicationTarget.display_id
        ).where(Display.branch_id.in_(scope))
        # Scheduled publications have no target rows until activation.
        # Their saved display IDs still determine which branch can see them.
        scoped_schedule = select(Display.id).where(
            Display.branch_id.in_(scope),
            func.json_contains(Publication.scheduled_display_ids, cast(Display.id, String)) == 1,
        ).correlate(Publication).exists()
        publication_filters.append(
            Publication.id.in_(scoped_publications)
            | Publication.scope_branch_id.in_(scope)
            | ((Publication.state == PublicationState.SCHEDULED.value) & scoped_schedule)
        )

    display_rows = db.execute(display_stmt.order_by(Display.id)).all()
    displays = [row[0] for row in display_rows]
    version_counts = dict(db.execute(version_stmt).all())
    job_counts = dict(db.execute(job_stmt).all())

    online = 0
    offline = 0
    stale = 0
    for display, desired_revision in display_rows:
        state = display_connection_state(display)
        if state == "online":
            online += 1
        else:
            offline += 1

        if desired_revision is not None and display.reported_revision < desired_revision:
            stale += 1

    live_version_id: Optional[int] = None
    live_label: Optional[str] = None
    for display in displays:
        if display.reported_version_id:
            live_version_id = display.reported_version_id
            version = db.get(RateVersion, live_version_id)
            live_label = f"v{version.version}" if version else None
            break

    last_publication = db.execute(
        select(Publication)
        .where(*publication_filters)
        .where(Publication.state != PublicationState.CANCELLED.value)
        .order_by(Publication.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    last_publish_by = None
    if last_publication is not None and last_publication.created_by:
        author = db.get(User, last_publication.created_by)
        last_publish_by = author.username if author else None

    pending_jobs = job_counts.get(JobStatus.QUEUED.value, 0) + job_counts.get(JobStatus.RUNNING.value, 0)
    failed_jobs = job_counts.get(JobStatus.FAILED.value, 0)
    scheduled = int(
        db.execute(
            select(func.count(Publication.id)).where(
                Publication.state == PublicationState.SCHEDULED.value
            ).where(*publication_filters)
        ).scalar()
        or 0
    )

    return DashboardStats(
        displays_total=len(displays),
        displays_online=online,
        displays_offline=offline,
        displays_stale=stale,
        versions_total=sum(version_counts.values()),
        versions_ready=version_counts.get(VersionStatus.READY.value, 0),
        live_version_id=live_version_id,
        live_version_label=live_label,
        last_publish_at=last_publication.effective_at if last_publication else None,
        last_publish_by=last_publish_by,
        pending_jobs=pending_jobs,
        failed_jobs=failed_jobs,
        scheduled_publications=scheduled,
    )
