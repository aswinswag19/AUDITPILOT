"""
Phase 7: FastAPI application entry point.
Exposes endpoints for health check, dataset upload, profiling, planning, execution, verification, trust, proof, and reports.
"""

import re
import uuid
from pathlib import Path
from typing import Dict, Any, List
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.app.config import DATA_DIR, ARTIFACTS_DIR, REPORTS_DIR
from backend.app.schemas import Policy, Mapping, Plan
from backend.app.mapping import infer_mapping, list_entities, latest_year
from backend.app.grouping import is_grouped, execute_grouped
from backend.app.profiler import profile_dataset
from backend.app.planner.groq_planner import GroqPlanner
from backend.app.engines.analyst import execute_pandas_analyst
from backend.app.engines.inspector import execute_duckdb_inspector
from backend.app.trust import compute_trust_decision
from backend.app.impact import compute_impact
from backend.app.sensitivity import compute_sensitivity
from backend.app.contradictions import check_contradictions
from backend.app.proof import generate_proof_bundle
from backend.app.guard import validate_proof_script_ast
from backend.app.pdf_report import generate_audit_pdf
from backend.app.currency import currency_check
from backend.app.preflight import plan_problems

app = FastAPI(title="AuditPilot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_transaction_mapping(mapping: Mapping) -> None:
    required = {
        "key_column": mapping.key_column,
        "date_column": mapping.date_column,
        "entity_column": mapping.entity_column,
        "amount_column": mapping.amount_column,
    }
    missing = [name for name, column in required.items() if not column]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "DATASET_MAPPING_FAILED",
                "message": "The CSV does not contain the columns needed for analysis.",
                "missing_fields": missing,
            },
        )

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "AuditPilot API"}

@app.post("/datasets/upload")
async def upload_dataset(file: UploadFile = File(...), overwrite: bool = False):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Strip any directory components (blocks path traversal like "../x.csv")
    safe_name = Path((file.filename or "").replace("\\", "/")).name
    if not safe_name or not safe_name.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv uploads are supported.")
    file_path = DATA_DIR / safe_name
    if file_path.exists() and not overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"{safe_name} already exists. Rename the file, or upload with ?overwrite=true to replace it.")
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    mapping = infer_mapping(DATA_DIR, safe_name)
    return {
        "dataset_id": str(uuid.uuid4()),
        "filename": safe_name,
        "mapping": mapping.model_dump()
    }

class ProfileRequest(BaseModel):
    filename: str = "sales.csv"

@app.post("/profile")
def profile_endpoint(req: ProfileRequest):
    mapping = infer_mapping(DATA_DIR, req.filename)
    _require_transaction_mapping(mapping)
    profile = profile_dataset(DATA_DIR, mapping)
    entities = list_entities(DATA_DIR, mapping)
    examples = ["What were the total sales?", "How many sales were recorded?"]
    if entities:
        examples.append(f"What were the total sales for {entities[0]}?")
    if len(entities) >= 2:
        examples.append(f"Which {mapping.entity_column} sold more: {entities[0]} or {entities[1]}?")
    return {"mapping": mapping.model_dump(), "profile": profile, "examples": examples}

class PlanRequest(BaseModel):
    question: str
    filename: str = "sales.csv"
    policy: Policy = Policy()

@app.post("/plan")
def plan_endpoint(req: PlanRequest):
    mapping = infer_mapping(DATA_DIR, req.filename)
    _require_transaction_mapping(mapping)
    profile = profile_dataset(DATA_DIR, mapping)
    schema_summary = {"tables": [req.filename], "entities": list_entities(DATA_DIR, mapping)}
    year = latest_year(DATA_DIR, mapping, req.policy.date_format)
    if year:
        schema_summary["default_year"] = year
    planner = GroqPlanner()
    plan = planner.create_plan(req.question, schema_summary, mapping, req.policy)
    out = plan.model_dump()
    if plan.status == "ready":
        # Tells the client up front which currency questions must be answered before this plan can run.
        out["currency_confirmation"] = currency_check(DATA_DIR, plan, mapping, req.policy)
    return out

