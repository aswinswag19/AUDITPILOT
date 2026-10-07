"""
Phase 6: Proof bundle and proof script generation.
Generates proof bundles and standalone proof scripts verified by the AST guard.
"""

import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Dict, Any
from backend.app.schemas import Plan, Policy, Mapping
from backend.app.guard import validate_proof_script_ast

def _run_proof_script(script_path: Path) -> str:
    """Execute the generated script in a separate interpreter and return its RESULT value."""
    proc = subprocess.run([sys.executable, str(script_path)], capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise ValueError(f"Proof script failed to run: {proc.stderr.strip()[-300:]}")
    m = re.search(r"RESULT=(\S+)", proc.stdout)
    if not m:
        raise ValueError("Proof script did not print a RESULT line.")
    return m.group(1)


def generate_proof_bundle(
    data_dir: Path,
    artifacts_dir: Path,
    plan: Plan,
    policy: Policy,
    mapping: Mapping,
    analyst_res: Dict[str, Any],
    inspector_res: Dict[str, Any]
) -> Dict[str, Any]:
    """Builds the proof bundle. Raises ValueError if the proof script is unsafe or does not
    independently reproduce the verified answer."""
    proof_id = f"proof_{uuid.uuid4().hex[:8]}"
    script_content = analyst_res.get("generated_code")
    if not script_content:
        raise ValueError("No proof script was generated for this plan.")
    if not validate_proof_script_ast(script_content):
        raise ValueError("Proof script rejected by the AST safety guard.")

    script_path = artifacts_dir / f"{proof_id}.py"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    reproduced = _run_proof_script(script_path)
    if reproduced != str(analyst_res.get("result")):
        raise ValueError(f"Proof script reproduced {reproduced}, expected {analyst_res.get('result')}.")

    return {
        "proof_id": proof_id,
        "answer": analyst_res.get("result"),
        "currency": policy.target_currency,
        "script_reproduced_result": reproduced,
        "analyst_status": analyst_res.get("status"),
        "inspector_status": inspector_res.get("status"),
        "proof_script_path": str(script_path),
        "source_rows_path": analyst_res.get("source_rows_path"),
        "guard_passed": True
    }

