"""Rate boards, immutable versions, and the individual rate rows.

A *version* is the unit that gets generated, saved and published. Editing an
existing version never mutates it; it seeds a new one. That is what makes
"edit the board that is currently on screen" safe.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    DECIMAL,
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
from app.models.enums import VersionStatus


class RateBoard(Base, IntPK, TimestampMixin):
    __tablename__ = "rate_boards"

    title: Mapped[str] = mapped_column(String(128), nullable=False)
    branch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("branches.id", ondelete="SET NULL"), index=True
    )
    owner_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    versions: Mapped[List["RateVersion"]] = relationship(
        back_populates="board", cascade="all, delete-orphan"
    )


class RateVersion(Base, IntPK, TimestampMixin):
    __tablename__ = "rate_versions"
    __table_args__ = (
        UniqueConstraint("board_id", "version", name="uq_rate_versions_board_id"),
        Index("ix_rate_versions_board_status", "board_id", "status"),
        Index("ix_rate_versions_status_created", "status", "created_at"),
    )

    board_id: Mapped[int] = mapped_column(
        ForeignKey("rate_boards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=VersionStatus.DRAFT.value, index=True
    )

    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    branch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("branches.id", ondelete="SET NULL"), index=True
    )

    # Version this one was opened from, so "open as new version" is traceable.
    source_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rate_versions.id", ondelete="SET NULL")
    )

    # Everything needed to re-render this exact board: title, subtitle, logo
    # asset reference, generator settings. Snapshotted so later config changes
    # never retroactively alter a published version.
    board_title: Mapped[str] = mapped_column(String(128), nullable=False, default="MONEY CHANGER")
    board_subtitle: Mapped[str] = mapped_column(
        String(191), nullable=False, default="PT. PRADNYANA ARTHA MANDIRI"
    )
    logo_asset_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    config_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    png_asset_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    mp4_asset_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    thumbnail_asset_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL")
    )

    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    board: Mapped[RateBoard] = relationship(back_populates="versions")
    items: Mapped[List["RateItem"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="RateItem.sort_order",
    )
    png_asset: Mapped[Optional["MediaAsset"]] = relationship(foreign_keys=[png_asset_id])
    mp4_asset: Mapped[Optional["MediaAsset"]] = relationship(foreign_keys=[mp4_asset_id])
    thumbnail_asset: Mapped[Optional["MediaAsset"]] = relationship(
        foreign_keys=[thumbnail_asset_id]
    )
    logo_asset: Mapped[Optional["MediaAsset"]] = relationship(foreign_keys=[logo_asset_id])

    @property
    def is_ready(self) -> bool:
        return self.status == VersionStatus.READY


class RateItem(Base, IntPK):
    """One currency row of one version.

    ``value`` is DECIMAL and **nullable**. NULL renders as "-" on the board and
    is semantically different from 0 — a currency that is not traded today is
    not a currency worth zero rupiah.
    """

    __tablename__ = "rate_items"
    __table_args__ = (
        UniqueConstraint("version_id", "currency", name="uq_rate_items_version_id"),
        Index("ix_rate_items_version_order", "version_id", "sort_order"),
    )

    version_id: Mapped[int] = mapped_column(
        ForeignKey("rate_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    # Printed under the code on the board, e.g. "(100, 50)" for USD.
    denomination: Mapped[Optional[str]] = mapped_column(String(32))
    value: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(18, 4))
    column_side: Mapped[str] = mapped_column(String(8), nullable=False, default="left")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    version: Mapped[RateVersion] = relationship(back_populates="items")


from app.models.media import MediaAsset  # noqa: E402  (resolves the string refs above)
