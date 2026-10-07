"""
Phase 3: Groq client wrapper (optional at runtime).
Handles Groq API calls for structured plan generation with automatic fallback.
"""

import json
from typing import Optional, Dict, Any
from backend.app.config import GROQ_API_KEY, GROQ_MODEL, GROQ_TIMEOUT_SECONDS, GROQ_TEMPERATURE, GROQ_MAX_TOKENS

def query_groq_planner(prompt: str, schema_summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not GROQ_API_KEY:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        
        system_msg = (
            "You are AuditPilot's planning assistant. Never calculate numbers. Never write "
            "Python, SQL, shell, or executable code. Return only valid JSON matching the "
            "Plan schema. Use only supplied schemas, mappings, actual entities, actual "
            "periods, and allowed intents. If ambiguous return needs_clarification. If "
            "unsupported/missing/false premise return refused. Never invent values."
        )
        
        user_msg = f"Question: {prompt}\nSchema Summary: {json.dumps(schema_summary)}"
        
        response = client.chat.completions.create(
            model=GROQ_MODEL,
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
    except Exception:
        return None

