"""Explicit, bounded maintenance. Dry-run unless --apply is supplied.

This module never starts another process and never deletes rate history.
"""
import argparse
import json
from datetime import timedelta

from sqlalchemy import delete, or_, select

from app.core.config import get_settings
from app.core.timeutils import utcnow
from app.db.session import SessionLocal, engine
from app.models import EventOutbox, Job, PairingCode, RateVersion, SaveRequest
from app.services.direct_save import SaveError, render_saved, render_slot


def cleanup(db, *, apply=False, limit=500, days=30):
    now = utcnow().replace(tzinfo=None)
    old = now - timedelta(days=days)
    candidates = (
        (EventOutbox, EventOutbox.id, EventOutbox.created_at < now - timedelta(hours=get_settings().event_retention_hours)),
        (Job, Job.id, (Job.status.in_(["succeeded", "failed", "cancelled"])) & (Job.finished_at < old)),
        (SaveRequest, SaveRequest.key_hash, (SaveRequest.version_id.is_(None)) & (SaveRequest.created_at < old)),
        (PairingCode, PairingCode.id, PairingCode.expires_at < old),
    )
    counts = {}
    for model, key, condition in candidates:
        ids = list(db.scalars(select(key).where(condition).order_by(key).limit(limit)))
        counts[model.__tablename__] = len(ids)
        if apply and ids:
            db.execute(delete(model).where(key.in_(ids)))
    if apply:
        db.commit()
    return counts


def recover_png(db, version_id, *, apply=False):
    """Operator retry for an interrupted request or a pre-upgrade queued PNG.

    Stop the old worker before using this command. Unexpired running jobs are
    rejected. Legacy records are cancelled only for this explicit version.
    """
    with render_slot(db):
        version = db.scalar(select(RateVersion).where(RateVersion.id == version_id).with_for_update())
        if version is None or version.status not in {"generating", "failed", "draft"}:
            raise SaveError("Version must exist and be draft, generating or failed.", 409)
        pending = list(db.scalars(select(Job).where(
            Job.version_id == version_id, Job.status.in_(["queued", "running"]),
        ).with_for_update()))
        now = utcnow().replace(tzinfo=None)
        if any(job.status == "running" and (not job.lease_expires_at or job.lease_expires_at > now) for job in pending):
            raise SaveError("An active job still owns this version; stop the old worker and wait for its lease.", 409)
        if any(job.job_type not in {"generate_board", "generate_video"} for job in pending):
            raise SaveError("Non-legacy work still references this version.", 409)
        result = {"version_id": version_id, "legacy_jobs": len(pending), "apply": apply}
        if apply:
            for job in pending:
                job.status = "cancelled"
                job.finished_at = now
                job.error_message = "Replaced by explicit direct-PNG recovery."
            version.status = "generating"
            db.commit()
            result["status"] = render_saved(db, version).status
        return result


def cancel_legacy_video(db, *, apply=False, limit=500):
    """Cancel obsolete video work only; preserve versions and all old files."""
    now = utcnow().replace(tzinfo=None)
    statement = select(Job).where(
        Job.job_type == "generate_video",
        or_(Job.status == "queued", (Job.status == "running") & (Job.lease_expires_at < now)),
    ).order_by(Job.id).limit(limit)
    rows = list(db.scalars(statement.with_for_update() if apply else statement))
    if apply:
        for job in rows:
            job.status = "cancelled"
            job.finished_at = now
            job.error_message = "Video generation retired by explicit maintenance."
        db.commit()
    return {"cancelled" if apply else "candidates": len(rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["cleanup", "recover-png", "cancel-legacy-video"])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--older-than-days", type=int, default=30)
    parser.add_argument("--version-id", type=int)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000 or args.older_than_days < 7:
        parser.error("limit must be 1..1000 and retention at least 7 days")
    if args.action == "recover-png" and not args.version_id:
        parser.error("recover-png requires --version-id")
    with engine.connect() as connection, SessionLocal(bind=connection) as db:
        if args.action == "recover-png":
            result = recover_png(db, args.version_id, apply=args.apply)
        elif args.action == "cancel-legacy-video":
            result = cancel_legacy_video(db, apply=args.apply, limit=args.limit)
        else:
            result = cleanup(db, apply=args.apply, limit=args.limit, days=args.older_than_days)
        print(json.dumps({"apply": args.apply, "result": result}))


if __name__ == "__main__":
    main()
