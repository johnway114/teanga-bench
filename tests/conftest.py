"""Shared test helpers. No test calls a model provider or the network."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from teanga_bench.context import set_context

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "data_root"


@pytest.fixture(autouse=True)
def _clear_context():
    yield
    set_context(None)


@pytest.fixture
def fixture_root() -> Path:
    return FIXTURE_ROOT


@pytest.fixture
def private_root(tmp_path: Path) -> Path:
    """A data root with a PRIVATE full set for blas/mutations: the public sample
    items plus two private-only items that must never appear in public output."""
    root = tmp_path / "root"
    shutil.copytree(FIXTURE_ROOT / "samples", root / "samples")
    import json

    sample_lines = (FIXTURE_ROOT / "samples" / "blas" / "mutations.jsonl").read_text(encoding="utf-8").splitlines()
    template = json.loads(sample_lines[0])
    extra = []
    for n in range(2):
        item = json.loads(json.dumps(template))
        item["id"] = f"private-only-{n}"
        item["input"] = f"PRIVATE PROMPT {n} zzqq. Reply with the answer on one line, in this exact form:\nANSWER: <answer>\n"
        item["target"] = f"private-answer-{n}"
        item["metadata"]["accept"] = [f"private-answer-{n}"]
        extra.append(json.dumps(item, ensure_ascii=False))
    private = root / "data" / "private" / "blas"
    private.mkdir(parents=True)
    (private / "mutations.jsonl").write_text("\n".join(sample_lines + extra) + "\n", encoding="utf-8")
    return root
