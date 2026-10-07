"""
Generates the standalone proof script for a plan.

The script recomputes the answer from the raw CSV files using only the libraries the AST guard
allows (pandas, decimal, pathlib, json) and prints  RESULT=<amount> <currency>.
It follows the same policy steps as the Pandas Analyst, so anybody can re-run it independently.
"""

import pprint
from pathlib import Path
from typing import Any, Dict, List
from backend.app.schemas import Plan, Policy, Mapping
from backend.app.common import dkey

_TEMPLATE = r"""# AuditPilot proof script (generated). Recomputes the answer from the raw CSV files.
# Run:  python <this file>      ->  prints RESULT=<amount> <currency>
# Expected answer when generated: __EXPECTED__
import pandas as pd
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

CFG = __CFG__
DATA = Path(CFG["data_dir"])
FMT = CFG["date_format"]
C = CFG["cols"]
CENT = Decimal("0.01")
MULT = Decimal(CFG["multiplier"])
TARGET = CFG["target"]
BASIS = CFG["basis"]        # "transaction_date" or "latest"
CMAP = CFG["currency_map"]  # currencies as confirmed by the user: {code in data: real code}


def find(name):
    for p in (DATA / name, DATA / "dataset_b" / name):
        if p.is_file():
            return p
    raise SystemExit("missing table: " + name)


def valid(y, m, d):
    if m < 1 or m > 12 or y < 1 or d < 1:
        return False
    if m == 2:
        dim = 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    elif m in (4, 6, 9, 11):
        dim = 30
    else:
        dim = 31
    return d <= dim


def dkey(text):
    parts = str(text).strip().split("/")
    if len(parts) != 3:
        return 0
    try:
        a, b, y = [int(x) for x in parts]
    except ValueError:
        return 0
    d, m = (a, b) if FMT == "DD/MM/YYYY" else (b, a)
    return y * 10000 + m * 100 + d if valid(y, m, d) else 0


def iso_key(text):
    s = str(text).strip()
    if "/" in s:
        return dkey(s)
    parts = s.split("-")
    if len(parts) != 3:
        return 0
    try:
        y, m, d = [int(x) for x in parts]
    except ValueError:
        return 0
    return y * 10000 + m * 100 + d if valid(y, m, d) else 0


def money(x):
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


RATES = {}
if CFG["rates"]:
    rdf = pd.read_csv(find(CFG["rates"]["table"]), dtype=str).fillna("")
    for _, r in rdf.iterrows():
        k = iso_key(r[CFG["rates"]["date"]])
        try:
            v = Decimal(r[CFG["rates"]["value"]])
        except Exception:
            continue
        if k:
            RATES.setdefault(r[CFG["rates"]["currency"]].strip().upper(), []).append((k, v))
    for cur in RATES:
        RATES[cur].sort(key=lambda t: t[0])


def eff(cur):
    code = str(cur).strip().upper() or "(BLANK)"
    out = CMAP.get(code, code)
    return "" if out == "(BLANK)" else out


def rate(cur, k):
    if cur == TARGET:
        return Decimal("1.00")
    if BASIS == "latest":
        series = RATES.get(cur)
        return series[-1][1] if series else None
    if not k:
        return None
    best = None
    for ek, v in RATES.get(cur, []):
        if ek <= k:
            best = v
        else:
            break
    return best


def convert(amount, cur, k):
    try:
        a = Decimal(str(amount).strip()) * MULT
    except Exception:
        a = Decimal("0")
    r = rate(eff(cur), k)
    return money(a * (r if r is not None else Decimal("0")))


def entity_ok(frame):
    ok = pd.Series(True, index=frame.index)
    for col, val in CFG["filters"]:
        if col == C["entity"]:
            ok &= frame["_ent"] == str(val).strip().casefold()
        elif col in frame.columns:
            ok &= frame[col] == val
    return ok


# 1. load, drop rows missing date or amount
df = pd.read_csv(find(CFG["tx"]), dtype=str).fillna("")
df["_ent"] = df[C["entity"]].str.strip().str.casefold() if C["entity"] in df.columns else ""
df = df[df[C["date"]].str.strip().ne("") & df[C["amount"]].str.strip().ne("")].copy()

# 2. convert every row to the target currency (rate effective on the transaction date)
df["_k"] = df[C["date"]].apply(dkey)
curs = df[C["currency"]] if C["currency"] in df.columns else [TARGET] * len(df)
df["_v"] = [convert(a, c, k) for a, c, k in zip(df[C["amount"]], curs, df["_k"])]

# 3. keep the first of exact duplicates, exclude invoices whose amounts conflict
subset = [c for c in (C["key"], C["date"], C["entity"], C["amount"]) if c and c in df.columns]
if C["key"] and C["key"] in df.columns:
    df = df.drop_duplicates(subset=subset, keep="first")
    nun = df.groupby(C["key"])[C["amount"]].nunique()
    df = df[~df[C["key"]].isin(nun[nun > 1].index.tolist())]

# 4. apply the plan's scope (entity filters + date range)
scope = entity_ok(df)
if CFG["start"]:
    scope &= (df["_k"] >= CFG["start"]) & (df["_k"] <= CFG["end"])
final = df[scope]

if CFG["count"]:
    print("RESULT=%d %s" % (len(final), CFG["currency"]))
    raise SystemExit(0)

total = sum(final["_v"], Decimal("0.00"))

# 5. refunds are subtracted (policy: include_as_negative)
if CFG["refunds"]:
    R = CFG["refunds"]
    first = df.drop_duplicates(subset=[C["key"]], keep="first")
    ok_keys = set(first.loc[entity_ok(first), C["key"]])
    cur_of = dict(zip(first[C["key"]], first[C["currency"]] if C["currency"] in first.columns else [TARGET] * len(first)))
    rf = pd.read_csv(find(R["table"]), dtype=str).fillna("")
    for _, r in rf.iterrows():
        key = r[R["key"]]
        if key not in ok_keys:
            continue
        k = dkey(r[R["date"]])
        if CFG["start"] and not (CFG["start"] <= k <= CFG["end"]):
            continue
        total -= convert(r[R["amount"]], cur_of[key], k)

print("RESULT=%s %s" % (money(total), CFG["currency"]))
"""


