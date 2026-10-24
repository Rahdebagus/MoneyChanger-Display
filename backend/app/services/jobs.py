"""Durable job queue backed by the jobs table.

Claiming avoids SKIP LOCKED (absent before MariaDB 10.6). Instead a worker
reads candidate ids, then issues a guarded UPDATE for one of them:

    UPDATE jobs SET status='running', claim_token=:tok
     WHERE id=:id AND status='queued'

Exactly one worker can see rowcount 1, so two workers never run the same job.
Every later write also carries the claim token, which stops a worker whose
lease expired from clobbering the result of the worker that took over.
"""

import secrets
import socket
import os
from datetime import timedelta
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timeutils import utcnow
from app.models import Job, JobStatus


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"[:64]


def enqueue(
    db: Session,
    *,
    job_type: str,
    payload: dict,
    version_id: Optional[int] = None,
    created_by: Optional[int] = None,
    max_attempts: Optional[int] = None,
) -> Job:
    settings = get_settings()
    job = Job(
        job_type=job_type,
        status=JobStatus.QUEUED.value,
        payload=payload,
        version_id=version_id,
        created_by=created_by,
        max_attempts=max_attempts or settings.job_max_attempts,
    )
    db.add(job)
    db.flush()
    return job


def claim_next(db: Session, job_types: Optional[List[str]] = None) -> Optional[Job]:
    """Atomically take ownership of one queued job, or return None."""
    settings = get_settings()
    now = utcnow().replace(tzinfo=None)

    stmt = select(Job.id).where(Job.status == JobStatus.QUEUED.value)
    if job_types:
        stmt = stmt.where(Job.job_type.in_(job_types))
    candidate_ids = list(db.execute(stmt.order_by(Job.id).limit(10)).scalars())

    for job_id in candidate_ids:
        token = secrets.token_hex(16)
        lease = now + timedelta(seconds=settings.job_timeout_seconds)
        result = db.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == JobStatus.QUEUED.value)
            .values(
                status=JobStatus.RUNNING.value,
                claimed_by=worker_identity(),
                claim_token=token,
                lease_expires_at=lease,
                started_at=now,
                attempts=Job.attempts + 1,
                progress=0,
            )
        )
        db.commit()

        if result.rowcount == 1:
            job = db.get(Job, job_id)
            if job is not None and job.claim_token == token:
                return job

    return None


def heartbeat(db: Session, job: Job, progress: Optional[int] = None) -> None:
    """Extend the lease while work is still in flight."""
    settings = get_settings()
    values = {
        "lease_expires_at": utcnow().replace(tzinfo=None)
        + timedelta(seconds=settings.job_timeout_seconds)
    }
    if progress is not None:
        values["progress"] = max(0, min(100, int(progress)))

    db.execute(
        update(Job)
        .where(Job.id == job.id, Job.claim_token == job.claim_token)
        .values(**values)
    )
    db.commit()


def complete(db: Session, job: Job, result: Optional[dict] = None) -> bool:
    now = utcnow().replace(tzinfo=None)
    outcome = db.execute(
        update(Job)
        .where(Job.id == job.id, Job.claim_token == job.claim_token)
        .values(
            status=JobStatus.SUCCEEDED.value,
            result=result or {},
            progress=100,
            finished_at=now,
            error_message=None,
            lease_expires_at=None,
        )
    )
    return outcome.rowcount == 1


def fail(db: Session, job: Job, message: str, *, retry: bool = True) -> bool:
    """Mark a job failed, or requeue it when attempts remain."""
    now = utcnow().replace(tzinfo=None)
    can_retry = retry and job.attempts < job.max_attempts

    values = {
        "error_message": message[:2000],
        "lease_expires_at": None,
        "claim_token": None,
        "claimed_by": None,
    }
    if can_retry:
        values["status"] = JobStatus.QUEUED.value
    else:
        values["status"] = JobStatus.FAILED.value
        values["finished_at"] = now

    outcome = db.execute(
        update(Job)
        .where(Job.id == job.id, Job.claim_token == job.claim_token)
        .values(**values)
    )
    return outcome.rowcount == 1


def recover_stale(db: Session) -> int:
    """Requeue jobs whose worker died mid-run.

    Called on worker startup and periodically, so a crash or a restart does
    not strand a version in 'generating' forever.
    """
    now = utcnow().replace(tzinfo=None)
    result = db.execute(
        update(Job)
        .where(
            Job.status == JobStatus.RUNNING.value,
            Job.lease_expires_at.is_not(None),
            Job.lease_expires_at < now,
        )
        .values(
            status=JobStatus.QUEUED.value,
            claim_token=None,
            claimed_by=None,
            lease_expires_at=None,
            error_message="Worker lease expired; job requeued.",
        )
    )
    return int(result.rowcount or 0)


def exhausted_to_failed(db: Session) -> int:
    """Any job past its attempt budget becomes terminally failed."""
    now = utcnow().replace(tzinfo=None)
    result = db.execute(
        update(Job)
        .where(
            Job.status == JobStatus.QUEUED.value,
            Job.attempts >= Job.max_attempts,
        )
        .values(status=JobStatus.FAILED.value, finished_at=now)
    )
    return int(result.rowcount or 0)
