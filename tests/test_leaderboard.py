"""Leaderboard and charts from result files."""

import json

import pytest
import xml.dom.minidom

from teanga_bench.leaderboard import load_runs, write_leaderboard
from teanga_bench.report import build_report, summary_sentences


def _stat(score, n=10, tests=2):
    return {"score": score, "ci95": [max(0.0, score - 0.1), min(1.0, score + 0.1)], "n_tests": tests, "n_items": n}


PAIR = ["deepseek/deepseek-v4.1-flash-1017", "qwen/qwen3.8-flash"]


def fake_run(model, score, cost, status="complete", irish=None, run_kind="live", suite="blas", judges=None, explanation=None, expl_status="scored"):
    irish = score if irish is None else irish
    block = {
        "suite": suite, "test": "mutations", "scoring": "accept_list", "dataset": "full", "status": status,
        "incomplete_reason": None, "n_items": 10, "n_items_dataset": 10, "epochs": 3, "consistency": 0.9,
        "score": score, "ci95": [score - 0.05, score + 0.05], "cost_usd": cost, "cost_per_correct_usd": 0.01,
        "failure_examples": [],
    }
    judges = PAIR if judges is None else judges
    expl = {"status": expl_status, "score": None, "ci95": None, "label": "judge-marked, not human-validated",
            "judge_agreement": None, "judge_failures": 0}
    if expl_status == "scored":
        e = score if explanation is None else explanation
        expl = {**expl, "status": "scored", "score": e, "ci95": [e - 0.1, e + 0.1]}
    tutor = {
        **block, "test": "tutor", "scoring": "tutor",
        "tutor": {"judges": judges, "explanation": expl, "headline": "rule-only",
                  "components": {"found": 0.5, "fixed": 0.5, "no_overcorrection": 0.5}},
    }
    overall = {**_stat(score), "by_language": {"irish": _stat(irish), "welsh": _stat(score)}}
    return {
        "schema_version": "2.0.0", "benchmark": "teanga-bench", "generated_at": "2026-11-15T00:00:00+00:00",
        "run_kind": run_kind, "status": status,
        "model": {"id": model, "family": model.split("/")[0]},
        "config": {"epochs": 3},
        "cost": {"total_usd": cost, "cap_usd": 5.0, "candidate_usd": cost, "judge_usd": 0.0, "cap_reached": False},
        "overall": overall if status == "complete" else None,
        "judges": judges, "explanation_status": expl_status,
        "suites": {suite: {"overall": _stat(score), "tests": {"mutations": block, "tutor": tutor}}},
    }


def _write(runs_dir, name, document):
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{name}.json").write_text(json.dumps(document), encoding="utf-8")


def test_leaderboard_from_two_result_files(tmp_path):
    runs, out = tmp_path / "runs", tmp_path / "out"
    _write(runs, "a__low", fake_run("a/low", 0.40, 0.10))
    _write(runs, "b__high", fake_run("b/high", 0.80, 0.50, irish=0.9))
    board = write_leaderboard(runs, out)

    assert [m["model"] for m in board["models"]] == ["b/high", "a/low"]
    assert [m["rank"] for m in board["models"]] == [1, 2]
    saved = json.loads((out / "leaderboard.json").read_text(encoding="utf-8"))
    assert saved["models"][0]["overall"]["score"] == 0.80
    assert saved["models"][0]["languages"]["irish"]["score"] == 0.9
    markdown = (out / "leaderboard.md").read_text(encoding="utf-8")
    assert "b/high" in markdown and "a/low" in markdown and "charts/suite-blas.svg" in markdown

    charts = {p.name for p in (out / "charts").glob("*.svg")}
    assert charts == {"suite-blas.svg", "language-irish.svg", "language-welsh.svg", "score-vs-cost.svg", "explanation.svg"}
    for name in charts:
        svg = (out / "charts" / name).read_text(encoding="utf-8")
        xml.dom.minidom.parseString(svg)  # well-formed
        assert 'fill="#ffffff"' in svg and 'fill="#1a1a1a"' in svg  # light background, dark text
        assert "b/high" in svg and "a/low" in svg
    bars = (out / "charts" / "suite-blas.svg").read_text(encoding="utf-8")
    assert "<line" in bars  # whiskers and grid
    assert "80.0%" in bars


