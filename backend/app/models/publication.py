"""Publications: one admin action, fanned out to per-display targets."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IntPK, TimestampMixin
from app.models.enums import PublicationState, TargetState


class Publication(Base, IntPK, TimestampMixin):
    __tablename__ = "publications"
    __table_args__ = (
        Index("ix_publications_state_scheduled", "state", "scheduled_at"),
        Index("ix_publications_version", "version_id", "created_at"),
    )

    version_id: Mapped[int] = mapped_column(
        ForeignKey("rate_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PublicationState.ACTIVE.value, index=True
    )
    # Either display or branch scope. Branch scope is resolved to concrete
    # displays at publish time and never re-resolved later, so a display added
    # tomorrow does not silently inherit yesterday's publish.
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="display")
    scope_branch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("branches.id", ondelete="SET NULL")
    )

    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    effective_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Retrying the same publish request must not publish twice.
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), unique=True)

    # Display ids chosen when a schedule was created. The scheduler fires at
    # exactly this set, so a display paired in the meantime is not swept in.
    scheduled_display_ids: Mapped[Optional[list]] = mapped_column(JSON)

    rollback_of_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("publications.id", ondelete="SET NULL")
    )
    note: Mapped[Optional[str]] = mapped_column(String(255))

    targets: Mapped[List["PublicationTarget"]] = relationship(
        back_populates="publication", cascade="all, delete-orphan"
    )


class PublicationTarget(Base, IntPK, TimestampMixin):
    """What one specific display is asked to show, and what it reports back."""

    __tablename__ = "publication_targets"
    __table_args__ = (
        UniqueConstraint("display_id", "revision", name="uq_publication_targets_display_id"),
        Index("ix_publication_targets_display_state", "display_id", "state"),
    )

    publication_id: Mapped[int] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_id: Mapped[int] = mapped_column(
        ForeignKey("displays.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[int] = mapped_column(
        ForeignKey("rate_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TargetState.PENDING.value, index=True
    )

    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    publication: Mapped[Publication] = relationship(back_populates="targets")
