"""
Phase 3: Groq-backed planner (optional, with fallback to smart rules).
"""

from typing import Dict, Any, Optional
from backend.app.schemas import Plan, Policy, Mapping
from backend.app.planner.rules import SmartRulesPlanner
from backend.app.groq_client import query_groq_planner
from backend.app.validator import validate_plan

class GroqPlanner:
    def __init__(self):
        self.rules_planner = SmartRulesPlanner()

    def create_plan(self, question: str, schema_summary: Dict[str, Any], mapping: Mapping, policy: Policy) -> Plan:
        groq_json = query_groq_planner(question, schema_summary)
        if groq_json:
            try:
                plan = Plan(**groq_json)
                valid_entities = schema_summary.get("entities", [])
                validated = validate_plan(plan, schema_summary, mapping, valid_entities)
                return validated
            except Exception:
                pass
        
        # Fallback to smart rules
        return self.rules_planner.create_plan(question, schema_summary, mapping, policy)

