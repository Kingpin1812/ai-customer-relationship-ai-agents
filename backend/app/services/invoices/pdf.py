"""Invoice PDF. Uses drawString, which does not parse markup, so CRM text cannot inject anything."""

import io
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from app.models import Customer, Invoice, InvoiceItem


def _money(currency: str, value) -> str:
    return f"{currency} {value:,.2f}"


def render_invoice_pdf(
    invoice: Invoice, customer: Customer, items: list[InvoiceItem], organization_name: str
) -> bytes:
    buffer = io.BytesIO()
    pdf = Canvas(buffer, pagesize=A4, invariant=1)
    width, height = A4
    left, right = 20 * mm, width - 20 * mm
    y = height - 25 * mm

    pdf.setTitle(f"Invoice {invoice.invoice_number}")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(left, y, "INVOICE")
    pdf.setFont("Helvetica", 10)
    pdf.drawRightString(right, y, organization_name[:60])
    y -= 10 * mm
    for label, value in (
        ("Invoice number", invoice.invoice_number),
        ("Issue date", invoice.issue_date.isoformat()),
        ("Due date", invoice.due_date.isoformat()),
        ("Bill to", customer.name[:70]),
        ("Email", customer.email[:70]),
    ):
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left, y, label)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(left + 35 * mm, y, value)
        y -= 6 * mm

    y -= 6 * mm
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left, y, "Description")
    pdf.drawRightString(right - 65 * mm, y, "Qty")
    pdf.drawRightString(right - 35 * mm, y, "Unit price")
    pdf.drawRightString(right, y, "Line total")
    y -= 2 * mm
    pdf.line(left, y, right, y)
    y -= 6 * mm
    pdf.setFont("Helvetica", 10)
    for item in items:
        if y < 50 * mm:
            pdf.showPage()
            y = height - 25 * mm
            pdf.setFont("Helvetica", 10)
        pdf.drawString(left, y, item.description[:50])
        pdf.drawRightString(right - 65 * mm, y, f"{item.quantity.normalize():f}")
        pdf.drawRightString(right - 35 * mm, y, f"{item.unit_price:,.2f}")
        pdf.drawRightString(right, y, f"{item.line_total:,.2f}")
        y -= 6 * mm

    y -= 2 * mm
    pdf.line(left, y, right, y)
    y -= 7 * mm
    tax_percent = items[0].tax_rate * 100 if items else Decimal(0)
    for label, value, bold in (
        ("Subtotal", _money(invoice.currency, invoice.subtotal), False),
        (f"Tax ({tax_percent.normalize():f}%)", _money(invoice.currency, invoice.tax), False),
        ("Total", _money(invoice.currency, invoice.total), True),
    ):
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        pdf.drawRightString(right - 40 * mm, y, label)
        pdf.drawRightString(right, y, value)
        y -= 6 * mm

    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(left, 15 * mm, "Synthetic demonstration document. Not a tax invoice.")
    pdf.save()
    return buffer.getvalue()
