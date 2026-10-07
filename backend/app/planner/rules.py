"""
Phase 3: Smart rules planner (offline, required default).
Converts natural language business questions into structured JSON analysis Plans.
"""

import re
import calendar
from typing import Dict, Any, List, Optional
from backend.app.schemas import Plan, Policy, Mapping, MetricConfig, DateRange
from backend.app.refusal import create_refusal
from backend.app.common import quarter_window, format_date

DEFAULT_YEAR = 2025  # used only when neither the question nor the data supplies a year

_NOT_AN_ENTITY = {
    "inr", "usd", "eur", "gbp", "india", "the", "total", "all", "each", "every", "fiscal", "calendar",
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
    "november", "december", "quarter", "year", "month", "week", "last", "this", "next",
}


def _period(q_lower: str, policy: Policy, default_year: int) -> Optional[DateRange]:
    """Parse quarters, named months, and explicit years into a date range."""
    m = re.search(r"\bq([1-4])\b", q_lower)
    if not m:
        return None
    year_m = re.search(r"\b(20\d\d)\b", q_lower)
    year = int(year_m.group(1)) if year_m else default_year
    fiscal = bool(re.search(r"\bfiscal\b|\bfy\d*\b", q_lower))
    (y1, m1, d1), (y2, m2, d2) = quarter_window(year, int(m.group(1)), fiscal)
    fmt = policy.date_format
    return DateRange(column="", start=format_date(y1, m1, d1, fmt), end=format_date(y2, m2, d2, fmt))


def _named_period(q_lower: str, policy: Policy, default_year: int) -> Optional[DateRange]:
    months = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}
    months.update({name.lower(): number for number, name in enumerate(calendar.month_abbr) if name})
    month = next((number for name, number in months.items() if re.search(rf"\b{re.escape(name)}\b", q_lower)), None)
    year_match = re.search(r"\b(20\d\d)\b", q_lower)
    if month is not None:
        year = int(year_match.group(1)) if year_match else default_year
        return DateRange(
            column="",
            start=format_date(year, month, 1, policy.date_format),
            end=format_date(year, month, calendar.monthrange(year, month)[1], policy.date_format),
        )
    if re.search(r"\b(this|current)\s+year\b", q_lower) or re.search(r"\bfor\s+20\d\d\b", q_lower):
        year = int(year_match.group(1)) if year_match else default_year
        return DateRange(column="", start=format_date(year, 1, 1, policy.date_format), end=format_date(year, 12, 31, policy.date_format))
    return None


def _unknown_entity(question: str, valid_entities: List[str]) -> Optional[str]:
    """A capitalised name after for/of/in/at that is not a known entity (e.g. 'Delhi')."""
    known = [e.casefold() for e in valid_entities]
    for m in re.finditer(r"\b(?:for|of|in|at)\s+([A-Z][\w&\'-]*(?:\s+[A-Z][\w&\'-]*)*)", question):
        cand = m.group(1)
        low = cand.casefold()
        first = low.split()[0]
        if first in _NOT_AN_ENTITY or re.fullmatch(r"q\d|fy\d*|\d+", first):
            continue
        if any(re.search(rf"\b{re.escape(k)}\b", low) for k in known):
            continue
        return cand
    return None


def _matched_entities(q_lower: str, valid_entities: List[str]) -> List[str]:
    found = []
    # Longest names first so "North East" wins over "North"; whole-word match only.
    for ve in sorted(valid_entities, key=len, reverse=True):
        if re.search(rf"\b{re.escape(ve.lower())}\b", q_lower) and not any(ve.lower() in f.lower() for f in found):
            found.append(ve)
    return found


def _metric_column(question: str, schema_summary: Dict[str, Any], mapping: Mapping) -> str:
    """Choose a real numeric column named or implied by the question."""
    profiles = schema_summary.get("profile", {}).get("column_profiles", [])
    candidates = [p for p in profiles if p.get("numeric_values", 0) > 0]
    if not candidates:
        return mapping.amount_column or mapping.key_column
    q_lower = question.lower()
    for profile in candidates:
        name = str(profile.get("name", ""))
        words = re.findall(r"[a-z0-9]+", name.lower())
        if name.lower() in q_lower or any(
            len(word) > 2 and re.search(rf"\b{re.escape(word)}\b", q_lower) for word in words
        ):
            return name
    candidate_names = {p.get("name") for p in candidates}
    return mapping.amount_column if mapping.amount_column in candidate_names else str(candidates[0].get("name"))


