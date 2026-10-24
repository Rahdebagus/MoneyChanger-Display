"""Websocket endpoints for players and the admin dashboard.

Browsers cannot set an Authorization header on a websocket, and putting a
secret in the query string would leak it into proxy and server logs. The token
travels in the Sec-WebSocket-Protocol header instead:

    new WebSocket(url, ["bearer", token])

The server echoes back only the "bearer" subprotocol, never the token.
"""

import logging
from typing import Optional, Tuple

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models import Display, User, UserRole
from app.services import pairing
from app.services.realtime import registry

logger = logging.getLogger(__name__)
router = APIRouter(tags=["realtime"])

SUBPROTOCOL = "bearer"


def _extract_token(websocket: WebSocket) -> Tuple[Optional[str], bool]:
    """Pull the token out of the subprotocol list. Returns (token, offered)."""
    raw = websocket.headers.get("sec-websocket-protocol")
    if not raw:
        return None, False
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) >= 2 and parts[0] == SUBPROTOCOL:
        return parts[1], True
    return None, SUBPROTOCOL in parts


def _resolve_device(token: str) -> Optional[int]:
    db = SessionLocal()
    try:
        display = pairing.authenticate_device(db, token)
        return display.id if display else None
    finally:
        db.close()


def _resolve_user(token: str) -> Optional[int]:
    payload = decode_access_token(token)
    if not payload:
        return None
    db = SessionLocal()
    try:
        user = db.get(User, int(payload.get("sub", 0)))
        if user is None or not user.is_active:
            return None
        if int(payload.get("tv", -1)) != int(user.token_version):
            return None
        return user.id
    except (TypeError, ValueError):
        return None
    finally:
        db.close()


@router.websocket("/ws/device")
async def device_socket(websocket: WebSocket):
    token, offered = _extract_token(websocket)
    if not token:
        await websocket.close(code=4401)
        return

    import asyncio

    display_id = await asyncio.to_thread(_resolve_device, token)
    if display_id is None:
        await websocket.close(code=4401)
        return

    await websocket.accept(subprotocol=SUBPROTOCOL if offered else None)
    await registry.add_device(display_id, websocket)
    logger.info("Display %s websocket connected", display_id)

    try:
        await websocket.send_json({"type": "connected", "display_id": display_id})
        while True:
            # Players do not push state over the socket; acknowledgements go
            # through the REST API so they are transactional. Reads here just
            # keep the connection alive and detect disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("Device websocket error", exc_info=True)
    finally:
        await registry.remove_device(display_id, websocket)
        if websocket.client_state is not WebSocketState.DISCONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass


@router.websocket("/ws/admin")
async def admin_socket(websocket: WebSocket):
    token, offered = _extract_token(websocket)
    if not token:
        await websocket.close(code=4401)
        return

    import asyncio

    user_id = await asyncio.to_thread(_resolve_user, token)
    if user_id is None:
        await websocket.close(code=4401)
        return

    await websocket.accept(subprotocol=SUBPROTOCOL if offered else None)
    await registry.add_admin(websocket)

    try:
        await websocket.send_json({"type": "connected"})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("Admin websocket error", exc_info=True)
    finally:
        await registry.remove_admin(websocket)
        if websocket.client_state is not WebSocketState.DISCONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass
