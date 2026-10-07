"""
Phase 4: DuckDB Inspector engine.
Independently recalculates verified metrics from the raw CSV files using DuckDB SQL with explicit
DECIMAL arithmetic, effective-date rate lookups, duplicate/conflict handling and refunds.
It shares no arithmetic code with the Pandas Analyst, only the file-lookup and date-key helpers.
"""

import duckdb
from pathlib import Path
from decimal import Decimal
from typing import Dict, Any
from backend.app.schemas import Plan, Policy, Mapping
from backend.app.common import find_table, dkey, key_to_iso, DD_MM, BLANK_CURRENCY, TRANSACTION_DATE, LATEST


def _q(col: str) -> str:
    return '"' + col.replace('"', '""') + '"'


def _lit(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def execute_duckdb_inspector(data_dir: Path, plan: Plan, mapping: Mapping, policy: Policy) -> Dict[str, Any]:
    if plan.status == "refused":
        return {"status": "REFUSED", "result": None}
    agg = plan.metric.agg if plan.metric else "sum"
    if agg not in ("sum", "count"):
        return {"status": "FAILED", "result": None, "reason": f"Aggregation '{agg}' is not supported."}

    tx_file = find_table(data_dir, mapping.transactions_table)
    if tx_file is None:
        return {"status": "FAILED", "result": None, "reason": "Transactions file not found"}
    rates_file = find_table(data_dir, mapping.rates_table)
    refunds_file = find_table(data_dir, mapping.refunds_table)

    fmt = policy.date_format
    pattern = "%d/%m/%Y" if fmt == DD_MM else "%m/%d/%Y"
    target = policy.target_currency
    latest_basis = (policy.conversion_basis or TRANSACTION_DATE) == LATEST

    start_k = end_k = 0
    if plan.date_range and plan.date_range.start and plan.date_range.end:
        start_k, end_k = dkey(plan.date_range.start, fmt), dkey(plan.date_range.end, fmt)
        if not start_k or not end_k or start_k > end_k:
            return {"status": "FAILED", "result": None,
                    "reason": f"Date range {plan.date_range.start} - {plan.date_range.end} is not valid for format {fmt}."}

    key, dt, ent = _q(mapping.key_column), _q(mapping.date_column), _q(mapping.entity_column or "")
    amt, cur = _q(mapping.amount_column), _q(mapping.currency_column or "")
    mult_i = int(Decimal(str(mapping.unit_multiplier)) * 10000)  # scale 1e4
    HALF, DIV = 50000000000000, 100000000000000  # round half up to cents; scale 1e6*1e4*1e6 / 1e2

    conn = duckdb.connect(database=":memory:")
    try:
        conn.execute(f"CREATE TABLE transactions AS SELECT * FROM read_csv_auto({_lit(tx_file)}, all_varchar=True);")
        cols = {r[0] for r in conn.execute("DESCRIBE transactions").fetchall()}
        if rates_file is not None:
            conn.execute(f"CREATE TABLE exchange_rates AS SELECT * FROM read_csv_auto({_lit(rates_file)}, all_varchar=True);")
        else:
            conn.execute(
                f"CREATE TABLE exchange_rates ({_q(mapping.rate_currency_column or 'c')} VARCHAR, "
                f"{_q(mapping.rate_value_column or 'v')} VARCHAR, {_q(mapping.rate_effective_date_column or 'd')} VARCHAR);")
        rc, rv, re_ = (_q(mapping.rate_currency_column or "c"), _q(mapping.rate_value_column or "v"),
                       _q(mapping.rate_effective_date_column or "d"))

        def cur_sql(expr: str) -> str:
            """Currency of a row after the user's confirmed currency_map (blank -> '')."""
            base = f"UPPER(TRIM(COALESCE({expr}, '')))"
            whens = "".join(
                f" WHEN {_lit('' if k == BLANK_CURRENCY else k)} THEN {_lit(v)}"
                for k, v in policy.currency_map.items() if ('' if k == BLANK_CURRENCY else k) != v)
            return f"(CASE {base}{whens} ELSE {base} END)" if whens else base

        def rate_sql(cur_expr: str, date_expr: str) -> str:
            # transaction_date: newest rate effective on/before the date; latest: newest rate on file.
            # Ties on the same effective date go to the later file row, as in the Analyst.
            date_pred = "" if latest_basis else f"AND TRY_CAST(r.{re_} AS DATE) <= CAST({date_expr} AS DATE)"
            return f"""COALESCE(
                CASE WHEN UPPER(TRIM({cur_expr})) = {_lit(target)} THEN CAST(1.00 AS DECIMAL(12,6)) END,
                (SELECT TRY_CAST(r.{rv} AS DECIMAL(12,6)) FROM exchange_rates r
                  WHERE UPPER(TRIM(r.{rc})) = UPPER(TRIM({cur_expr}))
                    AND TRY_CAST(r.{rv} AS DECIMAL(12,6)) IS NOT NULL
                    AND TRY_CAST(r.{re_} AS DATE) IS NOT NULL
                    {date_pred}
                  ORDER BY TRY_CAST(r.{re_} AS DATE) DESC, r.rowid DESC LIMIT 1),
                CAST(0.00 AS DECIMAL(12,6)))"""

        cur_expr_c = cur_sql(f"c.{cur}") if mapping.currency_column and mapping.currency_column in cols else _lit(target)

        def entity_where(alias: str) -> str:
            clauses = []
            for f in plan.filters:
                col, op, val = f.get("column"), f.get("op"), f.get("value")
                if not (col and op == "eq"):
                    continue
                if col == mapping.entity_column:
                    clauses.append(f"LOWER(TRIM({alias}.{_q(col)})) = {_lit(str(val).strip().casefold())}")
                elif col in cols:
                    clauses.append(f"{alias}.{_q(col)} = {_lit(val)}")
            return " AND ".join(clauses) or "TRUE"

        def date_where(date_expr: str) -> str:
            if not start_k:
                return "TRUE"
            return f"CAST({date_expr} AS DATE) BETWEEN DATE {_lit(key_to_iso(start_k))} AND DATE {_lit(key_to_iso(end_k))}"

        partition = ", ".join(c for c in (key, dt, ent if (mapping.entity_column in cols) else None, amt) if c)
        ctes = f"""
            WITH valid AS (
                SELECT *, rowid AS _rid FROM transactions
                WHERE {dt} IS NOT NULL AND TRIM({dt}) != '' AND {amt} IS NOT NULL AND TRIM({amt}) != ''
            ),
            dedup AS (
                SELECT * FROM valid QUALIFY ROW_NUMBER() OVER (PARTITION BY {partition} ORDER BY _rid) = 1
            ),
            conflicts AS (
                SELECT {key} AS k FROM dedup GROUP BY {key} HAVING COUNT(DISTINCT {amt}) > 1
            ),
            clean AS (
                SELECT * FROM dedup WHERE {key} NOT IN (SELECT k FROM conflicts)
            ),
            scoped0 AS (
                SELECT c.*,
                       COALESCE(CAST(ROUND(TRY_CAST(c.{amt} AS DECIMAL(28,6)) * 1000000) AS HUGEINT), 0) AS _a,
                       CAST(ROUND({rate_sql(cur_expr_c, f"TRY_STRPTIME(TRIM(c.{dt}), \'{pattern}\')")} * 1000000) AS HUGEINT) AS _r
                FROM clean c
                WHERE {entity_where("c")} AND {date_where(f"TRY_STRPTIME(TRIM(c.{dt}), \'{pattern}\')")}
            ),
            scoped AS (
                SELECT *, SIGN(_a) * ((ABS(_a) * {mult_i} * _r + {HALF}) // {DIV}) AS _cents FROM scoped0
            )
        """

        if agg == "count":
            total = Decimal(conn.execute(ctes + " SELECT COUNT(*) FROM scoped").fetchone()[0])
            final_amt = str(int(total))
        else:
            row = conn.execute(ctes + " SELECT COALESCE(SUM(_cents), 0) FROM scoped").fetchone()
            total = Decimal(str(row[0])) / 100

            if refunds_file is not None and policy.refunds == "include_as_negative":
                conn.execute(f"CREATE TABLE refunds AS SELECT * FROM read_csv_auto({_lit(refunds_file)}, all_varchar=True);")
                rk, ra, rd = _q(mapping.refund_key_column), _q(mapping.refund_amount_column), _q(mapping.refund_date_column)
                rdate = f"TRY_STRPTIME(TRIM(rf.{rd}), '{pattern}')"
                o_cur = cur_sql(f"o.{cur}") if mapping.currency_column and mapping.currency_column in cols else _lit(target)
                refund_sql = f"""
                    SELECT COALESCE(SUM(SIGN(_a) * ((ABS(_a) * {mult_i} * _r + {HALF}) // {DIV})), 0) FROM (
                        SELECT COALESCE(CAST(ROUND(TRY_CAST(rf.{ra} AS DECIMAL(28,6)) * 1000000) AS HUGEINT), 0) AS _a,
                               CAST(ROUND({rate_sql(o_cur, rdate)} * 1000000) AS HUGEINT) AS _r
                        FROM refunds rf
                        JOIN (SELECT * FROM clean QUALIFY ROW_NUMBER() OVER (PARTITION BY {key} ORDER BY _rid) = 1) o
                          ON rf.{rk} = o.{key}
                        WHERE {entity_where("o")} AND {date_where(rdate)}
                    )
                """
                total -= Decimal(str(conn.execute(ctes + refund_sql).fetchone()[0])) / 100
            final_amt = str(total.quantize(Decimal("0.01")))

        return {
            "status": "VERIFIED",
            "result": final_amt,
            "currency": policy.target_currency,
            "inspector": "DuckDB"
        }
    except Exception as e:
        return {
            "status": "BLOCKED_MISMATCH",
            "result": None,
            "reason": str(e)
        }
    finally:
        conn.close()
