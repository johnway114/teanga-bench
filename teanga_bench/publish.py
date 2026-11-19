"""Publish one finished run: rebuild the leaderboard and site, commit, push.

Only the results and the site are ever staged. Anything else in the index, and
anything under ``data/private/``, stops the publish and unstages everything.
There is no force push.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from teanga_bench.leaderboard import load_runs, write_leaderboard
from teanga_bench.paths import REPO_ROOT
from teanga_bench.site import SUITES, SiteError, build_site, check_public_examples

STAGE_PATHS = ("results/runs", "results/leaderboard.json", "results/leaderboard.md", "results/charts", "site")
_STAGE_FILES = {"results/leaderboard.json", "results/leaderboard.md"}
_STAGE_DIRS = ("results/runs/", "results/charts/", "site/")
PUBLIC_URLS = tuple(suite.url for suite in SUITES.values())


class PublishError(RuntimeError):
    """The run cannot be published, or a git step failed."""


def check_publishable(document: dict[str, Any], name: str) -> None:
    if document.get("run_kind") != "live":
        raise PublishError(f"{name} is a {document.get('run_kind') or 'unknown'} run; only live runs are published.")
    if document.get("status") != "complete":
        raise PublishError(f"{name} has status {document.get('status')!r}; only complete runs are published.")
    kinds = {
        block.get("dataset", "full")
        for suite in (document.get("suites") or {}).values()
        for block in (suite.get("tests") or {}).values()
    }
    if not kinds or kinds != {"full"}:
        found = ", ".join(sorted(kinds)) or "none"
        raise PublishError(f"{name} used {found} data; only full-set runs are published.")


def allowed_path(path: str) -> bool:
    if path == "data/private" or path.startswith("data/private/"):
        return False
    return path in _STAGE_FILES or path.startswith(_STAGE_DIRS)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise PublishError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def _staged(repo: Path) -> list[str]:
    return [path for path in _git(repo, "diff", "--cached", "--name-only", "-z").split("\0") if path]


def _upstream(repo: Path) -> tuple[str, str]:
    """(remote, branch ref) of the current branch's upstream."""
    branch = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD").strip()
    try:
        remote = _git(repo, "config", "--get", f"branch.{branch}.remote").strip()
        merge = _git(repo, "config", "--get", f"branch.{branch}.merge").strip()
    except PublishError:
        raise PublishError(f"branch {branch!r} has no upstream; set one with git push -u first.") from None
    return remote, merge


def publish_run(run_file: Path, *, repo_root: Path = REPO_ROOT, out: Callable[[str], None] = print) -> int:
    """Publish ``run_file``, which must sit in ``<repo_root>/results/runs``.

    Returns 0 when published or when there is nothing to commit. Raises
    ``PublishError`` when the run is refused or a step fails.
    """
    repo_root = Path(repo_root).resolve()
    results = repo_root / "results"
    runs_dir = results / "runs"
    run_file = Path(run_file).resolve()
    if run_file.parent != runs_dir:
        raise PublishError(f"{run_file} is not in {runs_dir}; only files in results/runs are published.")
    try:
        document = json.loads(run_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError(f"cannot read {run_file}: {exc}") from None
    check_publishable(document, run_file.name)
    model = document["model"]["id"]

    toplevel = Path(_git(repo_root, "rev-parse", "--show-toplevel").strip()).resolve()
    if toplevel != repo_root:
        raise PublishError(f"{repo_root} is not the top of its git worktree ({toplevel}).")
    remote, merge = _upstream(repo_root)

    runs, _skipped = load_runs(runs_dir)
    try:
        check_public_examples(runs)
    except SiteError as exc:
        raise PublishError(str(exc)) from None
    write_leaderboard(runs_dir, results)
    try:
        build_site(results, repo_root / "site", repo_root=repo_root)
    except SiteError as exc:
        raise PublishError(str(exc)) from None

    paths = [p for p in STAGE_PATHS if (repo_root / p).exists()]
    _git(repo_root, "add", "-A", "--", *paths)
    staged = _staged(repo_root)
    refused = [path for path in staged if not allowed_path(path)]
    if refused:
        _git(repo_root, "reset", "-q")
        raise PublishError(
            "refusing to publish: these staged paths are not results or site files: "
            + ", ".join(refused)
            + ". Everything was unstaged; nothing was committed."
        )
    if not staged:
        out("Nothing to publish: the results and the site are already committed.")
        return 0

    _git(repo_root, "commit", "-q", "-m", f"Publish results: {model}")
    try:
        _git(repo_root, "pull", "--rebase", "--autostash", remote, merge)
    except PublishError:
        subprocess.run(["git", "-C", str(repo_root), "rebase", "--abort"], capture_output=True)
        raise PublishError(
            f"git pull --rebase from {remote} failed. The publish commit is still local; "
            "resolve the conflict, then run teanga-bench publish again."
        ) from None
    _git(repo_root, "push", remote, f"HEAD:{merge}")
    out(f"Published {model} to {remote} {merge.removeprefix('refs/heads/')}.")
    for url in PUBLIC_URLS:
        out(url)
    return 0
