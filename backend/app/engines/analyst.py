"""
Phase 4: Pandas Analyst engine.
Executes validated analysis plans using Pandas with strict decimal currency conversion,
exact and conflicting duplicate handling, date parsing, unit multiplier, refunds, and source row export.

Pipeline (each stage is logged and totalled inside the query scope so the impact of every
cleaning rule can be reported):
  missing rows -> currency conversion -> exact duplicates -> conflicting duplicates -> scope -> refunds
"""

import pandas as pd
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List
from backend.app.schemas import Plan, Policy, Mapping
from backend.app.common import (
    find_table, dkey, iso_to_key, is_ambiguous_date, effective_currency, DD_MM, MM_DD, TRANSACTION_DATE, LATEST,
)
from backend.app.proof_script import build_proof_script

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def _money(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def _load_rates(rates_file, mapping: Mapping, fmt: str) -> Dict[str, List]:
    rates: Dict[str, List] = {}
    if rates_file is None:
        return rates
    rdf = pd.read_csv(rates_file, dtype=str).fillna("")
    for _, r in rdf.iterrows():
        k = iso_to_key(r[mapping.rate_effective_date_column], fmt)
        try:
            v = Decimal(r[mapping.rate_value_column])
        except Exception:
            continue
        if k:
            rates.setdefault(r[mapping.rate_currency_column].strip().upper(), []).append((k, v))
    for cur in rates:
        rates[cur].sort(key=lambda t: t[0])  # latest effective date wins, whatever the file order
    return rates


def _rate(rates, cur: str, k: int, target: str, basis: str = TRANSACTION_DATE):
    """Rate to convert `cur` into `target`.
    transaction_date: the rate in force on date key `k` (None when none is on file yet).
    latest:           the most recent rate on file, whatever the transaction date."""
    if cur == target:
        return Decimal("1.00")
    if basis == LATEST:
        series = rates.get(cur)
        return series[-1][1] if series else None
    if not k:
        return None
    best = None
    for eff, v in rates.get(cur, []):
        if eff <= k:
            best = v
        else:
            break
    return best


def execute_pandas_analyst(data_dir: Path, plan: Plan, mapping: Mapping, policy: Policy,
                           export_source_rows: bool = True) -> Dict[str, Any]:
    if plan.status == "refused":
        return {"status": "REFUSED", "result": None, "reason": plan.refusal.reason if plan.refusal else "Refused"}
    agg = plan.metric.agg if plan.metric else "sum"
    if agg not in ("sum", "count"):
        return {"status": "FAILED", "result": None, "reason": f"Aggregation '{agg}' is not supported."}

    tx_file = find_table(data_dir, mapping.transactions_table)
    if tx_file is None:
        return {"status": "FAILED", "result": None, "reason": f"Transactions file {mapping.transactions_table} not found."}

    fmt = policy.date_format
    target = policy.target_currency
    basis = policy.conversion_basis or TRANSACTION_DATE
    cmap = policy.currency_map
    key_col, date_col, amount_col = mapping.key_column, mapping.date_column, mapping.amount_column
    entity_col, currency_col = mapping.entity_column, mapping.currency_column

    start_k = end_k = 0
    if plan.date_range and plan.date_range.start and plan.date_range.end:
        start_k, end_k = dkey(plan.date_range.start, fmt), dkey(plan.date_range.end, fmt)
        if not start_k or not end_k or start_k > end_k:
            return {"status": "FAILED", "result": None,
                    "reason": f"Date range {plan.date_range.start} - {plan.date_range.end} is not valid for format {fmt}."}

    df = pd.read_csv(tx_file, dtype=str).fillna("")
    initial_rows = len(df)
    cleaning_log: List[str] = []
    stage_counts: Dict[str, int] = {"initial": initial_rows}
    multiplier = Decimal(str(mapping.unit_multiplier))
    if multiplier != Decimal("1.0"):
        cleaning_log.append(f"Applied unit multiplier {multiplier}")

    df["_entity_norm"] = df[entity_col].str.strip().str.casefold() if entity_col in df.columns else ""

    def entity_mask(frame: pd.DataFrame) -> pd.Series:
        m = pd.Series(True, index=frame.index)
        for f_item in plan.filters:
            col, op, val = f_item.get("column"), f_item.get("op"), f_item.get("value")
            if col and op == "eq":
                if col == entity_col:
                    m &= frame["_entity_norm"] == str(val).strip().casefold()
                elif col in frame.columns:
                    m &= frame[col] == val
        return m

    def scope(frame: pd.DataFrame) -> pd.DataFrame:
        m = entity_mask(frame)
        if start_k:
            m &= (frame["_dkey"] >= start_k) & (frame["_dkey"] <= end_k)
        return frame[m]

    def total(frame: pd.DataFrame) -> Decimal:
        return sum(frame["_converted_amount"], ZERO)

    # 1. Missing date or amount exclusion
    mask_valid = df[date_col].str.strip().ne("") & df[amount_col].str.strip().ne("")
    missing_df = df[~mask_valid]
    missing_in_entity_scope = int(entity_mask(missing_df).sum()) if len(missing_df) else 0
    if len(missing_df) > 0:
        cleaning_log.append(f"Excluded {len(missing_df)} rows with missing date or amount.")
    df = df[mask_valid].copy()
    stage_counts["after_missing_exclusion"] = len(df)

    # 2. Currency conversion (rate effective on the transaction date, per-row rounding)
    rates = _load_rates(find_table(data_dir, mapping.rates_table), mapping, fmt)
    df["_dkey"] = df[date_col].apply(lambda s: dkey(s, fmt))
    curs = df[currency_col] if currency_col in df.columns else pd.Series([target] * len(df), index=df.index)
    converted, unsupported_flags, effective = [], [], []
    for amt_str, cur, k in zip(df[amount_col], curs, df["_dkey"]):
        try:
            amt = Decimal(amt_str.strip()) * multiplier
        except Exception:
            amt = ZERO
        eff = effective_currency(cur, cmap)  # the user's confirmed currency for this row
        rate = _rate(rates, eff, k, target, basis)
        effective.append(eff)
        unsupported_flags.append(rate is None)
        converted.append(_money(amt * (rate if rate is not None else ZERO)))
    df["_converted_amount"] = converted
    df["_unsupported"] = unsupported_flags
    df["_cur"] = effective
    stage_counts["after_conversion"] = len(df)
    all_dates = df[date_col].copy()  # evidence for which date format the file uses

    uncleaned_scope = scope(df)
    uncleaned_total = total(uncleaned_scope)

    # 3. Exact duplicates: keep first
    if key_col and key_col in df.columns:
        subset = [c for c in (key_col, date_col, entity_col, amount_col) if c and c in df.columns]
        before_dup = len(df)
        df = df.drop_duplicates(subset=subset, keep="first")
        if before_dup - len(df) > 0:
            cleaning_log.append(f"Removed {before_dup - len(df)} exact duplicate rows.")
    stage_counts["after_exact_dedup"] = len(df)
    dedup_scope = scope(df)
    dedup_total = total(dedup_scope)

    # 4. Conflicting duplicates (same key, different amounts): flag and exclude
    conflicts_in_scope: Dict[str, Any] = {"keys": [], "rows": 0}
    if key_col and key_col in df.columns:
        nun = df.groupby(key_col)[amount_col].nunique()
        conflicting_keys = nun[nun > 1].index.tolist()
        if conflicting_keys:
            in_scope_rows = scope(df[df[key_col].isin(conflicting_keys)])
            conflicts_in_scope = {"keys": sorted(set(in_scope_rows[key_col])), "rows": int(len(in_scope_rows))}
            before_conf = len(df)
            df = df[~df[key_col].isin(conflicting_keys)].copy()
            cleaning_log.append(
                f"Excluded {before_conf - len(df)} conflicting duplicate rows across keys: {conflicting_keys}."
            )
    stage_counts["after_conflict_handling"] = len(df)

    # 5. Query scope
    final_df = scope(df)
    stage_counts["final_query_rows"] = len(final_df)
    conflict_total = total(final_df)

    unsup = final_df[final_df["_unsupported"]]
    by_currency: Dict[str, Any] = {}
    for _, u in unsup.iterrows():
        cur = u["_cur"] or "(blank)"
        slot = by_currency.setdefault(cur, {"rows": 0, "native_amount": ZERO})
        slot["rows"] += 1
        try:
            slot["native_amount"] += Decimal(u[amount_col])
        except Exception:
            pass
    unsupported_in_scope = {
        "count": int(len(unsup)),
        "by_currency": {k: {"rows": v["rows"], "native_amount": str(v["native_amount"])} for k, v in by_currency.items()},
        "keys": unsup[key_col].tolist()[:25] if key_col in unsup.columns else [],
    }
    if unsupported_in_scope["count"] > 0:
        cleaning_log.append(
            f"{unsupported_in_scope['count']} in-scope rows have no exchange rate "
            f"({', '.join(by_currency)}) and are excluded from the total."
        )

    # Opt-in strict modes: refuse to answer instead of answering with rows left out.
    block_reasons = []
    if policy.unsupported_currency == "block_answer" and unsupported_in_scope["count"] > 0:
        block_reasons.append(f"{unsupported_in_scope['count']} in-scope rows have unsupported currency "
                             f"({', '.join(by_currency)}).")
    if policy.conflicting_duplicate == "block_answer" and conflicts_in_scope["keys"]:
        block_reasons.append(f"In-scope invoices have conflicting duplicate amounts: {conflicts_in_scope['keys']}.")
    if block_reasons:
        return {
            "status": "BLOCKED_POLICY", "result": None, "reason": " ".join(block_reasons),
            "cleaning_log": cleaning_log, "stage_counts": stage_counts,
            "unsupported_in_scope": unsupported_in_scope, "conflicts_in_scope": conflicts_in_scope,
        }

    # 6. Refunds (policy: include_as_negative) - only for sums
    refunds_total = ZERO
    refunds_info: Dict[str, Any] = {"rows": 0, "total": "0.00", "unmatched_keys": [], "unsupported_rows": 0}
    refunds_file = find_table(data_dir, mapping.refunds_table)
    if refunds_file is not None and policy.refunds == "include_as_negative" and agg == "sum" and key_col in df.columns:
        first = df.drop_duplicates(subset=[key_col], keep="first")
        ok_keys = set(first.loc[entity_mask(first), key_col])
        all_keys = set(first[key_col])
        cur_of = dict(zip(first[key_col], first["_cur"]))
        rdf = pd.read_csv(refunds_file, dtype=str).fillna("")
        for _, r in rdf.iterrows():
            rkey = r[mapping.refund_key_column]
            if rkey not in all_keys:
                refunds_info["unmatched_keys"].append(rkey)
                continue
            if rkey not in ok_keys:
                continue
            rk = dkey(r[mapping.refund_date_column], fmt)
            if start_k and not (start_k <= rk <= end_k):
                continue
            rate = _rate(rates, cur_of[rkey], rk, target, basis)
            if rate is None:
                refunds_info["unsupported_rows"] += 1
            try:
                ramt = Decimal(r[mapping.refund_amount_column].strip()) * multiplier
            except Exception:
                ramt = ZERO
            refunds_total -= _money(ramt * (rate if rate is not None else ZERO))
            refunds_info["rows"] += 1
        refunds_info["total"] = str(refunds_total)
        if refunds_info["rows"]:
            cleaning_log.append(f"Subtracted {refunds_info['rows']} refund(s) totalling {-refunds_total}.")

    # 7. Aggregate
    if agg == "count":
        final_result = Decimal(str(len(final_df)))
    else:
        final_result = total(final_df) + refunds_total

    source_rows_path = None
    if export_source_rows:
        source_rows_path = str(data_dir / "source_rows_export.csv")
        final_df.head(50).to_csv(source_rows_path, index=False)

    result_str = str(_money(final_result)) if agg == "sum" else str(int(final_result))
    foreign = final_df[final_df["_cur"] != target]
    conversion = {
        "basis": basis,
        "currency_map": dict(cmap),
        "rows_in_scope": int(len(final_df)),
        "foreign_rows_in_scope": int(len(foreign)),
        "foreign_currencies_in_scope": sorted(set(c or "(blank)" for c in foreign["_cur"])),
    }
    impact_inputs = {
        "scope_rows_uncleaned": int(len(uncleaned_scope)),
        "uncleaned_total": str(uncleaned_total),
        "after_exact_dedup_total": str(dedup_total),
        "after_conflict_total": str(conflict_total),
        "duplicate_rows_removed_in_scope": int(len(uncleaned_scope) - len(dedup_scope)),
        "conflict_rows_removed_in_scope": int(len(dedup_scope) - len(final_df)),
        "missing_rows_in_entity_scope": missing_in_entity_scope,
        "ambiguous_date_rows_in_scope": int(sum(is_ambiguous_date(s) for s in uncleaned_scope[date_col])),
        "ambiguous_date_total": str(sum(
            (v for s, v in zip(final_df[date_col], final_df["_converted_amount"]) if is_ambiguous_date(s)), ZERO)),
        "rows_only_valid_as_dd_mm": int(sum(bool(dkey(s, DD_MM)) and not dkey(s, MM_DD) for s in all_dates)),
        "rows_only_valid_as_mm_dd": int(sum(bool(dkey(s, MM_DD)) and not dkey(s, DD_MM) for s in all_dates)),
        "refunds_total": str(refunds_total),
    }

    return {
        "status": "VERIFIED",
        "result": result_str,
        "currency": policy.target_currency,
        "cleaning_log": cleaning_log,
        "stage_counts": stage_counts,
        "source_rows_path": source_rows_path,
        "unsupported_in_scope": unsupported_in_scope,
        "conflicts_in_scope": conflicts_in_scope,
        "refunds": refunds_info,
        "impact_inputs": impact_inputs,
        "conversion": conversion,
        "generated_code": build_proof_script(data_dir, plan, mapping, policy, expected=result_str),
    }
