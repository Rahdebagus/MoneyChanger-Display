"""Scoped media delivery.

Media is private: every byte goes through an authorization check. Both
principal types can reach it, under different rules:

* a **user** may fetch media of a version in a branch they can access;
* a **device** may fetch media of any version that was ever published to it,
  which is what lets a TV refill its cache after a reconnect without needing
  a fresh signed URL.

URLs are immutable (an asset is written once, a new version gets a new id), so
responses carry a strong ETag and a long max-age. A player polling every 30
seconds re-downloads nothing.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import bearer_token, ensure_branch_access, get_current_user
from app.db.session import get_db
from app.models import Display, MediaAsset, PublicationTarget, RateVersion, User
from app.services import pairing, storage

logger = logging.getLogger(__name__)
router = APIRouter(tags=["media"])

CACHE_SECONDS = 60 * 60 * 24 * 30


def _version_for_asset(db: Session, asset_id: int) -> Optional[RateVersion]:
    return db.execute(
        select(RateVersion).where(
            or_(
                RateVersion.png_asset_id == asset_id,
                RateVersion.mp4_asset_id == asset_id,
                RateVersion.thumbnail_asset_id == asset_id,
                RateVersion.logo_asset_id == asset_id,
            )
        )
    ).scalars().first()


def _device_may_read(db: Session, display: Display, version_id: int) -> bool:
    assigned = db.execute(
        select(PublicationTarget.id)
        .where(
            PublicationTarget.display_id == display.id,
            PublicationTarget.version_id == version_id,
        )
        .limit(1)
    ).scalar()
    return bool(assigned)


@router.get("/media/{asset_id}")
def get_media(
    asset_id: int,
    request: Request,
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(bearer_token),
    if_none_match: Optional[str] = Header(None),
):
    asset = db.get(MediaAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Media tidak ditemukan.")

    version = _version_for_asset(db, asset_id)

    authorized = False
    if token:
        display = pairing.authenticate_device(db, token)
        if display is not None:
            authorized = version is not None and _device_may_read(db, display, version.id)
        else:
            user = _try_user(db, token)
            if user is not None:
                if version is not None:
                    ensure_branch_access(db, user, version.branch_id)
                authorized = True

    if not authorized:
        # Same response whether the asset is missing or merely forbidden, so
        # media ids cannot be probed.
        raise HTTPException(status_code=404, detail="Media tidak ditemukan.")

    if not storage.asset_exists(asset):
        logger.error("Media row %s has no file at %s", asset.id, asset.storage_key)
        raise HTTPException(status_code=404, detail="File media tidak ditemukan.")

    etag = f'"{asset.checksum}"' if asset.checksum else None
    if etag and if_none_match and if_none_match.strip() == etag:
        return Response(status_code=304, headers={"ETag": etag})

    headers = {"Cache-Control": f"private, max-age={CACHE_SECONDS}, immutable"}
    if etag:
        headers["ETag"] = etag
    if asset.checksum:
        headers["X-Content-Checksum"] = asset.checksum

    return FileResponse(
        storage.absolute_path(asset),
        media_type=asset.mime_type,
        headers=headers,
    )


def _try_user(db: Session, token: str) -> Optional[User]:
    from fastapi import HTTPException as _HTTPException

    try:
        return get_current_user(token=token, db=db)
    except _HTTPException:
        return None


@router.get("/media/{asset_id}/download")
def download_media(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Browser download with a friendly filename, for admins and staff."""
    asset = db.get(MediaAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Media tidak ditemukan.")

    version = _version_for_asset(db, asset_id)
    if version is not None:
        ensure_branch_access(db, user, version.branch_id)

    if not storage.asset_exists(asset):
        raise HTTPException(status_code=404, detail="File media tidak ditemukan.")

    suffix = "png" if asset.mime_type == "image/png" else asset.mime_type.split("/")[-1]
    label = f"v{version.version}" if version else f"asset{asset.id}"
    filename = f"pam_rate_board_{label}.{suffix}"

    return FileResponse(
        storage.absolute_path(asset),
        media_type=asset.mime_type,
        filename=filename,
    )
