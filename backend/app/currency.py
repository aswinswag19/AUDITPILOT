"""
Currency confirmation.

Before any figure is computed, every currency in the question's scope that is not the target
currency (e.g. USD / EUR when reporting in INR), and every blank or unrecognised code, has to be
confirmed by the user. They then choose how foreign amounts are converted:

  * transaction_date - the rate in force on each transaction's own date (the default for accounting)
  * latest           - the present (most recent) rate on file, applied to every row

The user's answers travel in the request policy:
    policy.currency_map      {"EUR": "USD", "USD": "USD", "RS": "INR"}   (code in data -> confirmed code)
    policy.conversion_basis  "transaction_date" | "latest"
The engines read those two fields; nothing is stored on the server.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from backend.app.schemas import Plan, Policy, Mapping, BLANK_CURRENCY
from backend.app.common import (
    find_table, dkey, key_to_iso, raw_currency, effective_currency, TRANSACTION_DATE,
)
from backend.app.engines.analyst import _load_rates, _rate

# Typical mis-spellings in real exports -> the currency they almost certainly mean.
_ALIASES = {
    "RS": "INR", "RS.": "INR", "INR.": "INR", "\u20b9": "INR", "RUPEE": "INR", "RUPEES": "INR",
    "$": "USD", "US$": "USD", "USD$": "USD", "DOLLAR": "USD", "DOLLARS": "USD",
    "\u20ac": "EUR", "EURO": "EUR", "EUROS": "EUR",
    "\u00a3": "GBP", "POUND": "GBP", "POUNDS": "GBP",
}


def _dec(x) -> Decimal:
    try:
        return Decimal(str(x).strip())
    except Exception:
        return Decimal("0")


def _scope_frame(df: pd.DataFrame, plan: Plan, mapping: Mapping, policy: Policy) -> pd.DataFrame:
    """Rows the question is about, before any cleaning (entity filters + date range)."""
    fmt = policy.date_format
    df = df[df[mapping.date_column].str.strip().ne("") & df[mapping.amount_column].str.strip().ne("")].copy()
    mask = pd.Series(True, index=df.index)
    ent_col = mapping.entity_column
    ent_norm = df[ent_col].str.strip().str.casefold() if ent_col in df.columns else pd.Series("", index=df.index)

    wanted = {str(e).strip().casefold() for e in plan.comparison_entities}
    if wanted:
        mask &= ent_norm.isin(wanted)
    for f in plan.filters:
        col, op, val = f.get("column"), f.get("op"), f.get("value")
        if col and op == "eq":
            if col == ent_col:
                mask &= ent_norm == str(val).strip().casefold()
            elif col in df.columns:
                mask &= df[col] == val
    if plan.date_range and plan.date_range.start and plan.date_range.end:
        s, e = dkey(plan.date_range.start, fmt), dkey(plan.date_range.end, fmt)
        if s and e:
            keys = df[mapping.date_column].apply(lambda t: dkey(t, fmt))
            mask &= (keys >= s) & (keys <= e)
    return df[mask]


def _suggestions(code: str, rate_codes: List[str], target: str) -> List[str]:
    out: List[str] = []
    alias = _ALIASES.get(code)
    for c in ([alias] if alias else []) + sorted(rate_codes) + [target]:
        if c and c != code and c not in out:
            out.append(c)
    return out


def currency_check(data_dir: Path, plan: Plan, mapping: Mapping, policy: Policy) -> Dict[str, Any]:
    """What still needs the user's confirmation before this plan can be computed."""
    target = policy.target_currency
    empty = {"needs_confirmation": False, "target_currency": target, "currencies": [], "questions": [],
             "current_answers": {"currency_map": dict(policy.currency_map), "conversion_basis": policy.conversion_basis}}
    if plan.status != "ready":
        return empty
    tx = find_table(data_dir, mapping.transactions_table)
    if tx is None or not mapping.currency_column or not mapping.date_column or not mapping.amount_column:
        return empty
    df = pd.read_csv(tx, dtype=str).fillna("")
    if mapping.currency_column not in df.columns:
        return empty

    fmt = policy.date_format
    scope = _scope_frame(df, plan, mapping, policy)
    rates = _load_rates(find_table(data_dir, mapping.rates_table), mapping, fmt)
    rate_codes = sorted(rates)
    mult = Decimal(str(mapping.unit_multiplier))
    scope = scope.assign(_raw=scope[mapping.currency_column].map(raw_currency),
                         _k=scope[mapping.date_column].map(lambda t: dkey(t, fmt)))

    currencies: List[Dict[str, Any]] = []
    questions: List[Dict[str, Any]] = []
    any_foreign = False

    for code in sorted(scope["_raw"].unique(), key=lambda c: (c != target, c)):
        rows = scope[scope["_raw"] == code]
        native = sum((_dec(a) * mult for a in rows[mapping.amount_column]), Decimal("0"))
        mapped = policy.currency_map.get(code)
        eff = effective_currency(code, policy.currency_map)
        series = rates.get(eff, [])
        no_rate_on_date = sum(1 for k in rows["_k"] if eff != target and _rate(rates, eff, k, target, TRANSACTION_DATE) is None)
        info: Dict[str, Any] = {
            "code": code, "rows": int(len(rows)), "native_amount": str(native),
            "confirmed_as": mapped, "converts_as": eff or None,
            "is_target": eff == target,
            "rate_on_file": bool(series) or eff == target,
            "first_rate_effective": key_to_iso(series[0][0]) if series else None,
            "latest_rate": str(series[-1][1]) if series else None,
            "latest_rate_effective": key_to_iso(series[-1][0]) if series else None,
            "rows_without_rate_on_transaction_date": int(no_rate_on_date),
        }
        currencies.append(info)

        if code == target or (mapped is not None and eff == target):
            continue                      # already in the reporting currency: nothing to ask
        any_foreign = True
        if mapped is not None:
            continue                      # the user has answered for this code
        n = len(rows)
        if code == BLANK_CURRENCY:
            text = (f"{n} in-scope row(s) have no currency recorded. Which currency are they in? "
                    f"Rows left unknown stay excluded from the total and are listed.")
            options = [{"label": f"They are in {target} (the reporting currency)", "answer": {"currency_map": {code: target}}}]
            options += [{"label": f"They are in {c}", "answer": {"currency_map": {code: c}}}
                        for c in _suggestions(code, rate_codes, target) if c != target]
            options.append({"label": "Leave unknown (exclude and list them)", "answer": {"currency_map": {code: "XXX"}}})
        else:
            recognised = bool(series)
            text = (f"{n} in-scope row(s) are recorded in {code} (native total {native:,.2f} {code}). "
                    + (f"Is {code} the correct currency for these rows?" if recognised else
                       f"Is {code} the correct currency? No exchange rate for {code} is on file, so these rows "
                       f"cannot be converted to {target} unless you reassign them or add a rate."))
            options = [{"label": f"Yes, these rows really are in {code}"
                                 + ("" if recognised else " (keep them excluded and listed)"),
                        "answer": {"currency_map": {code: code}}}]
            options += [{"label": f"No, these rows are in {c}", "answer": {"currency_map": {code: c}}}
                        for c in _suggestions(code, rate_codes, target)]
        options.append({"label": "Other: enter a 3-letter currency code", "answer": {"currency_map": {code: "<CODE>"}},
                        "free_text": True})
        questions.append({"id": f"confirm_currency:{code}", "type": "confirm_currency", "currency": code,
                          "rows": n, "native_amount": str(native), "question": text, "options": options})

    if any_foreign and policy.conversion_basis is None:
        foreign = [c for c in currencies if not c["is_target"] and c["code"] != BLANK_CURRENCY]
        detail = {c["code"]: {k: c[k] for k in ("first_rate_effective", "latest_rate", "latest_rate_effective",
                                                "rows_without_rate_on_transaction_date", "rate_on_file")}
                  for c in foreign}
        questions.append({
            "id": "conversion_basis", "type": "conversion_basis",
            "question": f"How should amounts in other currencies be converted to {target}: at the exchange rate on "
                        f"each transaction's date, or at the present (latest) rate on file?",
            "options": [
                {"label": "Rate on each transaction's date (standard for accounting)",
                 "answer": {"conversion_basis": "transaction_date"}},
                {"label": "Present (latest) rate on file, applied to every row",
                 "answer": {"conversion_basis": "latest"}},
            ],
            "details": detail,
        })

    return {
        "needs_confirmation": bool(questions),
        "target_currency": target,
        "currencies": currencies,
        "questions": questions,
        "current_answers": {"currency_map": dict(policy.currency_map), "conversion_basis": policy.conversion_basis},
        "how_to_answer": ("Send the same request again with policy.currency_map set to the merged answers "
                          "(one entry per currency question) and policy.conversion_basis set to the chosen basis."
                          if questions else None),
    }
