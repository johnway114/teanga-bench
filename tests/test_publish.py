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
    [({"run_kind": "mock"}, "mock run"), ({"status": "cost_cap_reached"}, "only complete runs"), ({"status": "incomplete"}, "only complete runs")],
)
def test_publish_refuses_mock_and_incomplete_runs(repo, kwargs, message):
    run = _write_run(repo, "a__model", fake_document("a/model", 0.7, **kwargs))
    head = _git(repo, "rev-parse", "HEAD")
    with pytest.raises(PublishError, match=message):
        publish_run(run, repo_root=repo, out=lambda _line: None)
    assert _git(repo, "rev-parse", "HEAD") == head
    assert not (repo / "site").exists()


def test_publish_refuses_files_outside_results_runs(repo, tmp_path):
    outside = tmp_path / "elsewhere.json"
    outside.write_text(json.dumps(fake_document("a/model", 0.7)), encoding="utf-8")
    with pytest.raises(PublishError, match="results/runs"):
        publish_run(outside, repo_root=repo, out=lambda _line: None)


def test_run_publish_refuses_mock_before_running(capsys):
    assert cli.main(["run", "--model", "mockllm/model", "--publish"]) == cli.EXIT_USAGE
    assert "refuses mock" in capsys.readouterr().err


def test_allowed_paths():
    assert allowed_path("site/blas/index.html")
    assert allowed_path("results/runs/a__b.json") and allowed_path("results/charts/x.svg")
    assert not allowed_path("data/private/blas/x.jsonl")
    assert not allowed_path("results/mock/x.json") and not allowed_path("teanga_bench/cli.py")