class ExecuteRequest(BaseModel):
    plan: Plan
    filename: str = "sales.csv"
    policy: Policy = Policy()

def _preflight(plan: Plan, mapping: Mapping, policy: Policy) -> None:
    """Refuse to compute until the plan is valid and the user has confirmed the currencies in scope."""
    found = plan_problems(DATA_DIR, plan, mapping)
    if found["problems"]:
        raise HTTPException(status_code=422, detail={"error": "INVALID_PLAN", **found})
    cur = currency_check(DATA_DIR, plan, mapping, policy)
    if cur["needs_confirmation"]:
        raise HTTPException(status_code=409, detail={"error": "CURRENCY_CONFIRMATION_REQUIRED", **cur})


def _require_single_value(plan: Plan):
    if is_grouped(plan):
        raise HTTPException(
            status_code=422,
            detail="Trust and proof apply to a single figure. Ask about one entity, or use /verify for the comparison.")


@app.post("/currency/check")
def currency_check_endpoint(req: ExecuteRequest):
    """Which currencies in this plan's scope still need confirming, and the questions to ask the user."""
    mapping = infer_mapping(DATA_DIR, req.filename)
    _require_transaction_mapping(mapping)
    found = plan_problems(DATA_DIR, req.plan, mapping)
    if found["problems"]:
        raise HTTPException(status_code=422, detail={"error": "INVALID_PLAN", **found})
    return currency_check(DATA_DIR, req.plan, mapping, req.policy)


@app.post("/impact")
def impact_endpoint(req: ExecuteRequest):
    _require_single_value(req.plan)
    mapping = infer_mapping(DATA_DIR, req.filename)
    _require_transaction_mapping(mapping)
    _preflight(req.plan, mapping, req.policy)
    analyst_res = execute_pandas_analyst(DATA_DIR, req.plan, mapping, req.policy, export_source_rows=False)
    return compute_impact(req.plan, req.policy, mapping, analyst_res)


@app.post("/sensitivity")
def sensitivity_endpoint(req: ExecuteRequest):
    _require_single_value(req.plan)
    mapping = infer_mapping(DATA_DIR, req.filename)
    _require_transaction_mapping(mapping)
    _preflight(req.plan, mapping, req.policy)
    analyst_res = execute_pandas_analyst(DATA_DIR, req.plan, mapping, req.policy, export_source_rows=False)
    if analyst_res.get("status") != "VERIFIED":
        raise HTTPException(status_code=409, detail=analyst_res.get("reason") or "No verified result to analyse.")
    return compute_sensitivity(req.plan, req.policy, mapping, analyst_res, DATA_DIR)


@app.post("/execute")
def execute_endpoint(req: ExecuteRequest):
    mapping = infer_mapping(DATA_DIR, req.filename)
    _require_transaction_mapping(mapping)
    _preflight(req.plan, mapping, req.policy)
    if is_grouped(req.plan):
        return {"grouped": execute_grouped(DATA_DIR, req.plan, mapping, req.policy)}
    analyst_res = execute_pandas_analyst(DATA_DIR, req.plan, mapping, req.policy)
    inspector_res = execute_duckdb_inspector(DATA_DIR, req.plan, mapping, req.policy)
    return {"analyst": analyst_res, "inspector": inspector_res}

@app.post("/verify")
def verify_endpoint(req: ExecuteRequest):
    mapping = infer_mapping(DATA_DIR, req.filename)
    _require_transaction_mapping(mapping)
    _preflight(req.plan, mapping, req.policy)
    if is_grouped(req.plan):
        grouped = execute_grouped(DATA_DIR, req.plan, mapping, req.policy)
        return {"verified": grouped["all_verified"], "grouped": grouped}
    analyst_res = execute_pandas_analyst(DATA_DIR, req.plan, mapping, req.policy)
    inspector_res = execute_duckdb_inspector(DATA_DIR, req.plan, mapping, req.policy)
    match = analyst_res.get("result") == inspector_res.get("result") and analyst_res.get("status") == "VERIFIED"
    return {"verified": match, "analyst": analyst_res, "inspector": inspector_res}

