"""Render a stored version into its media assets.

The board PNG is produced by the original generator at its original size and
quality - nothing here downsamples it. The small thumbnail used by the history
list is a separate asset, so list performance never costs board quality.
"""

import io
import logging
from typing import Optional, Tuple

from PIL import Image
from sqlalchemy.orm import Session

from app.models import MediaKind, RateVersion
from app.services import storage
from app.services.generator import generate_rate_image
from app.services.rates import rates_payload

logger = logging.getLogger(__name__)

THUMBNAIL_WIDTH = 480


def _image_size(data: bytes) -> Tuple[Optional[int], Optional[int]]:
    with Image.open(io.BytesIO(data)) as img:
        if img.format != "PNG" or img.size != (1280, 720):
            raise ValueError("Renderer returned an invalid PNG board")
        size = img.size
        img.verify()
        return size


def _make_thumbnail(png_bytes: bytes) -> Optional[bytes]:
    try:
        with Image.open(io.BytesIO(png_bytes)) as img:
            img = img.convert("RGB")
            ratio = THUMBNAIL_WIDTH / img.width
            size = (THUMBNAIL_WIDTH, max(1, int(img.height * ratio)))
            thumb = img.resize(size, Image.LANCZOS)
            buffer = io.BytesIO()
            thumb.save(buffer, format="JPEG", quality=82, optimize=True)
            return buffer.getvalue()
    except Exception:
        logger.warning("Thumbnail generation failed", exc_info=True)
        return None


def _logo_bytes(db: Session, version: RateVersion) -> Optional[bytes]:
    if version.logo_asset_id is None:
        return None
    from app.models import MediaAsset

    asset = db.get(MediaAsset, version.logo_asset_id)
    if asset is None or not storage.asset_exists(asset):
        return None
    try:
        return storage.read_asset(asset)
    except OSError:
        return None


def build_board(db: Session, version: RateVersion) -> RateVersion:
    """Write PNG and thumbnail; the caller commits readiness after verification.

    Status only moves to ready once the media is written and recorded. A
    version that fails here stays failed and can never be published.
    """
    payload = rates_payload(version.items)

    png_bytes = generate_rate_image(
        payload,
        title=version.board_title,
        subtitle=version.board_subtitle,
        logo_bytes=_logo_bytes(db, version),
    )

    width, height = _image_size(png_bytes)
    png_asset = storage.create_asset(
        db,
        kind=MediaKind.BOARD_PNG.value,
        storage_key=storage.version_storage_key(version.id, MediaKind.BOARD_PNG.value),
        data=png_bytes,
        width=width,
        height=height,
    )
    version.png_asset_id = png_asset.id

    thumb_bytes = _make_thumbnail(png_bytes)
    if thumb_bytes:
        thumb_asset = storage.create_asset(
            db,
            kind=MediaKind.THUMBNAIL.value,
            storage_key=storage.version_storage_key(version.id, MediaKind.THUMBNAIL.value),
            data=thumb_bytes,
        )
        version.thumbnail_asset_id = thumb_asset.id

    db.flush()
    return version
