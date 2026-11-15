"""Find, load, and validate the JSONL datasets.

Full sets live in ``data/private/<suite>/<test>.jsonl`` (git-ignored). Public
samples live in ``samples/<suite>/<test>.jsonl``. A test with no private file
falls back to its public sample. One file is one test.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from teanga_bench.paths import REPO_ROOT

SCORINGS = ("accept_list", "tutor", "translation", "round_trip")
LANGUAGES = ("irish", "welsh", "scots-gaelic", "manx", "breton", "cornish", "english")
L1S = ("none", "portuguese", "spanish", "vietnamese", "japanese")
CEFR = ("A1", "A2", "B1", "B2", "C1", "C2")

COMMON_METADATA = (
    "suite",
    "test",
    "scoring",
    "language",
    "l1",
    "phenomenon",
    "cefr",
    "source",
    "source_id",
    "source_path",
    "licence",
    "evidence",
    "human_checked",
)
TUTOR_METADATA = (
    "learner_sentence",
    "has_error",
    "error_span",
    "correction",
    "accept_spans",
    "accept_corrections",
    "acceptable_sentences",
    "explanation_points",
    "real_learner_error",
)
TRANSLATION_METADATA = ("source_text", "source_lang", "target_lang", "references")
ROUND_TRIP_METADATA = ("source_text", "source_lang", "pivot_lang")


@dataclass(frozen=True)
class DatasetFile:
    suite: str
    test: str
    path: Path
    kind: str  # "full" or "public_sample"
    sample_path: Path | None  # the public sample file for this test, if any

    @property
    def name(self) -> str:
        return f"{self.suite}/{self.test}"


def _scan(directory: Path) -> dict[tuple[str, str], Path]:
    found: dict[tuple[str, str], Path] = {}
    if directory.is_dir():
        for path in sorted(directory.glob("*/*.jsonl")):
            found[(path.parent.name, path.stem)] = path
    return found


def discover(root: Path = REPO_ROOT) -> dict[tuple[str, str], DatasetFile]:
    """Every test with a dataset, preferring the private full set over the sample."""
    private = _scan(root / "data" / "private")
    samples = _scan(root / "samples")
    files: dict[tuple[str, str], DatasetFile] = {}
    for key in sorted(set(private) | set(samples)):
        full = private.get(key)
        files[key] = DatasetFile(
            suite=key[0],
            test=key[1],
            path=full or samples[key],
            kind="full" if full else "public_sample",
            sample_path=samples.get(key),
        )
    return files


def select(files: dict[tuple[str, str], DatasetFile], names: list[str] | None) -> list[DatasetFile]:
    """Pick tests by ``test`` or ``suite/test``. No names means every test."""
    if not names:
        return list(files.values())
    chosen: list[DatasetFile] = []
    for name in names:
        matches = [
            item for item in files.values() if name in {item.test, item.name}
        ]
        if not matches:
            known = ", ".join(sorted(item.name for item in files.values())) or "none found"
            raise KeyError(f"No dataset for test {name!r}. Known tests: {known}")
        for match in matches:
            if match not in chosen:
                chosen.append(match)
    return chosen


def read_items(path: Path) -> list[dict[str, Any]]:
    items = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{number} is not valid JSON: {exc}") from exc
    return items


def public_ids(dataset: DatasetFile) -> set[str]:
    """Ids of the items published in samples/ for this test."""
    if dataset.sample_path is None:
        return set()
    return {str(item["id"]) for item in read_items(dataset.sample_path) if "id" in item}


def _nonempty_strings(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) > 0
        and all(isinstance(entry, str) and entry.strip() for entry in value)
    )


def validate_item(item: dict[str, Any], suite: str, test: str) -> list[str]:
    """Problems with one item, as short strings."""
    problems: list[str] = []
    item_id = item.get("id")
    if not isinstance(item_id, str) or not item_id:
        return ["item has no string id"]
    for field in ("input", "target"):
        if not isinstance(item.get(field), str) or not item[field].strip():
            problems.append(f"{item_id}: {field} must be a non-empty string")
    meta = item.get("metadata")
    if not isinstance(meta, dict):
        return problems + [f"{item_id}: metadata is missing"]
    for field in COMMON_METADATA:
        if field not in meta:
            problems.append(f"{item_id}: metadata.{field} is missing")
    if meta.get("suite") != suite:
        problems.append(f"{item_id}: metadata.suite is {meta.get('suite')!r}, path says {suite!r}")
    if meta.get("test") != test:
        problems.append(f"{item_id}: metadata.test is {meta.get('test')!r}, path says {test!r}")
    scoring = meta.get("scoring")
    if scoring not in SCORINGS:
        problems.append(f"{item_id}: metadata.scoring {scoring!r} is not one of {', '.join(SCORINGS)}")
    if "language" in meta and meta["language"] not in LANGUAGES:
        problems.append(f"{item_id}: metadata.language {meta['language']!r} is not a known language")
    if "l1" in meta and meta["l1"] not in L1S:
        problems.append(f"{item_id}: metadata.l1 {meta['l1']!r} is not a known l1")
    if "cefr" in meta and meta["cefr"] is not None and meta["cefr"] not in CEFR:
        problems.append(f"{item_id}: metadata.cefr {meta['cefr']!r} is not A1..C2 or null")
    if "human_checked" in meta and not isinstance(meta["human_checked"], bool):
        problems.append(f"{item_id}: metadata.human_checked must be true or false")
    for field in ("phenomenon", "source", "source_id", "source_path", "licence", "evidence"):
        if field in meta and (not isinstance(meta[field], str) or not meta[field].strip()):
            problems.append(f"{item_id}: metadata.{field} must be a non-empty string")
    if scoring == "accept_list":
        problems += _validate_accept_list(item_id, item, meta)
    elif scoring == "tutor":
        problems += _validate_tutor(item_id, meta)
    elif scoring == "translation":
        problems += _validate_translation(item_id, item, meta)
    elif scoring == "round_trip":
        problems += _validate_round_trip(item_id, meta)
    return problems


def _validate_accept_list(item_id: str, item: dict[str, Any], meta: dict[str, Any]) -> list[str]:
    accept = meta.get("accept")
    if not _nonempty_strings(accept):
        return [f"{item_id}: metadata.accept must be a non-empty list of non-empty strings"]
    if item.get("target") not in accept:
        return [f"{item_id}: target is not in metadata.accept"]
    return []


def _validate_translation(item_id: str, item: dict[str, Any], meta: dict[str, Any]) -> list[str]:
    problems = [f"{item_id}: metadata.{f} is missing" for f in TRANSLATION_METADATA if f not in meta]
    if "references" in meta:
        if not _nonempty_strings(meta["references"]):
            problems.append(f"{item_id}: metadata.references must be a non-empty list of non-empty strings")
        elif item.get("target") not in meta["references"]:
            problems.append(f"{item_id}: target is not in metadata.references")
    for field in ("source_text", "source_lang", "target_lang"):
        if field in meta and (not isinstance(meta[field], str) or not meta[field].strip()):
            problems.append(f"{item_id}: metadata.{field} must be a non-empty string")
    return problems


def _validate_round_trip(item_id: str, meta: dict[str, Any]) -> list[str]:
    problems = [f"{item_id}: metadata.{f} is missing" for f in ROUND_TRIP_METADATA if f not in meta]
    for field in ROUND_TRIP_METADATA:
        if field in meta and (not isinstance(meta[field], str) or not meta[field].strip()):
            problems.append(f"{item_id}: metadata.{field} must be a non-empty string")
    return problems


def _validate_tutor(item_id: str, meta: dict[str, Any]) -> list[str]:
    problems = [f"{item_id}: metadata.{f} is missing" for f in TUTOR_METADATA if f not in meta]
    if problems:
        return problems
    learner = meta["learner_sentence"]
    sentences = meta["acceptable_sentences"]
    if not isinstance(learner, str) or not learner.strip():
        return [f"{item_id}: metadata.learner_sentence must be a non-empty string"]
    if not _nonempty_strings(sentences):
        return [f"{item_id}: metadata.acceptable_sentences must be a non-empty list of non-empty strings"]
    for field in ("accept_spans", "accept_corrections", "explanation_points"):
        if not isinstance(meta[field], list):
            problems.append(f"{item_id}: metadata.{field} must be a list")
    for field in ("has_error", "real_learner_error"):
        if not isinstance(meta[field], bool):
            problems.append(f"{item_id}: metadata.{field} must be true or false")
    if problems:
        return problems
    span, correction = meta["error_span"], meta["correction"]
    if meta["has_error"]:
        if not isinstance(span, str) or not span or span not in learner:
            problems.append(f"{item_id}: error_span must be a non-empty substring of learner_sentence")
        elif learner.replace(span, correction, 1) not in sentences:
            problems.append(f"{item_id}: replacing error_span with correction does not give an acceptable sentence")
        if span not in meta["accept_spans"]:
            problems.append(f"{item_id}: error_span is not in accept_spans")
        if correction not in meta["accept_corrections"]:
            problems.append(f"{item_id}: correction is not in accept_corrections")
        if learner in sentences:
            problems.append(f"{item_id}: the erroneous sentence is listed as acceptable")
    else:
        if sentences != [learner]:
            problems.append(f"{item_id}: a clean item must have acceptable_sentences == [learner_sentence]")
        if span or correction:
            problems.append(f"{item_id}: a clean item must have an empty error_span and correction")
    return problems


def validate_dataset_file(path: Path, suite: str, test: str) -> list[str]:
    try:
        items = read_items(path)
    except ValueError as exc:
        return [str(exc)]
    if not items:
        return [f"{path}: file has no items"]
    problems: list[str] = []
    seen: set[str] = set()
    for item in items:
        problems += validate_item(item, suite, test)
        item_id = item.get("id")
        if isinstance(item_id, str):
            if item_id in seen:
                problems.append(f"{item_id}: duplicate id in {suite}/{test}")
            seen.add(item_id)
    return problems


def validate_all(root: Path = REPO_ROOT) -> tuple[list[str], int]:
    """Validate every dataset file under ``root``. Returns (problems, files checked)."""
    problems: list[str] = []
    checked = 0
    for directory in (root / "data" / "private", root / "samples"):
        seen_ids: dict[str, str] = {}
        for (suite, test), path in sorted(_scan(directory).items()):
            checked += 1
            label = path.relative_to(root) if path.is_relative_to(root) else path
            problems += [f"{label}: {problem}" for problem in validate_dataset_file(path, suite, test)]
            for item in _safe_items(path):
                item_id = item.get("id")
                if isinstance(item_id, str):
                    other = seen_ids.get(item_id)
                    if other and other != f"{suite}/{test}":
                        problems.append(f"{label}: id {item_id} is also used in {other}")
                    seen_ids.setdefault(item_id, f"{suite}/{test}")
    if checked == 0:
        problems.append("no dataset files found under data/private/ or samples/")
    return problems, checked


def _safe_items(path: Path) -> list[dict[str, Any]]:
    try:
        return read_items(path)
    except ValueError:
        return []
