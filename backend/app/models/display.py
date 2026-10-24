"""Displays (TVs), their pairing codes, and one-shot commands."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IntPK, TimestampMixin
from app.models.enums import CommandType


class Display(Base, IntPK, TimestampMixin):
    __tablename__ = "displays"
    __table_args__ = (Index("ix_displays_branch_active", "branch_id", "is_active"),)

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    branch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("branches.id", ondelete="SET NULL"), index=True
    )

    # Only the hash of the device secret is stored.
    credential_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    credential_issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255))

    # Monotonic per display. Every publish to this display takes the next
    # number; the player ignores anything lower than what it already shows,
    # which is what stops a slow old update from replacing a newer one.
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    desired_target_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "publication_targets.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_displays_desired_target_id",
        ),
        index=True,
    )
    reported_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reported_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rate_versions.id", ondelete="SET NULL")
    )
    reported_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_error: Mapped[Optional[str]] = mapped_column(Text)


class PairingCode(Base, IntPK, TimestampMixin):
    """Short-lived code shown on an unpaired TV.

    Only the hash is stored. A code is single use: ``consumed_at`` is set in
    the same transaction that mints the device credential.
    """

    __tablename__ = "pairing_codes"
    __table_args__ = (Index("ix_pairing_codes_expires", "expires_at", "consumed_at"),)

    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # Random per-browser value: the TV that requested the code is the only one
    # allowed to claim the credential afterwards.
    device_session_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Set by the admin when approving; the device then claims its credential.
    approved_display_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("displays.id", ondelete="CASCADE")
    )
    approved_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    display: Mapped[Optional[Display]] = relationship(foreign_keys=[approved_display_id])


class DisplayCommand(Base, IntPK, TimestampMixin):
    """One-shot instruction to a player, e.g. refresh.

    Carries an id and needs an acknowledgement, so a player that reconnects
    does not re-run a command it already executed — that is what would
    otherwise turn "refresh" into a reload loop.
    """

    __tablename__ = "display_commands"
    __table_args__ = (Index("ix_display_commands_pending", "display_id", "acknowledged_at"),)

    display_id: Mapped[int] = mapped_column(
        ForeignKey("displays.id", ondelete="CASCADE"), nullable=False, index=True
    )
    command: Mapped[str] = mapped_column(String(32), nullable=False, default=CommandType.REFRESH.value)
    issued_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
