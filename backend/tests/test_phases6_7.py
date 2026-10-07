"""
Tests for Phases 6 & 7: AST guard, Proof generation, PDF reports, and FastAPI API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from backend.app.main import app
from backend.app.guard import validate_proof_script_ast
from backend.app.pdf_report import generate_audit_pdf

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_ast_guard_safe():
    safe_code = """
import pandas as pd
from decimal import Decimal
df = pd.read_csv("sales.csv")
print("RESULT=100.00 INR")
"""
    assert validate_proof_script_ast(safe_code) is True

def test_ast_guard_unsafe():
    unsafe_code = """
import os
os.system("echo hacked")
"""
    assert validate_proof_script_ast(unsafe_code) is False

def test_pdf_report_generation(tmp_path):
    pdf_path = tmp_path / "test_report.pdf"
    bundle = {"proof_id": "test_01", "answer": "100.00", "currency": "INR", "publishability": "INTERNAL_EXPLORATION_OK"}
    generated = generate_audit_pdf(bundle, pdf_path, "verified")
    assert generated.exists()
    assert generated.stat().st_size > 0
    with open(generated, "rb") as f:
        header = f.read(4)
        assert header == b"%PDF"

def test_api_profile_and_plan():
    res = client.post("/profile", json={"filename": "sales.csv"})
    assert res.status_code == 200
    assert "profile" in res.json()

    plan_res = client.post("/plan", json={"question": "What was Chennai Q4 revenue in INR?", "filename": "sales.csv"})
    assert plan_res.status_code == 200
    assert plan_res.json()["intent"] == "aggregate"
