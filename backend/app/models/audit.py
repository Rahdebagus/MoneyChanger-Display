"""Append-only audit trail."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IntPK


class AuditLog(Base, IntPK):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_target", "target_type", "target_id"),
        Index("ix_audit_logs_created", "created_at"),
    )

    actor_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    actor_label: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    target_type: Mapped[Optional[str]] = mapped_column(String(32))
    target_id: Mapped[Optional[int]] = mapped_column(Integer)
    branch_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)

    # Redacted before it reaches here: never contains secrets or hashes.
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    request_id: Mapped[Optional[str]] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
