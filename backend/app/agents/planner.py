"""Interpret a request into a typed plan. The plan says what was asked; it authorizes nothing."""

import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.core.errors import ClarificationNeeded
from app.integrations.llm.ollama import LlmClient, LlmUnavailable, OllamaClient

log = structlog.get_logger()

Action = Literal["invoice", "crm_note", "report", "email"]
_NEEDS_CUSTOMER = {"invoice", "crm_note", "email"}
_CURRENCY_SYMBOLS = {"₹": "INR", "rs": "INR", "rs.": "INR", "$": "USD", "€": "EUR", "£": "GBP"}
_NUMBER = r"\d[\d,]*(?:\.\d+)?"
_UNITS = r"hours?|hrs?|days?|units?|licen[sc]es?|items?|seats?|months?"
_LINE = re.compile(
    rf"(?P<qty>{_NUMBER})\s+(?P<unit>{_UNITS})\s+(?:of\s+)?(?P<desc>[^,.;]*?)\s*"
    rf"at\s+(?P<cur>₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP)?\s*(?P<price>{_NUMBER})"
    rf"(?:\s*(?P<suffix>INR|USD|EUR|GBP|Rs)\b)?",
    re.IGNORECASE,
)
_CUSTOMER = re.compile(r"\bfor\s+(?:customer\s+)?([A-Z][\w&'-]*\.?(?:\s+[A-Z][\w&'-]*\.?){0,4})")


class PlanLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=300)
    quantity: Decimal
    unit_price: Decimal


class PlanReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["monthly_sales_summary"] = "monthly_sales_summary"
    period: Literal["this_month", "last_month"] = "this_month"


class WorkflowPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: list[Action] = Field(default_factory=list, max_length=4)
    customer_reference: str | None = Field(default=None, max_length=200)
    line_items: list[PlanLineItem] = Field(default_factory=list, max_length=50)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    report: PlanReport | None = None
    issue_invoice: bool = False
    clarifications: list[str] = Field(default_factory=list, max_length=10)


def _parse_number(text: str) -> Decimal:
    return Decimal(text.replace(",", ""))


def _written_currencies(text: str) -> list[str]:
    """Currencies of the priced lines in the request, in order, each once."""
    found = []
    for match in _LINE.finditer(text):
        symbol = (match["cur"] or match["suffix"] or "").lower()
        if symbol:
            found.append(_CURRENCY_SYMBOLS.get(symbol) or symbol.upper())
    return list(dict.fromkeys(found))


def _mixed_currency_questions(currencies: list[str]) -> list[str]:
    if len(currencies) < 2:
        return []
    return [
        f"This request mixes currencies ({', '.join(currencies)}), but an invoice uses one. "
        "Which currency should it use?"
    ]


def _apply_context_and_gaps(plan: WorkflowPlan, context: dict) -> WorkflowPlan:
    """Deterministic checks shared by both planners, so the LLM cannot skip them."""
    if context.get("customer_reference"):
        plan.customer_reference = context["customer_reference"]
    if context.get("currency"):
        plan.currency = context["currency"]
    plan.actions = list(dict.fromkeys(plan.actions))
    questions = list(plan.clarifications)
    if not plan.actions:
        questions.append(
            "I could not find a task to do. Try asking for an invoice, report, CRM note or email."
        )
    if _NEEDS_CUSTOMER & set(plan.actions) and not plan.customer_reference:
        questions.append("Which customer is this for?")
    if "invoice" in plan.actions and not plan.line_items:
        questions.append(
            "What should the invoice charge for? Give quantities and prices, "
            "for example: 10 hours of consulting at ₹2,500 per hour."
        )
    if "report" in plan.actions and plan.report is None:
        plan.report = PlanReport()
    plan.clarifications = list(dict.fromkeys(questions))
    return plan