@app.post("/trust")
def trust_endpoint(req: ExecuteRequest):
    _require_single_value(req.plan)
    mapping = infer_mapping(DATA_DIR, req.filename)
    _require_transaction_mapping(mapping)
    _preflight(req.plan, mapping, req.policy)
    analyst_res = execute_pandas_analyst(DATA_DIR, req.plan, mapping, req.policy)
    inspector_res = execute_duckdb_inspector(DATA_DIR, req.plan, mapping, req.policy)
    profile = profile_dataset(DATA_DIR, mapping)
    contradiction = check_contradictions(DATA_DIR, mapping, analyst_res, plan=req.plan, policy=req.policy)
    trust = compute_trust_decision(analyst_res, inspector_res, profile, contradiction)
    trust["contradiction"] = contradiction
    trust["unsupported_in_scope"] = analyst_res.get("unsupported_in_scope")
    return trust

@app.post("/proof")
def proof_endpoint(req: ExecuteRequest):
    _require_single_value(req.plan)
    mapping = infer_mapping(DATA_DIR, req.filename)
    _require_transaction_mapping(mapping)
    _preflight(req.plan, mapping, req.policy)
    analyst_res = execute_pandas_analyst(DATA_DIR, req.plan, mapping, req.policy)
    inspector_res = execute_duckdb_inspector(DATA_DIR, req.plan, mapping, req.policy)
    if inspector_res.get("status") != "VERIFIED":
        raise HTTPException(status_code=409, detail="Proof bundle not allowed unless Inspector status is VERIFIED.")
    if analyst_res.get("status") != "VERIFIED" or analyst_res.get("result") != inspector_res.get("result"):
        raise HTTPException(
            status_code=409,
            detail=f"Proof bundle not allowed: engine results disagree (Analyst={analyst_res.get('result')}, Inspector={inspector_res.get('result')}).",
        )
    try:
        bundle = generate_proof_bundle(DATA_DIR, ARTIFACTS_DIR, req.plan, req.policy, mapping, analyst_res, inspector_res)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=f"Proof could not be issued: {e}")
    profile = profile_dataset(DATA_DIR, mapping)
    contradiction = check_contradictions(DATA_DIR, mapping, analyst_res, plan=req.plan, policy=req.policy)
    trust = compute_trust_decision(analyst_res, inspector_res, profile, contradiction)
    bundle.update({
        "trust_decision": trust["trust_decision"],
        "publishability": trust["publishability"],
        "reasons": trust["reasons"],
        "remaining_risks": trust["remaining_risks"],
        "contradiction": contradiction,
        "conversion": analyst_res.get("conversion"),
        "impact": compute_impact(req.plan, req.policy, mapping, analyst_res),
        "sensitivity": compute_sensitivity(req.plan, req.policy, mapping, analyst_res, DATA_DIR),
    })
    return bundle

class ReportRequest(BaseModel):
    proof_bundle: Dict[str, Any]
    report_type: str = "verified"

@app.post("/reports/generate")
def generate_report(req: ReportRequest):
    if req.report_type not in ("verified", "refusal", "blocked"):
        raise HTTPException(status_code=422, detail="report_type must be one of: verified, refusal, blocked.")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_id = str(uuid.uuid4())[:8]
    pdf_filename = f"auditpilot_{req.report_type}_{report_id}.pdf"
    pdf_path = REPORTS_DIR / pdf_filename
    generate_audit_pdf(req.proof_bundle, pdf_path, req.report_type)
    return {"report_id": report_id, "report_type": req.report_type, "download_url": f"/reports/{report_id}/pdf"}

@app.get("/reports/{report_id}/pdf")
def download_pdf(report_id: str):
    # Safe lookup in REPORTS_DIR avoiding traversal / glob injection
    if not re.fullmatch(r"[0-9a-f]{8}", report_id):
        raise HTTPException(status_code=404, detail="Report PDF not found.")
    for pdf_file in REPORTS_DIR.glob(f"*_{report_id}.pdf"):
        if pdf_file.exists():
            return FileResponse(pdf_file, media_type="application/pdf", filename=pdf_file.name)
    raise HTTPException(status_code=404, detail="Report PDF not found.")

