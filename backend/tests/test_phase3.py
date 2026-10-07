"""
Tests for Phase 3: Smart Rules Planner, Groq Fallback, Plan Validator, and Refusal.
"""

import pytest
from pathlib import Path
from backend.app.schemas import Policy, Mapping
from backend.app.mapping import infer_mapping
from backend.app.planner.rules import SmartRulesPlanner
from backend.app.planner.groq_planner import GroqPlanner
from backend.app.validator import validate_plan
from backend.app.refusal import create_refusal

@pytest.fixture
def context():
    data_dir = Path("./backend/data")
    mapping = infer_mapping(data_dir)
    policy = Policy()
    schema_summary = {
        "tables": ["sales.csv", "exchange_rates.csv", "branches.csv"],
        "entities": ["Chennai", "Mumbai", "Bengaluru"]
    }
    return data_dir, mapping, policy, schema_summary

def test_smart_rules_planner_q4(context):
    _, mapping, policy, schema_summary = context
    planner = SmartRulesPlanner()
    plan = planner.create_plan("What was Chennai Q4 revenue in INR?", schema_summary, mapping, policy)
    
    assert plan.status == "ready"
    assert plan.intent == "aggregate"
    assert plan.metric.agg == "sum"
    assert len(plan.filters) == 1

def test_refusal_profit(context):
    _, mapping, policy, schema_summary = context
    planner = SmartRulesPlanner()
    plan = planner.create_plan("What was profit for Chennai?", schema_summary, mapping, policy)
    
    assert plan.status == "refused"
    assert plan.refusal is not None
    assert "profit" in plan.refusal.reason.lower()

def test_groq_planner_fallback(context):
    _, mapping, policy, schema_summary = context
    # With no API key set, GroqPlanner should seamlessly fallback to smart rules planner
    planner = GroqPlanner()
    plan = planner.create_plan("Compare Chennai and Mumbai revenue", schema_summary, mapping, policy)
    
    assert plan.status == "ready"
    assert plan.intent == "compare"
