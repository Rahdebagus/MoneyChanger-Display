"""Job worker and publication scheduler.

Run with:  python -m app.workers.runner      (from backend/)

One process does both jobs and schedules, because both are low volume and a
second moving part would be cost without benefit. Both are safe to run in
several copies:

* jobs are claimed with a guarded UPDATE (see services/jobs.py);
* schedules are claimed with a guarded state transition, so two workers can
  never fire one schedule twice.

Crash recovery runs on startup and on a timer, so a job whose worker died is
requeued instead of leaving a version stuck in 'generating' forever.
"""

import argparse
import logging
import signal
import sys
import time

from app.core.config import get_settings
from app.core.logging import configure_logging, new_request_id, set_request_id
from app.db.session import SessionLocal, session_scope
from app.models import JobType
from app.services import audit, events, jobs, pairing, publishing, storage
from app.services import version_cleanup

logger = logging.getLogger(__name__)

MAINTENANCE_INTERVAL_SECONDS = 120


class Worker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._running = True
        self._last_maintenance = 0.0
        self._last_temp_sweep = 0.0

    def stop(self, *_args) -> None:
        logger.info("Stop requested; finishing current job then exiting")
        self._running = False

    def run_once(self) -> bool:
        """Process at most one job. Returns True when work was done."""
        db = SessionLocal()
        try:
            job = jobs.claim_next(
                db,
                job_types=[JobType.CLEANUP_MEDIA.value],
            )
        except Exception:
            logger.exception("Failed to claim a job")
            db.close()
            return False

        if job is None:
            db.close()
            return False

        set_request_id(new_request_id())
        logger.info("Claimed job %s (%s) attempt %s", job.id, job.job_type, job.attempts)
        started = time.monotonic()

        try:
            if job.job_type == JobType.CLEANUP_MEDIA.value:
                result = version_cleanup.cleanup_media(db, job.payload)
            else:
                raise ValueError(f"Tipe job tidak dikenal: {job.job_type}")

            jobs.complete(db, job, result)
            db.commit()
            logger.info(
                "Job %s finished in %.2fs", job.id, time.monotonic() - started
            )

        except Exception as exc:
            db.rollback()
            message = f"{type(exc).__name__}: {exc}"
            logger.exception("Job %s failed", job.id)
            try:
                jobs.fail(db, job, message)
                db.commit()
            except Exception:
                logger.exception("Could not record failure for job %s", job.id)
                db.rollback()
        finally:
            set_request_id(None)
            db.close()

        return True

    def run_scheduler(self) -> int:
        """Fire any publication whose scheduled time has arrived."""
        fired = 0
        try:
            with session_scope() as db:
                due = publishing.due_schedules(db)
        except Exception:
            logger.exception("Could not read due schedules")
            return 0

        for publication_id in due:
            db = SessionLocal()
            try:
                publication = publishing.claim_schedule(db, publication_id)
                if publication is None:
                    # Another worker got there first.
                    db.rollback()
                    continue

                publishing.activate(db, publication)
                audit.record(
                    db,
                    action="publication.schedule_fired",
                    actor_label="scheduler",
                    target_type="publication",
                    target_id=publication.id,
                    details={"version_id": publication.version_id},
                )
                db.commit()
                fired += 1
                logger.info("Fired scheduled publication %s", publication.id)
            except Exception:
                logger.exception("Failed to fire publication %s", publication_id)
                db.rollback()
            finally:
                db.close()

        return fired

    def run_maintenance(self) -> None:
        now = time.monotonic()
        if now - self._last_maintenance < MAINTENANCE_INTERVAL_SECONDS:
            return
        self._last_maintenance = now

        try:
            with session_scope() as db:
                requeued = jobs.recover_stale(db)
                exhausted = jobs.exhausted_to_failed(db)
                pruned = events.prune(db)
                purged = pairing.purge_expired_codes(db)

            if requeued or exhausted or pruned or purged:
                logger.info(
                    "Maintenance: requeued=%s exhausted=%s events_pruned=%s codes_purged=%s",
                    requeued,
                    exhausted,
                    pruned,
                    purged,
                )

            if now - self._last_temp_sweep >= 3600:
                self._last_temp_sweep = now
                removed, freed = storage.sweep_orphan_temp_files()
                if removed:
                    logger.info("Removed %s orphan temp files (%s bytes)", removed, freed)
        except Exception:
            logger.exception("Maintenance pass failed")

    def serve_forever(self) -> None:
        configure_logging("DEBUG" if self.settings.debug else "INFO")
        logger.info("Worker starting (identity=%s)", jobs.worker_identity())

        # Anything left running by a previous crashed worker goes back in the
        # queue before we start taking new work.
        try:
            with session_scope() as db:
                recovered = jobs.recover_stale(db)
            if recovered:
                logger.info("Requeued %s stale job(s) from a previous run", recovered)
        except Exception:
            logger.exception("Startup recovery failed")

        idle_sleep = self.settings.job_poll_interval_seconds

        while self._running:
            try:
                did_work = self.run_once()
                self.run_scheduler()
                self.run_maintenance()
            except KeyboardInterrupt:
                break
            except Exception:
                logger.exception("Worker loop error")
                did_work = False

            if not did_work:
                time.sleep(idle_sleep)

        logger.info("Worker stopped")


def main() -> int:
    worker = Worker()
    signal.signal(signal.SIGINT, worker.stop)
    signal.signal(signal.SIGTERM, worker.stop)
    parser = argparse.ArgumentParser(description="Cleanup/scheduler only; PNG saves run in the API.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-jobs", type=int, default=10)
    args = parser.parse_args()
    if args.once:
        configure_logging("INFO")
        for _ in range(max(0, min(args.max_jobs, 100))):
            if not worker.run_once():
                break
        worker.run_scheduler()
        worker.run_maintenance()
    else:
        worker.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
