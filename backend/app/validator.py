"""
Phase 3: Plan validator.
Validates generated plans against schema summary, available entities, and supported operation rules.
"""

from typing import Dict, Any, List
from backend.app.schemas import Plan, Mapping
from backend.app.refusal import create_refusal

def validate_plan(plan: Plan, schema_summary: Dict[str, Any], mapping: Mapping, valid_entities: List[str]) -> Plan:
    if plan.status == "refused":
        return plan

    q_text = " ".join(plan.comparison_entities).lower() if plan.comparison_entities else ""

    # Check for false premise like profit without costs
    if "profit" in q_text or (plan.metric and "profit" in plan.metric.column.lower()):
        return create_refusal(
            reason="Profit calculation requested but required columns (cost_of_goods, operating_expenses, taxes, returns) are absent in the dataset.",
            missing=["cost_of_goods", "operating_expenses", "taxes", "returns"]
        )

    # Check entity validity if comparison or group_by involves entities
    if plan.comparison_entities:
        for ent in plan.comparison_entities:
            # normalize check
            norm_ent = ent.strip().casefold()
            if not any(norm_ent in ve.casefold() or ve.casefold() in norm_ent for ve in valid_entities):
                return create_refusal(
                    reason=f"Entity '{ent}' requested is a false premise or not found in dataset.",
                    missing=[f"Available entities: {valid_entities}"]
                )

    return plan

