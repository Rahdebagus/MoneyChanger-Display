"""Branch scope shared by API dependencies and save services."""

from typing import List, Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, UserBranch, UserRole


class BranchAccessDenied(ValueError):
    pass

def user_branch_ids(db: Session, user: User) -> List[int]:
    rows = db.execute(
        select(UserBranch.branch_id).where(UserBranch.user_id == user.id)
    ).scalars()
    return list(rows)


def accessible_branch_ids(db: Session, user: User) -> Optional[Set[int]]:
    """Branches this user may touch.

    None means "every branch" and is only ever returned for an admin. Callers
    must treat None as unrestricted and a set as a hard filter.
    """
    if user.role == UserRole.ADMIN:
        return None
    return set(user_branch_ids(db, user))


def ensure_branch_access(db: Session, user: User, branch_id: Optional[int]) -> None:
    """Reject a staff member reaching outside their assigned branches.

    A None branch_id is shared/global data, which staff may read but which is
    still gated by the role checks on the individual routes.
    """
    allowed = accessible_branch_ids(db, user)
    if allowed is None:
        return
    if branch_id is None:
        return
    if branch_id not in allowed:
        raise BranchAccessDenied("Cabang ini bukan bagian dari penugasan Anda.")


