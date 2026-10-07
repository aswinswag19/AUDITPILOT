"""
Phase 2: Mapping inference and management.
Profiles CSV tables and infers column mappings with confidence scores.
"""

import csv
from pathlib import Path
from typing import Optional, Dict, Any, List
from backend.app.schemas import Mapping

def discover_dataset(data_dir: Path) -> str:
    """Find the first CSV that looks like a transaction table."""
    ignored = {"exchange_rates.csv", "executive_summary.csv"}
    candidates = sorted(path for path in data_dir.glob("*.csv") if path.name not in ignored and not path.name.startswith("source_rows_export"))
    for path in candidates:
        with path.open("r", encoding="utf-8", newline="") as handle:
            fields = {(field or "").lower().replace("_", " ") for field in (csv.DictReader(handle).fieldnames or [])}
        has_date = any(token in field for field in fields for token in ("date", "timestamp", "time"))
        has_measure = any(token in field for field in fields for token in ("amount", "revenue", "sales", "total", "value", "price"))
        if has_date and has_measure:
            return path.name
    if candidates:
        return candidates[0].name
    return ""


def infer_mapping(data_dir: Path, transactions_filename: str = "") -> Mapping:
    transactions_filename = transactions_filename or discover_dataset(data_dir)
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

    # Header-driven matching keeps uploaded datasets independent from Dataset A's names.
    def pick(*needles: str) -> str:
        return next((field for field in fields if any(needle in field.lower().replace("_", " ") for needle in needles)), "")

    key_col = pick("invoice", "transaction id", "transaction_id", "order id", "order_id", "record id", "record_id", "id")
    date_col = pick("date", "timestamp", "time", "created", "occurred", "period")
    entity_col = pick("branch", "region", "entity", "customer", "client", "account", "store", "location", "category", "product", "item")
    amount_col = pick("amount", "revenue", "sales", "total", "value", "price", "cost", "debit", "credit", "gross", "net", "charge", "fee")
    currency_col = pick("currency", "curr")

    if not key_col and fields:
        key_col = fields[0]
    if not entity_col:
        # A transaction file may omit an entity dimension; use the first non-metric
        # column so the rest of the analysis pipeline can still operate.
        excluded = {key_col, date_col, amount_col, currency_col}
        entity_col = next((field for field in fields if field not in excluded), "")

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
