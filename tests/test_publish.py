"""Publish flow against a temporary git repository and bare remote. Offline."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from site_fakes import fake_document

from teanga_bench import cli
from teanga_bench.publish import PublishError, allowed_path, publish_run


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    for key, value in {
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
        "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
    }.items():
        monkeypatch.setenv(key, value)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    _git(work, "config", "commit.gpgsign", "false")
    (work / ".gitignore").write_text("data/private/\n", encoding="utf-8")
    (work / "README.md").write_text("x\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "init")
    _git(work, "remote", "add", "origin", str(remote))
    _git(work, "push", "-q", "-u", "origin", "main")
    (work / "results" / "runs").mkdir(parents=True)
    return work


def _write_run(repo: Path, name: str, document: dict) -> Path:
    path = repo / "results" / "runs" / f"{name}.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_publish_commits_only_results_and_site_and_pushes(repo, tmp_path):
    run = _write_run(repo, "a__model", fake_document("a/model", 0.7))
    (repo / "notes.txt").write_text("unrelated work in progress\n", encoding="utf-8")
    lines: list[str] = []
    assert publish_run(run, repo_root=repo, out=lines.append) == 0

    files = _git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert files and all(allowed_path(path) for path in files)
    assert "results/runs/a__model.json" in files and "site/blas/index.html" in files
    assert "results/leaderboard.json" in files and "notes.txt" not in files
    assert _git(repo, "log", "-1", "--format=%s", "origin/main").strip() == "Publish results: a/model"
    assert (repo / "notes.txt").exists()  # untouched, still uncommitted
    assert "https://research.blasapp.com/" in lines and "https://research.tonadaapp.com/" in lines


def test_publish_refuses_staged_private_file(repo):
    run = _write_run(repo, "a__model", fake_document("a/model", 0.7))
    private = repo / "data" / "private" / "blas"
    private.mkdir(parents=True)
    (private / "morphology.jsonl").write_text('{"id": "secret"}\n', encoding="utf-8")
    _git(repo, "add", "-f", "data/private/blas/morphology.jsonl")
    head = _git(repo, "rev-parse", "HEAD")

    with pytest.raises(PublishError, match="data/private/blas/morphology.jsonl"):
        publish_run(run, repo_root=repo, out=lambda _line: None)
    assert _git(repo, "diff", "--cached", "--name-only") == ""  # everything unstaged
    assert _git(repo, "rev-parse", "HEAD") == head  # nothing committed


def test_publish_refuses_other_staged_paths(repo):
    run = _write_run(repo, "a__model", fake_document("a/model", 0.7))
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    with pytest.raises(PublishError, match="README.md"):
        publish_run(run, repo_root=repo, out=lambda _line: None)
    assert _git(repo, "diff", "--cached", "--name-only") == ""


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"run_kind": "mock"}, "mock run"),
        ({"status": "cost_cap_reached"}, "only complete runs"),
        ({"status": "incomplete"}, "only complete runs"),
        ({"dataset": "public_sample"}, "only full-set runs"),
    ],
)
def test_publish_refuses_mock_and_incomplete_runs(repo, kwargs, message):
    run = _write_run(repo, "a__model", fake_document("a/model", 0.7, **kwargs))
    head = _git(repo, "rev-parse", "HEAD")
    with pytest.raises(PublishError, match=message):
        publish_run(run, repo_root=repo, out=lambda _line: None)
    assert _git(repo, "rev-parse", "HEAD") == head
    assert not (repo / "site").exists()


def test_run_publish_refuses_public_sample_and_smoke_before_running(fixture_root, capsys):
    assert cli.main(["run", "--model", "openai/gpt-6-luna", "--data-root", str(fixture_root), "--publish"]) == cli.EXIT_USAGE
    assert "data/private/ is missing" in capsys.readouterr().err
    assert cli.main(["run", "--model", "openai/gpt-6-luna", "--limit", "2", "--publish"]) == cli.EXIT_USAGE
    assert "refuses smoke runs" in capsys.readouterr().err


def test_publish_refuses_files_outside_results_runs(repo, tmp_path):
    outside = tmp_path / "elsewhere.json"
    outside.write_text(json.dumps(fake_document("a/model", 0.7)), encoding="utf-8")
    with pytest.raises(PublishError, match="results/runs"):
        publish_run(outside, repo_root=repo, out=lambda _line: None)


def test_run_publish_refuses_mock_before_running(capsys):
    assert cli.main(["run", "--model", "mockllm/model", "--publish"]) == cli.EXIT_USAGE
    assert "refuses mock" in capsys.readouterr().err


def test_publish_v2_does_not_touch_the_v1_archive(repo):
    from test_cutover import _historical, _v2, _write

    archive = _write(
        repo / "results" / "v1-archive" / "runs",
        "google/gemini-4-hydrogen",
        _historical("google/gemini-4-hydrogen", 0.8647533673882336),
    )
    archive.with_suffix(".md").write_text("# v1\n", encoding="utf-8")
    chart = repo / "results" / "v1-archive" / "charts" / "suite-blas.svg"
    chart.parent.mkdir(parents=True)
    chart.write_text("<svg>v1</svg>\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in (repo / "results" / "v1-archive").rglob("*") if path.is_file()}
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "archive v1")
    run = _write(repo / "results" / "runs", "thinkingmachines/inkling-2-mini", _v2())
    assert publish_run(run, repo_root=repo, out=lambda _line: None) == 0
    after = {path: path.read_bytes() for path in (repo / "results" / "v1-archive").rglob("*") if path.is_file()}
    assert after == before
    committed = _git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert "results/runs/thinkingmachines__inkling-2-mini.json" in committed
    assert "results/v1-archive/runs/google__gemini-4-hydrogen.json" not in committed
    assert all(not path.startswith("data/private/") for path in committed)
    board = json.loads((repo / "results" / "leaderboard.json").read_text(encoding="utf-8"))
    assert [entry["model"] for entry in board["models"]] == ["thinkingmachines/inkling-2-mini"]
    v2_home = (repo / "site" / "blas" / "index.html").read_text(encoding="utf-8")
    assert "Inkling 2 Mini" in v2_home and "gemini-4-hydrogen" not in v2_home
    archived = (repo / "site" / "blas" / "v1" / "models" / "google-gemini-4-hydrogen.html").read_text(encoding="utf-8")
    legacy = (repo / "site" / "blas" / "models" / "google-gemini-4-hydrogen.html").read_text(encoding="utf-8")
    assert "86.5%" in archived and "86.5%" not in legacy
    assert "../v1/models/google-gemini-4-hydrogen.html" in legacy


def test_allowed_paths():
    assert allowed_path("site/blas/index.html")
    assert allowed_path("site/blas/v1/models/google-gemini-4-hydrogen.html")
    assert allowed_path("results/runs/a__b.json") and allowed_path("results/charts/x.svg")
    assert allowed_path("results/v1-archive/runs/google__gemini-4-hydrogen.json")
    assert allowed_path("results/v1-archive/leaderboard.json")
    assert allowed_path("results/v1-archive/charts/suite-blas.svg")
    assert allowed_path("vercel.json")
    assert not allowed_path("data/private/blas/x.jsonl")
    assert not allowed_path("results/mock/x.json") and not allowed_path("teanga_bench/cli.py")
