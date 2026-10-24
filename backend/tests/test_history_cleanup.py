"""Deletion protects consumers and releases disk space only after commit."""

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.core.timeutils import utcnow
from app.db.session import engine
from app.models import AuditLog, Display, EventOutbox, Job, MediaAsset, Publication, PublicationTarget, RateVersion
from app.services import events, jobs, publishing, rates, storage
from app.workers.runner import Worker


@pytest.fixture
def ready(db, admin_user):
    def make(logo_id=None):
        board = rates.get_or_create_default_board(db, owner_id=admin_user.id, branch_id=None, title="Test")
        version = rates.create_version(
            db, board=board, rates={"USD": rates.parse_rate("16000")},
            board_title="Test", board_subtitle="", created_by=admin_user.id,
            branch_id=None, logo_asset_id=logo_id,
        )
        asset = storage.create_asset(
            db, kind="board_png", storage_key=storage.version_storage_key(version.id, "board_png"),
            data=(Path(__file__).parent / "fixtures" / "baseline_board.png").read_bytes(),
        )
        version.png_asset_id = asset.id
        rates.mark_ready(db, version)
        db.commit()
        return version
    return make


def test_deletion_queues_cleanup_and_worker_reclaims_files(client, auth, ready, db):
    version = ready()
    version_id, asset_id = version.id, version.png_asset_id
    file = storage.absolute_path(db.get(MediaAsset, asset_id))
    response = client.delete(f"/api/versions/{version_id}", headers=auth)
    assert response.status_code == 200, response.text
    db.rollback()
    db.expire_all()
    assert db.get(RateVersion, version_id) is None
    assert file.exists()  # Disk work starts only after the deletion committed.
    cleanup = db.execute(select(Job).where(Job.job_type == "cleanup_media")).scalar_one()
    assert cleanup.version_id is None
    assert Worker().run_once()
    db.rollback()
    db.expire_all()
    assert not file.exists()
    assert db.get(MediaAsset, asset_id) is None
    assert db.get(Job, cleanup.id).result["bytes_freed"] > 0
    assert db.execute(select(AuditLog.id).where(AuditLog.action == "version.deleted")).first()
    assert client.delete(f"/api/versions/{version_id}", headers=auth).status_code == 404


@pytest.mark.parametrize("consumer", ["desired", "reported", "scheduled", "queued", "running"])
def test_in_use_version_cannot_be_deleted(consumer, client, auth, ready, db):
    version = ready()
    if consumer in {"queued", "running"}:
        job = jobs.enqueue(db, job_type="generate_video", payload={}, version_id=version.id)
        job.status = consumer
    elif consumer == "reported":
        db.add(Display(name="Offline TV", reported_version_id=version.id))
    else:
        display = Display(name="TV")
        db.add(display)
        db.flush()
        publishing.create_publication(
            db, version=version, displays=[display], created_by=None,
            scheduled_at=utcnow() + timedelta(hours=1) if consumer == "scheduled" else None,
        )
    db.commit()
    response = client.delete(f"/api/versions/{version.id}", headers=auth)
    assert response.status_code == 409, response.text
    summary = client.get(f"/api/versions/{version.id}", headers=auth).json()
    assert summary["delete_blocked_reason"]
    assert storage.asset_exists(db.get(MediaAsset, version.png_asset_id))


def test_deleting_old_published_version_preserves_current_display(client, auth, ready, db):
    old, current = ready(), ready()
    display = Display(name="TV")
    db.add(display)
    db.flush()
    old_publication = publishing.create_publication(db, version=old, displays=[display], created_by=None)
    old_id = old_publication.id
    publishing.create_publication(db, version=current, displays=[display], created_by=None)
    display.reported_version_id = current.id
    current.source_version_id = old.id
    db.commit()
    assert client.delete(f"/api/versions/{old.id}", headers=auth).status_code == 200
    db.rollback()
    db.expire_all()
    assert db.get(Publication, old_id) is None
    assert db.get(RateVersion, current.id).source_version_id is None
    target = db.get(PublicationTarget, db.get(Display, display.id).desired_target_id)
    assert target.version_id == current.id
    assert Worker().run_once()
    assert storage.asset_exists(db.get(MediaAsset, current.png_asset_id))


def test_shared_logo_survives_until_last_version_is_deleted(client, auth, ready, db):
    logo = storage.create_asset(db, kind="logo", storage_key="logos/shared.png", data=b"shared logo")
    logo_id, path = logo.id, storage.absolute_path(logo)
    first, second = ready(logo_id), ready(logo_id)
    assert client.delete(f"/api/versions/{first.id}", headers=auth).status_code == 200
    assert Worker().run_once()
    db.rollback()
    db.expire_all()
    assert db.get(MediaAsset, logo_id) is not None and path.exists()
    assert client.delete(f"/api/versions/{second.id}", headers=auth).status_code == 200
    assert Worker().run_once()
    db.rollback()
    db.expire_all()
    assert db.get(MediaAsset, logo_id) is None and not path.exists()


