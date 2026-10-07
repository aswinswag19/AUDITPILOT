"""
Phase 3: Refusal logic.
Generates structured refusal responses when questions have false premises, missing fields, or are unsupported.
"""

from typing import List, Optional
from backend.app.schemas import Plan, RefusalInfo

def create_refusal(reason: str, missing: Optional[List[str]] = None) -> Plan:
    return Plan(
        status="refused",
        intent="metadata",
        refusal=RefusalInfo(
            reason=reason,
            missing=missing or []
        )
    )

