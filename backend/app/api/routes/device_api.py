"""Endpoints a paired TV may call. Nothing here touches admin data.

A device credential grants exactly four things: read my assignment, send a
heartbeat, acknowledge what I managed to show, and acknowledge a command. It
cannot list displays, read other branches, or reach any admin route - those
live behind user dependencies that a device token can never satisfy.
"""

import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_device
from app.core.config import get_settings
from app.core.ratelimit import RateLimiter
from app.core.timeutils import utcnow
from app.db.session import get_db
from app.models import (
    Branch,
    Display,
    DisplayCommand,
    MediaAsset,
    RateVersion,
    TargetState,
)
from app.schemas.common import Message
from app.schemas.displays import (
    AcknowledgeRequest,
    AssignmentMedia,
    AssignmentResponse,
    CommandAckRequest,
    HeartbeatRequest,
    HeartbeatResponse,
    PairingClaimRequest,
    PairingClaimResponse,
    PairingStartResponse,
    PairingStatusResponse,
)
from app.services import audit, events, pairing, publishing, storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/device", tags=["device"])

_settings = get_settings()
_pairing_limiter = RateLimiter(
    _settings.pairing_rate_limit_attempts,
    _settings.pairing_rate_limit_window_seconds,
)

ACK_STATES = {
    TargetState.DOWNLOADING.value,
    TargetState.LOADING.value,
    TargetState.DISPLAYED.value,
    TargetState.FAILED.value,
}


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# --------------------------------------------------------------------------
# Pairing (unauthenticated - this is how a TV gets a credential)
# --------------------------------------------------------------------------
@router.post("/pairing/start", response_model=PairingStartResponse)
def start_pairing(request: Request, db: Session = Depends(get_db)):
    if not _pairing_limiter.check(f"start:{_client_key(request)}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak permintaan pairing. Coba lagi nanti.",
        )

    code, device_session, ttl = pairing.create_code(db)
    db.commit()
    return PairingStartResponse(code=code, device_session=device_session, expires_in=ttl)


@router.get("/pairing/status", response_model=PairingStatusResponse)
def pairing_status(
    request: Request,
    device_session: str = Query(..., max_length=128),
    db: Session = Depends(get_db),
):
    if not _pairing_limiter.check(f"status:{_client_key(request)}:{hashlib.sha256(device_session.encode()).hexdigest()}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak permintaan. Coba lagi nanti.",
        )

    state = pairing.pairing_state(db, device_session)
    return PairingStatusResponse(state=state)


