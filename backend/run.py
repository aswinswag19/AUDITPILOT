"""
Start the API from anywhere:   python run.py
(Equivalent to `uvicorn backend.app.main:app` run from the folder above backend/.)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000)
