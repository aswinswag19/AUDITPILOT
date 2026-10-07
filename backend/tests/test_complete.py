"""
Regression tests: date handling, planner, refunds, engine agreement, proof scripts,
impact, sensitivity, strict policies, grouped questions, upload safety and PDF robustness.
"""
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.app.main as main
from backend.app.main import app
from backend.app.common import dkey, is_ambiguous_date, quarter_window, calendar_quarter_of, DD_MM, MM_DD
from backend.app.schemas import Policy
from backend.app.mapping import infer_mapping, list_entities
from backend.app.planner.rules import SmartRulesPlanner
from backend.app.engines.analyst import execute_pandas_analyst
from backend.app.engines.inspector import execute_duckdb_inspector
from backend.app.guard import validate_proof_script_ast
from backend.app.impact import compute_impact
from backend.app.sensitivity import compute_sensitivity
from backend.app.trust import compute_trust_decision
from backend.app.pdf_report import generate_audit_pdf

DATA = Path("./backend/data")
client = TestClient(app)

# What a user answers to the currency questions when they accept the data as it is.
CONFIRMED = {"currency_map": {"USD": "USD", "EUR": "EUR"}, "conversion_basis": "transaction_date"}


def plan_for(question, filename="sales.csv", policy=None):
    policy = policy or Policy()
    m = infer_mapping(DATA, filename)
    ents = list_entities(DATA, m)
    return SmartRulesPlanner().create_plan(question, {"entities": ents}, m, policy), m, policy


def both(question, filename="sales.csv", policy=None):
    plan, m, p = plan_for(question, filename, policy)
    return plan, m, p, execute_pandas_analyst(DATA, plan, m, p), execute_duckdb_inspector(DATA, plan, m, p)


# ---------------------------------------------------------------- dates
def test_date_keys_are_calendar_valid_and_format_aware():
    assert dkey("20/09/2025") == 20250920
    assert dkey("31/02/2025") == 0 and dkey("29/02/2024") == 20240229 and dkey("29/02/2025") == 0
    assert dkey("20/09/2025", MM_DD) == 0 and dkey("09/20/2025", MM_DD) == 20250920
    assert dkey("") == 0 and dkey("garbage") == 0
    assert is_ambiguous_date("05/06/2025") and not is_ambiguous_date("20/09/2025") and not is_ambiguous_date("05/05/2025")


def test_quarter_windows():
    assert quarter_window(2025, 4) == ((2025, 10, 1), (2025, 12, 31))
    assert quarter_window(2025, 4, fiscal=True) == ((2025, 1, 1), (2025, 3, 31))
    assert calendar_quarter_of(20251001, 20251231) == (2025, 4)
    assert calendar_quarter_of(20250101, 20250331) == (2025, 1)
    assert calendar_quarter_of(20251001, 20251130) is None


# ---------------------------------------------------------------- planner
@pytest.mark.parametrize("q,start,end", [
    ("What was Q3 revenue for Chennai?", "01/07/2025", "30/09/2025"),
    ("What was Q1 2025 revenue?", "01/01/2025", "31/03/2025"),
    ("What was fiscal Q4 revenue for Mumbai?", "01/01/2025", "31/03/2025"),
    ("What was Q4 revenue for Mumbai?", "01/10/2025", "31/12/2025"),
])
def test_planner_parses_any_quarter(q, start, end):
    plan, *_ = plan_for(q)
    assert plan.status == "ready"
    assert (plan.date_range.start, plan.date_range.end) == (start, end)


def test_planner_applies_entity_without_a_quarter():
    plan, *_ = plan_for("What was revenue for Chennai?")
    assert plan.filters[0]["value"] == "Chennai" and plan.date_range is None


def test_planner_refuses_unknown_entity_but_not_currency_or_quarter_words():
    plan, *_ = plan_for("What was Q4 revenue for Delhi?")
    assert plan.status == "refused" and "Delhi" in plan.refusal.reason
    for ok in ("What was Q4 revenue in INR?", "What was Q4 revenue for Chennai in INR?", "Revenue in Q4 for Mumbai"):
        assert plan_for(ok)[0].status == "ready", ok


def test_planner_compare_names_entities():
    plan, *_ = plan_for("Compare Chennai and Mumbai revenue")
    assert plan.intent == "compare" and set(plan.comparison_entities) == {"Chennai", "Mumbai"}


