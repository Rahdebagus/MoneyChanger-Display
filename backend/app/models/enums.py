"""String enums used across models.

Python 3.10 has no enum.StrEnum, so these subclass (str, Enum): members compare
equal to their plain string value, which is what the VARCHAR columns store.

Stored as VARCHAR rather than native SQL ENUM: adding a value later is a code
change instead of a table rebuild, and MariaDB ENUM reordering is a known
migration hazard.
"""

from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    STAFF = "staff"


class VersionStatus(str, Enum):
    DRAFT = "draft"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"
    ARCHIVED = "archived"


class MediaKind(str, Enum):
    BOARD_PNG = "board_png"
    BOARD_MP4 = "board_mp4"
    THUMBNAIL = "thumbnail"
    LOGO = "logo"


class MediaStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class DisplayStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    NEVER_SEEN = "never_seen"


class PublicationState(str, Enum):
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TargetState(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    LOADING = "loading"
    DISPLAYED = "displayed"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class JobType(str, Enum):
    GENERATE_BOARD = "generate_board"
    GENERATE_VIDEO = "generate_video"
    OCR_EXTRACT = "ocr_extract"
    CLEANUP_MEDIA = "cleanup_media"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CommandType(str, Enum):
    REFRESH = "refresh"
