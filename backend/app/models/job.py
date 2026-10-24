"""Durable background jobs and the websocket fan-out outbox."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IntPK, TimestampMixin
from app.models.enums import JobStatus


class Job(Base, IntPK, TimestampMixin):
    """A unit of slow work (OCR, PNG, MP4) owned by the worker process.

    Claiming uses a guarded UPDATE rather than SELECT ... FOR UPDATE SKIP
    LOCKED: MariaDB 10.4 has no SKIP LOCKED (it arrived in 10.6), and an
    UPDATE that checks rowcount == 1 is both portable and safe for any number
    of workers.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_created", "status", "created_at"),
        Index("ix_jobs_lease", "status", "lease_expires_at"),
    )

    job_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=JobStatus.QUEUED.value, index=True
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[Optional[dict]] = mapped_column(JSON)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # Set together when a worker claims the row; the token proves ownership so
    # a worker whose lease expired cannot overwrite the new owner's result.
    claimed_by: Mapped[Optional[str]] = mapped_column(String(64))
    claim_token: Mapped[Optional[str]] = mapped_column(String(64))
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    error_message: Mapped[Optional[str]] = mapped_column(Text)

    version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rate_versions.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    @property
    def is_terminal(self) -> bool:
        return self.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}


class EventOutbox(Base, IntPK):
    """Cross-process notification log for websockets.

    Any process (API or worker) appends here; every API process tails the
    table from its own cursor and pushes to the sockets it holds. That keeps
    broadcast correct across more than one process without adding Redis.
    """

    __tablename__ = "event_outbox"

    topic: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    display_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
