"""Users, branches, and the staff-to-branch access grants."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IntPK, TimestampMixin
from app.models.enums import UserRole


class User(Base, IntPK, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=UserRole.STAFF.value)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Bumped on password change / deactivation so every issued JWT stops
    # validating immediately, without needing a token blacklist.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    branch_links: Mapped[List["UserBranch"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN


class Branch(Base, IntPK, TimestampMixin):
    __tablename__ = "branches"

    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Makassar")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    user_links: Mapped[List["UserBranch"]] = relationship(
        back_populates="branch", cascade="all, delete-orphan"
    )


class UserBranch(Base, IntPK):
    __tablename__ = "user_branches"
    __table_args__ = (UniqueConstraint("user_id", "branch_id", name="uq_user_branches_user_id"),)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )

    user: Mapped[User] = relationship(back_populates="branch_links")
    branch: Mapped[Branch] = relationship(back_populates="user_links")
