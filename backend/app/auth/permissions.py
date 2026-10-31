from enum import StrEnum

from app.core.config import get_settings


class Permission(StrEnum):
    WORKFLOW_VIEW_ALL = "workflow_view_all"
    WORKFLOW_VIEW_OWN = "workflow_view_own"
    WORKFLOW_SUBMIT = "workflow_submit"
    BUSINESS_VIEW_ALL = "business_view_all"
    BUSINESS_VIEW_OWN = "business_view_own"
    INTEGRATION_VIEW = "integration_view"
    INTEGRATION_CONFIGURE = "integration_configure"
    APPROVE = "approve"
    USER_MANAGE = "user_manage"
    AUDIT_VIEW_ALL = "audit_view_all"
    AUDIT_VIEW_OWN = "audit_view_own"
    RETRY_ANY = "retry_any"
    RETRY_OWN = "retry_own"


# Spec section 5.2. The backend is the only place these are decided.
_ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "admin": frozenset(
        {
            Permission.WORKFLOW_VIEW_ALL,
            Permission.WORKFLOW_SUBMIT,
            Permission.BUSINESS_VIEW_ALL,
            Permission.INTEGRATION_VIEW,
            Permission.INTEGRATION_CONFIGURE,
            Permission.APPROVE,
            Permission.USER_MANAGE,
            Permission.AUDIT_VIEW_ALL,
            Permission.RETRY_ANY,
        }
    ),
    "manager": frozenset(
        {
            Permission.WORKFLOW_VIEW_ALL,
            Permission.WORKFLOW_SUBMIT,
            Permission.BUSINESS_VIEW_ALL,
            Permission.INTEGRATION_VIEW,
            Permission.APPROVE,
            Permission.AUDIT_VIEW_ALL,
            Permission.RETRY_ANY,
        }
    ),
    "operator": frozenset(
        {
            Permission.WORKFLOW_VIEW_OWN,
            Permission.WORKFLOW_SUBMIT,
            Permission.BUSINESS_VIEW_OWN,
            Permission.INTEGRATION_VIEW,
            Permission.AUDIT_VIEW_OWN,
            Permission.RETRY_OWN,
        }
    ),
    "viewer": frozenset(
        {
            Permission.WORKFLOW_VIEW_ALL,
            Permission.BUSINESS_VIEW_ALL,
            Permission.INTEGRATION_VIEW,
            Permission.AUDIT_VIEW_ALL,
        }
    ),
}


def role_has(role: str, permission: Permission) -> bool:
    if permission is Permission.APPROVE and role == "admin":
        return get_settings().admin_can_approve
    return permission in _ROLE_PERMISSIONS.get(role, frozenset())


def permissions_for(role: str) -> list[str]:
    return sorted(p.value for p in Permission if role_has(role, p))
