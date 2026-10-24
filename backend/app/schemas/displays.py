"""Display, pairing and publication payloads."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# --------------------------------------------------------------------------
# Pairing
# --------------------------------------------------------------------------
class PairingStartResponse(BaseModel):
    code: str
    device_session: str
    expires_in: int


class PairingStatusResponse(BaseModel):
    state: str
    display_id: Optional[int] = None
    display_name: Optional[str] = None


class PairingClaimRequest(BaseModel):
    device_session: str = Field(min_length=10, max_length=128)


class PairingClaimResponse(BaseModel):
    display_id: int
    display_name: str
    branch_name: Optional[str] = None
    device_token: str
    heartbeat_interval: int
    poll_interval: int


class PairingApproveRequest(BaseModel):
    code: str = Field(min_length=4, max_length=16)
    name: str = Field(min_length=1, max_length=128)
    branch_id: Optional[int] = None


# --------------------------------------------------------------------------
# Displays (admin view)
# --------------------------------------------------------------------------
class DisplayOut(BaseModel):
    id: int
    name: str
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    is_active: bool
    is_paired: bool
    connection: str
    last_seen_at: Optional[datetime] = None
    desired_revision: int
    desired_version_id: Optional[int] = None
    desired_version_label: Optional[str] = None
    reported_revision: int
    reported_version_id: Optional[int] = None
    reported_version_label: Optional[str] = None
    target_state: Optional[str] = None
    is_stale: bool = False
    last_error: Optional[str] = None
    revoked_at: Optional[datetime] = None


class DisplayUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    branch_id: Optional[int] = None
    is_active: Optional[bool] = None


# --------------------------------------------------------------------------
# Device-facing
# --------------------------------------------------------------------------
class AssignmentMedia(BaseModel):
    kind: str
    url: str
    mime_type: str
    checksum: Optional[str] = None
    byte_size: int
    width: Optional[int] = None
    height: Optional[int] = None


class AssignmentResponse(BaseModel):
    """What a player must show right now.

    revision is the ordering key. A player that already shows a higher
    revision ignores this payload.
    """

    has_assignment: bool
    revision: int = 0
    version_id: Optional[int] = None
    version_label: Optional[str] = None
    valid_until: Optional[datetime] = None
    server_time: datetime
    media: List[AssignmentMedia] = []
    pending_command: Optional[dict] = None
    heartbeat_interval: int
    poll_interval: int


class HeartbeatRequest(BaseModel):
    revision: Optional[int] = None
    version_id: Optional[int] = None
    status: Optional[str] = None


class HeartbeatResponse(BaseModel):
    server_time: datetime
    desired_revision: int
    needs_update: bool
    pending_command: Optional[dict] = None
    heartbeat_interval: int


class AcknowledgeRequest(BaseModel):
    revision: int = Field(ge=0)
    version_id: Optional[int] = None
    state: str
    error_message: Optional[str] = Field(None, max_length=500)


class CommandAckRequest(BaseModel):
    command_id: int


# --------------------------------------------------------------------------
# Publications
# --------------------------------------------------------------------------
class PublishRequest(BaseModel):
    version_id: int
    display_ids: List[int] = []
    branch_id: Optional[int] = None
    scheduled_at: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    idempotency_key: Optional[str] = Field(None, max_length=64)
    note: Optional[str] = Field(None, max_length=255)


class PublicationTargetOut(BaseModel):
    id: int
    display_id: int
    display_name: Optional[str] = None
    revision: int
    state: str
    acknowledged_at: Optional[datetime] = None
    error_message: Optional[str] = None


class PublicationOut(BaseModel):
    id: int
    version_id: int
    version_label: Optional[str] = None
    state: str
    scope: str
    scope_branch_id: Optional[int] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    scheduled_at: Optional[datetime] = None
    effective_at: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    rollback_of_id: Optional[int] = None
    note: Optional[str] = None
    targets: List[PublicationTargetOut] = []


class RollbackRequest(BaseModel):
    display_ids: List[int] = []
    idempotency_key: Optional[str] = Field(None, max_length=64)


class AuditOut(ORMModel):
    id: int
    actor_user_id: Optional[int] = None
    actor_label: str
    action: str
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    branch_id: Optional[int] = None
    details: dict = {}
    request_id: Optional[str] = None
    created_at: datetime


class DashboardStats(BaseModel):
    displays_total: int
    displays_online: int
    displays_offline: int
    displays_stale: int
    versions_total: int
    versions_ready: int
    live_version_id: Optional[int] = None
    live_version_label: Optional[str] = None
    last_publish_at: Optional[datetime] = None
    last_publish_by: Optional[str] = None
    pending_jobs: int
    failed_jobs: int
    scheduled_publications: int
