"""`teanga-bench validate` and the dataset rules."""

import json
import shutil

from teanga_bench import cli
from teanga_bench.datasets import validate_all, validate_item

from conftest import FIXTURE_ROOT


def _copy(tmp_path):
    root = tmp_path / "root"
    shutil.copytree(FIXTURE_ROOT, root)
    return root


def _lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _save(path, items):
    path.write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n", encoding="utf-8")


def test_fixtures_are_valid():
    problems, checked = validate_all(FIXTURE_ROOT)
    assert problems == [] and checked == 5


def test_cli_validate_exit_codes(tmp_path, capsys):
    assert cli.main(["validate", "--data-root", str(FIXTURE_ROOT)]) == 0
    empty = tmp_path / "empty"
    empty.mkdir()
    assert cli.main(["validate", "--data-root", str(empty)]) == 1


def test_duplicate_ids_are_reported(tmp_path):
    root = _copy(tmp_path)
    path = root / "samples" / "blas" / "mutations.jsonl"
    items = _lines(path)
    items.append(items[0])
    _save(path, items)
    assert any("fx-mut-00: duplicate id" in p for p in validate_all(root)[0])


def test_missing_required_metadata_is_reported(tmp_path):
    root = _copy(tmp_path)
    path = root / "samples" / "blas" / "mutations.jsonl"
    items = _lines(path)
    for field in ("evidence", "source_path", "human_checked"):
        del items[0]["metadata"][field]
    _save(path, items)
    problems = validate_all(root)[0]
    for field in ("evidence", "source_path", "human_checked"):
        assert any(f"metadata.{field} is missing" in p for p in problems)


def test_empty_accept_and_references_are_reported(tmp_path):
    root = _copy(tmp_path)
    path = root / "samples" / "blas" / "mutations.jsonl"
    items = _lines(path)
    items[0]["metadata"]["accept"] = []
    _save(path, items)
    path = root / "samples" / "blas" / "translation.jsonl"
    items = _lines(path)
    items[0]["metadata"]["references"] = [""]
    _save(path, items)
    problems = validate_all(root)[0]
    assert any("accept must be a non-empty list" in p for p in problems)
    assert any("references must be a non-empty list" in p for p in problems)


def test_tutor_edit_consistency_is_checked(tmp_path):
    root = _copy(tmp_path)
    path = root / "samples" / "blas" / "tutor.jsonl"
    items = _lines(path)
    items[0]["metadata"]["correction"] = "X"  # span C -> X does not give the gold sentence
    items[0]["metadata"]["accept_corrections"] = ["X"]
    items[1]["metadata"]["acceptable_sentences"] = ["Something else entirely."]  # clean item changed
    _save(path, items)
    problems = validate_all(root)[0]
    assert any("does not give an acceptable sentence" in p for p in problems)
    assert any("clean item must have acceptable_sentences" in p for p in problems)


def test_unknown_scoring_and_bad_values_are_reported():
    item = {
        "id": "x", "input": "q", "target": "a",
        "metadata": {"suite": "blas", "test": "t", "scoring": "mystery", "language": "klingon", "l1": "none",
                     "phenomenon": "p", "cefr": "Z9", "source": "s", "source_id": "i", "source_path": "p",
                     "licence": "l", "evidence": "e", "human_checked": "yes"},
    }
    problems = validate_item(item, "blas", "t")
    assert any("scoring" in p for p in problems)
    assert any("language" in p for p in problems)
    assert any("cefr" in p for p in problems)
    assert any("human_checked" in p for p in problems)


def test_no_item_count_ceiling(tmp_path):
    root = _copy(tmp_path)
    path = root / "samples" / "blas" / "mutations.jsonl"
    template = _lines(path)[0]
    items = []
    for n in range(500):
        item = json.loads(json.dumps(template))
        item["id"] = f"many-{n}"
        items.append(item)
    _save(path, items)
    assert validate_all(root)[0] == []
