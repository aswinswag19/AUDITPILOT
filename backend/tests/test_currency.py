"""
Currency confirmation, conversion basis, plan pre-flight, and the related bug fixes.
Expected figures are worked out by hand from tiny purpose-built datasets, not copied from the engines.
"""
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.app.main as main
from backend.app.main import app
from backend.app.schemas import Policy, Plan
from backend.app.mapping import infer_mapping, list_entities
from backend.app.planner.rules import SmartRulesPlanner
from backend.app.engines.analyst import execute_pandas_analyst
from backend.app.engines.inspector import execute_duckdb_inspector
from backend.app.currency import currency_check
from backend.app.preflight import plan_problems
from backend.app.profiler import profile_dataset
from backend.app.contradictions import check_contradictions
from backend.app.trust import compute_trust_decision

SHIPPED = Path(__file__).resolve().parents[1] / "data"
client = TestClient(app)

RATES = "currency,rate_to_inr,effective_date\nINR,1.00,2025-01-01\nUSD,80.00,2025-09-01\nUSD,90.00,2025-11-01\n"
HEADER = "invoice_id,order_date,branch,product,amount,currency\n"


def make_data(tmp_path, rows, rates=RATES):
    (tmp_path / "sales.csv").write_text(HEADER + "".join(rows))
    (tmp_path / "exchange_rates.csv").write_text(rates)
    return tmp_path


def plan_for(d, question, policy=None):
    policy = policy or Policy()
    m = infer_mapping(d, "sales.csv")
    return SmartRulesPlanner().create_plan(question, {"entities": list_entities(d, m)}, m, policy), m, policy