# ---------------------------------------------------------------- engines
@pytest.mark.parametrize("filename,question", [
    ("sales.csv", "Q4 revenue"), ("sales.csv", "Q4 revenue for Chennai"), ("sales.csv", "Q4 revenue for Mumbai"),
    ("sales.csv", "Q4 revenue for Bengaluru"), ("sales.csv", "Q1 revenue"), ("sales.csv", "Q3 revenue for Chennai"),
    ("sales.csv", "fiscal Q4 revenue"), ("sales.csv", "total revenue"), ("sales.csv", "revenue for Chennai"),
    ("orders.csv", "Q4 revenue"), ("orders.csv", "Q4 revenue for North"), ("orders.csv", "Q4 revenue for West"),
    ("orders.csv", "total revenue"),
])
def test_engines_agree_everywhere(filename, question):
    _, _, _, a, i = both(question, filename)
    assert a["status"] == i["status"] == "VERIFIED", (a, i)
    assert a["result"] == i["result"]


def test_engines_agree_under_mm_dd_policy():
    p = Policy(date_format="MM/DD/YYYY")
    _, _, _, a, i = both("Q4 revenue for Chennai", policy=p)
    assert a["status"] == i["status"] == "VERIFIED" and a["result"] == i["result"]


def test_engines_agree_on_count():
    plan, m, p = plan_for("Q4 revenue for Chennai")
    plan = plan.model_copy(update={"metric": plan.metric.model_copy(update={"agg": "count"})})
    a, i = execute_pandas_analyst(DATA, plan, m, p), execute_duckdb_inspector(DATA, plan, m, p)
    assert a["result"] == i["result"] == "61"  # 68 in scope - 5 exact duplicates - 2 conflicting-invoice rows


def test_unsupported_aggregation_is_rejected_not_zero():
    plan, m, p = plan_for("Q4 revenue")
    plan = plan.model_copy(update={"metric": plan.metric.model_copy(update={"agg": "mean"})})
    assert execute_pandas_analyst(DATA, plan, m, p)["status"] == "FAILED"
    assert execute_duckdb_inspector(DATA, plan, m, p)["status"] == "FAILED"


def test_invalid_date_range_fails_loudly():
    plan, m, p = plan_for("Q4 revenue")
    plan.date_range.end = "31/02/2025"
    assert execute_pandas_analyst(DATA, plan, m, p)["status"] == "FAILED"
    assert execute_duckdb_inspector(DATA, plan, m, p)["status"] == "FAILED"


def test_ground_truth_matches_engines_for_calendar_and_fiscal():
    gt = json.loads((DATA / "ground_truth.json").read_text())
    assert both("Q4 revenue")[3]["result"] == gt["calendar_q4_total_inr"]
    assert both("fiscal Q4 revenue")[3]["result"] == gt["fiscal_q4_total_inr"]
    assert both("fiscal Q4 revenue for Chennai")[3]["result"] == gt["fiscal_q4_chennai_inr"]
    assert both("Q4 revenue for Chennai")[3]["result"] == gt["chennai_calendar_q4_revenue_inr"]


# ---------------------------------------------------------------- refunds (dataset B)
def test_refunds_are_applied_and_policy_controlled():
    _, _, _, a, i = both("Q4 revenue", "orders.csv")
    # 1200*10 + 450*10*90(EUR) + 800*10 - refund 150*10 = 423,500
    assert a["result"] == i["result"] == "423500.00"
    assert a["refunds"]["rows"] == 1
    _, _, _, a2, i2 = both("Q4 revenue", "orders.csv", Policy(refunds="exclude"))
    assert a2["result"] == i2["result"] == "425000.00"
    assert both("Q4 revenue for North", "orders.csv")[3]["result"] == "18500.00"  # refund follows its order's region


def test_refund_outside_period_is_not_subtracted():
    plan, m, p = plan_for("Q4 revenue", "orders.csv")
    plan.date_range.start, plan.date_range.end = "16/10/2025", "31/12/2025"  # refund was on 15/10
    a, i = execute_pandas_analyst(DATA, plan, m, p), execute_duckdb_inspector(DATA, plan, m, p)
    assert a["result"] == i["result"] == "8000.00"  # only ORD-503 (20/10); ORD-502 (12/10) and the refund are out


# ---------------------------------------------------------------- impact & sensitivity
def test_impact_reconciles_to_verified_total():
    plan, m, p, a, _ = both("Q4 revenue for Chennai")
    imp = compute_impact(plan, p, m, a)
    assert imp["raw_total_before_cleaning"] == "60734349.62"
    assert imp["duplicate_effect"] == "-2259346.55" and imp["conflict_effect"] == "-4925693.10"
    assert imp["conflicting_invoices"] == ["INV-1011"] and imp["reconciles"] is True
    assert "EUR" in imp["unsupported_currency_effect"] and "INV-1011" in imp["minimum_cleanup_recommendation"]