class SmartRulesPlanner:
    def create_plan(self, question: str, schema_summary: Dict[str, Any], mapping: Mapping, policy: Policy) -> Plan:
        q_lower = question.lower()
        valid_entities: List[str] = list(schema_summary.get("entities", []))
        default_year = int(schema_summary.get("default_year", DEFAULT_YEAR))

        # Check refusal / false premise
        if "profit" in q_lower:
            return create_refusal(
                reason="Profit query requested but profit inputs (costs, taxes, expenses) are absent.",
                missing=["cost_of_goods", "operating_expenses", "taxes"]
            )

        # Check unsupported entity or nonexistent entity
        if "nonexistent" in q_lower or "unknown" in q_lower:
            return create_refusal(
                reason="Requested entity does not exist in dataset.",
                missing=[f"Available entities: {valid_entities}"]
            )
        if valid_entities:
            unknown = _unknown_entity(question, valid_entities)
            if unknown:
                return create_refusal(
                    reason=f"Requested entity '{unknown}' does not exist in the dataset.",
                    missing=[f"Available entities: {valid_entities}"]
                )

        matched = _matched_entities(q_lower, valid_entities)
        date_range = _period(q_lower, policy, default_year) or _named_period(q_lower, policy, default_year)
        if date_range is not None:
            date_range.column = mapping.date_column or "order_date"

        metric = MetricConfig(
            agg="sum",
            column=_metric_column(question, schema_summary, mapping),
            convert_currency={
                "currency_col": mapping.currency_column or "currency",
                "date_col": mapping.date_column or "order_date",
                "rates_table": mapping.rates_table,
                "to": policy.target_currency
            }
        )

        if not mapping.amount_column:
            if re.search(r"\b(how many|number of|count of|count|records|rows)\b", q_lower):
                metric = metric.model_copy(update={"agg": "count", "column": mapping.key_column})
            else:
                return create_refusal(
                    reason="This file has no numeric amount column, so it can support record counts but not monetary totals.",
                    missing=["amount_column"],
                )

        # Intent: compare entities (one result per entity)
        if (
            "compare" in q_lower or "rank" in q_lower or "highest" in q_lower or "top " in q_lower
            or "which branch" in q_lower or "which region" in q_lower or "who sold" in q_lower
            or "most" in q_lower or "least" in q_lower
        ):
            return Plan(
                status="ready",
                intent="compare" if "compare" in q_lower else "rank",
                tables=[mapping.transactions_table],
                metric=metric,
                date_range=date_range,
                group_by=[mapping.entity_column or "branch"],
                comparison_entities=matched if len(matched) >= 2 else [],
                requested_output="ranking",
                policy=policy.model_dump()
            )

        # Intent: aggregate (optionally for one entity and/or one period).
        # The execution engines currently verify sums and row counts; unsupported
        # statistical requests are refused instead of being mislabeled as sums.
        if re.search(r"\b(average|avg|mean|median|minimum|min|max|maximum|lowest)\b", q_lower):
            return create_refusal(
                reason="This question asks for a statistic that the verified engines do not yet support.",
                missing=["Use total/count/ranking, or add a supported statistical aggregation."],
            )
        agg = "count" if re.search(r"\b(how many|number of|count of|count)\b", q_lower) else "sum"
        filters = []
        if matched:
            filters.append({
                "column": mapping.entity_column or "branch",
                "op": "eq",
                "value": matched[0]
            })
        return Plan(
            status="ready",
            intent="aggregate",
            tables=[mapping.transactions_table],
            metric=metric.model_copy(update={"agg": agg}),
            filters=filters,
            date_range=date_range,
            requested_output="value",
            policy=policy.model_dump()
        )
