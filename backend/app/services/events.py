"""Cross-process event fan-out via a database outbox.

The database is the source of truth; these events are only a nudge that says
"something changed, go ask". A player that misses an event still converges
because it polls and because it re-reads its assignment on reconnect.
"""

from datetime import timedelta
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timeutils import utcnow
from app.models import EventOutbox

TOPIC_ASSIGNMENT = "display.assignment"
TOPIC_COMMAND = "display.command"
TOPIC_REVOKED = "display.revoked"
TOPIC_DISPLAY_STATE = "admin.display_state"
TOPIC_JOB = "admin.job"


def emit(
    db: Session,
    topic: str,
    *,
    display_id: Optional[int] = None,
    payload: Optional[dict] = None,
) -> EventOutbox:
    event = EventOutbox(
        topic=topic,
        display_id=display_id,
        payload=payload or {},
        created_at=utcnow().replace(tzinfo=None),
    )
    db.add(event)
    db.flush()
    return event


def latest_event_id(db: Session) -> int:
    value = db.execute(select(EventOutbox.id).order_by(EventOutbox.id.desc()).limit(1)).scalar()
    return int(value or 0)


def events_after(db: Session, cursor: int, limit: int = 200):
    stmt = (
        select(EventOutbox)
        .where(EventOutbox.id > cursor)
        .order_by(EventOutbox.id)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())


def prune(db: Session, limit: int = 1000) -> int:
    """Outbox rows are transient; keep the table from growing forever."""
    settings = get_settings()
    cutoff = (utcnow() - timedelta(hours=settings.event_retention_hours)).replace(tzinfo=None)
    ids = list(db.execute(
        select(EventOutbox.id).where(EventOutbox.created_at < cutoff)
        .order_by(EventOutbox.created_at, EventOutbox.id).limit(limit)
    ).scalars())
    if not ids:
        return 0
    result = db.execute(delete(EventOutbox).where(EventOutbox.id.in_(ids)))
    return int(result.rowcount or 0)
