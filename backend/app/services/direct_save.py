"""A bounded, synchronous save/render transaction with durable retry identity."""

import base64
import binascii
import hashlib
import io
import json
import logging
import time
from contextlib import contextmanager

from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.models import MediaAsset, MediaKind, RateVersion, SaveRequest, VersionStatus
from app.services import audit, board_builder, rates, storage
from app.services.access import accessible_branch_ids, ensure_branch_access

logger = logging.getLogger(__name__)
MAX_LOGO_BYTES = 4 * 1024 * 1024


class SaveError(Exception):
    def __init__(self, message, status=503):
        self.message, self.status = message, status
        super().__init__(message)


def decode_logo(raw):
    if not raw:
        return None
    if len(raw) > MAX_LOGO_BYTES * 4 // 3 + 1024:
        raise SaveError("Ukuran logo maksimal 4MB.", 400)
    try:
        data = base64.b64decode(raw.split(",", 1)[-1], validate=True)
        if len(data) > MAX_LOGO_BYTES:
            raise ValueError("logo too large")
        with Image.open(io.BytesIO(data)) as image:
            if (image.width * image.height > 4_000_000 or max(image.size) > 4096
                    or image.height * 165 / image.width > 2048):
                raise ValueError("too many logo pixels")
            image.verify()
        return data
    except (ValueError, OSError, binascii.Error, Image.DecompressionBombError):
        raise SaveError("Logo tidak valid; maksimal 4MB dan 4 juta piksel.", 400)


@contextmanager
def render_slot(db):
    """One renderer per database, including multiple Passenger processes.

    MariaDB owns the lock, so a killed process cannot leave a stale lock file.
    The request session pins its connection across the two save commits.
    """
    connection = db.get_bind()
    if not isinstance(connection, Connection):
        raise RuntimeError("Direct saves require a connection-bound request session")
    database = connection.engine.url.database or "pam"
    name = "pam:png:" + hashlib.sha256(database.encode()).hexdigest()[:40]
    acquired = db.scalar(text("SELECT GET_LOCK(:name, :timeout)"), {
        "name": name, "timeout": get_settings().png_lock_timeout_seconds,
    })
    if acquired != 1:
        raise SaveError("Server sedang membuat PNG lain. Coba simpan lagi sebentar.")
    try:
        # Auth may have started a repeatable-read snapshot before another save.
        db.rollback()
        yield
    finally:
        db.rollback()
        try:
            db.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})
        except Exception:
            # Discard the physical connection so no advisory lock reaches the pool.
            connection.invalidate()
            logger.exception("Could not release PNG render lock")


def _branch(db, user, requested):
    allowed = accessible_branch_ids(db, user)
    if requested is not None:
        ensure_branch_access(db, user, requested)
        return requested
    if allowed is None:
        return None
    if len(allowed) == 1:
        return next(iter(allowed))
    raise SaveError("Pilih cabang yang ditugaskan ke akun Anda.", 400 if allowed else 403)


def _available(db, version):
    asset = db.get(MediaAsset, version.png_asset_id) if version.png_asset_id else None
    return version.status == VersionStatus.READY.value and asset is not None and storage.asset_exists(asset)


def save(db, user, payload):
    parsed = rates.normalise_input(payload.rates)
    if not rates.has_any_value(parsed):
        raise SaveError("Isi minimal satu nilai rate.", 400)
    logo = decode_logo(payload.logo_base64)
    branch_id = _branch(db, user, payload.branch_id)
    identity = {"rates": {code: str(parsed.get(code)) for code in rates.ALL_CURRENCIES},
                "title": payload.title, "subtitle": payload.subtitle,
                "branch_id": branch_id, "source_version_id": payload.source_version_id,
                "logo": hashlib.sha256(logo).hexdigest() if logo else None}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    key = hashlib.sha256(f"{user.id}:{payload.idempotency_key}".encode()).hexdigest() if payload.idempotency_key else None
    with render_slot(db):
        receipt = db.get(SaveRequest, key) if key else None
        if receipt is not None:
            if receipt.payload_hash != fingerprint:
                raise SaveError("Kunci simpan sudah dipakai untuk data berbeda.", 409)
            if receipt.version_id is None:
                raise SaveError("Versi dari permintaan ini sudah dihapus. Mulai penyimpanan baru.", 410)
            version = db.scalar(select(RateVersion).where(
                RateVersion.id == receipt.version_id,
            ).with_for_update().execution_options(populate_existing=True))
            ensure_branch_access(db, user, version.branch_id)
            if _available(db, version):
                return version
            if version.status == VersionStatus.ARCHIVED.value:
                raise SaveError("Versi dari permintaan ini sudah diarsipkan.", 409)
        else:
            source = None
            if payload.source_version_id is not None:
                source = db.execute(select(RateVersion).where(
                    RateVersion.id == payload.source_version_id,
                ).with_for_update()).scalar_one_or_none()
                if source is None:
                    raise SaveError("Versi sumber tidak ditemukan.", 404)
                ensure_branch_access(db, user, source.branch_id)
            logo_id = source.logo_asset_id if source else None
            if logo:
                logo_id = storage.create_asset(db, kind=MediaKind.LOGO.value,
                    storage_key=f"logos/{storage.checksum_name(logo)}.png", data=logo).id
            board = rates.get_or_create_default_board(db, owner_id=user.id, branch_id=branch_id, title=payload.title)
            version = rates.create_version(db, board=board, rates=parsed,
                board_title=payload.title, board_subtitle=payload.subtitle,
                created_by=user.id, branch_id=branch_id, logo_asset_id=logo_id,
                source_version_id=source.id if source else None,
                config_snapshot={"title": payload.title, "subtitle": payload.subtitle, "has_custom_logo": logo_id is not None})
            if key:
                db.add(SaveRequest(key_hash=key, payload_hash=fingerprint, version_id=version.id))
            audit.record(db, action="version.created", actor_user_id=user.id,
                         actor_label=user.username, target_type="rate_version",
                         target_id=version.id, branch_id=branch_id, details={"version": version.version})
        version.status = VersionStatus.GENERATING.value
        version.error_message = None
        db.commit()  # Durable rates + retry receipt, before any PNG work.
        return render_saved(db, version)


def render_saved(db, version):
    version_id = version.id
    started = time.monotonic()
    try:
        board_builder.build_board(db, version)
        elapsed = time.monotonic() - started
        if elapsed > get_settings().png_render_budget_seconds:
            raise TimeoutError("PNG rendering exceeded its configured budget")
        asset = db.get(MediaAsset, version.png_asset_id)
        if asset is None or not storage.asset_exists(asset):
            raise OSError("PNG was not durably written")
        rates.mark_ready(db, version)
        db.commit()
        logger.info("PNG ready version_id=%s render_seconds=%.3f", version_id, elapsed)
        return version
    except Exception as error:
        logger.exception("Direct PNG save failed version_id=%s", version_id)
        db.rollback()
        db.expire_all()
        try:
            current = db.get(RateVersion, version_id)
            # A connection error can occur after the server committed. Never
            # delete that valid image or regress its status to failed.
            if current and _available(db, current):
                return current
            if current:
                rates.mark_failed(db, current, f"PNG gagal dibuat ({type(error).__name__}). Coba simpan ulang dengan data yang sama.")
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not persist failed PNG status version_id=%s", version_id)
        raise SaveError("PNG gagal dibuat. Data tersimpan; coba simpan ulang dengan data yang sama.") from error
