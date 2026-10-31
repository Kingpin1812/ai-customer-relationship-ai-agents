from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"
_DEV_SECRET = "dev-only-insecure-secret-do-not-use-in-production"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ROOT_ENV, extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://workflow:workflow@localhost:5432/workflow"

    auth_mode: Literal["dev", "oidc"] = "dev"
    jwt_secret: str = _DEV_SECRET
    jwt_ttl_minutes: int = 480
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None

    task_executor: Literal["thread", "celery", "inline"] = "thread"
    redis_url: str = "redis://localhost:6379/0"
    maintenance_interval_seconds: int = 30
    worker_metrics_port: int | None = None

    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: str = "var/artifacts"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "workflow-artifacts"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"

    planner_mode: Literal["auto", "rules", "llm"] = "rules"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:latest"
    ollama_timeout_seconds: float = 45.0

    default_tax_rate: Decimal = Decimal("0.18")
    default_payment_terms_days: int = 30
    default_currency: str = "INR"
    allowed_currencies: str = "INR,USD,EUR,GBP"

    enable_fault_injection: bool = False
    approval_ttl_hours: int = 72
    allow_self_approval: bool = True
    admin_can_approve: bool = True

    retry_max_attempts: int = 4
    retry_base_delay_seconds: float = 0.5
    retry_max_delay_seconds: float = 8.0
    operation_timeout_seconds: float = 15.0

    max_request_chars: int = 4000
    max_body_bytes: int = 1_048_576
    max_upload_bytes: int = 5_242_880
    rate_limit_per_minute: int = 120
    cors_origins: str = "http://localhost:3000"

    otel_exporter_otlp_endpoint: str | None = None
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _refuse_unsafe_production(self) -> "Settings":
        if self.environment != "production":
            return self
        problems = []
        if self.auth_mode != "oidc":
            problems.append("AUTH_MODE must be oidc")
        if not (self.oidc_issuer and self.oidc_audience and self.oidc_jwks_url):
            problems.append("OIDC_ISSUER, OIDC_AUDIENCE and OIDC_JWKS_URL are required")
        if self.enable_fault_injection:
            problems.append("ENABLE_FAULT_INJECTION must be false")
        if self.task_executor == "inline":
            problems.append("TASK_EXECUTOR must not be inline")
        if self.jwt_secret == _DEV_SECRET or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be a unique value of at least 32 characters")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def currencies(self) -> set[str]:
        return {c.strip().upper() for c in self.allowed_currencies.split(",") if c.strip()}

    @property
    def checkpoint_conninfo(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
