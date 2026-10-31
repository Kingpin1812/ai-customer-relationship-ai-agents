"""Approved report definitions. A report that is not listed here cannot run."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import SalesRecord


class MonthlySalesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: Literal["this_month", "last_month"] = "this_month"
    currency: Literal["INR", "USD", "EUR", "GBP"] | None = None


def resolve_period(period: str, today: date | None = None) -> tuple[date, date]:
    today = today or datetime.now(UTC).date()
    first = today.replace(day=1)
    if period == "last_month":
        end = first - timedelta(days=1)
        return end.replace(day=1), end
    next_month = (first + timedelta(days=32)).replace(day=1)
    return first, next_month - timedelta(days=1)


def monthly_sales_rows(
    db: Session, organization_id: UUID, start: date, end: date, currency: str | None
) -> list[dict]:
    statement = (
        select(
            SalesRecord.customer_name,
            SalesRecord.currency,
            func.count().label("sales_count"),
            func.sum(SalesRecord.amount).label("amount"),
        )
        .where(
            SalesRecord.organization_id == organization_id,
            SalesRecord.sold_on >= start,
            SalesRecord.sold_on <= end,
        )
        .group_by(SalesRecord.customer_name, SalesRecord.currency)
        .order_by(SalesRecord.customer_name)
    )
    if currency:
        statement = statement.where(SalesRecord.currency == currency)
    return [
        {
            "customer_name": r.customer_name,
            "currency": r.currency,
            "sales_count": r.sales_count,
            "amount": f"{r.amount:.2f}",
        }
        for r in db.execute(statement)
    ]


@dataclass(frozen=True)
class ReportDefinition:
    title: str
    query_name: str
    params_model: type[BaseModel]
    run: Callable[..., list[dict]]


REPORTS: dict[str, ReportDefinition] = {
    "monthly_sales_summary": ReportDefinition(
        title="Monthly sales summary",
        query_name="monthly_sales_summary.v1",
        params_model=MonthlySalesParams,
        run=monthly_sales_rows,
    )
}
