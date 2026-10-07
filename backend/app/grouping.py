"""
Grouped execution for compare / rank questions.
Runs both engines once per entity (so each figure is independently verified) and ranks the results.
"""

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List
from backend.app.schemas import Plan, Policy, Mapping
from backend.app.mapping import list_entities
from backend.app.engines.analyst import execute_pandas_analyst
from backend.app.engines.inspector import execute_duckdb_inspector


def is_grouped(plan: Plan) -> bool:
    return bool(plan.group_by) and plan.intent in ("compare", "rank")


def execute_grouped(data_dir: Path, plan: Plan, mapping: Mapping, policy: Policy) -> Dict[str, Any]:
    entities: List[str] = list(plan.comparison_entities) or list_entities(data_dir, mapping)
    rows: List[Dict[str, Any]] = []
    for ent in entities:
        sub = plan.model_copy(update={
            "filters": [{"column": mapping.entity_column, "op": "eq", "value": ent}],
            "group_by": [], "comparison_entities": [], "intent": "aggregate", "requested_output": "value",
        })
        a = execute_pandas_analyst(data_dir, sub, mapping, policy, export_source_rows=False)
        i = execute_duckdb_inspector(data_dir, sub, mapping, policy)
        verified = a.get("status") == "VERIFIED" and i.get("status") == "VERIFIED" and a.get("result") == i.get("result")
        rows.append({
            "entity": ent,
            "analyst_result": a.get("result"),
            "inspector_result": i.get("result"),
            "verified": verified,
            "unsupported_rows": (a.get("unsupported_in_scope") or {}).get("count", 0),
            "conflicting_invoices": (a.get("conflicts_in_scope") or {}).get("keys", []),
            "reason": a.get("reason") or i.get("reason"),
        })

    def sort_key(r):
        try:
            return Decimal(str(r["analyst_result"]))
        except (InvalidOperation, TypeError):
            return Decimal("-Infinity")

    ranking = sorted(rows, key=sort_key, reverse=True)
    for pos, r in enumerate(ranking, 1):
        r["rank"] = pos
    return {
        "intent": plan.intent,
        "currency": policy.target_currency,
        "ranking": ranking,
        "all_verified": bool(rows) and all(r["verified"] for r in rows),
    }
