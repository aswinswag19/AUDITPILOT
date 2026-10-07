"""
Phase 2: Mapping inference and management.
Profiles CSV tables and infers column mappings with confidence scores.
"""

import csv
from pathlib import Path
from typing import Optional, Dict, Any, List
from backend.app.schemas import Mapping

def infer_mapping(data_dir: Path, transactions_filename: str = "sales.csv") -> Mapping:
    csv_path = data_dir / transactions_filename
    if "dataset_b" in transactions_filename or transactions_filename == "orders.csv" or not csv_path.exists():
        mapping_json = data_dir / "dataset_b" / "dataset_b_mapping.json"
        if mapping_json.exists():
            import json
            with open(mapping_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                return Mapping(**data)
        return Mapping(
            transactions_table="orders.csv",
            key_column="order_id",
            date_column="order_date",
            entity_column="region",
            amount_column="amount",
            currency_column="currency",
            rates_table="exchange_rates_b.csv",
            rate_currency_column="cur",
            rate_value_column="rate",
            rate_effective_date_column="dt",
            refunds_table="refunds.csv",
            refund_key_column="ref_id",
            refund_amount_column="ref_amt",
            refund_date_column="ref_dt",
            unit_multiplier=10.0
        )

    # Default Dataset A inference
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []

    # Heuristic matching for Dataset A
    key_col = next((f for f in fields if "id" in f.lower() or "invoice" in f.lower()), fields[0] if fields else "")
    date_col = next((f for f in fields if "date" in f.lower()), "")
    entity_col = next((f for f in fields if "branch" in f.lower() or "region" in f.lower() or "entity" in f.lower()), "")
    amount_col = next((f for f in fields if "amount" in f.lower() or "revenue" in f.lower() or "total" in f.lower()), "")
    currency_col = next((f for f in fields if "currency" in f.lower() or "curr" in f.lower()), "")

    rates_table = "exchange_rates.csv" if (data_dir / "exchange_rates.csv").exists() else ""

    return Mapping(
        transactions_table=transactions_filename,
        key_column=key_col,
        date_column=date_col,
        entity_column=entity_col,
        amount_column=amount_col,
        currency_column=currency_col,
        rates_table=rates_table,
        rate_currency_column="currency",
        rate_value_column="rate_to_inr",
        rate_effective_date_column="effective_date",
        summary_table="executive_summary.csv" if (data_dir / "executive_summary.csv").exists() else "",
        summary_period_column="quarter",
        summary_amount_column="reported_revenue_inr",
        unit_multiplier=1.0
    )


def list_entities(data_dir: Path, mapping: Mapping) -> List[str]:
    """Distinct entity names (e.g. branches/regions) actually present in the transactions file.
    Case/whitespace variants are merged, so 'CHENNAI', 'chennai ' and 'Chennai' give one entry."""
    if not mapping.entity_column:
        return []
    tx = data_dir / mapping.transactions_table
    if not tx.is_file():
        tx = data_dir / "dataset_b" / mapping.transactions_table
    if not tx.is_file():
        return []
    seen: Dict[str, str] = {}
    with open(tx, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            v = (row.get(mapping.entity_column) or "").strip()
            if v:
                seen.setdefault(v.casefold(), v.title() if (v.islower() or v.isupper()) else v)
    return sorted(seen.values())


def latest_year(data_dir: Path, mapping: Mapping, fmt: str = "DD/MM/YYYY") -> Optional[int]:
    """Most recent year that appears in the transactions' date column."""
    from backend.app.common import dkey, find_table
    tx = find_table(data_dir, mapping.transactions_table)
    if tx is None or not mapping.date_column:
        return None
    best = 0
    with open(tx, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            best = max(best, dkey(row.get(mapping.date_column) or "", fmt))
    return best // 10000 or None
