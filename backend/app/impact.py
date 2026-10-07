"""
Phase 5: Impact analysis.
Quantifies what each cleaning rule did to the answer: duplicates, conflicting invoices,
missing dates, unsupported currencies and refunds. Every figure comes from the Analyst's
per-stage totals inside the query scope, so  raw + effects == verified  (checked and reported).
"""

from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List
from backend.app.schemas import Plan, Policy, Mapping

ZERO = Decimal("0.00")


def _d(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return ZERO


def _fmt(x: Decimal) -> str:
    return f"{x.quantize(Decimal('0.01')):,.2f}"


def compute_impact(plan: Plan, policy: Policy, mapping: Mapping, analyst_result: Dict[str, Any]) -> Dict[str, Any]:
    inp = analyst_result.get("impact_inputs")
    verified = analyst_result.get("result")
    if not inp or verified is None:
        return {
            "status": "NOT_AVAILABLE",
            "verified_total": verified,
            "reason": "The Analyst did not return a verified result with stage totals.",
        }

    cur = policy.target_currency
    raw = _d(inp["uncleaned_total"])
    dup = _d(inp["after_exact_dedup_total"]) - raw
    conf = _d(inp["after_conflict_total"]) - _d(inp["after_exact_dedup_total"])
    refund = _d(inp["refunds_total"])
    reconciles = (plan.metric is None or plan.metric.agg == "sum") and \
        (raw + dup + conf + refund).quantize(Decimal("0.01")) == _d(verified).quantize(Decimal("0.01"))

    unsup = analyst_result.get("unsupported_in_scope") or {}
    unsup_n = int(unsup.get("count", 0))
    conflicts = (analyst_result.get("conflicts_in_scope") or {}).get("keys", [])
    missing_n = int(inp.get("missing_rows_in_entity_scope", 0))
    dup_rows = int(inp.get("duplicate_rows_removed_in_scope", 0))

    if unsup_n:
        native = ", ".join(f"{c} {_fmt(_d(v['native_amount']))}" for c, v in unsup.get("by_currency", {}).items())
        unsupported_effect = f"{unsup_n} row(s) not converted (no exchange rate): {native} in original currency"
    else:
        unsupported_effect = "0.00"
    missing_effect = ("0.00" if not missing_n else
                      f"{missing_n} row(s) excluded for a missing date or amount; their value cannot be attributed to a period")

    effects = {
        "duplicate rows": abs(dup),
        "conflicting invoices": abs(conf),
        "refunds": abs(refund),
    }
    biggest_name, biggest_val = max(effects.items(), key=lambda kv: kv[1])
    if biggest_val > 0:
        largest = f"{biggest_name} ({cur} {_fmt(biggest_val)})"
    elif unsup_n or missing_n:
        largest = "rows excluded without a convertible amount (value unknown)"
    else:
        largest = "None identified"

    steps: List[str] = []
    if conflicts:
        steps.append(f"Resolve conflicting amounts for invoice(s) {', '.join(map(str, conflicts))} with the source system.")
    if unsup_n:
        steps.append(f"Add exchange rates for {', '.join(unsup.get('by_currency', {}))} so the {unsup_n} excluded row(s) can be included.")
    if missing_n:
        steps.append(f"Supply dates/amounts for {missing_n} incomplete row(s).")
    if dup_rows:
        steps.append(f"Remove {dup_rows} exact duplicate row(s) at the source.")
    if not steps:
        steps.append("No cleanup required.")

    return {
        "raw_total_before_cleaning": str(raw),
        "verified_total": verified,
        "currency": cur,
        "duplicate_effect": str(dup),
        "duplicate_rows_removed": dup_rows,
        "conflict_effect": str(conf),
        "conflicting_invoices": conflicts,
        "missing_date_effect": missing_effect,
        "unsupported_currency_effect": unsupported_effect,
        "refund_effect": str(refund),
        "reconciles": bool(reconciles),
        "largest_monetary_risk": largest,
        "minimum_cleanup_recommendation": " ".join(steps),
    }