def test_impact_for_refund_dataset():
    plan, m, p, a, _ = both("Q4 revenue", "orders.csv")
    imp = compute_impact(plan, p, m, a)
    assert imp["refund_effect"] == "-1500.00" and imp["reconciles"] is True
    assert imp["minimum_cleanup_recommendation"] == "No cleanup required."


def test_sensitivity_covers_date_quarter_and_refund_readings():
    plan, m, p, a, _ = both("Q4 revenue", "orders.csv")
    s = compute_sensitivity(plan, p, m, a, DATA)
    names = {x["name"] for x in s["scenarios"]}
    assert names == {"date_format", "quarter_definition", "refunds", "conversion_basis"}
    refunds = next(x for x in s["scenarios"] if x["name"] == "refunds")
    assert refunds["result"] == "425000.00" and refunds["difference"] == "1500.00"
    assert s["materiality"] in ("Low", "Medium", "High")


def test_sensitivity_without_dates_or_refunds_is_still_valid():
    plan, m, p, a, _ = both("total revenue")
    s = compute_sensitivity(plan, p, m, a, DATA)
    assert {x["name"] for x in s["scenarios"]} == {"date_format", "conversion_basis"}  # foreign rows are in scope


# ---------------------------------------------------------------- strict policies
def test_block_answer_policy_blocks_instead_of_excluding():
    p = Policy(unsupported_currency="block_answer")
    plan, m, _, a, i = both("Q4 revenue for Chennai", policy=p)
    assert a["status"] == "BLOCKED_POLICY" and a["result"] is None and "EUR" in a["reason"]
    t = compute_trust_decision(a, i, {}, {})
    assert t["trust_decision"] == "BLOCKED" and any("EUR" in r for r in t["reasons"])
    p2 = Policy(conflicting_duplicate="block_answer")
    assert both("Q4 revenue for Chennai", policy=p2)[3]["status"] == "BLOCKED_POLICY"
    assert both("Q4 revenue for Mumbai", policy=p2)[3]["status"] == "VERIFIED"  # no conflicts in Mumbai scope


def test_trust_flags_conflicting_invoice_in_scope():
    _, _, _, a, i = both("Q4 revenue for Mumbai")
    assert compute_trust_decision(a, i, {}, {"status": "CONSISTENT"})["trust_decision"] == "VERIFIED_WITH_POLICY"
    plan, m, p, a, i = both("Q4 revenue for Chennai")
    t = compute_trust_decision(a, i, {}, {"status": "CONSISTENT"})
    assert any("INV-1011" in r for r in t["reasons"])


# ---------------------------------------------------------------- proof scripts
def _run_script(code, tmp_path):
    path = tmp_path / "proof.py"
    path.write_text(code)
    out = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip().split("RESULT=")[1]


@pytest.mark.parametrize("filename,question", [
    ("sales.csv", "Q4 revenue for Chennai"), ("sales.csv", "fiscal Q4 revenue"), ("sales.csv", "total revenue"),
    ("orders.csv", "Q4 revenue"), ("orders.csv", "Q4 revenue for North"),
])
def test_proof_script_really_recomputes_the_answer(filename, question, tmp_path):
    plan, m, p, a, _ = both(question, filename)
    assert validate_proof_script_ast(a["generated_code"])
    assert _run_script(a["generated_code"], tmp_path) == f"{a['result']} INR"


def test_proof_script_does_not_just_echo_a_constant(tmp_path):
    plan, m, p, a, _ = both("Q4 revenue for Mumbai")
    tampered = a["generated_code"].replace("'Mumbai'", "'Bengaluru'")
    assert _run_script(tampered, tmp_path) != f"{a['result']} INR"  # change the logic, the output changes


def test_proof_script_embedding_is_injection_safe(tmp_path):
    plan, m, p = plan_for("Q4 revenue for Chennai")
    evil = "x\'\'\'); import os; os.system('echo pwned'); (\'\'\'"
    plan = plan.model_copy(update={"filters": [{"column": m.entity_column, "op": "eq", "value": evil}]})
    a = execute_pandas_analyst(DATA, plan, m, p)
    assert validate_proof_script_ast(a["generated_code"])
    assert _run_script(a["generated_code"], tmp_path) == "0.00 INR"


def test_api_proof_bundle_is_real(tmp_path):
    plan = client.post("/plan", json={"question": "What was Q4 revenue for Mumbai?"}).json()
    b1 = client.post("/proof", json={"plan": plan, "policy": CONFIRMED}).json()
    b2 = client.post("/proof", json={"plan": plan, "policy": CONFIRMED}).json()
    assert b1["proof_id"] != b2["proof_id"]
    assert Path(b1["proof_script_path"]).exists() and b1["script_reproduced_result"] == b1["answer"]
    assert b1["trust_decision"] == "VERIFIED_WITH_POLICY" and b1["impact"]["reconciles"] is True
    assert b1["sensitivity"]["materiality"] in ("Low", "Medium", "High")
    assert "reasons" in b1 and "remaining_risks" in b1


