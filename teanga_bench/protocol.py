"""v1 and v2 are different protocols. Scores from one are not comparable with the other.

``methodology`` is an additive results field (``"v1"`` or ``"v2"``). It is not a
``schema_version`` bump. Files written before the field existed are v1 only when
they match the historical shape of the nine published v1 runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

V1 = "v1"
V2 = "v2"
METHODOLOGIES = (V1, V2)

# Retired in v2. A historical v1 run includes all three, plus the four core tests.
RETIRED_V1_TESTS = frozenset(
    {
        "blas/lesson_exercises",
        "blas/round_trip",
        "tonada/exercises",
    }
)

V1_NOTE = (
    "This is the archived v1 leaderboard: 7 tests, 3 epochs, provider-default reasoning, "
    "2,260 items. It is not comparable with v2."
)
V2_NOTE = (
    "This is the v2 leaderboard: 4 core tests, 1 epoch, low reasoning, 1,260 items. "
    "It is not comparable with the archived v1 leaderboard."
)
VERSION_NOTES = {V1: V1_NOTE, V2: V2_NOTE}

ARCHIVE_DIR = "v1-archive"
ZENODO_DOI = "10.5281/zenodo.24305705"
ZENODO_URL = f"https://doi.org/{ZENODO_DOI}"


def test_names(document: dict[str, Any]) -> set[str]:
    """``suite/test`` names recorded on a results document."""
    names: set[str] = set()
    config = document.get("config") or {}
    for name in config.get("tests") or []:
        if isinstance(name, str) and "/" in name:
            names.add(name)
    for suite, body in (document.get("suites") or {}).items():
        for test in (body.get("tests") or {}):
            names.add(f"{suite}/{test}")
    return names


def is_historical_v1(document: dict[str, Any]) -> bool:
    """The shape of the nine published v1 runs: 7 tests, 3 epochs, no reasoning setting.

    An explicit ``methodology`` field is not required. Site fixtures and other
    files that merely have ``epochs: 3`` do not match unless they also include
    the three retired v1 tests.
    """
    config = document.get("config") or {}
    if config.get("epochs") != 3 or "reasoning_effort" in config:
        return False
    names = test_names(document)
    return len(names) >= 7 and RETIRED_V1_TESTS <= names


def methodology_of(document: dict[str, Any]) -> str:
    """``v1`` or ``v2``. An explicit field wins; otherwise only the historical shape is v1."""
    explicit = document.get("methodology")
    if explicit in METHODOLOGIES:
        return str(explicit)
    if is_historical_v1(document):
        return V1
    return V2


def archive_runs_dir(results_dir: Path) -> Path:
    return results_dir / ARCHIVE_DIR / "runs"


def result_candidates(results_dir: Path, filename: str) -> list[Path]:
    """Places a results file may live, active v2 path first."""
    return [
        results_dir / "runs" / filename,
        archive_runs_dir(results_dir) / filename,
        results_dir / "mock" / filename,
        results_dir / filename,
    ]


def path_methodology(path: Path) -> str | None:
    """The protocol a destination path is reserved for, if the layout implies one."""
    parts = path.parts
    if ARCHIVE_DIR in parts:
        return V1
    if path.parent.name == "runs":
        return V2
    return None


def _read_run(path: Path) -> dict[str, Any] | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(document, dict) and "model" in document and "suites" in document:
        return document
    return None


def assert_compatible_destination(document: dict[str, Any], source: Path, dest: Path) -> None:
    """Refuse to write one protocol's rebuild over the other protocol's file or directory."""
    method = methodology_of(document)
    if dest.resolve() == source.resolve():
        return
    existing = _read_run(dest)
    if existing is not None and methodology_of(existing) != method:
        other = methodology_of(existing)
        raise ValueError(f"refusing to write a {method} reexport over a {other} file at {dest}")
    implied = path_methodology(dest)
    if implied is not None and implied != method:
        raise ValueError(f"refusing to write a {method} reexport to a {implied} path ({dest})")


def resolve_reexport_source(results_dir: Path, filename: str, output: Path | None) -> Path:
    """The file reexport should read.

    A lone archive file is that source, so a v1 model is not rewritten into
    ``results/runs/``. When both protocols exist, ``--output`` has to choose.
    """
    existing = [path for path in result_candidates(results_dir, filename) if path.is_file()]
    if output is not None and output.is_file():
        return output
    if len(existing) > 1:
        methods = {}
        for path in existing:
            document = _read_run(path)
            if document is not None:
                methods[path] = methodology_of(document)
        if len(set(methods.values())) > 1:
            raise ValueError(
                "both a v1 archive file and a v2 results/runs file exist for this model; "
                "pass --output to choose which file to update"
            )
    if existing:
        return existing[0]
    if output is not None:
        return output
    return result_candidates(results_dir, filename)[0]
