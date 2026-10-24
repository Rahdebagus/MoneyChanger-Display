"""Authentication and branch scoping.

These assert the server-side rules, not the UI. Every case calls the API
directly, the way a staff member with a token and curl would.
"""

from app.core.security import create_access_token
from app.models import User


def test_login_rejects_wrong_password(client, admin_user):
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "nope"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Username atau password salah."


def test_login_failure_does_not_reveal_whether_user_exists(client, admin_user):
    unknown = client.post(
        "/api/auth/login", json={"username": "ghost", "password": "whatever"}
    )
    wrong = client.post(
        "/api/auth/login", json={"username": "admin", "password": "whatever"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_error_response_carries_request_id_and_no_traceback(client, admin_user):
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "nope"}
    )
    body = response.json()
    assert body.get("request_id")
    serialized = response.text.lower()
    for leak in ("traceback", "c:\\\\", "site-packages", ".py\"", "sqlalchemy"):
        assert leak not in serialized


def test_me_requires_a_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_deactivating_a_user_invalidates_existing_tokens(client, db, admin_user, auth):
    staff = User(
        username="temp",
        password_hash=admin_user.password_hash,
        role="staff",
        is_active=True,
    )
    db.add(staff)
    db.commit()

    token, _ = create_access_token(
        user_id=staff.id, role=staff.role, token_version=staff.token_version
    )
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    response = client.patch(
        f"/api/users/{staff.id}", json={"is_active": False}, headers=auth
    )
    assert response.status_code == 200

    # The old token must stop working immediately, with no blacklist involved.
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_password_change_invalidates_old_tokens(client, db, admin_user, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "AdminPass123", "new_password": "BrandNewPass123"},
        headers=headers,
    )
    assert response.status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_staff_cannot_reach_admin_only_routes(client, staff_auth):
    assert client.get("/api/users", headers=staff_auth).status_code == 403
    assert client.get("/api/branches", headers=staff_auth).status_code == 403
    assert (
        client.post(
            "/api/publications",
            json={"version_id": 1, "display_ids": [1]},
            headers=staff_auth,
        ).status_code
        == 403
    )


def test_staff_cannot_read_another_branch(client, db, branches, auth, staff_auth):
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
    assert created.status_code == 201
    version_id = created.json()["version"]["id"]

    # The staff fixture is assigned to Ubud only.
    assert client.get(f"/api/versions/{version_id}", headers=staff_auth).status_code == 403

    listing = client.get("/api/versions", headers=staff_auth)
    assert listing.status_code == 200
    assert listing.json()["total"] == 0


def test_staff_may_create_a_draft_in_their_own_branch(client, branches, staff_auth):
    response = client.post(
        "/api/versions",
        json={
            "rates": {"USD": "16950", "AUD": "12050"},
            "title": "MONEY CHANGER",
            "subtitle": "PT. PRADNYANA ARTHA MANDIRI",
        },
        headers=staff_auth,
    )
    assert response.status_code == 201
    assert response.json()["version"]["branch_id"] == branches["ubud"]
