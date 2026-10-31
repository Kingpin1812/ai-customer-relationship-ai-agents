from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select

from app.auth.permissions import Permission, role_has
from app.models import AuditEvent


@pytest.mark.parametrize(
    ("role", "permission", "allowed"),
    [
        ("admin", Permission.WORKFLOW_SUBMIT, True),
        ("manager", Permission.WORKFLOW_SUBMIT, True),
        ("operator", Permission.WORKFLOW_SUBMIT, True),
        ("viewer", Permission.WORKFLOW_SUBMIT, False),
        ("admin", Permission.INTEGRATION_CONFIGURE, True),
        ("manager", Permission.INTEGRATION_CONFIGURE, False),
        ("operator", Permission.INTEGRATION_CONFIGURE, False),
        ("viewer", Permission.INTEGRATION_CONFIGURE, False),
        ("admin", Permission.APPROVE, True),
        ("manager", Permission.APPROVE, True),
        ("operator", Permission.APPROVE, False),
        ("viewer", Permission.APPROVE, False),
        ("admin", Permission.USER_MANAGE, True),
        ("manager", Permission.USER_MANAGE, False),
        ("operator", Permission.USER_MANAGE, False),
        ("viewer", Permission.USER_MANAGE, False),
        ("admin", Permission.AUDIT_VIEW_ALL, True),
        ("manager", Permission.AUDIT_VIEW_ALL, True),
        ("operator", Permission.AUDIT_VIEW_ALL, False),
        ("operator", Permission.AUDIT_VIEW_OWN, True),
        ("viewer", Permission.AUDIT_VIEW_ALL, True),
        ("admin", Permission.RETRY_ANY, True),
        ("manager", Permission.RETRY_ANY, True),
        ("operator", Permission.RETRY_ANY, False),
        ("operator", Permission.RETRY_OWN, True),
        ("viewer", Permission.RETRY_OWN, False),
        ("viewer", Permission.RETRY_ANY, False),
        ("operator", Permission.WORKFLOW_VIEW_ALL, False),
        ("operator", Permission.WORKFLOW_VIEW_OWN, True),
        ("viewer", Permission.WORKFLOW_VIEW_ALL, True),
    ],
)
def test_role_matrix(role, permission, allowed):
    assert role_has(role, permission) is allowed


def test_protected_endpoint_needs_a_token(client):
    response = client.get("/api/v1/workflows")
    assert response.status_code == 401
    assert response.json()["error"]["category"] == "authentication_error"


def test_tampered_and_expired_tokens_are_refused(client, operator, settings):
    tampered = operator.token[:-3] + "abc"
    expired = jwt.encode(
        {"sub": "dev|operator@demo.test", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    for token in (tampered, expired):
        response = client.get("/api/v1/workflows", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


def test_token_signed_with_none_algorithm_is_refused(client):
    token = jwt.encode({"sub": "dev|admin@demo.test"}, "", algorithm="none")
    response = client.get("/api/v1/workflows", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_lists_role_and_permissions(manager, operator):
    me = manager.get("/auth/me").json()
    assert me["role"] == "manager"
    assert "approve" in me["permissions"]
    assert "approve" not in operator.get("/auth/me").json()["permissions"]


def test_org_header_for_foreign_org_is_forbidden(operator, other_admin):
    other_org = other_admin.get("/auth/me").json()["organization_id"]
    response = operator.get("/workflows", headers={"X-Organization-Id": other_org})
    assert response.status_code == 403


def test_dev_login_is_unavailable_outside_dev_mode(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "auth_mode", "oidc")
    response = client.post("/api/v1/auth/dev-login", json={"email": "admin@demo.test"})
    assert response.status_code == 404


def test_unknown_user_cannot_dev_login(client):
    response = client.post("/api/v1/auth/dev-login", json={"email": "ghost@demo.test"})
    assert response.status_code == 401


def test_admin_changes_role_and_it_is_audited(admin, operator, db):
    members = admin.get("/members").json()["items"]
    target = next(m for m in members if m["email"] == "operator@demo.test")
    response = admin.patch(f"/members/{target['user_id']}", json={"role": "viewer"})
    assert response.status_code == 200
    assert operator.get("/auth/me").json()["role"] == "viewer"
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "member.role_changed"))
    assert event is not None
    assert event.event_metadata["new_role"] == "viewer"


def test_non_admin_cannot_change_roles(manager):
    members = manager.get("/members")
    assert members.status_code == 403


def test_last_admin_cannot_be_demoted(admin):
    me = admin.get("/auth/me").json()
    response = admin.patch(f"/members/{me['user_id']}", json={"role": "viewer"})
    assert response.status_code == 409
