# AuditPilot: Proof-Carrying AI Data Analyst

AuditPilot is a proof-carrying AI data analyst for messy multi-table CSV business data. It answers supported business questions only when the answer can be proven.

## Architecture (Mermaid)

```mermaid
graph TD
    CSV[Uploaded CSV Tables] --> Profiler[Profiler & Schema Inference]
    Profiler --> Planner[Smart Rules / Groq Planner]
    Planner --> Validator[Plan Validator]
    Validator --> Analyst[Pandas Analyst Engine]
    Validator --> Inspector[DuckDB Inspector Engine]
    Analyst --> Trust[Trust & Contradiction Radar]
    Inspector --> Trust
    Trust --> Proof[Proof Bundle & AST Guard]
    Proof --> PDF[ReportLab PDF Reports]
```

## Setup & Commands

1. **Install backend requirements**:
   ```bash
   pip install -r backend/requirements.txt
   ```
2. **Generate deterministic datasets**:
   ```bash
   python -m backend.data_gen.generate_data
   python -m backend.data_gen.compute_ground_truth
   ```
3. **Run tests**:
   ```bash
   python -m pytest
   ```
4. **Start FastAPI backend**:
   ```bash
   uvicorn backend.app.main:app --reload --port 8000
   ```
