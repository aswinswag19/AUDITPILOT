"""
Simple chart data for the dashboard.

Builds a small "cube" (month x entity x category -> converted amount) from the transactions file.
The frontend turns it into a pie, a bar chart, a trend line and KPI tiles, and filters it
client-side (click a slice or a bar to cross-filter).

These numbers are for looking at the data. Verified answers still come from the question flow:
this view does not apply the conflicting-invoice rule or refunds.
"""

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from backend.app.common import DD_MM, TRANSACTION_DATE, dkey, effective_currency, find_table
from backend.app.engines.analyst import _load_rates, _rate
from backend.app.schemas import Mapping, Policy

BLANK_LABEL = "(blank)"


def _pretty(value: str) -> str:
    """Merge 'CHENNAI', 'chennai ' and 'Chennai' into one label."""
    v = (value or "").strip()
    if not v:
        return BLANK_LABEL
    return v.title() if (v.islower() or v.isupper()) else v


def _pick_category(df: pd.DataFrame, skip: set) -> str:
    """A second text column with a handful of values (e.g. product), if there is one."""
    for col in df.columns:
        if col in skip or col.lower().replace(" ", "_").endswith("id"):
            continue
        vals = df[col].str.strip()
        vals = vals[vals != ""]
        if not len(vals):
            continue
        numeric = pd.to_numeric(vals.str.replace(",", "", regex=False), errors="coerce").notna().mean()
        if numeric < 0.5 and 2 <= vals.str.casefold().nunique() <= 20:
            return col
    return ""


def build_visuals(data_dir: Path, mapping: Mapping, policy: Policy) -> Dict[str, Any]:
    tx = find_table(data_dir, mapping.transactions_table)
    if tx is None:
        return {"error": f"{mapping.transactions_table} not found."}

    fmt = policy.date_format or DD_MM
    target = policy.target_currency
    df = pd.read_csv(tx, dtype=str).fillna("")
    total_rows = len(df)

    date_col, amt_col = mapping.date_column, mapping.amount_column
    ent_col, cur_col = mapping.entity_column, mapping.currency_column
    if amt_col not in df.columns:
        return {"error": "This file has no amount column to chart."}

    # Exact repeats would be counted twice in every chart.
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    dup_rows = before - len(df)

    skip = {mapping.key_column, date_col, amt_col, ent_col, cur_col}
    cat_col = _pick_category(df, skip)

    rates = {}
    rates_file = find_table(data_dir, mapping.rates_table) if mapping.rates_table else None
    if rates_file is not None and cur_col:
        rates = _load_rates(rates_file, mapping, fmt)

    multiplier = Decimal(str(mapping.unit_multiplier))
    cube: Dict[tuple, Decimal] = {}
    counts: Dict[tuple, int] = {}
    currency_rows: Dict[str, int] = {}
    skipped = {"no amount": 0, "no exchange rate": 0, "no currency": 0}
    undated = 0
    used = 0

    for _, row in df.iterrows():
        raw_amt = row[amt_col].strip().replace(",", "")
        try:
            amount = Decimal(raw_amt) * multiplier
        except (InvalidOperation, ValueError):
            skipped["no amount"] += 1
            continue

        key = dkey(row[date_col], fmt) if date_col in df.columns else 0
        if cur_col and cur_col in df.columns:
            cur = effective_currency(row[cur_col], {})
            if not cur:
                skipped["no currency"] += 1
                continue
            rate = _rate(rates, cur, key, target, TRANSACTION_DATE)
            if rate is None:
                skipped["no exchange rate"] += 1
                continue
            amount = amount * rate
            currency_rows[cur] = currency_rows.get(cur, 0) + 1
        else:
            currency_rows[target] = currency_rows.get(target, 0) + 1

        month = f"{key // 10000:04d}-{(key // 100) % 100:02d}" if key else ""
        if not month:
            undated += 1
        entity = _pretty(row[ent_col]) if ent_col in df.columns else BLANK_LABEL
        category = _pretty(row[cat_col]) if cat_col else ""
        k = (month, entity, category)
        cube[k] = cube.get(k, Decimal("0")) + amount
        counts[k] = counts.get(k, 0) + 1
        used += 1

    notes: List[str] = []
    if dup_rows:
        notes.append(f"{dup_rows:,} repeated rows were left out so nothing is counted twice.")
    for why, n in skipped.items():
        if n:
            notes.append(f"{n:,} rows were left out ({why}).")
    if undated:
        notes.append(f"{undated:,} rows have no readable date, so they are missing from the trend.")
    if rates:
        notes.append(f"Amounts are converted to {target} using the rate on each row's date.")
    notes.append("These charts are for exploring. Ask a question below for a double-checked figure.")

    return {
        "file": mapping.transactions_table,
        "currency": target,
        "entity_label": ent_col or "Group",
        "category_label": cat_col,
        "rows_total": total_rows,
        "rows_used": used,
        "cube": [
            {"m": m, "e": e, "c": c, "v": float(round(v, 2)), "n": counts[(m, e, c)]}
            for (m, e, c), v in sorted(cube.items())
        ],
        "currencies": [{"name": k, "rows": v} for k, v in sorted(currency_rows.items(), key=lambda t: -t[1])],
        "notes": notes,
    }
