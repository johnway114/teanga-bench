"""Repository hygiene."""

from pathlib import Path

BANNED_NAME = "Blas" + " Bench"


def test_project_is_not_named_blas_bench():
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in root.rglob("*"):
        if path.is_dir() or any(part in {".git", ".venv", "__pycache__", "logs", "data", "samples"} for part in path.parts):
            continue
        if path.suffix not in {".py", ".md", ".yml", ".yaml", ".json", ".toml", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if BANNED_NAME in line and "Do not" not in line and "existing" not in line and "BANNED" not in line:
                offenders.append(f"{path.relative_to(root)}:{lineno}")
    assert offenders == []
