"""Publishing, revision ordering, pairing and device isolation.

These are the rules that keep two TVs and two admins from corrupting each
other's state, so they are tested against real SQL rather than mocks.
"""

import json
from datetime import timedelta
from pathlib import Path

import pytest

from app.core.timeutils import utcnow
from app.db.session import SessionLocal
from app.models import (
    Display,
    Job,
    JobStatus,
    Publication,
    PublicationState,
    PublicationTarget,
    RateVersion,
    TargetState,
    VersionStatus,
)
from app.services import jobs as jobs_service, publishing

FIXTURE_RATES = json.loads(
    (Path(__file__).parent / "fixtures" / "baseline_rates.json").read_text("utf-8")
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def make_ready_version(client, auth, branch_id, overrides=None):
    """The save response must already contain a usable PNG, without a worker."""
    rates = {k: str(v) for k, v in FIXTURE_RATES.items()}
    rates.update(overrides or {})

    response = client.post(
        "/api/versions",
        json={
            "rates": rates,
            "title": "MONEY CHANGER",
            "subtitle": "PT. PRADNYANA ARTHA MANDIRI",
            "branch_id": branch_id,
        },
        headers=auth,
    )
    assert response.status_code == 201, response.text
    version_id = response.json()["version"]["id"]

    assert response.json()["version"]["status"] == "ready"
    assert response.json()["job"] is None

    return version_id


def pair_display(client, auth, name="TV 1", branch_id=None):
    start = client.post("/api/device/pairing/start").json()
    approve = client.post(
        "/api/displays/pair",
        json={"code": start["code"], "name": name, "branch_id": branch_id},
        headers=auth,
    )
    assert approve.status_code == 201, approve.text
    claim = client.post(
        "/api/device/pairing/claim", json={"device_session": start["device_session"]}
    )
    assert claim.status_code == 200, claim.text
    body = claim.json()
    return body["display_id"], {"Authorization": f"Bearer {body['device_token']}"}


# --------------------------------------------------------------------------
# Pairing
# --------------------------------------------------------------------------
def test_pairing_code_is_single_use(client, auth, branches):
    start = client.post("/api/device/pairing/start").json()
    client.post(
        "/api/displays/pair",
        json={"code": start["code"], "name": "TV", "branch_id": branches["kuta"]},
        headers=auth,
    )

    first = client.post(
        "/api/device/pairing/claim", json={"device_session": start["device_session"]}
    )
    assert first.status_code == 200

    replay = client.post(
        "/api/device/pairing/claim", json={"device_session": start["device_session"]}
    )
    assert replay.status_code == 400


def test_claim_before_approval_is_rejected(client):
    start = client.post("/api/device/pairing/start").json()
    response = client.post(
        "/api/device/pairing/claim", json={"device_session": start["device_session"]}
    )
    assert response.status_code == 400


def test_expired_pairing_code_is_rejected(client, auth, branches, db):
    from app.models import PairingCode

    start = client.post("/api/device/pairing/start").json()

    entry = db.query(PairingCode).one()
    entry.expires_at = (utcnow() - timedelta(minutes=1)).replace(tzinfo=None)
    db.commit()

    response = client.post(
        "/api/displays/pair",
        json={"code": start["code"], "name": "TV", "branch_id": branches["kuta"]},
        headers=auth,
    )
    assert response.status_code == 400


def test_unknown_pairing_code_is_rejected_without_hinting(client, auth, branches):
    response = client.post(
        "/api/displays/pair",
        json={"code": "ZZZZZZ", "name": "TV", "branch_id": branches["kuta"]},
        headers=auth,
    )
    assert response.status_code == 400
    assert "kedaluwarsa" in response.json()["detail"].lower()


def test_revoked_device_loses_access_on_next_request(client, auth, branches):
    display_id, device = pair_display(client, auth, branch_id=branches["kuta"])
    assert client.get("/api/device/assignment", headers=device).status_code == 200

    revoke = client.post(f"/api/displays/{display_id}/revoke", headers=auth)
    assert revoke.status_code == 200

    assert client.get("/api/device/assignment", headers=device).status_code == 401


# --------------------------------------------------------------------------
# Device isolation
# --------------------------------------------------------------------------
def test_device_token_cannot_reach_admin_api(client, auth, branches):
    _display_id, device = pair_display(client, auth, branch_id=branches["kuta"])

    for method, path in (
        ("get", "/api/displays"),
        ("get", "/api/users"),
        ("get", "/api/versions"),
        ("get", "/api/dashboard"),
        ("get", "/api/audit"),
    ):
        response = getattr(client, method)(path, headers=device)
        assert response.status_code == 401, f"{path} returned {response.status_code}"


def test_device_cannot_read_media_it_was_never_assigned(client, auth, branches):
    version_id = make_ready_version(client, auth, branches["kuta"])
    _display_id, device = pair_display(client, auth, branch_id=branches["kuta"])

    db = SessionLocal()
    try:
        asset_id = db.get(RateVersion, version_id).png_asset_id
    finally:
        db.close()

    # Nothing published to this display yet.
    assert client.get(f"/api/media/{asset_id}", headers=device).status_code == 404


# --------------------------------------------------------------------------
# Publishing
# --------------------------------------------------------------------------
def test_cannot_publish_a_version_that_is_not_ready(client, auth, branches):
    created = client.post(
        "/api/versions",
        json={
            "rates": {"USD": "16950"},
            "title": "MONEY CHANGER",
            "subtitle": "PT. PRADNYANA ARTHA MANDIRI",
            "branch_id": branches["kuta"],
        },
        headers=auth,
    )
    version_id = created.json()["version"]["id"]
    with SessionLocal() as draft_db:
        draft_db.get(RateVersion, version_id).status = "draft"
        draft_db.commit()
    display_id, _device = pair_display(client, auth, branch_id=branches["kuta"])

    response = client.post(
        "/api/publications",
        json={"version_id": version_id, "display_ids": [display_id]},
        headers=auth,
    )
    assert response.status_code == 400
    assert "ready" in response.json()["detail"].lower()


def test_saving_a_version_does_not_change_what_is_displayed(client, auth, branches):
    version_id = make_ready_version(client, auth, branches["kuta"])
    display_id, device = pair_display(client, auth, branch_id=branches["kuta"])

    client.post(
        "/api/publications",
        json={"version_id": version_id, "display_ids": [display_id]},
        headers=auth,
    )
    before = client.get("/api/device/assignment", headers=device).json()

    # Save a brand new version; the TV must be unaffected.
    make_ready_version(client, auth, branches["kuta"], overrides={"USD": "17500"})

    after = client.get("/api/device/assignment", headers=device).json()
    assert after["revision"] == before["revision"]
    assert after["version_id"] == before["version_id"]


def test_publish_is_idempotent_under_retry(client, auth, branches):
    version_id = make_ready_version(client, auth, branches["kuta"])
    display_id, _device = pair_display(client, auth, branch_id=branches["kuta"])

    payload = {
        "version_id": version_id,
        "display_ids": [display_id],
        "idempotency_key": "retry-me",
    }
    first = client.post("/api/publications", json=payload, headers=auth).json()
    second = client.post("/api/publications", json=payload, headers=auth).json()

    assert first["id"] == second["id"]

    db = SessionLocal()
    try:
        targets = db.query(PublicationTarget).filter_by(display_id=display_id).all()
        assert len(targets) == 1
    finally:
        db.close()


def test_each_publish_increments_the_display_revision(client, auth, branches):
    first_version = make_ready_version(client, auth, branches["kuta"])
    second_version = make_ready_version(client, auth, branches["kuta"], {"USD": "17200"})
    display_id, _device = pair_display(client, auth, branch_id=branches["kuta"])

    one = client.post(
        "/api/publications",
        json={"version_id": first_version, "display_ids": [display_id]},
        headers=auth,
    ).json()
    two = client.post(
        "/api/publications",
        json={"version_id": second_version, "display_ids": [display_id]},
        headers=auth,
    ).json()

    assert one["targets"][0]["revision"] == 1
    assert two["targets"][0]["revision"] == 2


def test_late_acknowledgement_cannot_rewind_reported_state(client, auth, branches):
    v1 = make_ready_version(client, auth, branches["kuta"])
    v2 = make_ready_version(client, auth, branches["kuta"], {"USD": "17200"})
    display_id, device = pair_display(client, auth, branch_id=branches["kuta"])

    client.post(
        "/api/publications",
        json={"version_id": v1, "display_ids": [display_id]},
        headers=auth,
    )
    client.post(
        "/api/publications",
        json={"version_id": v2, "display_ids": [display_id]},
        headers=auth,
    )

    client.post(
        "/api/device/acknowledge",
        json={"revision": 2, "version_id": v2, "state": "displayed"},
        headers=device,
    )
    # A straggler for the older revision arrives afterwards.
    client.post(
        "/api/device/acknowledge",
        json={"revision": 1, "version_id": v1, "state": "displayed"},
        headers=device,
    )

    state = client.get(f"/api/displays/{display_id}", headers=auth).json()
    assert state["reported_revision"] == 2
    assert state["reported_version_id"] == v2


def test_failed_media_does_not_advance_reported_version(client, auth, branches):
    v1 = make_ready_version(client, auth, branches["kuta"])
    v2 = make_ready_version(client, auth, branches["kuta"], {"USD": "17200"})
    display_id, device = pair_display(client, auth, branch_id=branches["kuta"])

    client.post(
        "/api/publications",
        json={"version_id": v1, "display_ids": [display_id]},
        headers=auth,
    )
    client.post(
        "/api/device/acknowledge",
        json={"revision": 1, "version_id": v1, "state": "displayed"},
        headers=device,
    )

    client.post(
        "/api/publications",
        json={"version_id": v2, "display_ids": [display_id]},
        headers=auth,
    )
    client.post(
        "/api/device/acknowledge",
        json={
            "revision": 2,
            "version_id": v2,
            "state": "failed",
            "error_message": "decode error",
        },
        headers=device,
    )

    state = client.get(f"/api/displays/{display_id}", headers=auth).json()
    # Still reporting the version it actually managed to show.
    assert state["reported_version_id"] == v1
    assert state["target_state"] == "failed"
    assert state["is_stale"] is True
    assert state["last_error"]


def test_branch_publish_resolves_to_current_displays_only(client, auth, branches):
    version_id = make_ready_version(client, auth, branches["kuta"])
    first_display, _d1 = pair_display(client, auth, "TV A", branches["kuta"])

    published = client.post(
        "/api/publications",
        json={"version_id": version_id, "branch_id": branches["kuta"]},
        headers=auth,
    ).json()
    assert [t["display_id"] for t in published["targets"]] == [first_display]

    # A display paired afterwards must not inherit that publication.
    later_display, later_device = pair_display(client, auth, "TV B", branches["kuta"])
    assignment = client.get("/api/device/assignment", headers=later_device).json()
    assert assignment["has_assignment"] is False
    assert later_display not in [t["display_id"] for t in published["targets"]]


def test_two_displays_can_hold_different_versions(client, auth, branches):
    v1 = make_ready_version(client, auth, branches["kuta"])
    v2 = make_ready_version(client, auth, branches["kuta"], {"USD": "17200"})

    display_a, device_a = pair_display(client, auth, "TV A", branches["kuta"])
    display_b, device_b = pair_display(client, auth, "TV B", branches["kuta"])

    client.post(
        "/api/publications",
        json={"version_id": v1, "display_ids": [display_a]},
        headers=auth,
    )
    client.post(
        "/api/publications",
        json={"version_id": v2, "display_ids": [display_b]},
        headers=auth,
    )

    assert client.get("/api/device/assignment", headers=device_a).json()["version_id"] == v1
    assert client.get("/api/device/assignment", headers=device_b).json()["version_id"] == v2


def test_rollback_creates_a_new_publication_and_revision(client, auth, branches):
    v1 = make_ready_version(client, auth, branches["kuta"])
    v2 = make_ready_version(client, auth, branches["kuta"], {"USD": "17200"})
    display_id, _device = pair_display(client, auth, branch_id=branches["kuta"])

    client.post(
        "/api/publications",
        json={"version_id": v1, "display_ids": [display_id]},
        headers=auth,
    )
    client.post(
        "/api/publications",
        json={"version_id": v2, "display_ids": [display_id]},
        headers=auth,
    )

    rollback = client.post(
        f"/api/displays/{display_id}/rollback", json={}, headers=auth
    )
    assert rollback.status_code == 200
    body = rollback.json()

    assert body["version_id"] == v1
    assert body["targets"][0]["revision"] == 3  # forward, never reusing revision 1
    assert body["rollback_of_id"] is not None


def test_version_in_use_cannot_be_archived_or_deleted(client, auth, branches):
    version_id = make_ready_version(client, auth, branches["kuta"])
    display_id, _device = pair_display(client, auth, branch_id=branches["kuta"])
    client.post(
        "/api/publications",
        json={"version_id": version_id, "display_ids": [display_id]},
        headers=auth,
    )

    assert client.post(f"/api/versions/{version_id}/archive", headers=auth).status_code == 409
    assert client.delete(f"/api/versions/{version_id}", headers=auth).status_code == 409


def test_refresh_command_is_one_shot(client, auth, branches):
    display_id, device = pair_display(client, auth, branch_id=branches["kuta"])

    assert client.post(f"/api/displays/{display_id}/refresh", headers=auth).status_code == 200

    assignment = client.get("/api/device/assignment", headers=device).json()
    command = assignment["pending_command"]
    assert command and command["command"] == "refresh"

    client.post(
        "/api/device/command-ack", json={"command_id": command["id"]}, headers=device
    )

    # Once acknowledged it must not come back, or the player would reload forever.
    again = client.get("/api/device/assignment", headers=device).json()
    assert again["pending_command"] is None


# --------------------------------------------------------------------------
# Scheduling
# --------------------------------------------------------------------------
def test_scheduled_publication_does_not_apply_before_its_time(client, auth, branches):
    version_id = make_ready_version(client, auth, branches["kuta"])
    display_id, device = pair_display(client, auth, branch_id=branches["kuta"])

    future = (utcnow() + timedelta(hours=2)).isoformat()
    response = client.post(
        "/api/publications",
        json={
            "version_id": version_id,
            "display_ids": [display_id],
            "scheduled_at": future,
        },
        headers=auth,
    )
    assert response.status_code == 201
    assert response.json()["state"] == "scheduled"

    assignment = client.get("/api/device/assignment", headers=device).json()
    assert assignment["has_assignment"] is False


def test_scheduler_fires_once_even_with_two_workers(client, auth, branches):
    version_id = make_ready_version(client, auth, branches["kuta"])
    display_id, _device = pair_display(client, auth, branch_id=branches["kuta"])

    # Schedule ahead, then backdate the row so it is genuinely due. Passing a
    # past timestamp to the API means "publish now", which is a different path.
    future = (utcnow() + timedelta(hours=1)).isoformat()
    created = client.post(
        "/api/publications",
        json={
            "version_id": version_id,
            "display_ids": [display_id],
            "scheduled_at": future,
        },
        headers=auth,
    ).json()
    publication_id = created["id"]
    assert created["state"] == "scheduled"

    setup_db = SessionLocal()
    try:
        publication = setup_db.get(Publication, publication_id)
        publication.scheduled_at = (utcnow() - timedelta(minutes=5)).replace(tzinfo=None)
        setup_db.commit()
    finally:
        setup_db.close()

    due_db = SessionLocal()
    try:
        assert publication_id in publishing.due_schedules(due_db)
    finally:
        due_db.close()

    # Two workers race for the same schedule.
    db_one = SessionLocal()
    db_two = SessionLocal()
    try:
        first = publishing.claim_schedule(db_one, publication_id)
        db_one.commit()
        second = publishing.claim_schedule(db_two, publication_id)
        db_two.commit()
    finally:
        db_one.close()
        db_two.close()

    assert first is not None
    assert second is None, "a schedule must only ever be claimed once"


def test_cancelled_schedule_never_fires(client, auth, branches):
    version_id = make_ready_version(client, auth, branches["kuta"])
    display_id, device = pair_display(client, auth, branch_id=branches["kuta"])

    future = (utcnow() + timedelta(hours=1)).isoformat()
    created = client.post(
        "/api/publications",
        json={
            "version_id": version_id,
            "display_ids": [display_id],
            "scheduled_at": future,
        },
        headers=auth,
    ).json()

    cancelled = client.post(
        f"/api/publications/{created['id']}/cancel", headers=auth
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"

    db = SessionLocal()
    try:
        assert publishing.claim_schedule(db, created["id"]) is None
    finally:
        db.close()

    assert client.get("/api/device/assignment", headers=device).json()["has_assignment"] is False


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------
def test_a_job_is_claimed_by_exactly_one_worker(client, auth, branches):
    with SessionLocal() as queue_db:
        jobs_service.enqueue(queue_db, job_type="cleanup_media", payload={"deleted_version_id": 999, "asset_ids": []})
        queue_db.commit()

    db_one = SessionLocal()
    db_two = SessionLocal()
    try:
        first = jobs_service.claim_next(db_one)
        second = jobs_service.claim_next(db_two)
    finally:
        db_one.close()
        db_two.close()

    assert first is not None
    assert second is None


def test_stale_job_is_requeued_after_its_lease_expires(client, auth, branches, db):
    with SessionLocal() as queue_db:
        jobs_service.enqueue(queue_db, job_type="cleanup_media", payload={"deleted_version_id": 999, "asset_ids": []})
        queue_db.commit()

    worker_db = SessionLocal()
    try:
        job = jobs_service.claim_next(worker_db)
        assert job is not None
        # Simulate the worker dying mid-job.
        job.lease_expires_at = (utcnow() - timedelta(minutes=30)).replace(tzinfo=None)
        worker_db.commit()
        job_id = job.id
    finally:
        worker_db.close()

    recovery_db = SessionLocal()
    try:
        recovered = jobs_service.recover_stale(recovery_db)
        recovery_db.commit()
        assert recovered == 1
        assert recovery_db.get(Job, job_id).status == JobStatus.QUEUED.value
    finally:
        recovery_db.close()


def test_concurrent_generates_write_to_separate_files(client, auth, branches):
    """Two versions generated at once must not overwrite each other."""
    first = make_ready_version(client, auth, branches["kuta"], {"USD": "16000"})
    second = make_ready_version(client, auth, branches["kuta"], {"USD": "18000"})

    db = SessionLocal()
    try:
        a = db.get(RateVersion, first)
        b = db.get(RateVersion, second)
        assert a.png_asset_id != b.png_asset_id

        from app.models import MediaAsset

        key_a = db.get(MediaAsset, a.png_asset_id).storage_key
        key_b = db.get(MediaAsset, b.png_asset_id).storage_key
        assert key_a != key_b

        from app.services import storage

        assert storage.read_asset(db.get(MediaAsset, a.png_asset_id)) != storage.read_asset(
            db.get(MediaAsset, b.png_asset_id)
        )
    finally:
        db.close()


def test_scheduling_in_the_past_publishes_immediately(client, auth, branches):
    """A past timestamp means now, not a schedule that never fires."""
    version_id = make_ready_version(client, auth, branches["kuta"])
    display_id, device = pair_display(client, auth, branch_id=branches["kuta"])

    past = (utcnow() - timedelta(minutes=5)).isoformat()
    created = client.post(
        "/api/publications",
        json={
            "version_id": version_id,
            "display_ids": [display_id],
            "scheduled_at": past,
        },
        headers=auth,
    ).json()

    assert created["state"] == "active"
    assert client.get("/api/device/assignment", headers=device).json()["has_assignment"] is True
