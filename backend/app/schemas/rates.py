"""Rate version payloads.

Rates cross the wire as strings. A JSON number would be parsed as a float by
every JavaScript client, and 16950.0001 is not a rate anybody typed. Strings
keep the DECIMAL exact in both directions, and null stays distinct from "0".
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class RateItemOut(ORMModel):
    currency: str
    denomination: Optional[str] = None
    value: Optional[str] = None
    column_side: str
    sort_order: int


class MediaOut(ORMModel):
    id: int
    kind: str
    mime_type: str
    checksum: Optional[str] = None
    byte_size: int
    width: Optional[int] = None
    height: Optional[int] = None
    url: Optional[str] = None


class VersionSummary(BaseModel):
    id: int
    board_id: int
    version: int
    status: str
    board_title: str
    board_subtitle: str
    created_at: datetime
    generated_at: Optional[datetime] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    source_version_id: Optional[int] = None
    thumbnail_url: Optional[str] = None
    png_url: Optional[str] = None
    mp4_url: Optional[str] = None
    is_live: bool = False
    delete_blocked_reason: Optional[str] = None
    error_message: Optional[str] = None


class VersionDetail(VersionSummary):
    items: List[RateItemOut] = []
    rates: Dict[str, Optional[str]] = {}
    config_snapshot: dict = {}


class VersionCreate(BaseModel):
    """Save rates and return only after the PNG is available."""

    rates: Dict[str, Optional[str]] = Field(default_factory=dict)
    title: str = Field("MONEY CHANGER", max_length=128)
    subtitle: str = Field("PT. PRADNYANA ARTHA MANDIRI", max_length=191)
    logo_base64: Optional[str] = None
    branch_id: Optional[int] = None
    source_version_id: Optional[int] = None
    idempotency_key: Optional[str] = Field(None, min_length=8, max_length=128)


class JobOut(ORMModel):
    id: int
    job_type: str
    status: str
    progress: int
    attempts: int
    max_attempts: int
    version_id: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[dict] = None


class GenerateResponse(BaseModel):
    version: VersionSummary
    # Deprecated response slot, retained for clients that inspect the envelope.
    job: Optional[JobOut] = None