def test_api_proof_refused_when_policy_blocks():
    plan = client.post("/plan", json={"question": "What was Q4 revenue for Chennai?"}).json()
    r = client.post("/proof", json={"plan": plan, "policy": {**CONFIRMED, "unsupported_currency": "block_answer"}})
    assert r.status_code == 409


# ---------------------------------------------------------------- API behaviours
def test_api_impact_and_sensitivity_endpoints():
    plan = client.post("/plan", json={"question": "What was Q4 revenue for Chennai?"}).json()
    imp = client.post("/impact", json={"plan": plan, "policy": CONFIRMED}).json()
    assert imp["reconciles"] is True and imp["verified_total"] == "53549309.97"
    sens = client.post("/sensitivity", json={"plan": plan, "policy": CONFIRMED}).json()
    assert sens["base_result"] == "53549309.97" and sens["scenarios"]


def test_api_plan_refuses_unknown_entity_and_handles_quarters():
    assert client.post("/plan", json={"question": "Q4 revenue for Delhi"}).json()["status"] == "refused"
    p = client.post("/plan", json={"question": "What was Q3 revenue for Chennai?"}).json()
    assert p["date_range"]["start"] == "01/07/2025"
    assert client.post("/execute", json={"plan": p, "policy": CONFIRMED}).json()["analyst"]["result"] == \
        client.post("/execute", json={"plan": p, "policy": CONFIRMED}).json()["inspector"]["result"]


def test_api_compare_is_grouped_and_verified():
    plan = client.post("/plan", json={"question": "Compare Chennai and Mumbai Q4 revenue"}).json()
    assert plan["group_by"]
    v = client.post("/verify", json={"plan": plan, "policy": CONFIRMED}).json()
    rows = v["grouped"]["ranking"]
    assert v["verified"] is True and [r["entity"] for r in rows] == ["Chennai", "Mumbai"]
    assert rows[0]["analyst_result"] == "53549309.97" and rows[1]["analyst_result"] == "42563940.59"
    assert rows[0]["conflicting_invoices"] == ["INV-1011"] and rows[0]["unsupported_rows"] > 0
    ex = client.post("/execute", json={"plan": plan, "policy": CONFIRMED}).json()
    assert "grouped" in ex
    assert client.post("/trust", json={"plan": plan, "policy": CONFIRMED}).status_code == 422
    assert client.post("/proof", json={"plan": plan, "policy": CONFIRMED}).status_code == 422


def test_rank_question_without_names_covers_every_entity():
    plan = client.post("/plan", json={"question": "Which branch had the highest Q4 revenue?"}).json()
    rows = client.post("/verify", json={"plan": plan, "policy": CONFIRMED}).json()["grouped"]["ranking"]
    assert [r["entity"] for r in rows] == ["Chennai", "Mumbai", "Bengaluru"]


def test_upload_never_silently_overwrites(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    f = {"file": ("mine.csv", b"a,b\n1,2\n")}
    assert client.post("/datasets/upload", files=f).status_code == 200
    assert client.post("/datasets/upload", files={"file": ("mine.csv", b"a,b\n9,9\n")}).status_code == 409
    assert (tmp_path / "mine.csv").read_bytes() == b"a,b\n1,2\n"
    assert client.post("/datasets/upload?overwrite=true", files={"file": ("mine.csv", b"a,b\n9,9\n")}).status_code == 200
    assert (tmp_path / "mine.csv").read_bytes() == b"a,b\n9,9\n"


def test_pdf_survives_markup_characters_and_shows_risks(tmp_path):
    bundle = {
        "proof_id": "p<1>", "answer": "1.00", "currency": "INR", "trust_decision": "VERIFIED_WITH_POLICY",
        "reasons": ["Invoice <INV&1> excluded"], "remaining_risks": ["a < b"],
        "impact": {"raw_total_before_cleaning": "2.00", "duplicate_effect": "-1.00", "conflict_effect": "0.00",
                   "refund_effect": "0.00", "verified_total": "1.00", "unsupported_currency_effect": "0.00",
                   "largest_monetary_risk": "x", "minimum_cleanup_recommendation": "y"},
        "sensitivity": {"materiality": "Low", "explanation": "fine"},
    }
    out = generate_audit_pdf(bundle, tmp_path / "r.pdf", "verified")
    assert out.read_bytes()[:4] == b"%PDF"