def build_proof_script(data_dir: Path, plan: Plan, mapping: Mapping, policy: Policy, expected: str = "") -> str:
    fmt = policy.date_format
    start = end = 0
    if plan.date_range and plan.date_range.start and plan.date_range.end:
        start, end = dkey(plan.date_range.start, fmt), dkey(plan.date_range.end, fmt)
    filters: List[List[Any]] = [
        [f.get("column"), f.get("value")] for f in plan.filters if f.get("column") and f.get("op") == "eq"
    ]
    is_count = bool(plan.metric and plan.metric.agg == "count")
    cfg: Dict[str, Any] = {
        "data_dir": str(Path(data_dir).resolve()),
        "tx": mapping.transactions_table,
        "cols": {
            "key": mapping.key_column, "date": mapping.date_column, "entity": mapping.entity_column,
            "amount": mapping.amount_column, "currency": mapping.currency_column,
        },
        "rates": ({
            "table": mapping.rates_table, "currency": mapping.rate_currency_column,
            "value": mapping.rate_value_column, "date": mapping.rate_effective_date_column,
        } if mapping.rates_table else None),
        "refunds": ({
            "table": mapping.refunds_table, "key": mapping.refund_key_column,
            "amount": mapping.refund_amount_column, "date": mapping.refund_date_column,
        } if (mapping.refunds_table and policy.refunds == "include_as_negative" and not is_count) else None),
        "multiplier": str(mapping.unit_multiplier),
        "date_format": fmt,
        "basis": policy.conversion_basis or "transaction_date",
        "currency_map": dict(policy.currency_map),
        "target": policy.target_currency,
        "currency": policy.target_currency,
        "filters": filters,
        "start": start,
        "end": end,
        "count": is_count,
    }
    return (_TEMPLATE
            .replace("__EXPECTED__", f"{expected} {policy.target_currency}" if expected else "n/a")
            .replace("__CFG__", pprint.pformat(cfg, width=100, sort_dicts=False)))
