"""Real MariaDB transactions and direct PNG responses, with no running worker."""
import io
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timeutils import utcnow
from app.db.session import SessionLocal, engine
from app.maintenance import cancel_legacy_video, cleanup, recover_png
from app.models import EventOutbox, Job, MediaAsset, RateBoard, RateVersion, SaveRequest
from app.services import board_builder, direct_save, events, jobs, storage


def body(key="save-request-123", **extra):
    return {"rates": {"USD": "16000.1250", "JPY": "100.25", "EUR": None},
            "title": "MONEY CHANGER", "idempotency_key": key, **extra}


def post(client, auth, payload=None):
    return client.post("/api/versions", headers=auth, json=payload or body())


def count(db, model):
    db.rollback()
    return db.scalar(select(func.count()).select_from(model))


def test_save_returns_real_png_and_exact_rates_without_jobs_or_ocr(client, auth, db):
    response = post(client, auth)
    assert response.status_code == 201, response.text
    version = response.json()["version"]
    assert version["status"] == "ready" and version["mp4_url"] is None
    assert response.json()["job"] is None
    image = client.get(version["png_url"], headers=auth)
    assert image.status_code == 200
    with Image.open(io.BytesIO(image.content)) as png:
        assert png.format == "PNG" and png.size == (1280, 720)
        png.verify()
    detail = client.get(f"/api/versions/{version['id']}", headers=auth).json()
    assert detail["rates"]["USD"] == "16000.125"
    assert detail["rates"]["JPY"] == "100.25" and detail["rates"]["EUR"] is None
    assert count(db, Job) == 0
    assert "app.services.ocr" not in sys.modules


def test_duplicate_and_changed_payload(client, auth, db, monkeypatch):
    first = post(client, auth).json()["version"]
    def unexpected(*_args):
        pytest.fail("A ready retry must not render again")
    monkeypatch.setattr(board_builder, "build_board", unexpected)
    retry = post(client, auth)
    assert retry.status_code == 201 and retry.json()["version"]["id"] == first["id"]
    assert count(db, RateVersion) == count(db, SaveRequest) == 1
    conflict = post(client, auth, body(title="Different"))
    assert conflict.status_code == 409


