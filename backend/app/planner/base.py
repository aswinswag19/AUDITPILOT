"""
Phase 3: Base planner protocol.
Defines the interface for creating analysis plans from natural language questions.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from backend.app.schemas import Plan, Policy, Mapping

class BasePlanner(ABC):
    @abstractmethod
    def create_plan(self, question: str, schema_summary: Dict[str, Any], mapping: Mapping, policy: Policy) -> Plan:
        pass

