"""
Phase 5: Trust decision engine.
Evaluates engine statuses, data quality risks, contradictions, and sensitivity to assign trust decision and publishability.
"""

from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List

def compute_trust_decision(
    analyst_res: Dict[str, Any],
    inspector_res: Dict[str, Any],
    profile: Dict[str, Any],
    contradiction: Dict[str, Any]
) -> Dict[str, Any]:
    a_status = analyst_res.get("status")
    i_status = inspector_res.get("status")

    if a_status == "REFUSED" or i_status == "REFUSED":
        return {
            "trust_decision": "REFUSED",
            "publishability": "EXTERNAL_REPORTING_BLOCKED",
            "reasons": ["Question refused by policy or parser."],
            "remaining_risks": [],
            "recommendation": "Refuse and display guidance."
        }

    if a_status != "VERIFIED" or i_status != "VERIFIED":
        return {
            "trust_decision": "BLOCKED",
            "publishability": "EXTERNAL_REPORTING_BLOCKED",
            "reasons": [f"Engine mismatch or block: Analyst={a_status}, Inspector={i_status}"]
                       + [str(r) for r in (analyst_res.get("reason"), inspector_res.get("reason")) if r],
            "remaining_risks": ["Engine verification failed or data blocked."],
            "recommendation": "Resolve blocking issues before publishing."
        }

    # Both engines claim success: their results must actually agree.
    a_val, i_val = analyst_res.get("result"), inspector_res.get("result")
    try:
        results_match = Decimal(str(a_val)) == Decimal(str(i_val))
    except (InvalidOperation, TypeError, ValueError):
        results_match = a_val == i_val
    if not results_match:
        return {
            "trust_decision": "BLOCKED",
            "publishability": "EXTERNAL_REPORTING_BLOCKED",
            "reasons": [f"Engine results disagree: Analyst={a_val}, Inspector={i_val}"],
            "remaining_risks": ["Independent recalculation does not reproduce the Analyst result."],
            "recommendation": "Resolve the discrepancy between engines before publishing."
        }

    # Rows inside the query scope that had no exchange rate were left out of the total.
    conflicts = (analyst_res.get("conflicts_in_scope") or {}).get("keys", [])
    unsup = analyst_res.get("unsupported_in_scope") or {}
    unsup_n = int(unsup.get("count", 0) or 0)
    reasons: List[str] = []
    risks: List[str] = []
    if unsup_n:
        cur_list = ", ".join(unsup.get("by_currency", {}).keys()) or "unknown"
        reasons.append(f"{unsup_n} in-scope row(s) with unsupported currency ({cur_list}) were excluded from the total.")
        risks.append(f"Reported figure omits {unsup_n} transaction(s) that have no exchange rate; the true total is higher or lower by their converted value.")

    if conflicts:
        reasons.append(f"Conflicting duplicate invoice(s) {', '.join(map(str, conflicts))} fall inside the query scope and were excluded.")
        risks.append("Excluded conflicting invoice(s) could change the total once the correct amount is confirmed.")

    # No transaction matched the entity / period: 0 here means "no data", not "no revenue".
    scope_rows = (analyst_res.get("stage_counts") or {}).get("final_query_rows")
    if scope_rows == 0:
        reasons.append("No transactions matched the question's entity and period, so the 0 reflects missing data rather than a verified zero.")
        risks.append("The period or entity may be absent from the dataset; confirm before reporting a zero.")

    # If contradiction detected with executive summary
    if contradiction.get("status") == "CONTRADICTION_DETECTED":
        return {
            "trust_decision": "VERIFIED_WITH_POLICY",
            "publishability": "MANAGEMENT_REVIEW_REQUIRED",
            "reasons": ["Engines match and verified, but executive summary discrepancy detected."] + reasons,
            "remaining_risks": ["Executive summary reported revenue differs from verified transaction ledger."] + risks,
            "recommendation": "Management review required prior to external reporting."
        }

    if unsup_n or conflicts or scope_rows == 0:
        return {
            "trust_decision": "VERIFIED_WITH_POLICY",
            "publishability": "MANAGEMENT_REVIEW_REQUIRED",
            "reasons": ["Engines match, but the result needs review (see reasons)."] + reasons,
            "remaining_risks": risks,
            "recommendation": "Resolve the listed items (missing exchange rates, conflicting invoices, empty scope) or have management accept them before external reporting."
        }

    return {
        "trust_decision": "VERIFIED",
        "publishability": "INTERNAL_EXPLORATION_OK",
        "reasons": ["Pandas Analyst and DuckDB Inspector match perfectly."],
        "remaining_risks": [],
        "recommendation": "Ready for publication."
    }
