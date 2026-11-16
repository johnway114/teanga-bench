"""Repository paths that stay valid under an editable install."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "config" / "models.yaml"
RESULTS = REPO_ROOT / "results"
RUNS = RESULTS / "runs"
LOGS = REPO_ROOT / "logs"

# Dataset builders in scripts/ still write here until they are replaced.
SUITES = REPO_ROOT / "suites"


def safe_name(model: str) -> str:
    """A model id as a file or folder name: ``openai/gpt-6-luna`` -> ``openai__gpt-6-luna``."""
    return model.replace("/", "__")
