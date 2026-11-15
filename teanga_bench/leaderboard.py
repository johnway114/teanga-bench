"""Leaderboard from every ``results/runs/*.json``.

Writes ``leaderboard.json``, ``leaderboard.md``, and SVG charts. Only runs with
status ``complete`` are ranked and charted. Mock runs are skipped unless asked for.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from teanga_bench import BENCHMARK, BENCHMARK_NAME, __version__
from teanga_bench.charts import Bar, Point, bar_chart, scatter_chart
from teanga_bench.export import EXPLANATION_SCORED, SCHEMA_VERSION, now_iso
from teanga_bench.models_config import configured_judges
from teanga_bench.report import interval_text, pct, usd

BLAS_LANGUAGES = ("irish", "welsh", "scots-gaelic", "manx", "breton", "cornish")


def _major(version: str) -> str:
    return str(version).split(".", 1)[0]


def load_runs(runs_dir: Path, include_mock: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
    """Read result files. Returns (runs, skipped file names with reasons)."""
    runs: list[dict[str, Any]] = []
    skipped: list[str] = []
    for path in sorted(runs_dir.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            skipped.append(f"{path.name}: not valid JSON")
            continue
        if "suites" not in document or "model" not in document:
            skipped.append(f"{path.name}: not a run file")
            continue
        if _major(document.get("schema_version", "")) != _major(SCHEMA_VERSION):
            skipped.append(f"{path.name}: schema {document.get('schema_version')!r}")
            continue
        if document.get("run_kind") == "mock" and not include_mock:
            skipped.append(f"{path.name}: mock run")
            continue
        document["_file"] = path.name
        runs.append(document)
    return runs, skipped


def _stat(block: dict[str, Any] | None) -> dict[str, Any] | None:
    if not block:
        return None
    return {key: block.get(key) for key in ("score", "ci95", "n_tests", "n_items") if key in block}


DIFFERENT_PAIR = "judge_pair_differs_from_current_config"


def _explanations(document: dict[str, Any], current_pair: list[str]) -> dict[str, Any]:
    """Explanation score per tutor test, shown only when the run used the current judge pair."""
    result: dict[str, Any] = {}
    for suite_name, suite in document["suites"].items():
        for test_name, block in suite["tests"].items():
            tutor = block.get("tutor")
            if not tutor:
                continue
            explanation = tutor["explanation"]
            judges = list(tutor.get("judges") or document.get("judges") or [])
            status = explanation.get("status")
            if status != EXPLANATION_SCORED:
                reason = status
            elif set(judges) != set(current_pair):
                reason = DIFFERENT_PAIR
            elif explanation.get("score") is None:
                reason = "no_judged_items"
            else:
                reason = None
            comparable = reason is None
            result[f"{suite_name}/{test_name}"] = {
                "score": explanation["score"] if comparable else None,
                "ci95": explanation.get("ci95") if comparable else None,
                "comparable": comparable,
                "reason": reason,
                "judges": judges,
            }
    return result


def summarise_run(document: dict[str, Any], current_pair: list[str]) -> dict[str, Any]:
    tests: dict[str, Any] = {}
    kinds: set[str] = set()
    for suite_name, suite in document["suites"].items():
        for test_name, block in suite["tests"].items():
            kinds.add(block.get("dataset", "full"))
            tests[f"{suite_name}/{test_name}"] = {
                "score": block.get("score"),
                "ci95": block.get("ci95"),
                "n_items": block.get("n_items"),
                "status": block.get("status"),
                "dataset": block.get("dataset"),
                "consistency": block.get("consistency"),
                "cost_usd": block.get("cost_usd"),
            }
    overall = document.get("overall")
    return {
        "model": document["model"]["id"],
        "family": document["model"].get("family"),
        "run_file": document["_file"],
        "run_kind": document["run_kind"],
        "status": document["status"],
        "ranked": document["status"] == "complete" and overall is not None,
        "generated_at": document["generated_at"],
        "data": kinds.pop() if len(kinds) == 1 else "mixed",
        "epochs": document["config"]["epochs"],
        "overall": _stat(overall),
        "cost_usd": document["cost"]["total_usd"],
        "suites": {name: _stat(suite.get("overall")) for name, suite in document["suites"].items()},
        "languages": {
            language: _stat(stat) for language, stat in ((overall or {}).get("by_language") or {}).items()
        },
        "tests": tests,
        "judges": list(document.get("judges") or []),
        "explanation_status": document.get("explanation_status"),
        "explanation": _explanations(document, current_pair),
    }


def _rank_key(entry: dict[str, Any]) -> tuple:
    score = entry["overall"]["score"] if entry["overall"] else -1.0
    return (not entry["ranked"], -score, entry["cost_usd"], entry["model"])


def build_leaderboard(
    runs: list[dict[str, Any]], skipped: list[str], judge_pair: list[str] | None = None
) -> dict[str, Any]:
    current = list(judge_pair) if judge_pair is not None else [j.id for j in configured_judges()]
    entries = sorted((summarise_run(run, current) for run in runs), key=_rank_key)
    rank = 0
    for entry in entries:
        if entry["ranked"]:
            rank += 1
            entry["rank"] = rank
        else:
            entry["rank"] = None
    return {
        "schema_version": SCHEMA_VERSION,
        "benchmark": BENCHMARK,
        "benchmark_name": BENCHMARK_NAME,
        "benchmark_version": __version__,
        "generated_at": now_iso(),
        "note": (
            "Only runs with status complete are ranked. Scores are means over items with a "
            "95% bootstrap interval. Runs on public samples and runs on full sets are not "
            "comparable; the data column says which. Explanation scores are judge-marked, "
            "not human-validated, and shown only for runs that used the current judge pair."
        ),
        "current_judges": current,
        "models": entries,
        "skipped": skipped,
    }


def _ranked(board: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry for entry in board["models"] if entry["ranked"]]


def _bars(entries: list[dict[str, Any]], stat_of) -> list[Bar]:
    bars = []
    for entry in entries:
        stat = stat_of(entry)
        if stat and stat.get("score") is not None:
            ci = stat.get("ci95")
            bars.append(Bar(entry["model"], stat["score"], ci[0] if ci else None, ci[1] if ci else None))
    return bars


def build_charts(board: dict[str, Any]) -> dict[str, str]:
    """Chart file name to SVG text."""
    ranked = _ranked(board)
    charts: dict[str, str] = {}
    suites = sorted({name for entry in ranked for name, stat in entry["suites"].items() if stat})
    for suite in suites:
        charts[f"suite-{suite}.svg"] = bar_chart(
            f"Overall score: {suite} suite",
            _bars(ranked, lambda entry, s=suite: entry["suites"].get(s)),
            "Mean over tests, 95% interval over items",
        )
    present = {language for entry in ranked for language in entry["languages"]}
    for language in BLAS_LANGUAGES:
        if language in present:
            charts[f"language-{language}.svg"] = bar_chart(
                f"Overall score: {language}",
                _bars(ranked, lambda entry, l=language: entry["languages"].get(l)),
                "Mean over tests, 95% interval over items",
            )
    explanation_bars = []
    for entry in ranked:
        for test, stat in sorted(entry["explanation"].items()):
            if stat["comparable"]:
                ci = stat["ci95"]
                explanation_bars.append(
                    Bar(f"{entry['model']} ({test})", stat["score"], ci[0] if ci else None, ci[1] if ci else None)
                )
    if any(entry["explanation"] for entry in ranked):
        charts["explanation.svg"] = bar_chart(
            "Tutor explanation score (judge-marked, not human-validated)",
            explanation_bars,
            "Judges: " + ", ".join(board["current_judges"]),
        )
    points = [
        Point(entry["model"], entry["cost_usd"], entry["overall"]["score"])
        for entry in ranked
        if entry["overall"] and entry["overall"]["score"] is not None
    ]
    charts["score-vs-cost.svg"] = scatter_chart("Overall score against run cost", points)
    return charts


def render_markdown(board: dict[str, Any], chart_names: list[str]) -> str:
    ranked = _ranked(board)
    lines = ["# Teanga Bench leaderboard", "", board["note"], ""]
    lines += ["| Rank | Model | Overall | 95% interval | Cost (USD) | Data |", "| --- | --- | --- | --- | --- | --- |"]
    for entry in board["models"]:
        overall = entry["overall"] or {}
        rank = entry["rank"] if entry["rank"] is not None else "-"
        flag = "" if entry["ranked"] else f" ({entry['status']})"
        lines.append(
            f"| {rank} | {entry['model']}{flag} | {pct(overall.get('score'))} "
            f"| {interval_text(overall.get('ci95'))} | {usd(entry['cost_usd'])} | {entry['data']} |"
        )
    if not board["models"]:
        lines.append("| - | No runs yet | n/a | n/a | n/a | n/a |")
    suites = sorted({name for entry in ranked for name, stat in entry["suites"].items() if stat})
    for suite in suites:
        lines += ["", f"## Suite: {suite}", "", "| Model | Score | 95% interval |", "| --- | --- | --- |"]
        for entry in ranked:
            stat = entry["suites"].get(suite)
            if stat:
                lines.append(f"| {entry['model']} | {pct(stat['score'])} | {interval_text(stat['ci95'])} |")
    test_names = sorted({name for entry in ranked for name in entry["tests"]})
    if test_names:
        lines += ["", "## Tests", "", "| Model | " + " | ".join(test_names) + " |", "| --- |" + " --- |" * len(test_names)]
        for entry in ranked:
            cells = [pct(entry["tests"][n]["score"]) if n in entry["tests"] else "n/a" for n in test_names]
            lines.append(f"| {entry['model']} | " + " | ".join(cells) + " |")
    if any(entry["explanation"] for entry in ranked):
        lines += [
            "",
            "## Tutor explanation (judge-marked, not human-validated)",
            "",
            "Judges: " + ", ".join(board["current_judges"]) + ". Only runs that used this pair are compared.",
            "",
            "| Model | Test | Explanation | 95% interval | Note |",
            "| --- | --- | --- | --- | --- |",
        ]
        for entry in ranked:
            for test, stat in sorted(entry["explanation"].items()):
                note = "" if stat["comparable"] else f"not comparable: {stat['reason']}"
                lines.append(
                    f"| {entry['model']} | {test} | {pct(stat['score'])} | {interval_text(stat['ci95'])} | {note} |"
                )
    lines += ["", "## Charts", ""]
    for name in chart_names:
        lines.append(f"![{name}](charts/{name})")
    if board["skipped"]:
        lines += ["", "## Skipped result files", ""] + [f"- {item}" for item in board["skipped"]]
    lines.append("")
    return "\n".join(lines)


def write_leaderboard(
    runs_dir: Path, out_dir: Path, include_mock: bool = False, judge_pair: list[str] | None = None
) -> dict[str, Any]:
    runs, skipped = load_runs(runs_dir, include_mock=include_mock)
    board = build_leaderboard(runs, skipped, judge_pair)
    charts = build_charts(board)
    chart_dir = out_dir / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    for stale in chart_dir.glob("*.svg"):
        stale.unlink()
    for name, svg in charts.items():
        (chart_dir / name).write_text(svg, encoding="utf-8")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "leaderboard.json").write_text(
        json.dumps(board, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "leaderboard.md").write_text(render_markdown(board, sorted(charts)), encoding="utf-8")
    return board
