"""
Tests for Phase 2: Schemas, Policy, Mapping inference, and Profiler.
"""

import pytest
from pathlib import Path
from backend.app.schemas import Policy, Mapping, Plan
from backend.app.mapping import infer_mapping
from backend.app.profiler import profile_dataset

@pytest.fixture
def data_dir():
    return Path("./backend/data")

def test_default_policy():
    policy = Policy()
    assert policy.target_currency == "INR"
    assert policy.duplicate == "keep_first_by_key"
    assert policy.calendar == "calendar_quarters"

def test_mapping_inference(data_dir):
    mapping = infer_mapping(data_dir)
    assert mapping.transactions_table == "sales.csv"
    assert mapping.key_column == "invoice_id"
    assert mapping.date_column == "order_date"
    assert mapping.amount_column == "amount"
    assert mapping.currency_column == "currency"

def test_profiler(data_dir):
    mapping = infer_mapping(data_dir)
    profile = profile_dataset(data_dir, mapping)
    assert "quality_score" in profile
    assert profile["rows"] > 0
    assert profile["exact_duplicate_groups"] >= 4
    assert profile["conflicting_duplicate_groups"] >= 1
    assert len(profile["unsupported_currencies"]) > 0

def test_dataset_b_mapping_and_profiling(data_dir):
    db_dir = data_dir / "dataset_b"
    if db_dir.exists():
        mapping = infer_mapping(data_dir, transactions_filename="dataset_b/orders.csv")
        assert mapping.unit_multiplier == 10.0
        profile = profile_dataset(data_dir, mapping)
        assert profile["rows"] > 0
