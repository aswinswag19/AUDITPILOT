"""
Regression tests for: entity discovery, unsupported-currency reporting,
real contradiction computation, engine/ground-truth agreement, and API hardening.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas import Policy
from backend.app.mapping import infer_mapping, list_entities
from backend.app.planner.rules import SmartRulesPlanner
from backend.app.engines.analyst import execute_pandas_analyst
from backend.app.engines.inspector import execute_duckdb_inspector
from backend.app.contradictions import check_contradictions
from backend.app.trust import compute_trust_decision

DATA = Path("./backend/data")


def _plan(question, mapping, policy, entities=None):
    entities = entities if entities is not None else list_entities(DATA, mapping)
    return SmartRulesPlanner().create_plan(question, {"entities": entities}, mapping, policy)


def test_entities_come_from_data():
    ents = list_entities(DATA, infer_mapping(DATA))
    assert ents == ["Bengaluru", "Chennai", "Mumbai"]  # case/space variants merged


def test_planner_uses_discovered_entities_not_hardcoded_ones():
    m, p = infer_mapping(DATA), Policy()
    plan = _plan("What was Q4 revenue for Pune?", m, p, entities=["Pune", "Chennai"])
    assert plan.filters and plan.filters[0]["value"] == "Pune"
    # A name merely contained in another word must not match
    plan = _plan("What was Q4 revenue for Chennaiville?", m, p, entities=["Chennai"])
    assert plan.filters == []


def test_engines_match_independent_ground_truth():
    m, p = infer_mapping(DATA), Policy()
    gt = json.loads((DATA / "ground_truth.json").read_text())
    plan = _plan("What was Chennai Q4 revenue in INR?", m, p)
    a = execute_pandas_analyst(DATA, plan, m, p)
    i = execute_duckdb_inspector(DATA, plan, m, p)
    assert a["result"] == i["result"] == gt["chennai_calendar_q4_revenue_inr"]


def test_unsupported_currency_rows_are_listed_not_hidden():
    m, p = infer_mapping(DATA), Policy()
    gt = json.loads((DATA / "ground_truth.json").read_text())
    plan = _plan("What was Chennai Q4 revenue in INR?", m, p)
    a = execute_pandas_analyst(DATA, plan, m, p)
    u = a["unsupported_in_scope"]
    assert u["count"] == gt["chennai_q4_unsupported_currency_rows"] > 0
    assert set(u["by_currency"]) == {"EUR"}
    assert any("exchange rate" in line for line in a["cleaning_log"])


def test_trust_flags_unsupported_rows_and_never_says_ready_for_publication():
    m, p = infer_mapping(DATA), Policy()
    plan = _plan("What was Chennai Q4 revenue in INR?", m, p)
    a = execute_pandas_analyst(DATA, plan, m, p)
    i = execute_duckdb_inspector(DATA, plan, m, p)
    consistent = {"status": "CONSISTENT"}
    t = compute_trust_decision(a, i, {}, consistent)
    assert t["trust_decision"] == "VERIFIED_WITH_POLICY"
    assert t["publishability"] == "MANAGEMENT_REVIEW_REQUIRED"
    assert any("unsupported currency" in r for r in t["reasons"])


def test_trust_blocks_when_engine_results_disagree():
    t = compute_trust_decision({"status": "VERIFIED", "result": "1.00"},
                               {"status": "VERIFIED", "result": "2.00"}, {}, {})
    assert t["trust_decision"] == "BLOCKED"


def test_contradiction_is_computed_from_data():
    m, p = infer_mapping(DATA), Policy()
    plan = _plan("What was Chennai Q4 revenue in INR?", m, p)
    a = execute_pandas_analyst(DATA, plan, m, p)
    gt = json.loads((DATA / "ground_truth.json").read_text())
    c = check_contradictions(DATA, m, a, plan=plan, policy=p)
    assert c["status"] == "CONTRADICTION_DETECTED"
    assert "company-wide" in c["compared_scope"]
    assert c["compared_verified_result"] == gt["calendar_q4_total_inr"]
    expected = Decimal("99999999.00") - Decimal(gt["calendar_q4_total_inr"])
    assert Decimal(c["difference"]) == expected


def test_contradiction_consistent_when_summary_matches(tmp_path):
    import shutil
    d = tmp_path / "data"
    shutil.copytree(DATA, d)
    m, p = infer_mapping(d), Policy()
    gt = json.loads((d / "ground_truth.json").read_text())
    (d / "executive_summary.csv").write_text(
        f"quarter,reported_revenue_inr,source\nQ4_2025,{gt['calendar_q4_total_inr']},test\n")
    plan = _plan("What was Q4 revenue for Mumbai?", m, p)
    a = execute_pandas_analyst(d, plan, m, p)
    assert check_contradictions(d, m, a, plan=plan, policy=p)["status"] == "CONSISTENT"


def test_contradiction_not_comparable_without_summary_table():
    # Dataset B has no summary table: must not crash or invent numbers
    m = infer_mapping(DATA, "orders.csv")
    c = check_contradictions(DATA, m, {"result": "100.00"})
    assert c["status"] == "NOT_COMPARABLE"


def test_contradiction_does_not_clobber_source_rows_export():
    m, p = infer_mapping(DATA), Policy()
    plan = _plan("What was Chennai Q4 revenue in INR?", m, p)
    a = execute_pandas_analyst(DATA, plan, m, p)
    before = Path(a["source_rows_path"]).read_bytes()
    check_contradictions(DATA, m, a, plan=plan, policy=p)
    assert Path(a["source_rows_path"]).read_bytes() == before

# What a user answers to the currency questions when they accept the data as it is.
CONFIRMED = {"currency_map": {"USD": "USD", "EUR": "EUR"}, "conversion_basis": "transaction_date"}


def test_api_trust_proof_report_flow_and_hardening():
    c = TestClient(app)
    plan = c.post("/plan", json={"question": "What was Q4 revenue for Mumbai?"}).json()
    assert plan["filters"][0]["value"] == "Mumbai"
    t = c.post("/trust", json={"plan": plan, "policy": CONFIRMED}).json()
    assert t["trust_decision"] == "VERIFIED_WITH_POLICY"
    assert t["contradiction"]["status"] == "CONTRADICTION_DETECTED"
    proof = c.post("/proof", json={"plan": plan, "policy": CONFIRMED})
    assert proof.status_code == 200
    rep = c.post("/reports/generate", json={"proof_bundle": proof.json()})
    assert rep.status_code == 200
    assert c.get(rep.json()["download_url"]).headers["content-type"] == "application/pdf"
    assert c.post("/reports/generate", json={"proof_bundle": {}, "report_type": "../../x"}).status_code == 422
    assert c.get("/reports/*/pdf").status_code == 404
    assert c.post("/datasets/upload", files={"file": ("x.py", b"1")}).status_code == 400


def test_dataset_b_trust_does_not_crash():
    c = TestClient(app)
    plan = c.post("/plan", json={"question": "total revenue", "filename": "orders.csv"}).json()
    r = c.post("/trust", json={"plan": plan, "filename": "orders.csv", "policy": CONFIRMED})
    assert r.status_code == 200
