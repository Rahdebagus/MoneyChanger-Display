"""Importing this package registers every table on Base.metadata."""

from app.db.base import Base
from app.models.audit import AuditLog
from app.models.display import Display, DisplayCommand, PairingCode
from app.models.enums import (
    CommandType,
    DisplayStatus,
    JobStatus,
    JobType,
    MediaKind,
    MediaStatus,
    PublicationState,
    TargetState,
    UserRole,
    VersionStatus,
)
from app.models.job import EventOutbox, Job
from app.models.media import MediaAsset
from app.models.publication import Publication, PublicationTarget
from app.models.rate import RateBoard, RateItem, RateVersion
from app.models.user import Branch, User, UserBranch

__all__ = [
    "Base",
    "AuditLog",
    "Branch",
    "CommandType",
    "Display",
    "DisplayCommand",
    "DisplayStatus",
    "EventOutbox",
    "Job",
    "JobStatus",
    "JobType",
    "MediaAsset",
    "MediaKind",
    "MediaStatus",
    "PairingCode",
    "Publication",
    "PublicationState",
    "PublicationTarget",
    "RateBoard",
    "RateItem",
    "RateVersion",
    "TargetState",
    "User",
    "UserBranch",
    "UserRole",
    "VersionStatus",
]
