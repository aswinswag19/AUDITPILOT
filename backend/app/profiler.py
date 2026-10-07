"""
Phase 2: Data quality profiler.
Profiles CSV tables, detects anomalies (duplicates, conflicts, missing values, unsupported currencies, ambiguous dates),
and computes transparent Data Quality Score starting at 100.
"""

import csv
from pathlib import Path
from typing import Dict, Any, List
from backend.app.schemas import Mapping

def _supported_currencies(data_dir: Path, mapping: Mapping, target: str) -> set:
    """Currencies that can be converted: the reporting currency plus every code in the rates table."""
    supported = {target}
    rates = (data_dir / mapping.rates_table) if mapping.rates_table else None
    if rates is not None and not rates.is_file():
        rates = data_dir / "dataset_b" / mapping.rates_table
    if rates is not None and rates.is_file() and mapping.rate_currency_column:
        with open(rates, "r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                code = (row.get(mapping.rate_currency_column) or "").strip().upper()
                if code:
                    supported.add(code)
    return supported


def profile_dataset(data_dir: Path, mapping: Mapping, target_currency: str = "INR") -> Dict[str, Any]:
    tx_file = data_dir / mapping.transactions_table
    if not tx_file.exists():
        # Fallback to dataset_b if needed
        alt_tx = data_dir / "dataset_b" / mapping.transactions_table
        if alt_tx.exists():
            tx_file = alt_tx
        else:
            return {"error": f"Transactions table {mapping.transactions_table} not found."}

    rows = []
    with open(tx_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        for row in reader:
            rows.append(row)

    total_rows = len(rows)
    quality_score = 100.0
    deductions = []

    # Detect exact duplicates
    key_col = mapping.key_column
    date_col = mapping.date_column
    amount_col = mapping.amount_column
    currency_col = mapping.currency_column

    supported_currencies = _supported_currencies(data_dir, mapping, target_currency)
    key_counts = {}
    invoice_amounts = {}
    missing_date_count = 0
    missing_amount_count = 0
    unsupported_currencies = set()
    ambiguous_date_count = 0
    currencies_found = set()

    for r in rows:
        k_val = r.get(key_col, "")
        dt_val = r.get(date_col, "").strip()
        amt_val = r.get(amount_col, "").strip()
        cur_val = r.get(currency_col, "INR").strip().upper()

        if cur_val:
            currencies_found.add(cur_val)
            if cur_val not in supported_currencies:
                unsupported_currencies.add(cur_val)

        if not dt_val:
            missing_date_count += 1
        else:
            # Check ambiguous date (day and month both <= 12 in DD/MM/YYYY or similar)
            parts = dt_val.split("/")
            if len(parts) == 3:
                try:
                    d, m = int(parts[0]), int(parts[1])
                    if d <= 12 and m <= 12:
                        ambiguous_date_count += 1
                except Exception:
                    pass

        if not amt_val:
            missing_amount_count += 1

        full_key = tuple(r.get(f, "") for f in fields)
        key_counts[full_key] = key_counts.get(full_key, 0) + 1

        if k_val:
            if k_val not in invoice_amounts:
                invoice_amounts[k_val] = set()
            invoice_amounts[k_val].add(amt_val)

    exact_dup_groups = sum(1 for k, c in key_counts.items() if c > 1)
    conflicting_dup_groups = sum(1 for inv, amts in invoice_amounts.items() if len(amts) > 1)

    # Scoring deductions
    if exact_dup_groups > 0:
        deduction = min(20.0, exact_dup_groups * 5.0)
        quality_score -= deduction
        deductions.append(f"Exact duplicate groups ({exact_dup_groups}): -{deduction}")

    if conflicting_dup_groups > 0:
        deduction = min(20.0, conflicting_dup_groups * 10.0)
        quality_score -= deduction
        deductions.append(f"Conflicting duplicate groups ({conflicting_dup_groups}): -{deduction}")

    missing_total = missing_date_count + missing_amount_count
    if missing_total > 0:
        deduction = min(15.0, missing_total * 3.0)
        quality_score -= deduction
        deductions.append(f"Missing required values ({missing_total}): -{deduction}")

    if unsupported_currencies:
        deduction = min(10.0, len(unsupported_currencies) * 5.0)
        quality_score -= deduction
        deductions.append(f"Unsupported currencies ({list(unsupported_currencies)}): -{deduction}")

    if ambiguous_date_count > 0:
        deduction = min(10.0, ambiguous_date_count * 1.0)
        quality_score -= deduction
        deductions.append(f"Ambiguous date rows ({ambiguous_date_count}): -{deduction}")

    quality_score = max(0.0, quality_score)

    return {
        "file": mapping.transactions_table,
        "rows": total_rows,
        "columns": len(fields),
        "quality_score": quality_score,
        "exact_duplicate_groups": exact_dup_groups,
        "conflicting_duplicate_groups": conflicting_dup_groups,
        "missing_date_count": missing_date_count,
        "missing_amount_count": missing_amount_count,
        "unsupported_currencies": list(unsupported_currencies),
        "currencies_found": list(currencies_found),
        "ambiguous_date_count": ambiguous_date_count,
        "deductions": deductions
    }

