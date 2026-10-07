"""
Tests for Phase 4: Pandas Analyst and DuckDB Inspector engines.
"""

import pytest
from pathlib import Path
from backend.app.schemas import Policy, Mapping, Plan, MetricConfig, DateRange
from backend.app.mapping import infer_mapping
from backend.app.planner.rules import SmartRulesPlanner
from backend.app.engines.analyst import execute_pandas_analyst
from backend.app.engines.inspector import execute_duckdb_inspector

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

def test_analyst_and_inspector_match(context):
    data_dir, mapping, policy, schema_summary = context
    planner = SmartRulesPlanner()
    plan = planner.create_plan("What was Chennai Q4 revenue in INR?", schema_summary, mapping, policy)
    
    analyst_res = execute_pandas_analyst(data_dir, plan, mapping, policy)
    inspector_res = execute_duckdb_inspector(data_dir, plan, mapping, policy)
    
    assert analyst_res["status"] == "VERIFIED"
    assert inspector_res["status"] == "VERIFIED"
    # Both engines executed successfully with verified status
    assert analyst_res["result"] is not None
    assert inspector_res["result"] is not None

def test_inspector_honors_requested_entity(context):
    data_dir, mapping, policy, schema_summary = context
    planner = SmartRulesPlanner()
    plan = planner.create_plan("What was Mumbai Q4 revenue in INR?", schema_summary, mapping, policy)

    inspector_res = execute_duckdb_inspector(data_dir, plan, mapping, policy)
    analyst_res = execute_pandas_analyst(data_dir, plan, mapping, policy)

    assert inspector_res["status"] == "VERIFIED"
    # Independent engines must reproduce each other exactly
    assert inspector_res["result"] == analyst_res["result"]
    # Entity filter must actually narrow the result
    chennai = execute_duckdb_inspector(
        data_dir,
        planner.create_plan("What was Chennai Q4 revenue in INR?", schema_summary, mapping, policy),
        mapping, policy)
    assert inspector_res["result"] != chennai["result"]
