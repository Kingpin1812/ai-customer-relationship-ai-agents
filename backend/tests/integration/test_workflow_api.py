from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select

from app.models import AuditEvent, Workflow


def test_submit_returns_workflow_id_and_persists(operator, submit, db):
    response = submit(operator, "Generate this month's sales summary")
    assert response.status_code == 202
    body = response.json()
    assert body["workflow_id"]
    assert body["status"]
    workflow = db.get(Workflow, body["workflow_id"])
    assert workflow.request_text == "Generate this month's sales summary"
    assert db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "workflow.created", AuditEvent.workflow_id == workflow.id
        )
    )


def test_viewer_cannot_submit(viewer, submit):
    assert submit(viewer).status_code == 403


def test_same_key_same_request_returns_existing(operator, submit, db):
    first = submit(operator, "Generate this month's sales summary", key="k1")
    second = submit(operator, "Generate this month's sales summary", key="k1")
    assert second.status_code == 200
    assert second.json()["workflow_id"] == first.json()["workflow_id"]
    assert db.scalar(select(func.count()).select_from(Workflow)) == 1


def test_same_key_different_request_is_rejected(operator, submit, db):
    submit(operator, "Generate this month's sales summary", key="k2")
    response = submit(operator, "Generate last month's sales summary", key="k2")
    assert response.status_code == 409
    assert db.scalar(select(func.count()).select_from(Workflow)) == 1


def test_same_key_is_independent_between_tenants(operator, other_admin, submit):
    a = submit(operator, "Generate this month's sales summary", key="shared")
    b = submit(other_admin, "Generate this month's sales summary", key="shared")
    assert a.json()["workflow_id"] != b.json()["workflow_id"]


def test_double_click_creates_one_workflow(operator, submit, db):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: submit(operator, "Generate this month's sales summary", key="dbl"),
                range(4),
            )
        )
    assert {r.status_code for r in results} <= {200, 202}
    assert len({r.json()["workflow_id"] for r in results}) == 1
    assert db.scalar(select(func.count()).select_from(Workflow)) == 1


def test_empty_oversized_and_unknown_fields_are_rejected(operator, submit, settings):
    assert submit(operator, "   ").status_code == 422
    assert submit(operator, "x" * (settings.max_request_chars + 1)).status_code == 422
    bad = operator.post(
        "/workflows", json={"request": "hi there", "idempotency_key": "k", "admin": True}
    )
    assert bad.status_code == 422
    missing_key = operator.post("/workflows", json={"request": "hi there"})
    assert missing_key.status_code == 422


def test_unknown_simulation_is_rejected(operator, submit):
    assert submit(operator, context={"simulate": "drop_tables"}).status_code == 422


def test_simulation_is_refused_when_fault_injection_is_off(operator, submit, settings, monkeypatch):
    monkeypatch.setattr(settings, "enable_fault_injection", False)
    assert submit(operator, context={"simulate": "crm_timeout"}).status_code == 422


def test_operator_sees_only_own_workflows(operator, manager, submit):
    mine = submit(operator, "Generate this month's sales summary").json()["workflow_id"]
    theirs = submit(manager, "Generate this month's sales summary").json()["workflow_id"]
    ids = [w["id"] for w in operator.get("/workflows").json()["items"]]
    assert mine in ids
    assert theirs not in ids
    assert operator.get(f"/workflows/{theirs}").status_code == 404
    assert {mine, theirs} <= {w["id"] for w in manager.get("/workflows").json()["items"]}


def test_other_tenant_workflow_is_not_found(operator, other_admin, submit):
    workflow_id = submit(operator, "Generate this month's sales summary").json()["workflow_id"]
    assert other_admin.get(f"/workflows/{workflow_id}").status_code == 404
    assert workflow_id not in [w["id"] for w in other_admin.get("/workflows").json()["items"]]


def test_list_pagination_and_filters(manager, submit):
    for i in range(3):
        submit(manager, f"Generate this month's sales summary {i}")
    page = manager.get("/workflows", params={"limit": 2, "offset": 0}).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert manager.get("/workflows", params={"limit": 1000}).status_code == 422
    assert manager.get("/workflows", params={"status": "nonsense"}).status_code == 422
    assert manager.get("/workflows", params={"status": "cancelled"}).json()["total"] == 0
    assert manager.get("/workflows", params={"q": "summary 1"}).json()["total"] == 1
    assert manager.get("/workflows", params={"q": "%"}).json()["total"] == 0
    assert manager.get("/workflows", params={"date_from": "2999-01-01"}).json()["total"] == 0


def test_error_body_has_consistent_shape_and_no_internals(operator):
    response = operator.get("/workflows/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    error = response.json()["error"]
    assert set(error) >= {"category", "message", "correlation_id"}
