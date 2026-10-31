"""Docker is not available everywhere tests run, so check what the deploy files promise statically."""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from celery.signals import worker_init
from prometheus_client import REGISTRY

import app.observability.metrics  # noqa: F401 - registers the metrics
from app.workers import celery_app as celery_module

ROOT = Path(__file__).resolve().parents[3]
MONITORING = ROOT / "infra" / "monitoring"
_SUFFIXES = ("", "_total", "_bucket", "_sum", "_count")


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def _exposed_metric_names() -> set[str]:
    names = set()
    for family in REGISTRY.collect():
        names.update(family.name + suffix for suffix in _SUFFIXES)
    return names


def test_every_dashboard_query_uses_a_metric_the_app_exposes():
    dashboard = json.loads(
        (MONITORING / "grafana" / "dashboards" / "workflow-overview.json").read_text(
            encoding="utf-8"
        )
    )
    exposed = _exposed_metric_names()
    used = set()
    for panel in dashboard["panels"]:
        for target in panel["targets"]:
            used.update(re.findall(r"[a-z_]+(?:_total|_bucket)\b", target["expr"]))
    assert used
    assert used <= exposed, f"not exposed: {used - exposed}"


def test_prometheus_scrapes_the_api_and_the_worker_metrics_port(compose):
    config = yaml.safe_load((MONITORING / "prometheus.yml").read_text(encoding="utf-8"))
    targets = {
        t for job in config["scrape_configs"] for c in job["static_configs"] for t in c["targets"]
    }
    port = compose["services"]["worker"]["environment"]["WORKER_METRICS_PORT"]
    assert targets == {"api:8000", f"worker:{port}"}


def test_published_ports_are_local_only(compose):
    for name, service in compose["services"].items():
        for port in service.get("ports", []):
            assert port.startswith("127.0.0.1:"), f"{name} publishes {port} to the network"


def test_compose_holds_no_literal_secrets(compose):
    env = compose["x-backend-env"]
    for key in ("JWT_SECRET", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        assert env[key].startswith("${"), key
    assert "${POSTGRES_PASSWORD" in env["DATABASE_URL"]


def test_built_services_have_dockerfiles(compose):
    built = [s["build"] for s in compose["services"].values() if isinstance(s.get("build"), str)]
    assert {"./backend", "./frontend"} <= set(built)
    for context in built:
        assert (ROOT / context / "Dockerfile").is_file()


def test_env_example_defines_every_required_compose_variable():
    required = set(
        re.findall(r"\$\{(\w+):\?", (ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    )
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    defined = set(re.findall(r"^(\w+)=", example, re.M))
    assert required and required <= defined


def test_worker_serves_metrics_when_a_port_is_set(monkeypatch):
    started = []
    monkeypatch.setattr(celery_module, "configure_logging", lambda: None)
    monkeypatch.setattr(celery_module, "configure_tracing", lambda: None)
    monkeypatch.setattr(celery_module, "start_http_server", started.append)
    monkeypatch.setattr(
        celery_module, "get_settings", lambda: SimpleNamespace(worker_metrics_port=9101)
    )
    worker_init.send(sender=None)
    assert started == [9101]


def test_worker_serves_no_metrics_by_default(monkeypatch):
    started = []
    monkeypatch.setattr(celery_module, "configure_logging", lambda: None)
    monkeypatch.setattr(celery_module, "configure_tracing", lambda: None)
    monkeypatch.setattr(celery_module, "start_http_server", started.append)
    monkeypatch.setattr(
        celery_module, "get_settings", lambda: SimpleNamespace(worker_metrics_port=None)
    )
    worker_init.send(sender=None)
    assert started == []


def test_settings_in_dot_env_reach_the_backend_containers(compose):
    assert compose["x-backend"]["env_file"] == [".env"]
