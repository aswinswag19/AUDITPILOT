"""
Plan pre-flight checks.

The planner already refuses questions about entities that do not exist, but /execute, /verify,
/trust and /proof accept any hand-built Plan. The engines only understand `eq` filters on real
columns, so anything else used to be ignored silently and produced a "verified" figure for the
wrong scope (an unknown branch gave 0.00, an `in` filter gave the company-wide total).
This module rejects such plans before any number is computed.
"""

import csv
from pathlib import Path
from typing import Any, Dict, List

from backend.app.schemas import Plan, Mapping
from backend.app.common import find_table
from backend.app.mapping import list_entities


def plan_problems(data_dir: Path, plan: Plan, mapping: Mapping) -> Dict[str, Any]:
    """{'problems': [...], 'available_entities': [...]} - empty problems means the plan is safe to run."""
    problems: List[str] = []
    if plan.status != "ready":
        return {"problems": problems, "available_entities": []}

    tx = find_table(data_dir, mapping.transactions_table)
    columns: List[str] = []
    if tx is not None:
        with open(tx, "r", encoding="utf-8", newline="") as f:
            columns = next(csv.reader(f), [])
    entities = list_entities(data_dir, mapping)
    known = {e.casefold() for e in entities}
    ent_col = mapping.entity_column

    for flt in plan.filters:
        col, op, val = flt.get("column"), flt.get("op"), flt.get("value")
        if op != "eq":
            problems.append(f"Filter operator '{op}' on '{col}' is not supported (only 'eq'); it would be ignored.")
            continue
        if not col or (columns and col not in columns):
            problems.append(f"Filter column '{col}' does not exist in {mapping.transactions_table}.")
            continue
        if col == ent_col and known and str(val).strip().casefold() not in known:
            problems.append(f"'{val}' is not a known {ent_col}.")

    for ent in plan.comparison_entities:
        if known and str(ent).strip().casefold() not in known:
            problems.append(f"'{ent}' is not a known {ent_col}.")

    if plan.group_by and [g for g in plan.group_by if g != ent_col]:
        problems.append(f"Grouping by {plan.group_by} is not supported; only by '{ent_col}'.")

    return {"problems": problems, "available_entities": entities}
