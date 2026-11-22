"""v1 stays published and citable; v2 is a separate board."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from teanga_bench.cost import CostGuard
from teanga_bench.export import build_document
from teanga_bench.leaderboard import write_leaderboard
from teanga_bench.paths import REPO_ROOT
from teanga_bench.protocol import V1, V2, methodology_of
from teanga_bench.runner import RunError, refuse_protocol_overwrite
from teanga_bench.site import build_site, legacy_model_redirects, slugify
from teanga_bench.site_charts import pct

# Scores of the nine published v1 runs. A cutover may add methodology: "v1"
# and nothing else: these overall scores stay put.
V1_SCORES = {
    "anthropic/claude-fable-5.2": 0.8751778855199442,
    "google/gemini-4-hydrogen": 0.8647533673882336,
    "openai/gpt-6-astra": 0.8600413946808138,
    "google/gemini-4-argon": 0.8443041573912234,
    "moonshotai/kimi-k3.1-pro": 0.8167358958243633,
    "deepseek/deepseek-v4.1-flash-1017": 0.8100263331374072,
    "openai/gpt-6-luna": 0.7797924159821337,
    "anthropic/claude-haiku-5.5": 0.7214651742283115,
    "qwen/qwen3.8-flash": 0.6852968401846565,
}
RETIRED = (
    "blas/lesson_exercises",
    "blas/morphology",
    "blas/translation",
    "blas/round_trip",
    "blas/tutor_accuracy",
    "tonada/exercises",
    "tonada/tutor_accuracy",
)


def _historical(model: str = "google/gemini-4-hydrogen", score: float = 0.5) -> dict:
    suites: dict = {}
    for name in RETIRED:
        suite, test = name.split("/")
        suites.setdefault(suite, {"overall": {"score": score, "ci95": [score - 0.1, score + 0.1], "n_tests": 1, "n_items": 10}, "tests": {}})
        suites[suite]["tests"][test] = {
            "dataset": "full", "status": "complete", "score": score, "ci95": [score - 0.1, score + 0.1],
            "n_items": 10, "epochs": 3, "cost_usd": 0.1,
        }
    return {
        "schema_version": "2.2.0",
        "benchmark": "teanga-bench",
        "generated_at": "2026-11-16T00:00:00+00:00",
        "run_kind": "live",
        "status": "complete",
        "model": {"id": model, "family": model.split("/")[0]},
        "config": {"epochs": 3, "tests": list(RETIRED)},
        "judges": [],
        "explanation_status": "not_scored_judge_unavailable",
        "cost": {"total_usd": 1.0, "cap_usd": 5.0, "candidate_usd": 1.0, "judge_usd": 0.0, "cap_reached": False},
        "overall": {"score": score, "ci95": [score - 0.1, score + 0.1], "n_tests": 7, "n_items": 2260},
        "suites": suites,
    }


def _v2(model: str = "thinkingmachines/inkling-2-mini", score: float = 0.4) -> dict:
    document = _historical(model, score)
    document["methodology"] = V2
    document["config"] = {"epochs": 1, "reasoning_effort": "low", "tests": ["blas/morphology", "tonada/tutor_accuracy"]}
    document["suites"] = {
        "blas": {"overall": {"score": score, "ci95": [0.3, 0.5], "n_tests": 1, "n_items": 10}, "tests": {
            "morphology": {"dataset": "full", "status": "complete", "score": score, "ci95": [0.3, 0.5], "n_items": 10, "epochs": 1, "cost_usd": 0.2},
        }},
        "tonada": {"overall": {"score": score, "ci95": [0.3, 0.5], "n_tests": 1, "n_items": 10}, "tests": {
            "tutor_accuracy": {"dataset": "full", "status": "complete", "score": score, "ci95": [0.3, 0.5], "n_items": 10, "epochs": 1, "cost_usd": 0.2},
        }},
    }
    document["overall"]["n_tests"] = 2
    document["overall"]["n_items"] = 20
    return document


def _write(directory: Path, model: str, document: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{model.replace('/', '__')}.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_methodology_stamp_wins_and_historical_shape_is_v1():
    historical = _historical()
    assert "methodology" not in historical
    assert methodology_of(historical) == V1
    historical["methodology"] = V1
    assert methodology_of(historical) == V1
    stamped_v2 = dict(historical)
    stamped_v2["methodology"] = V2
    assert methodology_of(stamped_v2) == V2  # explicit field wins over the old shape
    guard = CostGuard(max_cost=Decimal("1"))
    fresh = build_document(
        run_kind="live",
        status="complete",
        incomplete_reason=None,
        model={"id": "thinkingmachines/inkling-2-mini", "family": "thinkingmachines"},
        config={"epochs": 1, "max_tokens": {"candidate": 16000}, "reasoning_effort": "low"},
        judges=[],
        judge_info={},
        explanation_status="scored",
        guard=guard,
        outcomes=[],
        blocks_not_run=[],
        started_at="2026-11-22T00:00:00+00:00",
    )
    assert fresh["methodology"] == V2


def test_mixed_directory_writes_two_boards_and_charts_do_not_wipe(tmp_path):
    runs = tmp_path / "runs"
    _write(runs, "google/gemini-4-hydrogen", _historical("google/gemini-4-hydrogen", 0.86))
    _write(runs, "thinkingmachines/inkling-2-mini", _v2())
    out = tmp_path / "out"
    board = write_leaderboard(runs, out)
    assert board["methodology"] == V2
    assert [m["model"] for m in board["models"]] == ["thinkingmachines/inkling-2-mini"]
    archived = json.loads((out / "v1-split" / "leaderboard.json").read_text(encoding="utf-8"))
    assert archived["methodology"] == V1
    assert [m["model"] for m in archived["models"]] == ["google/gemini-4-hydrogen"]
    assert archived["models"][0]["overall"]["score"] == 0.86
    v1_chart = (out / "v1-split" / "charts" / "score-vs-cost.svg").read_text(encoding="utf-8")
    write_leaderboard(runs, out)  # again: v2 chart wipe must leave the v1 chart
    assert (out / "v1-split" / "charts" / "score-vs-cost.svg").read_text(encoding="utf-8") == v1_chart
    assert "gemini-4-hydrogen" not in (out / "leaderboard.md").read_text(encoding="utf-8")
    assert "gemini-4-hydrogen" in (out / "v1-split" / "leaderboard.md").read_text(encoding="utf-8")


def test_published_v1_archive_keeps_the_nine_scores_off_the_v2_board():
    archive = REPO_ROOT / "results" / "v1-archive" / "runs"
    files = sorted(archive.glob("*.json"))
    assert len(files) == 9
    found = {}
    for path in files:
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["methodology"] == V1
        assert document["schema_version"] == "2.2.0"
        assert document["status"] == "complete" and document["run_kind"] == "live"
        assert document["config"]["epochs"] == 3
        assert "reasoning_effort" not in document["config"]
        assert document["overall"]["n_items"] == 2260
        assert path.with_suffix(".md").is_file()
        found[document["model"]["id"]] = document["overall"]["score"]
    assert found == V1_SCORES
    v1_board = json.loads((REPO_ROOT / "results" / "v1-archive" / "leaderboard.json").read_text(encoding="utf-8"))
    assert v1_board["methodology"] == V1
    assert {m["model"]: m["overall"]["score"] for m in v1_board["models"]} == V1_SCORES
    v2_board = json.loads((REPO_ROOT / "results" / "leaderboard.json").read_text(encoding="utf-8"))
    assert v2_board["methodology"] == V2
    assert v2_board["models"] == []
    assert not list((REPO_ROOT / "results" / "runs").glob("*.json"))


def test_site_keeps_v1_urls_and_leaves_v2_empty(tmp_path):
    out = tmp_path / "site"
    runs = {}
    for path in (REPO_ROOT / "results" / "v1-archive" / "runs").glob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        runs[document["model"]["id"]] = document
    summary = build_site(REPO_ROOT / "results", out, repo_root=REPO_ROOT)
    assert summary["suites"]["blas"]["ranked"] == 0
    assert summary["archive"]["blas"]["ranked"] == 9
    assert summary["archive"]["tonada"]["ranked"] == 9
    redirects = []
    for suite, host in (("blas", "https://research.blasapp.com"), ("tonada", "https://research.tonadaapp.com")):
        v2 = json.loads((out / suite / "data" / "leaderboard.json").read_text(encoding="utf-8"))
        v1 = json.loads((out / suite / "v1" / "data" / "leaderboard.json").read_text(encoding="utf-8"))
        assert v2["methodology"] == V2 and v2["models"] == []
        assert {m["model"] for m in v1["models"]} == set(V1_SCORES)
        home = (out / suite / "index.html").read_text(encoding="utf-8")
        assert "v2 leaderboard" in home and 'href="./v1/"' in home
        assert "not comparable" in home
        assert "10.5281/zenodo.24305705" in home
        archive_home = (out / suite / "v1" / "index.html").read_text(encoding="utf-8")
        assert "v1 (archived)" in archive_home and "not comparable" in archive_home
        method = (out / suite / "methodology.html").read_text(encoding="utf-8")
        assert "v1 (archived)" in method and "not comparable" in method
        for model in v1["models"]:
            expected = runs[model["model"]]["suites"][suite]["overall"]["score"]
            assert model["overall"]["score"] == expected
            slug = slugify(model["model"])
            legacy = out / suite / "models" / f"{slug}.html"
            archived = out / suite / "v1" / "models" / f"{slug}.html"
            assert legacy.is_file() and archived.is_file()
            legacy_html = legacy.read_text(encoding="utf-8")
            target = f"../v1/models/{slug}.html"
            assert f'url={target}' in legacy_html
            assert f'href="{target}"' in legacy_html
            assert f"{host}/v1/models/{slug}" in legacy_html
            page = archived.read_text(encoding="utf-8")
            assert model["model"] in page and pct(expected) in page
            assert pct(expected) not in legacy_html  # the old URL does not carry a swapped score
            redirects.append((suite, slug))
        assert (out / suite / "v1" / "models" / "google-gemini-4-hydrogen.html").is_file()
    rules = {(rule["source"], rule["destination"]) for rule in legacy_model_redirects(
        {"blas": [slugify(m) for m in V1_SCORES], "tonada": [slugify(m) for m in V1_SCORES]}
    )}
    assert ("/models/google-gemini-4-hydrogen", "/v1/models/google-gemini-4-hydrogen") in rules
    assert len(redirects) == 18


def test_a_model_with_both_versions_links_the_pages_and_keeps_the_v2_url(tmp_path):
    results = tmp_path / "results"
    _write(results / "v1-archive" / "runs", "google/gemini-4-hydrogen", _historical("google/gemini-4-hydrogen", 0.86))
    _write(results / "runs", "google/gemini-4-hydrogen", _v2("google/gemini-4-hydrogen", 0.42))
    out = tmp_path / "site"
    build_site(results, out, repo_root=tmp_path / "repo")
    v2 = (out / "blas" / "models" / "google-gemini-4-hydrogen.html").read_text(encoding="utf-8")
    v1 = (out / "blas" / "v1" / "models" / "google-gemini-4-hydrogen.html").read_text(encoding="utf-8")
    assert "42.0%" in v2 and "86.0%" in v1
    assert 'href="../v1/models/google-gemini-4-hydrogen.html"' in v2
    assert 'href="../../models/google-gemini-4-hydrogen.html"' in v1
    assert "http-equiv=\"refresh\"" not in v2
    assert "86.0%" not in v2 and "42.0%" not in v1


def test_run_refuses_to_overwrite_v1_or_write_into_the_archive(tmp_path):
    path = tmp_path / "runs" / "google__gemini-4-hydrogen.json"
    _write(path.parent, "google/gemini-4-hydrogen", _historical())
    with pytest.raises(RunError, match="v1"):
        refuse_protocol_overwrite(path, resume=False)
    refuse_protocol_overwrite(path, resume=True)  # continuing that file is the same protocol
    archive = tmp_path / "v1-archive" / "runs" / "new.json"
    archive.parent.mkdir(parents=True)
    archive.write_text("{}", encoding="utf-8")
    with pytest.raises(RunError, match="archive"):
        refuse_protocol_overwrite(archive, resume=False)

