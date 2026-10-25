"""Small durable receipt for retrying a save without creating another version."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.timeutils import utcnow


class SaveRequest(Base):
    __tablename__ = "save_requests"

    # SHA-256(user_id + client key): keys cannot expose another user's version.
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rate_versions.id", ondelete="SET NULL"), index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True,
        default=lambda: utcnow().replace(tzinfo=None),
    )
