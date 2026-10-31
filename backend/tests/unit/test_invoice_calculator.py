from decimal import Decimal as D

import pytest

from app.core.errors import ValidationFailed
from app.services.invoices.calculator import LineInput, calculate


def test_demo_invoice_totals():
    totals = calculate([LineInput("Consulting", D("10"), D("2500"))], D("0.18"))
    assert totals.subtotal == D("25000.00")
    assert totals.tax == D("4500.00")
    assert totals.total == D("29500.00")
    assert totals.lines[0].line_total == D("25000.00")


def test_rounding_is_half_up_not_bankers():
    totals = calculate([LineInput("x", D("1"), D("0.125"))], D("0"))
    assert totals.subtotal == D("0.13")


def test_binary_float_trap_is_avoided():
    totals = calculate([LineInput("x", D("3"), D("0.10"))], D("0"))
    assert totals.subtotal == D("0.30")


def test_total_always_equals_subtotal_plus_tax():
    totals = calculate(
        [LineInput("a", D("3"), D("33.33")), LineInput("b", D("7"), D("14.29"))], D("0.18")
    )
    assert totals.total == totals.subtotal + totals.tax


@pytest.mark.parametrize(
    ("quantity", "price", "tax"),
    [
        (D("0"), D("10"), D("0.18")),
        (D("-1"), D("10"), D("0.18")),
        (D("1"), D("-10"), D("0.18")),
        (D("1"), D("10"), D("-0.01")),
        (D("1"), D("10"), D("1.01")),
        (D("NaN"), D("10"), D("0.18")),
        (D("1"), D("Infinity"), D("0.18")),
    ],
)
def test_invalid_values_are_rejected(quantity, price, tax):
    with pytest.raises(ValidationFailed):
        calculate([LineInput("x", quantity, price)], tax)


def test_no_lines_is_rejected():
    with pytest.raises(ValidationFailed):
        calculate([], D("0.18"))


def test_amount_too_large_is_rejected():
    with pytest.raises(ValidationFailed):
        calculate([LineInput("x", D("999999"), D("999999999"))], D("0"))


@pytest.mark.parametrize(
    "quantity,price",
    [
        (D("1.2345"), D("100")),  # the quantity column holds 3 decimals
        (D("1"), D("1.23456")),  # the price column holds 4 decimals
        (D("1"), D("10000000000")),  # the price column holds 10 whole digits
    ],
)
def test_values_the_database_would_change_are_refused(quantity, price):
    with pytest.raises(ValidationFailed):
        calculate([LineInput("x", quantity, price)], D("0"))


def test_trailing_zeros_are_not_extra_precision():
    totals = calculate([LineInput("x", D("1.50000"), D("2.000000"))], D("0"))
    assert totals.subtotal == D("3.00")
