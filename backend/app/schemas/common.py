"""Shared response shapes."""

from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        if self.page_size <= 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size


class PageParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class Message(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    """What a client sees when something fails.

    Carries a request id so a user can quote it, and never a traceback or an
    internal file path.
    """

    detail: str
    request_id: Optional[str] = None


class TimestampPair(BaseModel):
    """UTC plus the same instant rendered in the branch timezone."""

    utc: datetime
    local: datetime
    timezone: str