def test_failed_commit_does_not_remove_files_or_queue_cleanup(client, auth, ready, db, monkeypatch):
    version = ready()
    version_id, asset_id = version.id, version.png_asset_id
    def fail_commit(_self):
        raise RuntimeError("simulated transaction failure")
    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        with pytest.raises(RuntimeError):
            client.delete(f"/api/versions/{version_id}", headers=auth)
    db.rollback()
    db.expire_all()
    assert db.get(RateVersion, version_id) is not None
    assert storage.asset_exists(db.get(MediaAsset, asset_id))
    assert not db.execute(select(Job.id).where(Job.job_type == "cleanup_media")).first()


def test_cleanup_retries_file_errors(client, auth, ready, db, monkeypatch):
    version = ready()
    asset_id = version.png_asset_id
    assert client.delete(f"/api/versions/{version.id}", headers=auth).status_code == 200
    def locked(_path, *args, **kwargs):
        raise PermissionError("file temporarily open")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", locked)
        assert Worker().run_once()
    db.rollback()
    db.expire_all()
    job = db.execute(select(Job).where(Job.job_type == "cleanup_media")).scalar_one()
    assert job.status == "queued"
    assert Worker().run_once()
    db.rollback()
    db.expire_all()
    assert db.get(MediaAsset, asset_id) is None
    assert db.get(Job, job.id).status == "succeeded"


def test_staff_cannot_delete_history(client, staff_auth, ready):
    version = ready()
    assert client.delete(f"/api/versions/{version.id}", headers=staff_auth).status_code == 403


def test_repeated_acknowledgement_does_not_write_more_events(ready, db):
    version = ready()
    display = Display(name="TV")
    db.add(display)
    db.flush()
    publishing.create_publication(db, version=version, displays=[display], created_by=None)
    kwargs = dict(display=display, revision=1, version_id=version.id, state="displayed")
    publishing.acknowledge(db, **kwargs)
    db.commit()
    before = db.scalar(select(func.count(EventOutbox.id)))
    for _ in range(5):
        publishing.acknowledge(db, **kwargs)
    db.commit()
    assert db.scalar(select(func.count(EventOutbox.id))) == before


def test_outbox_pruning_has_a_batch_limit(db):
    for _ in range(5):
        row = events.emit(db, events.TOPIC_JOB)
        row.created_at = (utcnow() - timedelta(days=2)).replace(tzinfo=None)
    db.commit()
    assert events.prune(db, limit=2) == 2
    db.commit()
    assert db.scalar(select(func.count(EventOutbox.id))) == 3


def test_display_list_query_count_stays_bounded(client, auth, ready, db):
    for index in range(15):
        version = ready()
        display = Display(name=f"TV {index}")
        db.add(display)
        db.flush()
        publishing.create_publication(db, version=version, displays=[display], created_by=None)
    db.commit()
    queries = []
    def count(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)
    event.listen(engine, "before_cursor_execute", count)
    try:
        response = client.get("/api/displays", headers=auth)
        display_queries = list(queries)
        queries.clear()
        dashboard = client.get("/api/dashboard", headers=auth)
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert response.status_code == 200
    assert len(response.json()) == 15
    assert len(display_queries) <= 6, display_queries
    assert dashboard.status_code == 200
    assert dashboard.json()["displays_total"] == 15
    assert dashboard.json()["displays_stale"] == 15
    assert dashboard.json()["versions_ready"] == 15
    assert len(queries) <= 8, queries


def test_dashboard_counts_respect_staff_branches(client, auth, staff_auth, branches, ready, db):
    for branch, job_status in (("kuta", "failed"), ("ubud", "queued")):
        version = ready()
        version.branch_id = branches[branch]
        display = Display(name=branch, branch_id=branches[branch])
        db.add(display)
        db.flush()
        publishing.create_publication(
            db, version=version, displays=[display], created_by=None,
            scheduled_at=utcnow() + timedelta(hours=1),
        )
        job = jobs.enqueue(db, job_type="generate_video", payload={}, version_id=version.id)
        job.status = job_status
        db.commit()
    admin = client.get("/api/dashboard", headers=auth).json()
    staff = client.get("/api/dashboard", headers=staff_auth).json()
    assert admin["displays_total"] == admin["versions_total"] == admin["scheduled_publications"] == 2
    assert admin["failed_jobs"] == 1
    assert staff["displays_total"] == staff["versions_total"] == staff["scheduled_publications"] == 1
    assert staff["pending_jobs"] == 1
    assert staff["failed_jobs"] == 0