def run_script(code):
    """Run a generated proof script in its own interpreter, from a scratch folder (never the data folder)."""
    with tempfile.TemporaryDirectory() as scratch:
        p = Path(scratch) / "proof_under_test.py"
        p.write_text(code)
        out = subprocess.run([sys.executable, str(p)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip().split("RESULT=")[1].split()[0]


def all_three(d, question, **policy_fields):
    plan, m, p = plan_for(d, question, Policy(**policy_fields))
    a = execute_pandas_analyst(d, plan, m, p, export_source_rows=False)
    i = execute_duckdb_inspector(d, plan, m, p)
    return a, i, run_script(a["generated_code"])


# ---------------------------------------------------------------- what gets asked
def test_inr_only_scope_asks_nothing(tmp_path):
    d = make_data(tmp_path, ["A1,10/10/2025,Chennai,W,500.00,INR\n", "A2,11/10/2025,Chennai,W,250.00,INR\n"])
    plan, m, p = plan_for(d, "total revenue")
    chk = currency_check(d, plan, m, p)
    assert chk["needs_confirmation"] is False and chk["questions"] == []


def test_foreign_currency_asks_confirmation_then_conversion_basis(tmp_path):
    d = make_data(tmp_path, ["A1,10/10/2025,Chennai,W,500.00,INR\n", "A2,10/10/2025,Chennai,W,100.00,USD\n",
                             "A3,10/10/2025,Chennai,W,50.00,EUR\n"])
    plan, m, p = plan_for(d, "total revenue")
    chk = currency_check(d, plan, m, p)
    assert [q["id"] for q in chk["questions"]] == ["confirm_currency:EUR", "confirm_currency:USD", "conversion_basis"]
    eur = chk["questions"][0]
    assert "No exchange rate for EUR" in eur["question"]
    assert {"currency_map": {"EUR": "USD"}} in [o["answer"] for o in eur["options"]]
    basis = chk["questions"][2]
    assert [o["answer"]["conversion_basis"] for o in basis["options"]] == ["transaction_date", "latest"]
    assert basis["details"]["USD"]["latest_rate"] == "90.00" and basis["details"]["USD"]["first_rate_effective"] == "2025-09-01"


def test_answers_remove_their_questions_and_partial_answers_keep_the_rest(tmp_path):
    d = make_data(tmp_path, ["A1,10/10/2025,Chennai,W,100.00,USD\n", "A2,10/10/2025,Chennai,W,50.00,EUR\n"])
    plan, m, _ = plan_for(d, "total revenue")
    partial = currency_check(d, plan, m, Policy(currency_map={"USD": "USD"}))
    assert [q["id"] for q in partial["questions"]] == ["confirm_currency:EUR", "conversion_basis"]
    full = currency_check(d, plan, m, Policy(currency_map={"USD": "USD", "EUR": "USD"}, conversion_basis="latest"))
    assert full["needs_confirmation"] is False


def test_reassigning_everything_to_the_reporting_currency_asks_no_basis(tmp_path):
    d = make_data(tmp_path, ["A1,10/10/2025,Chennai,W,100.00,RS\n", "A2,10/10/2025,Chennai,W,50.00,INR\n"])
    plan, m, _ = plan_for(d, "total revenue")
    first = currency_check(d, plan, m, Policy())
    assert first["questions"][0]["currency"] == "RS"
    assert {"currency_map": {"RS": "INR"}} in [o["answer"] for o in first["questions"][0]["options"]]  # alias suggested
    assert currency_check(d, plan, m, Policy(currency_map={"RS": "INR"}))["needs_confirmation"] is False


def test_only_in_scope_currencies_are_asked_about(tmp_path):
    d = make_data(tmp_path, ["A1,10/10/2025,Chennai,W,100.00,INR\n", "A2,10/10/2025,Mumbai,W,50.00,EUR\n",
                             "A3,10/04/2025,Chennai,W,70.00,USD\n"])
    plan, m, p = plan_for(d, "Q4 revenue for Chennai")  # Mumbai's EUR and the Q2 USD row are out of scope
    assert currency_check(d, plan, m, p)["needs_confirmation"] is False


def test_blank_currency_is_asked_about_and_can_be_assigned(tmp_path):
    d = make_data(tmp_path, ["A1,10/10/2025,Chennai,W,500.00,\n", "A2,10/10/2025,Chennai,W,100.00,INR\n"])
    plan, m, p = plan_for(d, "total revenue")
    q = currency_check(d, plan, m, p)["questions"][0]
    assert q["currency"] == "(BLANK)" and "no currency" in q["question"]
    for pol, expected in ((Policy(), "100.00"), (Policy(currency_map={"(BLANK)": "INR"}), "600.00"),
                          (Policy(currency_map={"(BLANK)": "XXX"}), "100.00")):
        a, i, s = all_three(d, "total revenue", **pol.model_dump())
        assert a["result"] == i["result"] == s == expected


# ---------------------------------------------------------------- conversion maths
def test_transaction_date_versus_latest_rate_by_hand(tmp_path):
    # 100 USD on 10/10/2025: rate in force that day is 80 (the 90 starts 01/11); latest rate on file is 90.
    # 10 USD on 01/08/2025 is before the first USD rate: unconvertible by date, convertible at the latest rate.
    d = make_data(tmp_path, ["A1,10/10/2025,Chennai,W,100.00,USD\n", "A2,01/08/2025,Chennai,W,10.00,USD\n",
                             "A3,05/12/2025,Chennai,W,1.00,USD\n"])
    a, i, s = all_three(d, "total revenue", conversion_basis="transaction_date")
    assert a["result"] == i["result"] == s == "8090.00"          # 100*80 + 1*90, the early row excluded
    assert a["unsupported_in_scope"]["count"] == 1
    a, i, s = all_three(d, "total revenue", conversion_basis="latest")
    assert a["result"] == i["result"] == s == "9990.00"          # 111 * 90
    assert a["unsupported_in_scope"]["count"] == 0
    assert a["conversion"]["basis"] == "latest" and a["conversion"]["foreign_rows_in_scope"] == 3


def test_reassigned_currency_is_converted_as_the_new_currency(tmp_path):
    d = make_data(tmp_path, ["A1,10/10/2025,Chennai,W,100.00,EUR\n", "A2,10/10/2025,Chennai,W,1.00,USD\n"])
    a, i, s = all_three(d, "total revenue", currency_map={"EUR": "USD", "USD": "USD"}, conversion_basis="transaction_date")
    assert a["result"] == i["result"] == s == "8080.00"         # 101 USD at 80
    a, i, s = all_three(d, "total revenue", currency_map={"EUR": "EUR", "USD": "USD"}, conversion_basis="transaction_date")
    assert a["result"] == i["result"] == s == "80.00"           # EUR stays excluded without a rate
    assert list(a["unsupported_in_scope"]["by_currency"]) == ["EUR"]


def test_refunds_follow_currency_map_and_basis():
    # Dataset B: refunds are converted from the refunded order's currency.
    for pol in ({}, {"conversion_basis": "latest"}, {"currency_map": {"EUR": "INR"}}):
        m = infer_mapping(SHIPPED, "orders.csv")
        p = Policy(**pol)
        plan = SmartRulesPlanner().create_plan("Q4 revenue", {"entities": list_entities(SHIPPED, m)}, m, p)
        a = execute_pandas_analyst(SHIPPED, plan, m, p, export_source_rows=False)
        i = execute_duckdb_inspector(SHIPPED, plan, m, p)
        assert a["result"] == i["result"] and a["status"] == i["status"] == "VERIFIED"


@pytest.mark.parametrize("question", ["total revenue", "Q4 revenue for Chennai", "Q3 revenue for Mumbai", "fiscal Q4 revenue"])
@pytest.mark.parametrize("pol", [{}, {"conversion_basis": "latest"}, {"currency_map": {"EUR": "USD"}},
                                 {"currency_map": {"EUR": "USD"}, "conversion_basis": "latest"},
                                 {"currency_map": {"EUR": "INR", "USD": "INR"}}])
def test_three_independent_engines_agree_on_shipped_data(question, pol, tmp_path):
    a, i, s = all_three(SHIPPED, question, **pol)
    assert a["status"] == i["status"] == "VERIFIED"
    assert a["result"] == i["result"] == s


def test_currency_choices_actually_change_the_answer():
    base = all_three(SHIPPED, "Q4 revenue for Chennai")[0]["result"]
    latest = all_three(SHIPPED, "Q4 revenue for Chennai", conversion_basis="latest")[0]["result"]
    reassigned = all_three(SHIPPED, "Q4 revenue for Chennai", currency_map={"EUR": "USD"})[0]["result"]
    assert len({base, latest, reassigned}) == 3
    assert base == "53549309.97"  # defaults still reproduce the original answer


def test_large_amounts_with_reassigned_currency_stay_exact(tmp_path):
    d = make_data(tmp_path, ["B1,10/11/2025,Chennai,W,99999999999999.99,EUR\n", "B2,10/11/2025,Chennai,W,123456789012345.67,USD\n"])
    a, i, s = all_three(d, "total revenue", currency_map={"EUR": "USD", "USD": "USD"}, conversion_basis="latest")
    assert a["result"] == i["result"] == s
    assert Decimal(a["result"]) == (Decimal("99999999999999.99") + Decimal("123456789012345.67")) * 90


# ---------------------------------------------------------------- policy validation
def test_policy_validation():
    assert Policy(currency_map={"eur": "usd", "": "inr"}).currency_map == {"EUR": "USD", "(BLANK)": "INR"}
    with pytest.raises(ValueError):
        Policy(currency_map={"EUR": "dollars"})
    with pytest.raises(ValueError):
        Policy(conversion_basis="today")


# ---------------------------------------------------------------- API gate
def test_api_blocks_until_currencies_are_confirmed():
    plan = client.post("/plan", json={"question": "What was Q4 revenue for Chennai?"}).json()
    assert plan["currency_confirmation"]["needs_confirmation"] is True
    for ep in ("execute", "verify", "trust", "proof", "impact", "sensitivity"):
        r = client.post(f"/{ep}", json={"plan": plan})
        assert r.status_code == 409 and r.json()["detail"]["error"] == "CURRENCY_CONFIRMATION_REQUIRED", ep
        assert r.json()["detail"]["questions"], ep
    pol = {"currency_map": {"EUR": "USD", "USD": "USD"}, "conversion_basis": "latest"}
    v = client.post("/verify", json={"plan": plan, "policy": pol}).json()
    assert v["verified"] is True and v["analyst"]["result"] == v["inspector"]["result"] == "84709141.27"
    bundle = client.post("/proof", json={"plan": plan, "policy": pol}).json()
    assert bundle["conversion"]["basis"] == "latest" and bundle["conversion"]["currency_map"] == pol["currency_map"]
    assert "conversion_basis" in {s["name"] for s in bundle["sensitivity"]["scenarios"]}
    assert client.post("/reports/generate", json={"proof_bundle": bundle}).status_code == 200


def test_api_currency_check_endpoint_and_grouped_plans():
    g = client.post("/plan", json={"question": "Rank branches by Q4 revenue"}).json()
    ids = [q["id"] for q in client.post("/currency/check", json={"plan": g}).json()["questions"]]
    assert ids == ["confirm_currency:EUR", "confirm_currency:USD", "conversion_basis"]
    assert client.post("/verify", json={"plan": g}).status_code == 409
    ok = client.post("/verify", json={"plan": g, "policy": {"currency_map": {"EUR": "EUR", "USD": "USD"},
                                                           "conversion_basis": "transaction_date"}})
    assert ok.status_code == 200 and ok.json()["verified"] is True


def test_api_rejects_invalid_policy_answers():
    plan = client.post("/plan", json={"question": "total revenue"}).json()
    assert client.post("/verify", json={"plan": plan, "policy": {"conversion_basis": "yesterday"}}).status_code == 422
    assert client.post("/verify", json={"plan": plan, "policy": {"currency_map": {"EUR": "<CODE>"}}}).status_code == 422


def test_refused_plan_is_not_blocked_by_currency_questions():
    plan = client.post("/plan", json={"question": "What was profit for Chennai?"}).json()
    assert plan["status"] == "refused" and "currency_confirmation" not in plan
    r = client.post("/execute", json={"plan": plan})
    assert r.status_code == 200 and r.json()["analyst"]["status"] == "REFUSED"


# ---------------------------------------------------------------- plan pre-flight
CONFIRMED = {"currency_map": {"USD": "USD", "EUR": "EUR"}, "conversion_basis": "transaction_date"}


def _plan_with_filter(flt):
    plan = client.post("/plan", json={"question": "What was Q4 revenue for Chennai?"}).json()
    plan["filters"] = [flt]
    return plan


@pytest.mark.parametrize("flt,fragment", [
    ({"column": "branch", "op": "eq", "value": "Delhi"}, "'Delhi' is not a known branch"),
    ({"column": "branch", "op": "in", "value": ["Chennai", "Mumbai"]}, "operator 'in'"),
    ({"column": "region_x", "op": "eq", "value": "Chennai"}, "does not exist"),
])
@pytest.mark.parametrize("endpoint", ["execute", "verify", "trust", "proof", "impact", "sensitivity"])
def test_api_rejects_plans_the_engines_would_misread(endpoint, flt, fragment):
    r = client.post(f"/{endpoint}", json={"plan": _plan_with_filter(flt), "policy": CONFIRMED})
    assert r.status_code == 422 and r.json()["detail"]["error"] == "INVALID_PLAN"
    assert fragment in r.json()["detail"]["problems"][0]


def test_unknown_entity_is_rejected_case_insensitively_but_known_variants_pass():
    assert client.post("/execute", json={"plan": _plan_with_filter({"column": "branch", "op": "eq", "value": "chennai "}),
                                         "policy": CONFIRMED}).status_code == 200
    plan = client.post("/plan", json={"question": "Compare Chennai and Mumbai Q4 revenue"}).json()
    plan["comparison_entities"] = ["Chennai", "Atlantis"]
    r = client.post("/verify", json={"plan": plan, "policy": CONFIRMED})
    assert r.status_code == 422 and "Atlantis" in r.json()["detail"]["problems"][0]
    plan["comparison_entities"], plan["group_by"] = ["Chennai"], ["product"]
    assert client.post("/verify", json={"plan": plan, "policy": CONFIRMED}).status_code == 422


def test_plan_problems_is_clean_for_a_good_plan():
    m = infer_mapping(SHIPPED)
    plan = SmartRulesPlanner().create_plan("Q4 revenue for Chennai", {"entities": list_entities(SHIPPED, m)}, m, Policy())
    assert plan_problems(SHIPPED, plan, m)["problems"] == []


# ---------------------------------------------------------------- other fixes
def test_profiler_uses_the_rates_table_not_a_hardcoded_currency_list():
    a = profile_dataset(SHIPPED, infer_mapping(SHIPPED))
    assert a["unsupported_currencies"] == ["EUR"] and "USD" in a["currencies_found"]   # sales: no EUR rate
    b = profile_dataset(SHIPPED, infer_mapping(SHIPPED, "orders.csv"))
    assert b["unsupported_currencies"] == []                                          # dataset B has a EUR rate


def test_contradiction_check_compares_the_same_year_only():
    m, p = infer_mapping(SHIPPED), Policy(**CONFIRMED)
    for q, expect in (("Q4 revenue for Chennai", "CONTRADICTION_DETECTED"), ("Q4 2024 revenue", "NOT_COMPARABLE")):
        plan = SmartRulesPlanner().create_plan(q, {"entities": list_entities(SHIPPED, m)}, m, p)
        a = execute_pandas_analyst(SHIPPED, plan, m, p, export_source_rows=False)
        assert check_contradictions(SHIPPED, m, a, plan=plan, policy=p)["status"] == expect, q


def test_empty_scope_is_flagged_not_reported_as_a_clean_zero():
    plan = client.post("/plan", json={"question": "Q4 2024 revenue"}).json()
    t = client.post("/trust", json={"plan": plan, "policy": CONFIRMED}).json()
    assert t["trust_decision"] == "VERIFIED_WITH_POLICY"
    assert any("No transactions matched" in r for r in t["reasons"])
