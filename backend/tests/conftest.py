"""
Makes the test suite independent of the directory pytest is launched from.
The project is imported as the `backend` package, and several tests use paths
relative to the folder that contains `backend/`.
"""
import sys
from pathlib import Path

import pytest

PROJECT_PARENT = Path(__file__).resolve().parents[2]
if str(PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(PROJECT_PARENT))


@pytest.fixture(autouse=True)
def _run_from_project_parent(monkeypatch):
    monkeypatch.chdir(PROJECT_PARENT)


@pytest.fixture(autouse=True)
def _isolate_generated_files(monkeypatch, tmp_path):
    """Proof scripts and PDF reports produced by API tests go to a temp folder, not the project."""
    import backend.app.main as main
    monkeypatch.setattr(main, "ARTIFACTS_DIR", tmp_path / "artifacts")
    monkeypatch.setattr(main, "REPORTS_DIR", tmp_path / "artifacts" / "reports")
