"""
Tests for Phase 1: Deterministic Data Generator & Ground Truth computation.
"""

import os
import hashlib
import json
from pathlib import Path
import pytest

from backend.data_gen.generate_data import generate_datasets
from backend.data_gen.compute_ground_truth import compute_ground_truth

@pytest.fixture
def temp_data_dirs(tmp_path):
    dir1 = tmp_path / "run1"
    dir2 = tmp_path / "run2"
    
    generate_datasets(dir1)
    generate_datasets(dir2)
    
    compute_ground_truth(dir1)
    compute_ground_truth(dir2)
    
    return dir1, dir2

def hash_file(filepath: Path) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def test_determinism(temp_data_dirs):
    dir1, dir2 = temp_data_dirs
    files = ["sales.csv", "exchange_rates.csv", "branches.csv", "executive_summary.csv", "ground_truth.json"]
    
    for filename in files:
        f1 = dir1 / filename
        f2 = dir2 / filename
        assert f1.exists()
        assert f2.exists()
        assert hash_file(f1) == hash_file(f2), f"File {filename} is not deterministic across runs!"

def test_dataset_b_determinism(temp_data_dirs):
    dir1, dir2 = temp_data_dirs
    b_files = ["orders.csv", "customers.csv", "refunds.csv", "exchange_rates_b.csv", "dataset_b_mapping.json"]
    
    for filename in b_files:
        f1 = dir1 / "dataset_b" / filename
        f2 = dir2 / "dataset_b" / filename
        assert f1.exists()
        assert f2.exists()
        assert hash_file(f1) == hash_file(f2), f"Dataset B file {filename} is not deterministic!"

def test_ground_truth_content(temp_data_dirs):
    dir1, _ = temp_data_dirs
    gt_path = dir1 / "ground_truth.json"
    assert gt_path.exists()
    
    with open(gt_path, "r", encoding="utf-8") as f:
        gt = json.load(f)
        
    assert gt["exact_duplicate_count"] == 4
    assert gt["conflicting_duplicate_count"] == 1
    assert gt["missing_date_count"] == 2
    assert gt["unsupported_currency_count"] >= 2
    assert "chennai_calendar_q4_revenue_inr" in gt
    assert gt["executive_summary_discrepancy_q4"] == "99999999.00"

def test_dataset_b_mapping_unit_multiplier(temp_data_dirs):
    dir1, _ = temp_data_dirs
    mapping_path = dir1 / "dataset_b" / "dataset_b_mapping.json"
    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)
        
    assert "unit_multiplier" in mapping
    assert mapping["unit_multiplier"] == 10
    assert mapping["refunds_table"] == "refunds.csv"