@router.post("/pairing/claim", response_model=PairingClaimResponse)
def claim_pairing(
    payload: PairingClaimRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    if not _pairing_limiter.check(f"claim:{_client_key(request)}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak permintaan. Coba lagi nanti.",
        )

    try:
        display, secret = pairing.claim(db, payload.device_session)
    except pairing.PairingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    branch = db.get(Branch, display.branch_id) if display.branch_id else None

    audit.record(
        db,
        action="display.paired",
        actor_label=f"display:{display.id}",
        target_type="display",
        target_id=display.id,
        branch_id=display.branch_id,
        details={"name": display.name},
    )
    db.commit()

    return PairingClaimResponse(
        display_id=display.id,
        display_name=display.name,
        branch_name=branch.name if branch else None,
        device_token=secret,
        heartbeat_interval=_settings.heartbeat_interval_seconds,
        poll_interval=_settings.player_poll_interval_seconds,
    )


# --------------------------------------------------------------------------
# Authenticated device endpoints
# --------------------------------------------------------------------------
def _pending_command(db: Session, display: Display) -> Optional[dict]:
    command = db.execute(
        select(DisplayCommand)
        .where(
            DisplayCommand.display_id == display.id,
            DisplayCommand.acknowledged_at.is_(None),
        )
        .order_by(DisplayCommand.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if command is None:
        return None
    return {"id": command.id, "command": command.command}


def _assignment_media(db: Session, version: RateVersion) -> list:
    media = []
    for asset_id, kind in (
        (version.png_asset_id, "board_png"),
    ):
        if asset_id is None:
            continue
        asset = db.get(MediaAsset, asset_id)
        if asset is None or not storage.asset_exists(asset):
            continue
        media.append(
            AssignmentMedia(
                kind=kind,
                url=f"/api/media/{asset.id}",
                mime_type=asset.mime_type,
                checksum=asset.checksum,
                byte_size=asset.byte_size,
                width=asset.width,
                height=asset.height,
            )
        )
    return media


@router.get("/assignment", response_model=AssignmentResponse)
def get_assignment(
    display: Display = Depends(get_current_device),
    db: Session = Depends(get_db),
):
    """The single source of truth for what this TV should show.

    A player calls this on connect, on every websocket nudge, and on its poll
    fallback. The answer always reflects the database, never cached state, so
    a reconnecting player converges on the newest revision.
    """
    settings = get_settings()
    now = utcnow()

    target = publishing.current_target(db, display)
    command = _pending_command(db, display)

    if target is None:
        return AssignmentResponse(
            has_assignment=False,
            server_time=now,
            pending_command=command,
            heartbeat_interval=settings.heartbeat_interval_seconds,
            poll_interval=settings.player_poll_interval_seconds,
        )

    version = db.get(RateVersion, target.version_id)
    if version is None:
        return AssignmentResponse(
            has_assignment=False,
            server_time=now,
            pending_command=command,
            heartbeat_interval=settings.heartbeat_interval_seconds,
            poll_interval=settings.player_poll_interval_seconds,
        )

    return AssignmentResponse(
        has_assignment=True,
        revision=target.revision,
        version_id=version.id,
        version_label=f"v{version.version}",
        valid_until=target.valid_until,
        server_time=now,
        media=_assignment_media(db, version),
        pending_command=command,
        heartbeat_interval=settings.heartbeat_interval_seconds,
        poll_interval=settings.player_poll_interval_seconds,
    )


@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    payload: HeartbeatRequest,
    display: Display = Depends(get_current_device),
    db: Session = Depends(get_db),
):
    """Cheap liveness ping. Does no rendering work and loads no OCR model."""
    settings = get_settings()
    target = publishing.current_target(db, display)
    desired_revision = target.revision if target else 0

    reported = payload.revision if payload.revision is not None else display.reported_revision
    needs_update = bool(target is not None and reported < target.revision)

    db.commit()

    return HeartbeatResponse(
        server_time=utcnow(),
        desired_revision=desired_revision,
        needs_update=needs_update,
        pending_command=_pending_command(db, display),
        heartbeat_interval=settings.heartbeat_interval_seconds,
    )


@router.post("/acknowledge", response_model=Message)
def acknowledge(
    payload: AcknowledgeRequest,
    display: Display = Depends(get_current_device),
    db: Session = Depends(get_db),
):
    """Report progress or completion for a revision.

    A 'displayed' acknowledgement means the player decoded the media and swapped
    it in. It is evidence about the browser, not proof that the physical panel
    is powered on.
    """
    if payload.state not in ACK_STATES:
        raise HTTPException(status_code=400, detail="Status acknowledgement tidak dikenal.")

    target = publishing.acknowledge(
        db,
        display=display,
        revision=payload.revision,
        version_id=payload.version_id,
        state=payload.state,
        error_message=payload.error_message,
    )

    if target is None:
        db.commit()
        # Not an error: the revision is simply no longer current.
        return Message(message="Acknowledgement diabaikan (revisi tidak aktif).")

    db.commit()
    return Message(message="Acknowledgement diterima.")


@router.post("/command-ack", response_model=Message)
def acknowledge_command(
    payload: CommandAckRequest,
    display: Display = Depends(get_current_device),
    db: Session = Depends(get_db),
):
    """Close out a one-shot command so it is never executed twice."""
    command = db.get(DisplayCommand, payload.command_id)
    if command is None or command.display_id != display.id:
        raise HTTPException(status_code=404, detail="Perintah tidak ditemukan.")

    if command.acknowledged_at is None:
        command.acknowledged_at = utcnow().replace(tzinfo=None)
    db.commit()
    return Message(message="Perintah dikonfirmasi.")
