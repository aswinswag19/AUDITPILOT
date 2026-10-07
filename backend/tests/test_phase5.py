"""
Tests for Phase 5: Trust, Impact, Sensitivity, and Contradictions.
"""

import pytest
from pathlib import Path
from backend.app.schemas import Policy, Mapping
from backend.app.mapping import infer_mapping
from backend.app.profiler import profile_dataset
from backend.app.planner.rules import SmartRulesPlanner
from backend.app.engines.analyst import execute_pandas_analyst
from backend.app.engines.inspector import execute_duckdb_inspector
from backend.app.impact import compute_impact
from backend.app.sensitivity import compute_sensitivity
from backend.app.contradictions import check_contradictions
from backend.app.trust import compute_trust_decision

@pytest.fixture
def context():
    data_dir = Path("./backend/data")
    mapping = infer_mapping(data_dir)
    policy = Policy()
    schema_summary = {"tables": ["sales.csv"], "entities": ["Chennai"]}
    return data_dir, mapping, policy, schema_summary

def test_phase5_engines_and_trust(context):
    data_dir, mapping, policy, schema_summary = context
    planner = SmartRulesPlanner()
    plan = planner.create_plan("What was Chennai Q4 revenue in INR?", schema_summary, mapping, policy)
    
    analyst_res = execute_pandas_analyst(data_dir, plan, mapping, policy)
    inspector_res = execute_duckdb_inspector(data_dir, plan, mapping, policy)
    profile = profile_dataset(data_dir, mapping)
    
    impact = compute_impact(plan, policy, mapping, analyst_res)
    sensitivity = compute_sensitivity(plan, policy, mapping, analyst_res)
    contradiction = check_contradictions(data_dir, mapping, analyst_res)
    trust = compute_trust_decision(analyst_res, inspector_res, profile, contradiction)
    
    assert impact["verified_total"] is not None
    assert sensitivity["base_result"] is not None
    assert contradiction["status"] == "CONTRADICTION_DETECTED"
    assert trust["trust_decision"] == "VERIFIED_WITH_POLICY"
    assert trust["publishability"] == "MANAGEMENT_REVIEW_REQUIRED"
