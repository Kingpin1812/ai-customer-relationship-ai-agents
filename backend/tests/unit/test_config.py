import pytest
from pydantic import ValidationError

from app.core.config import Settings

STRONG = "x" * 40


def production(**overrides):
    values = {
        "environment": "production",
        "auth_mode": "oidc",
        "jwt_secret": STRONG,
        "oidc_issuer": "https://id.example",
        "oidc_audience": "workflow",
        "oidc_jwks_url": "https://id.example/jwks",
        "enable_fault_injection": False,
        "task_executor": "celery",
        "database_url": "postgresql+psycopg://u:p@db/app",
    }
    return Settings(_env_file=None, **{**values, **overrides})


def test_valid_production_settings_load():
    assert production().environment == "production"


@pytest.mark.parametrize(
    "overrides",
    [
        {"auth_mode": "dev"},
        {"enable_fault_injection": True},
        {"jwt_secret": "short"},
        {"task_executor": "inline"},
        {"oidc_issuer": None},
    ],
)
def test_production_refuses_unsafe_settings(overrides):
    with pytest.raises(ValidationError):
        production(**overrides)


def test_planner_defaults_to_rules_so_no_model_is_required(monkeypatch):
    monkeypatch.delenv("PLANNER_MODE")
    assert Settings(_env_file=None).planner_mode == "rules"
