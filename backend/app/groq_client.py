"""
Phase 3: Groq client wrapper (optional at runtime).
Handles Groq API calls for structured plan generation with automatic fallback.
"""

import json
import logging
from time import perf_counter
from typing import Optional, Dict, Any
from backend.app.config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_SECONDARY_MODEL,
    GROQ_TIMEOUT_SECONDS,
    GROQ_TEMPERATURE,
    GROQ_MAX_TOKENS,
)

logger = logging.getLogger(__name__)

def query_groq_planner(
    prompt: str,
    schema_summary: Dict[str, Any],
    model: str = GROQ_MODEL,
) -> Optional[Dict[str, Any]]:
    if not GROQ_API_KEY:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        
        system_msg = (
            "You are AuditPilot's planning assistant. Never calculate numbers. Never write "
            "Python, SQL, shell, or executable code. Return only valid JSON matching the "
            "Plan schema. Use only supplied schemas, mappings, actual entities, actual "
            "periods, columns, and allowed intents. For files without an amount column, "
            "use count for row/record questions and refuse monetary questions. If ambiguous "
            "return needs_clarification. If unsupported/missing/false premise return refused. "
            "Never invent values."
        )
        
        user_msg = f"Question: {prompt}\nSchema Summary: {json.dumps(schema_summary)}"
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            temperature=GROQ_TEMPERATURE,
            max_tokens=GROQ_MAX_TOKENS,
            timeout=GROQ_TIMEOUT_SECONDS,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as exc:
        logger.warning("Groq planner request failed for model %s: %s", model, exc)
        return None


def query_groq_planners(prompt: str, schema_summary: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Ask both configured models the same planning question for comparison."""
    results = {}
    for model in dict.fromkeys((GROQ_MODEL, GROQ_SECONDARY_MODEL)):
        started = perf_counter()
        results[model] = {
            "plan": query_groq_planner(prompt, schema_summary, model),
            "latency_ms": round((perf_counter() - started) * 1000, 1),
        }
    return results

