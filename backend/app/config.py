"""
Phase 2: Application configuration loading.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _resolve_dir(env_name: str, default: Path) -> Path:
    """Resolve a directory from the environment; relative paths are anchored
    to the project root (not the current working directory)."""
    p = Path(os.getenv(env_name) or default)
    return (p if p.is_absolute() else BASE_DIR / p).resolve()


DATA_DIR = _resolve_dir("DATA_DIR", BASE_DIR / "data")
ARTIFACTS_DIR = _resolve_dir("ARTIFACTS_DIR", BASE_DIR / "artifacts")
REPORTS_DIR = _resolve_dir("REPORTS_DIR", ARTIFACTS_DIR / "reports")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_SECONDARY_MODEL = os.getenv("GROQ_SECONDARY_MODEL", "qwen/qwen3.8-27b")
GROQ_TIMEOUT_SECONDS = int(os.getenv("GROQ_TIMEOUT_SECONDS", "20"))
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "600"))
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0"))

