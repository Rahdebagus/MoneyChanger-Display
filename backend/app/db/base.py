"""Declarative base and column conventions shared by every model."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Explicit naming so Alembic autogenerate emits stable constraint names
# instead of letting MariaDB invent them.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class TimestampMixin:
    """created_at / updated_at maintained by the database in UTC.

    ``func.now()`` on MariaDB is the server clock. The deployment docs require
    the database server to run in UTC so these line up with the application's
    own ``utcnow()``.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class IntPK:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
