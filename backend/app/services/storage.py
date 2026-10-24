"""Durable media storage.

Bytes live on disk under settings.media_path; the database only holds the
relative storage key plus metadata. Writes are atomic (temp file then
os.replace) so a crash mid-write can never leave a half-written PNG that a TV
would try to display.
"""

import os
import shutil
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import checksum_bytes
from app.core.timeutils import utcnow
from app.models import MediaAsset, MediaStatus

MIME_BY_KIND = {
    "board_png": "image/png",
    "thumbnail": "image/jpeg",
    "board_mp4": "video/mp4",
    "logo": "image/png",
}

EXT_BY_KIND = {
    "board_png": "png",
    "thumbnail": "jpg",
    "board_mp4": "mp4",
    "logo": "png",
}


@dataclass
class StoredFile:
    storage_key: str
    byte_size: int
    checksum: str


def _absolute(storage_key: str) -> Path:
    settings = get_settings()
    # Reject traversal: a storage key is always a simple relative path we
    # generated ourselves, never user input.
    candidate = (settings.media_path / storage_key).resolve()
    root = settings.media_path.resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError("storage key escapes media root")
    return candidate


def absolute_path(asset: MediaAsset) -> Path:
    return _absolute(asset.storage_key)


def write_bytes(storage_key: str, data: bytes) -> StoredFile:
    target = _absolute(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)

    tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, target)

    return StoredFile(
        storage_key=storage_key,
        byte_size=len(data),
        checksum=checksum_bytes(data),
    )


def checksum_name(data: bytes) -> str:
    """Content-addressed name: identical logos reuse one file on disk."""
    return checksum_bytes(data)[:32]


def version_storage_key(version_id: int, kind: str) -> str:
    """Immutable, unique per version.

    Deliberately not a single shared name such as preview_board.png: two users
    generating at the same time must never write to the same file.
    """
    ext = EXT_BY_KIND.get(kind, "bin")
    return f"versions/{version_id:08d}/{kind}.{ext}"


def create_asset(
    db: Session,
    *,
    kind: str,
    storage_key: str,
    data: bytes,
    width: Optional[int] = None,
    height: Optional[int] = None,
    mime_type: Optional[str] = None,
) -> MediaAsset:
    # Content-addressed logos can be shared. Lock an existing row so cleanup
    # cannot remove its file while another version is being linked to it.
    existing = db.execute(
        select(MediaAsset).where(MediaAsset.storage_key == storage_key).with_for_update()
    ).scalar_one_or_none()
    if existing is not None:
        if not asset_exists(existing):
            write_bytes(storage_key, data)
        return existing
    stored = write_bytes(storage_key, data)
    asset = MediaAsset(
        kind=kind,
        storage_key=stored.storage_key,
        mime_type=mime_type or MIME_BY_KIND.get(kind, "application/octet-stream"),
        checksum=stored.checksum,
        byte_size=stored.byte_size,
        width=width,
        height=height,
        status=MediaStatus.READY.value,
    )
    db.add(asset)
    db.flush()
    return asset


def read_asset(asset: MediaAsset) -> bytes:
    with open(absolute_path(asset), "rb") as handle:
        return handle.read()


def asset_exists(asset: MediaAsset) -> bool:
    try:
        return absolute_path(asset).is_file()
    except ValueError:
        return False


def delete_version_files(version_id: int) -> int:
    """Remove the whole directory of a version. Returns bytes freed."""
    settings = get_settings()
    if not isinstance(version_id, int) or version_id <= 0:
        raise ValueError("invalid version id")
    directory = _absolute(f"versions/{version_id:08d}")
    expected_parent = (settings.media_path / "versions").resolve()
    if directory.parent != expected_parent or directory.name != f"{version_id:08d}":
        raise ValueError("version directory escapes its expected location")
    if not directory.is_dir():
        return 0
    freed = sum(f.stat().st_size for f in directory.rglob("*") if f.is_file())
    shutil.rmtree(directory)
    return freed


def sweep_orphan_temp_files(max_age_hours: int = 6) -> Tuple[int, int]:
    """Delete stale .tmp files left behind by a crashed write.

    Targeted: only files matching our own temp suffix, only when old enough to
    be certain no write is still in flight.
    """
    settings = get_settings()
    cutoff = utcnow() - timedelta(hours=max_age_hours)
    removed = 0
    freed = 0
    for root in (settings.media_path, settings.tmp_path):
        if not root.is_dir():
            continue
        for path in root.rglob("*.tmp"):
            try:
                stat = path.stat()
                if stat.st_mtime < cutoff.timestamp():
                    freed += stat.st_size
                    path.unlink()
                    removed += 1
            except OSError:
                continue
    return removed, freed