def test_incomplete_and_mock_runs_are_not_ranked_or_charted(tmp_path):
    runs, out = tmp_path / "runs", tmp_path / "out"
    _write(runs, "ok", fake_run("a/ok", 0.5, 0.1))
    _write(runs, "capped", fake_run("c/capped", 0.9, 4.9, status="cost_cap_reached"))
    _write(runs, "mock", fake_run("mockllm/model", 0.1, 0.0, run_kind="mock"))
    (runs / "notes.json").write_text("{}", encoding="utf-8")
    board = write_leaderboard(runs, out)
    by_model = {m["model"]: m for m in board["models"]}
    assert set(by_model) == {"a/ok", "c/capped"}
    assert by_model["c/capped"]["rank"] is None and by_model["c/capped"]["ranked"] is False
    assert any("mock" in item for item in board["skipped"])
    svg = (out / "charts" / "suite-blas.svg").read_text(encoding="utf-8")
    assert "a/ok" in svg and "c/capped" not in svg
    assert "cost_cap_reached" in (out / "leaderboard.md").read_text(encoding="utf-8")


def test_mock_runs_can_be_included_on_request(tmp_path):
    runs = tmp_path / "runs"
    _write(runs, "mock", fake_run("mockllm/model", 0.1, 0.0, run_kind="mock"))
    assert load_runs(runs)[0] == []
    assert len(load_runs(runs, include_mock=True)[0]) == 1


def test_public_sample_runs_are_not_ranked_or_charted(tmp_path):
    runs, out = tmp_path / "runs", tmp_path / "out"
    full = fake_run("a/full", 0.7, 0.2)
    sample = fake_run("b/sample", 0.95, 0.05)
    for suite in sample["suites"].values():
        for block in suite["tests"].values():
            block["dataset"] = "public_sample"
    _write(runs, "a__full", full)
    _write(runs, "b__sample", sample)
    board = write_leaderboard(runs, out)
    by_model = {m["model"]: m for m in board["models"]}
    assert by_model["a/full"]["ranked"] is True and by_model["a/full"]["rank"] == 1
    assert by_model["b/sample"]["ranked"] is False and by_model["b/sample"]["rank"] is None
    svg = (out / "charts" / "suite-blas.svg").read_text(encoding="utf-8")
    assert "a/full" in svg and "b/sample" not in svg


def test_empty_runs_directory_still_writes_a_valid_leaderboard(tmp_path):
    board = write_leaderboard(tmp_path / "none", tmp_path / "out")
    assert board["models"] == []
    xml.dom.minidom.parseString((tmp_path / "out" / "charts" / "score-vs-cost.svg").read_text(encoding="utf-8"))


def test_report_summary_is_three_to_five_sentences():
    document = fake_run("a/low", 0.4, 0.1)
    document["config"]["epochs"] = 3
    sentences = summary_sentences(document)
    assert 3 <= len(sentences) <= 5
    assert all(sentence.endswith(".") for sentence in sentences)
    assert "a/low" in build_report(document)


def test_explanation_is_shown_only_for_runs_with_the_current_judge_pair(tmp_path):
    runs, out = tmp_path / "runs", tmp_path / "out"
    _write(runs, "same", fake_run("a/same", 0.6, 0.1, explanation=0.55))
    _write(runs, "other", fake_run("b/other", 0.7, 0.1, explanation=0.99, judges=["x/judge1", "y/judge2"]))
    _write(runs, "family", fake_run("deepseek/d", 0.5, 0.1, expl_status="not_scored_same_family_as_judge"))
    _write(runs, "gone", fake_run("c/gone", 0.4, 0.1, expl_status="not_scored_judge_unavailable"))
    board = write_leaderboard(runs, out)
    assert board["current_judges"] == PAIR
    by_model = {m["model"]: m for m in board["models"]}
    assert by_model["b/other"]["judges"] == ["x/judge1", "y/judge2"]
    same = by_model["a/same"]["explanation"]["blas/tutor"]
    assert same["score"] == 0.55 and same["ci95"] == pytest.approx([0.45, 0.65])
    assert (same["comparable"], same["reason"], same["judges"]) == (True, None, PAIR)
    other = by_model["b/other"]["explanation"]["blas/tutor"]
    assert other["score"] is None and other["comparable"] is False
    assert other["reason"] == "judge_pair_differs_from_current_config"
    assert by_model["deepseek/d"]["explanation"]["blas/tutor"]["reason"] == "not_scored_same_family_as_judge"
    assert by_model["c/gone"]["explanation"]["blas/tutor"]["reason"] == "not_scored_judge_unavailable"

    markdown = (out / "leaderboard.md").read_text(encoding="utf-8")
    assert "55.0%" in markdown and "99.0%" not in markdown
    assert "not comparable: judge_pair_differs_from_current_config" in markdown
    svg = (out / "charts" / "explanation.svg").read_text(encoding="utf-8")
    xml.dom.minidom.parseString(svg)
    assert "a/same" in svg and "b/other" not in svg and "99.0%" not in svg
    assert "not human-validated" in svg
