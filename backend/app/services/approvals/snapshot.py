"""The exact thing a person approves, rebuilt only from trusted records."""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.crm import get_crm_adapter
from app.models import Artifact, Customer, EmailDraft, Invoice, Workflow


def payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def crm_note_text(workflow: Workflow, invoice: Invoice | None) -> str:
    if invoice:
        return (
            f"Invoice {invoice.invoice_number} for {invoice.currency} {invoice.total:.2f} "
            f"prepared by workflow {workflow.id}."
        )
    return f"Account reviewed by workflow {workflow.id}."


def should_issue_invoice(plan: dict) -> bool:
    return "invoice" in plan["actions"] and (
        plan.get("issue_invoice") or "email" in plan["actions"]
    )


def has_sensitive_actions(plan: dict) -> bool:
    return bool({"crm_note", "email"} & set(plan["actions"])) or should_issue_invoice(plan)


def build_snapshot(db: Session, workflow: Workflow) -> dict:
    """Read current trusted state. Recipient comes from the CRM now, not from any earlier draft."""
    plan = workflow.plan
    customer = db.get(Customer, workflow.customer_id)
    current = get_crm_adapter(workflow.organization_id).get(customer.provider_customer_id)
    invoice = db.scalar(
        select(Invoice).where(
            Invoice.organization_id == workflow.organization_id, Invoice.workflow_id == workflow.id
        )
    )
    artifact = db.get(Artifact, invoice.artifact_id) if invoice and invoice.artifact_id else None
    artifact_ref = (
        {
            "artifact_id": str(artifact.id),
            "filename": artifact.filename,
            "checksum": artifact.checksum,
        }
        if artifact
        else None
    )

    actions: list[dict] = []
    if invoice and should_issue_invoice(plan):
        actions.append(
            {
                "type": "issue_invoice",
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "currency": invoice.currency,
                "subtotal": f"{invoice.subtotal:.2f}",
                "tax": f"{invoice.tax:.2f}",
                "total": f"{invoice.total:.2f}",
                "due_date": invoice.due_date.isoformat(),
                "artifact": artifact_ref,
            }
        )
    if "crm_note" in plan["actions"]:
        actions.append(
            {
                "type": "update_crm_note",
                "provider": "mock_crm",
                "provider_customer_id": customer.provider_customer_id,
                "note": crm_note_text(workflow, invoice),
            }
        )
    if "email" in plan["actions"]:
        draft = db.scalar(
            select(EmailDraft).where(
                EmailDraft.organization_id == workflow.organization_id,
                EmailDraft.workflow_id == workflow.id,
            )
        )
        actions.append(
            {
                "type": "send_email",
                "provider": "mock_email",
                "to": current.email,
                "subject": draft.subject,
                "body": draft.body,
                "attachments": [artifact_ref] if artifact_ref else [],
            }
        )
    return {
        "action_type": "workflow_bundle",
        "workflow_id": str(workflow.id),
        "organization_id": str(workflow.organization_id),
        "customer": {
            "id": str(customer.id),
            "provider_customer_id": customer.provider_customer_id,
            "name": current.name,
        },
        "actions": actions,
    }


def describe(snapshot: dict) -> str:
    parts = []
    for action in snapshot["actions"]:
        if action["type"] == "issue_invoice":
            parts.append(
                f"Issue invoice {action['invoice_number']} for "
                f"{action['currency']} {action['total']}"
            )
        elif action["type"] == "update_crm_note":
            parts.append("Add a note to the CRM record")
        elif action["type"] == "send_email":
            parts.append(f"Email {action['to']}")
    return f"{snapshot['customer']['name']}: " + "; ".join(parts) + "."
