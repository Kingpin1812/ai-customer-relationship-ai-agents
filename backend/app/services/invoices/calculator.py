"""All invoice arithmetic. Decimal only, half-up to 2 places; no model output is ever trusted here."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.core.errors import ValidationFailed

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("999999999999.99")
MAX_QUANTITY = Decimal("999999999.999")
MAX_UNIT_PRICE = Decimal("9999999999.9999")
QUANTITY_STEP = Decimal("0.001")
PRICE_STEP = Decimal("0.0001")


@dataclass(frozen=True)
class LineInput:
    description: str
    quantity: Decimal
    unit_price: Decimal


@dataclass(frozen=True)
class LineTotal:
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


@dataclass(frozen=True)
class InvoiceTotals:
    lines: list[LineTotal]
    tax_rate: Decimal
    subtotal: Decimal
    tax: Decimal
    total: Decimal


def _round(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def calculate(items: list[LineInput], tax_rate: Decimal) -> InvoiceTotals:
    if not items:
        raise ValidationFailed("An invoice needs at least one line item.")
    if not tax_rate.is_finite() or not Decimal(0) <= tax_rate <= Decimal(1):
        raise ValidationFailed("Tax rate must be between 0% and 100%.")

    lines = []
    for item in items:
        if not item.description.strip():
            raise ValidationFailed("Every line item needs a description.")
        if not item.quantity.is_finite() or not Decimal(0) < item.quantity <= MAX_QUANTITY:
            raise ValidationFailed(f"Quantity for '{item.description}' must be greater than zero.")
        if item.quantity != item.quantity.quantize(QUANTITY_STEP):
            raise ValidationFailed(f"Quantity for '{item.description}' allows 3 decimal places.")
        if (
            not item.unit_price.is_finite()
            or item.unit_price < 0
            or item.unit_price > MAX_UNIT_PRICE
        ):
            raise ValidationFailed(f"Unit price for '{item.description}' is not valid.")
        if item.unit_price != item.unit_price.quantize(PRICE_STEP):
            raise ValidationFailed(f"Unit price for '{item.description}' allows 4 decimal places.")
        lines.append(
            LineTotal(
                item.description,
                item.quantity,
                item.unit_price,
                _round(item.quantity * item.unit_price),
            )
        )

    subtotal = sum((line.line_total for line in lines), Decimal("0.00"))
    tax = _round(subtotal * tax_rate)
    total = subtotal + tax
    if total > MAX_AMOUNT:
        raise ValidationFailed("The invoice total is larger than this system allows.")
    return InvoiceTotals(lines, tax_rate, subtotal, tax, total)
