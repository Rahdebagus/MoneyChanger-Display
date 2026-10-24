"""Media asset metadata. Bytes live on disk; the database points at them."""

from typing import Optional

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IntPK, TimestampMixin
from app.models.enums import MediaStatus


class MediaAsset(Base, IntPK, TimestampMixin):
    __tablename__ = "media_assets"

    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # Path relative to settings.media_path — never an absolute host path, so
    # the storage volume can move between machines and containers.
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    checksum: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=MediaStatus.PENDING.value)
