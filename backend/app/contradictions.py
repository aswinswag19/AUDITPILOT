"""
Phase 5: Contradiction radar.
Compares the verified query result with the executive summary's reported Q4 number.
All figures are computed from the data; nothing is hardcoded.
"""

import csv
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Optional
from backend.app.schemas import Plan, Policy, Mapping
from backend.app.common import dkey, calendar_quarter_of

# Differences at or below this percentage of the verified figure are treated as consistent.
TOLERANCE_PCT = Decimal("0.5")


def _dec(value: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


def _reported_q4(data_dir: Path, mapping: Mapping, year: Optional[int] = None) -> Optional[Decimal]:
    """Reported Q4 revenue. With `year`, only a Q4 row for that year counts (a label without any year is accepted)."""
    if not mapping.summary_table:
        return None
    summary_file = data_dir / mapping.summary_table
    if not summary_file.is_file():
        return None
    reported = None
    with open(summary_file, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            label = row.get(mapping.summary_period_column) or ""
            if "Q4" in label:
                years = re.findall(r"(?<!\d)(20\d\d)(?!\d)", label)
                if year is not None and years and str(year) not in years:
                    continue
                reported = _dec(row.get(mapping.summary_amount_column))
    return reported


def _not_comparable(verified: Any, reason: str) -> Dict[str, Any]:
    return {
        "raw_verified_result": verified,
        "summary_reported_result": None,
        "difference": None,
        "percentage_difference": None,
        "status": "NOT_COMPARABLE",
        "recommendation": reason,
    }


def check_contradictions(
    data_dir: Path,
    mapping: Mapping,
    analyst_result: Dict[str, Any],
    plan: Optional[Plan] = None,
    policy: Optional[Policy] = None,
) -> Dict[str, Any]:
    verified_raw = analyst_result.get("result")
    verified = _dec(verified_raw)
    if verified is None:
        return _not_comparable(verified_raw, "No verified result to compare.")

    q_year = None
    if plan is not None and plan.date_range and plan.date_range.start and plan.date_range.end:
        cq = calendar_quarter_of(dkey(plan.date_range.start, (policy or Policy()).date_format),
                                 dkey(plan.date_range.end, (policy or Policy()).date_format))
        q_year = cq[0] if cq else None
    reported = _reported_q4(data_dir, mapping, q_year)
    if reported is None:
        what = f"Q4 {q_year}" if q_year else "Q4"
        return _not_comparable(verified_raw, f"No {what} figure available in an executive summary for this dataset.")

    scope = "as provided"
    if plan is not None:
        fmt = (policy or Policy()).date_format
        quarter = None
        if plan.date_range and plan.date_range.start and plan.date_range.end:
            quarter = calendar_quarter_of(dkey(plan.date_range.start, fmt), dkey(plan.date_range.end, fmt))
        if not quarter or quarter[1] != 4:
            return _not_comparable(verified_raw, "The query is not for a calendar Q4, so it cannot be compared with the Q4 summary.")
        entity_scoped = any(f.get("column") == mapping.entity_column for f in plan.filters)
        if entity_scoped:
            # The summary is company-wide; compare like with like by dropping the entity filter.
            from backend.app.engines.analyst import execute_pandas_analyst
            wide = execute_pandas_analyst(
                data_dir, plan.model_copy(update={"filters": []}), mapping, policy or Policy(),
                export_source_rows=False,
            )
            wide_val = _dec(wide.get("result")) if wide.get("status") == "VERIFIED" else None
            if wide_val is None:
                return _not_comparable(verified_raw, "Could not compute a company-wide Q4 total to compare with the summary.")
            verified = wide_val
            scope = "company-wide (entity filter removed to match the summary)"

    diff = (reported - verified).quantize(Decimal("0.01"))
    pct = (abs(diff) / abs(verified) * 100) if verified != 0 else None
    contradiction = pct is None or pct > TOLERANCE_PCT

    return {
        "raw_verified_result": verified_raw,
        "compared_verified_result": str(verified.quantize(Decimal("0.01"))),
        "compared_scope": scope,
        "summary_reported_result": str(reported.quantize(Decimal("0.01"))),
        "difference": str(diff),
        "percentage_difference": f"{pct:.1f}%" if pct is not None else "n/a",
        "status": "CONTRADICTION_DETECTED" if contradiction else "CONSISTENT",
        "recommendation": (
            "Management review required: executive summary Q4 reported revenue materially diverges from verified transaction ledger."
            if contradiction else "Executive summary agrees with the verified ledger within tolerance."
        ),
    }