def test_failed_render_is_persisted_and_retry_recovers_same_version(client, auth, db, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(board_builder, "generate_rate_image", lambda *_a, **_k: (_ for _ in ()).throw(OSError("disk failure")))
        response = post(client, auth)
    assert response.status_code == 503
    version = db.scalar(select(RateVersion))
    version_id = version.id
    assert version.status == "failed" and "OSError" in version.error_message
    assert version.png_asset_id is None
    db.rollback()
    retried = post(client, auth)
    assert retried.status_code == 201, retried.text
    assert retried.json()["version"]["id"] == version_id
    assert count(db, RateVersion) == 1 and count(db, Job) == 0


@pytest.mark.parametrize("same_key", [False, True])
def test_concurrent_saves_have_unique_versions_or_share_retry(same_key, client, auth, db):
    db.rollback()  # Release the fixture connection; production pool has only two.
    barrier = threading.Barrier(2)
    def send(index):
        barrier.wait(timeout=5)
        return post(client, auth, body("concurrent-same" if same_key else f"concurrent-{index}"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send, [1, 2]))
    assert [r.status_code for r in responses] == [201, 201], [r.text for r in responses]
    versions = [r.json()["version"] for r in responses]
    assert len({v["id"] for v in versions}) == (1 if same_key else 2)
    assert count(db, RateBoard) == 1
    assert count(db, Job) == 0
    if not same_key:
        assert {v["version"] for v in versions} == {1, 2}
        assert len({v["png_url"] for v in versions}) == 2


def test_busy_renderer_returns_retryable_error_without_creating_version(client, auth, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "png_lock_timeout_seconds", 0)
    db.rollback()
    with engine.connect() as connection, SessionLocal(bind=connection) as owner:
        with direct_save.render_slot(owner):
            response = post(client, auth)
    assert response.status_code == 503
    assert count(db, RateVersion) == 0


@pytest.mark.parametrize("failed_commit", [1, 2])
def test_transaction_failure_never_returns_false_success(failed_commit, client, auth, db, monkeypatch):
    original, calls = Session.commit, 0
    def commit(session):
        nonlocal calls
        # Limit fault injection to the direct-save connection-bound session.
        if session.get_bind() is not engine:
            calls += 1
            if calls == failed_commit:
                raise SQLAlchemyError("simulated commit failure")
        return original(session)
    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", commit)
        response = post(client, auth)
    assert response.status_code == 503, response.text
    assert count(db, RateVersion) == (0 if failed_commit == 1 else 1)
    if failed_commit == 2:
        assert db.scalar(select(RateVersion.status)) == "failed"
        assert count(db, MediaAsset) == 0
    db.rollback()
    assert post(client, auth).status_code == 201
    assert count(db, RateVersion) == 1


def test_lost_commit_confirmation_preserves_committed_png(client, auth, db, monkeypatch):
    original, calls = Session.commit, 0
    def commit(session):
        nonlocal calls
        result = original(session)
        if session.get_bind() is not engine:
            calls += 1
            if calls == 2:
                raise SQLAlchemyError("connection lost after commit")
        return result
    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", commit)
        response = post(client, auth)
    assert response.status_code == 201, response.text
    assert count(db, RateVersion) == 1
    assert client.get(response.json()["version"]["png_url"], headers=auth).status_code == 200


def test_deleted_request_cannot_resurrect_history(client, auth, db):
    version = post(client, auth).json()["version"]
    assert client.delete(f"/api/versions/{version['id']}", headers=auth).status_code == 200
    assert post(client, auth).status_code == 410
    assert count(db, RateVersion) == 0


def test_missing_file_retry_restores_png(client, auth, db):
    version = post(client, auth).json()["version"]
    asset = db.get(MediaAsset, db.get(RateVersion, version["id"]).png_asset_id)
    storage.absolute_path(asset).unlink()
    db.rollback()
    retry = post(client, auth)
    assert retry.status_code == 201
    assert retry.json()["version"]["id"] == version["id"]
    assert client.get(retry.json()["version"]["png_url"], headers=auth).status_code == 200


def test_video_generation_removed(client, auth, db):
    version = post(client, auth, body(generate_video=True)).json()["version"]
    assert client.post(f"/api/versions/{version['id']}/video", headers=auth).status_code == 404
    assert client.post("/generate-video", headers=auth, json={"rates": {"USD": 100}}).status_code == 404
    assert count(db, Job) == 0
    legacy = storage.create_asset(db, kind="board_mp4", storage_key="legacy/old.mp4", data=b"old video", mime_type="video/mp4")
    legacy_id = legacy.id
    db.commit()
    assert client.get(f"/api/media/{legacy_id}", headers=auth).status_code == 404
    assert client.get(f"/api/media/{legacy_id}/download", headers=auth).status_code == 404


def test_same_key_is_scoped_to_the_authenticated_user(client, auth, staff_auth, db):
    first = post(client, auth).json()["version"]
    second = post(client, staff_auth)
    assert second.status_code == 201, second.text
    assert second.json()["version"]["id"] != first["id"]
    assert count(db, SaveRequest) == 2


def test_exceeded_render_budget_does_not_mark_ready(client, auth, db, monkeypatch):
    times = iter([0, get_settings().png_render_budget_seconds + 1])
    class Clock:
        @staticmethod
        def monotonic():
            return next(times)
    monkeypatch.setattr(direct_save, "time", Clock)
    response = post(client, auth)
    assert response.status_code == 503
    assert db.scalar(select(RateVersion.status)) == "failed"


def test_rendering_version_cannot_be_archived_or_deleted(client, auth, db):
    version_id = post(client, auth).json()["version"]["id"]
    db.get(RateVersion, version_id).status = "generating"
    db.commit()
    assert client.post(f"/api/versions/{version_id}/archive", headers=auth).status_code == 409
    assert client.delete(f"/api/versions/{version_id}", headers=auth).status_code == 409


def test_invalid_logo_and_ocr_image_are_rejected_before_heavy_work(client, auth):
    assert post(client, auth, body(logo_base64="not-an-image")).status_code == 400
    assert client.post("/api/ocr/upload", headers=auth, files={"file": ("invalid.png", b"not png", "image/png")}).status_code == 400
    assert "app.services.ocr" not in sys.modules


def test_busy_ocr_does_not_load_paddle(client, auth):
    from app.services import ocr_runner
    image = io.BytesIO()
    Image.new("RGB", (10, 10)).save(image, format="PNG")
    assert ocr_runner._slots.acquire(timeout=1)
    try:
        response = client.post("/api/ocr/upload", headers=auth, files={"file": ("test.png", image.getvalue(), "image/png")})
    finally:
        ocr_runner._slots.release()
    assert response.status_code == 503
    assert "app.services.ocr" not in sys.modules


def test_polling_profile_does_not_write_outbox(client, auth, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "realtime_enabled", False)
    assert events.emit(db, events.TOPIC_ASSIGNMENT) is None
    db.commit()
    assert post(client, auth).status_code == 201
    assert count(db, EventOutbox) == 0


def test_cleanup_is_optional_bounded_and_preserves_versions(client, auth, db):
    post(client, auth)
    for _ in range(3):
        event = events.emit(db, events.TOPIC_JOB)
        event.created_at = utcnow().replace(tzinfo=None) - timedelta(days=40)
    db.commit()
    assert cleanup(db, limit=2)["event_outbox"] == 2
    assert count(db, EventOutbox) == 3
    cleanup(db, limit=2, apply=True)
    assert count(db, EventOutbox) == 1
    assert count(db, RateVersion) == count(db, SaveRequest) == 1


def test_explicit_recovery_of_legacy_queued_png(client, auth, db):
    version = post(client, auth).json()["version"]
    stored = db.get(RateVersion, version["id"])
    stored.status = "generating"
    jobs.enqueue(db, job_type="generate_board", payload={}, version_id=stored.id)
    db.commit()
    with engine.connect() as connection, SessionLocal(bind=connection) as recovery:
        assert recover_png(recovery, version["id"])["legacy_jobs"] == 1
        assert recover_png(recovery, version["id"], apply=True)["status"] == "ready"
    db.rollback()
    assert db.scalar(select(Job.status)) == "cancelled"


def test_video_queue_retirement_is_explicit_and_skips_active_lease(db):
    old = jobs.enqueue(db, job_type="generate_video", payload={})
    active = jobs.enqueue(db, job_type="generate_video", payload={})
    active.status = "running"
    active.lease_expires_at = utcnow().replace(tzinfo=None) + timedelta(minutes=5)
    cleanup_job = jobs.enqueue(db, job_type="cleanup_media", payload={})
    db.commit()
    assert cancel_legacy_video(db) == {"candidates": 1}
    assert old.status == "queued"
    assert cancel_legacy_video(db, apply=True) == {"cancelled": 1}
    assert old.status == "cancelled" and active.status == "running"
    assert cleanup_job.status == "queued"