def parse_with_rules(text: str, context: dict) -> WorkflowPlan:
    actions: list[Action] = []
    if re.search(r"\binvoice\b", text, re.I):
        actions.append("invoice")
    if re.search(r"\bcrm\b|\bnote\b", text, re.I):
        actions.append("crm_note")
    if re.search(r"\breport\b|\bsummary\b", text, re.I):
        actions.append("report")
    if re.search(r"\be-?mail\b", text, re.I):
        actions.append("email")

    items = []
    for match in _LINE.finditer(text):
        try:
            quantity, price = _parse_number(match["qty"]), _parse_number(match["price"])
        except InvalidOperation:
            continue
        items.append(
            PlanLineItem(
                description=(match["desc"].strip() or match["unit"])[:300],
                quantity=quantity,
                unit_price=price,
            )
        )

    currencies = _written_currencies(text)
    customer = _CUSTOMER.search(text)
    reference = customer.group(1).rstrip(".,") if customer else None
    period: Literal["this_month", "last_month"] = (
        "last_month" if re.search(r"\b(last|previous)\s+month", text, re.I) else "this_month"
    )
    return _apply_context_and_gaps(
        WorkflowPlan(
            actions=actions,
            customer_reference=reference,
            line_items=items,
            currency=currencies[0] if currencies else None,
            report=PlanReport(period=period) if "report" in actions else None,
            issue_invoice=bool(re.search(r"\b(issue|finali[sz]e)\b", text, re.I)),
            clarifications=_mixed_currency_questions(currencies),
        ),
        context,
    )


def validate_llm_plan(raw: str, request_text: str, context: dict) -> WorkflowPlan:
    """Raise ValueError unless the output is schema-valid and invents nothing."""
    plan = WorkflowPlan.model_validate_json(raw)
    if "actions" not in plan.model_fields_set:
        raise ValueError("plan does not say which actions were asked for")
    written = {_parse_number(n) for n in re.findall(_NUMBER, request_text)}
    for item in plan.line_items:
        if item.quantity not in written or item.unit_price not in written:
            raise ValueError("plan contains a number that is not in the request")
    if plan.customer_reference and plan.customer_reference.lower() not in request_text.lower():
        raise ValueError("plan names a customer that is not in the request")
    currencies = _written_currencies(request_text)
    if plan.line_items and currencies and plan.currency not in currencies:
        raise ValueError("plan uses a currency that is not in the request")
    # Our own checks decide what is missing; a model's questions would stall complete plans.
    plan.clarifications = _mixed_currency_questions(currencies)
    return _apply_context_and_gaps(plan, context)


@lru_cache
def _system_prompt() -> str:
    return (Path(__file__).parent / "prompts" / "planner.md").read_text(encoding="utf-8")


def llm_schema() -> dict:
    """Fields with defaults are optional in JSON Schema, and models then leave them out."""
    schema = WorkflowPlan.model_json_schema()
    schema["required"] = list(schema["properties"])
    return schema


def _default_llm() -> LlmClient:
    settings = get_settings()
    return OllamaClient(
        settings.ollama_base_url, settings.ollama_model, settings.ollama_timeout_seconds
    )


def build_plan(
    request_text: str, context: dict, mode: str | None = None, llm: LlmClient | None = None
) -> tuple[WorkflowPlan, str]:
    """Return the plan and which planner produced it: rules, llm or rules_fallback."""
    mode = mode or get_settings().planner_mode
    if mode == "rules":
        return parse_with_rules(request_text, context), "rules"
    try:
        raw = (llm or _default_llm()).generate_json(
            _system_prompt(),
            f"<request>{request_text}</request>",
            llm_schema(),
        )
        plan = validate_llm_plan(raw, request_text, context)
        if plan.actions or mode == "llm":
            return plan, "llm"
        log.warning("planner_llm_found_no_actions")
    except (LlmUnavailable, ValueError) as exc:
        log.warning("planner_llm_failed", error_type=type(exc).__name__)
        if mode == "llm":
            raise ClarificationNeeded(
                "The planning model could not interpret this request. Try rephrasing it."
            ) from exc
    return parse_with_rules(request_text, context), "rules_fallback"
