"""
Phase 3: Groq-backed planner (optional, with fallback to smart rules).
"""

from typing import Dict, Any
from backend.app.schemas import Plan, Policy, Mapping
from backend.app.planner.rules import SmartRulesPlanner
from backend.app.config import GROQ_API_KEY
from backend.app.groq_client import query_groq_planners
from backend.app.validator import validate_plan

class GroqPlanner:
    def __init__(self):
        self.rules_planner = SmartRulesPlanner()

    def create_plan(self, question: str, schema_summary: Dict[str, Any], mapping: Mapping, policy: Policy) -> Plan:
        # Local planning owns executable semantics: it is deterministic, schema-aware,
        # and keeps the two verification engines in agreement. The LLM is only used
        # when the local planner cannot resolve a question into a ready plan.
        rules_plan = self.rules_planner.create_plan(question, schema_summary, mapping, policy)
        if rules_plan.status == "ready":
            return rules_plan

        comparison = self.compare_models(question, schema_summary, mapping)
        selected = next((candidate for candidate in comparison if candidate.get("selected") and candidate.get("plan")), None)
        if selected:
            return Plan(**selected["plan"])
        return rules_plan

    def create_plan_with_comparison(
        self,
        question: str,
        schema_summary: Dict[str, Any],
        mapping: Mapping,
        policy: Policy,
    ) -> tuple[Plan, list[Dict[str, Any]]]:
        """Plan once and return the exact model comparison used for fallback selection."""
        rules_plan = self.rules_planner.create_plan(question, schema_summary, mapping, policy)
        comparison = self.compare_models(question, schema_summary, mapping)
        if rules_plan.status == "ready":
            return rules_plan, comparison
        selected = next((candidate for candidate in comparison if candidate.get("selected") and candidate.get("plan")), None)
        if selected:
            selected["used_for_planning"] = True
        return (Plan(**selected["plan"]) if selected else rules_plan), comparison

    def compare_models(self, question: str, schema_summary: Dict[str, Any], mapping: Mapping) -> list[Dict[str, Any]]:
        """Return validated, scored candidates without changing execution authority."""
        valid_entities = schema_summary.get("entities", [])
        candidates = []
        for model, response in query_groq_planners(question, schema_summary).items():
            raw_plan = response["plan"]
            elapsed_ms = response["latency_ms"]
            if not raw_plan:
                reason = "Groq API key is not configured." if not GROQ_API_KEY else "No usable plan was returned; check the backend log for the model error."
                candidates.append({"model": model, "status": "unavailable", "score": 0, "optimized_score": 0, "latency_ms": elapsed_ms, "reasons": [reason]})
                continue
            try:
                plan = validate_plan(Plan(**raw_plan), schema_summary, mapping, valid_entities)
                score, reasons = self._score_plan(plan)
                candidates.append({
                    "model": model,
                    "status": plan.status,
                    "score": score,
                    "optimized_score": score,
                    "latency_ms": elapsed_ms,
                    "reasons": reasons,
                    "plan": plan.model_dump(),
                })
            except Exception as exc:
                candidates.append({"model": model, "status": "invalid", "score": 0, "optimized_score": 0, "latency_ms": elapsed_ms, "reasons": [f"Plan rejected: {type(exc).__name__}."]})

        available = [candidate for candidate in candidates if candidate["status"] != "unavailable"]
        if available:
            best = max(available, key=lambda candidate: (candidate["score"], -candidate["latency_ms"]))
            for candidate in candidates:
                candidate["selected"] = candidate is best and candidate["score"] > 0
                if candidate["selected"]:
                    candidate["selection_reason"] = "Highest validated plan quality; latency used as the tie-breaker."
                elif candidate["status"] != "unavailable":
                    candidate["selection_reason"] = "Not selected because another validated plan ranked higher."
        return candidates

    @staticmethod
    def _score_plan(plan: Plan) -> tuple[int, list[str]]:
        score = 0
        reasons = []
        if plan.status == "ready":
            score += 50
            reasons.append("Ready to execute")
        elif plan.status == "needs_clarification":
            score += 20
            reasons.append("Needs clarification")
        else:
            reasons.append("Correctly refused")
        if plan.tables:
            score += 15
            reasons.append("Uses a known table")
        if plan.metric and plan.metric.column:
            score += 15
            reasons.append("Names a mapped metric")
        if plan.intent in {"compare", "rank"} and plan.group_by:
            score += 10
            reasons.append("Includes a grouping strategy")
        elif plan.intent == "aggregate" and (plan.filters or plan.date_range):
            score += 10
            reasons.append("Captures question scope")
        return score, reasons

