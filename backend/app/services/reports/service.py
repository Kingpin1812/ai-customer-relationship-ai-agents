import csv
import io
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.models import Report
from app.services.artifacts import store_artifact
from app.services.reports.definitions import REPORTS, ReportDefinition, resolve_period


def _csv_safe(value: object) -> str:
    """Stop spreadsheet apps treating CRM-derived text as a formula."""
    text = str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _render_csv(
    report_type: str, start: date, end: date, generated: datetime, summary: dict
) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["report", report_type])
    writer.writerow(["period_start", start.isoformat()])
    writer.writerow(["period_end", end.isoformat()])
    writer.writerow(["generated_at", generated.isoformat()])
    writer.writerow([])
    writer.writerow(["customer_name", "currency", "sales_count", "amount"])
    for row in summary["rows"]:
        writer.writerow(
            [_csv_safe(row["customer_name"]), row["currency"], row["sales_count"], row["amount"]]
        )
    writer.writerow(["total", "", "", summary["total"]])
    return buffer.getvalue().encode()


def _render_pdf(title: str, start: date, end: date, generated: datetime, summary: dict) -> bytes:
    buffer = io.BytesIO()
    pdf = Canvas(buffer, pagesize=A4, invariant=1)
    width, height = A4
    left, right = 20 * mm, width - 20 * mm
    y = height - 25 * mm
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(left, y, title)
    y -= 8 * mm
    pdf.setFont("Helvetica", 10)
    pdf.drawString(left, y, f"Period: {start.isoformat()} to {end.isoformat()}")
    y -= 5 * mm
    pdf.drawString(left, y, f"Generated: {generated.isoformat(timespec='seconds')}")
    y -= 10 * mm
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left, y, "Customer")
    pdf.drawRightString(right - 40 * mm, y, "Sales")
    pdf.drawRightString(right, y, "Amount")
    y -= 2 * mm
    pdf.line(left, y, right, y)
    y -= 6 * mm
    pdf.setFont("Helvetica", 10)
    for row in summary["rows"]:
        if y < 30 * mm:
            pdf.showPage()
            y = height - 25 * mm
            pdf.setFont("Helvetica", 10)
        pdf.drawString(left, y, row["customer_name"][:50])
        pdf.drawRightString(right - 40 * mm, y, str(row["sales_count"]))
        pdf.drawRightString(right, y, f"{row['currency']} {Decimal(row['amount']):,.2f}")
        y -= 6 * mm
    pdf.line(left, y + 3 * mm, right, y + 3 * mm)
    y -= 2 * mm
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(left, y, "Total")
    pdf.drawRightString(right, y, f"{Decimal(summary['total']):,.2f}")
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(
        left, 15 * mm, "Source: approved query over tenant sales records. Synthetic data."
    )
    pdf.save()
    return buffer.getvalue()


def _definition(report_type: str) -> ReportDefinition:
    definition = REPORTS.get(report_type)
    if definition is None:
        raise ValidationFailed(f"Report type '{report_type[:40]}' is not an approved report.")
    return definition


def generate_report(
    db: Session, organization_id: UUID, workflow_id: UUID, report_type: str, params: dict
) -> Report:
    """Run an approved, parameterized report. Returns the existing one on a repeat call."""
    definition = _definition(report_type)
    try:
        parsed: Any = definition.params_model.model_validate(params)
    except ValidationError as exc:
        raise ValidationFailed("Those report filters are not valid.") from exc

    existing = db.scalar(
        select(Report).where(
            Report.organization_id == organization_id,
            Report.workflow_id == workflow_id,
            Report.report_type == report_type,
        )
    )
    if existing:
        return existing

    start, end = resolve_period(parsed.period)
    rows = definition.run(db, organization_id, start, end, parsed.currency)
    total = sum((Decimal(r["amount"]) for r in rows), Decimal("0.00"))
    summary = {"rows": rows, "total": f"{total:.2f}"}
    generated = datetime.now(UTC)

    pdf = store_artifact(
        db,
        organization_id,
        workflow_id,
        "report",
        f"{report_type}_{start.isoformat()}.pdf",
        "application/pdf",
        _render_pdf(definition.title, start, end, generated, summary),
    )
    csv_file = store_artifact(
        db,
        organization_id,
        workflow_id,
        "report",
        f"{report_type}_{start.isoformat()}.csv",
        "text/csv",
        _render_csv(report_type, start, end, generated, summary),
    )
    report = Report(
        organization_id=organization_id,
        workflow_id=workflow_id,
        report_type=report_type,
        period_start=start,
        period_end=end,
        filters=parsed.model_dump(mode="json"),
        source={"query": definition.query_name, "table": "sales_records"},
        summary=summary,
        pdf_artifact_id=pdf.id,
        csv_artifact_id=csv_file.id,
        generated_at=generated,
    )
    db.add(report)
    db.flush()
    return report
