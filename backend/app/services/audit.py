"""Audit trail writer. Never records a secret."""

from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging import get_request_id, redact
from app.core.timeutils import utcnow
from app.models import AuditLog


def record(
    db: Session,
    *,
    action: str,
    actor_user_id: Optional[int] = None,
    actor_label: str = "system",
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    details: Optional[dict] = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        actor_label=actor_label[:64],
        action=action[:64],
        target_type=target_type,
        target_id=target_id,
        branch_id=branch_id,
        details=redact(details or {}),
        request_id=get_request_id(),
        created_at=utcnow().replace(tzinfo=None),
    )
    db.add(entry)
    return entry
