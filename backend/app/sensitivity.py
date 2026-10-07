"""
Phase 5: Sensitivity analysis.
Re-runs the Pandas Analyst under alternative interpretations and reports how much the answer moves:
  * dates read as MM/DD/YYYY instead of DD/MM/YYYY
  * calendar quarter vs fiscal quarter (April-March fiscal year) for the same "Qn" label
  * refunds included vs excluded
"""

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Any, List, Optional
from backend.app.schemas import Plan, Policy, Mapping, DateRange
from backend.app.common import (
    DD_MM, MM_DD, dkey, key_parts, format_date, quarter_window, calendar_quarter_of,
)

LOW, MEDIUM = Decimal("0.5"), Decimal("5")


def _d(v: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _compare(base: Optional[Decimal], alt: Optional[Decimal]):
    if base is None or alt is None:
        return None, None
    diff = (alt - base).quantize(Decimal("0.01"))
    pct = (abs(diff) / abs(base) * 100) if base != 0 else None
    return str(diff), (f"{pct:.1f}%" if pct is not None else "n/a")


def _pct(base: Optional[Decimal], alt: Optional[Decimal]) -> Decimal:
    if base is None or alt is None:
        return Decimal(0)
    return (abs(alt - base) / abs(base) * 100) if base != 0 else Decimal(0)


def _run(data_dir, plan, mapping, policy):
    from backend.app.engines.analyst import execute_pandas_analyst
    res = execute_pandas_analyst(data_dir, plan, mapping, policy, export_source_rows=False)
    return _d(res.get("result")) if res.get("status") == "VERIFIED" else None


def _reformat_range(plan: Plan, old_fmt: str, new_fmt: str) -> Optional[DateRange]:
    if not (plan.date_range and plan.date_range.start and plan.date_range.end):
        return plan.date_range
    out = []
    for text in (plan.date_range.start, plan.date_range.end):
        y, m, d = key_parts(dkey(text, old_fmt))
        out.append(format_date(y, m, d, new_fmt))
    return DateRange(column=plan.date_range.column, start=out[0], end=out[1])


def compute_sensitivity(plan: Plan, policy: Policy, mapping: Mapping, analyst_result: Dict[str, Any],
                        data_dir: Optional[Path] = None) -> Dict[str, Any]:
    if data_dir is None:
        from backend.app.config import DATA_DIR
        data_dir = DATA_DIR
    base_val = analyst_result.get("result")
    base = _d(base_val)
    inp = analyst_result.get("impact_inputs") or {}
    scenarios: List[Dict[str, Any]] = []
    contributions: List[Decimal] = []
    notes: List[str] = []

    # 1. Date format
    alt_fmt = MM_DD if policy.date_format == DD_MM else DD_MM
    alt_plan = plan.model_copy(update={"date_range": _reformat_range(plan, policy.date_format, alt_fmt)})
    alt_date = _run(data_dir, alt_plan, mapping, policy.model_copy(update={"date_format": alt_fmt}))
    d_diff, d_pct = _compare(base, alt_date)
    only_base = inp.get("rows_only_valid_as_dd_mm" if policy.date_format == DD_MM else "rows_only_valid_as_mm_dd", 0)
    only_alt = inp.get("rows_only_valid_as_mm_dd" if policy.date_format == DD_MM else "rows_only_valid_as_dd_mm", 0)
    amb_rows = int(inp.get("ambiguous_date_rows_in_scope", 0))
    scope_rows = int(inp.get("scope_rows_uncleaned", 0))
    amb_total = _d(inp.get("ambiguous_date_total")) or Decimal(0)
    if only_base > 0 and only_alt == 0:
        # The file itself proves the format: only a handful of day/month-ambiguous rows are really at risk.
        date_contrib = (abs(amb_total) / abs(base) * 100) if base else Decimal(0)
        notes.append(
            f"{only_base} row(s) only parse as {policy.date_format}, so that format is established by the data; "
            f"swapping the whole file to {alt_fmt} is not a plausible reading. "
            f"Exposure is limited to {amb_rows} day/month-ambiguous in-scope row(s) worth {policy.target_currency} {amb_total}."
        )
        date_status = "format established by data"
    else:
        date_contrib = _pct(base, alt_date)
        date_status = "format not established by data"
        notes.append(f"Reading dates as {alt_fmt} changes the result by {d_pct or 'n/a'}.")
    contributions.append(date_contrib)
    scenarios.append({
        "name": "date_format", "description": f"Dates read as {alt_fmt}", "result": str(alt_date) if alt_date is not None else None,
        "difference": d_diff, "percent_difference": d_pct, "assessment": date_status,
    })

    # 2. Calendar vs fiscal quarter
    fiscal_alt = None
    if plan.date_range and plan.date_range.start and plan.date_range.end:
        s_k, e_k = dkey(plan.date_range.start, policy.date_format), dkey(plan.date_range.end, policy.date_format)
        cal = calendar_quarter_of(s_k, e_k)
        target = None
        if cal:
            year, q = cal
            target, label = quarter_window(year, q, fiscal=True), f"Q{q} read as fiscal quarter (April-March year)"
        else:
            for q in (1, 2, 3, 4):
                y = key_parts(s_k)[0]
                (y1, m1, d1), (y2, m2, d2) = quarter_window(y, q, fiscal=True)
                if s_k == y1 * 10000 + m1 * 100 + d1 and e_k == y2 * 10000 + m2 * 100 + d2:
                    target, label = quarter_window(y, q), f"Fiscal Q{q} read as calendar quarter"
        if target:
            (y1, m1, d1), (y2, m2, d2) = target
            fplan = plan.model_copy(update={"date_range": DateRange(
                column=plan.date_range.column, start=format_date(y1, m1, d1, policy.date_format),
                end=format_date(y2, m2, d2, policy.date_format))})
            fiscal_alt = _run(data_dir, fplan, mapping, policy)
            f_diff, f_pct = _compare(base, fiscal_alt)
            contributions.append(_pct(base, fiscal_alt))
            notes.append(f"{label}: result would be {fiscal_alt} ({f_pct} different).")
            scenarios.append({"name": "quarter_definition", "description": label,
                              "result": str(fiscal_alt) if fiscal_alt is not None else None,
                              "difference": f_diff, "percent_difference": f_pct, "assessment": "genuinely ambiguous label"})

    # 3. Refunds
    if mapping.refunds_table:
        flip = "exclude" if policy.refunds == "include_as_negative" else "include_as_negative"
        r_alt = _run(data_dir, plan, mapping, policy.model_copy(update={"refunds": flip}))
        r_diff, r_pct = _compare(base, r_alt)
        contributions.append(_pct(base, r_alt))
        scenarios.append({"name": "refunds", "description": f"Refund policy = {flip}", "result": str(r_alt) if r_alt is not None else None,
                          "difference": r_diff, "percent_difference": r_pct, "assessment": "policy choice"})
        notes.append(f"Refund policy '{flip}' would give {r_alt} ({r_pct} different).")

    # 4. Conversion basis (rate on the transaction date vs the present/latest rate)
    conv = analyst_result.get("conversion") or {}
    if conv.get("foreign_rows_in_scope"):
        label = {"transaction_date": "the rate on each transaction's date", "latest": "the present (latest) rate on file"}
        cur_basis = conv.get("basis") or "transaction_date"
        alt_basis = "latest" if cur_basis == "transaction_date" else "transaction_date"
        b_alt = _run(data_dir, plan, mapping, policy.model_copy(update={"conversion_basis": alt_basis}))
        b_diff, b_pct = _compare(base, b_alt)
        contributions.append(_pct(base, b_alt))
        scenarios.append({"name": "conversion_basis", "description": f"Foreign amounts converted at {label[alt_basis]}",
                          "result": str(b_alt) if b_alt is not None else None, "difference": b_diff,
                          "percent_difference": b_pct, "assessment": "policy choice (confirmed by the user)"})
        notes.append(f"Converting at {label[alt_basis]} instead of {label[cur_basis]} would give {b_alt} ({b_pct} different).")

    worst = max(contributions) if contributions else Decimal(0)
    materiality = "Low" if worst < LOW else ("Medium" if worst < MEDIUM else "High")
    return {
        "base_result": base_val,
        "alternate_result_date_format": str(alt_date) if alt_date is not None else None,
        "difference": d_diff,
        "percent_difference": d_pct,
        "ambiguity_in_scope": f"{amb_rows} of {scope_rows} in-scope rows have a day and month that could be swapped.",
        "materiality": materiality,
        "worst_case_percent": f"{worst:.1f}%",
        "scenarios": scenarios,
        "explanation": " ".join(notes) if notes else "No alternative interpretation applies.",
    }
