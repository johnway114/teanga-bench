"""Command line for Teanga Bench.

``run`` benchmarks one model and writes its results, or with ``--resume``
finishes an earlier incomplete run (with ``--rerun-truncated``, also asks again
the answers a lower token limit cut off). ``resume-plan`` shows, read-only, what a
resume would reuse and run. ``leaderboard`` rebuilds the leaderboard from all
runs. ``validate`` checks the dataset files. ``site`` builds the static research
site, and ``publish`` commits and pushes one finished run with the rebuilt
leaderboard and site.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from teanga_bench import BENCHMARK_NAME, __version__
from teanga_bench.paths import LOGS, REPO_ROOT, RESULTS, RUNS, safe_name
from teanga_bench.protocol import V1, V2, archive_runs_dir, resolve_reexport_source, result_candidates

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_USAGE = 2
EXIT_COST_CAP = 3
EXIT_NO_CREDIT = 4


def _money(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"{text!r} is not a dollar amount") from None
    if value <= 0:
        raise argparse.ArgumentTypeError("must be above 0")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="teanga-bench", description=f"{BENCHMARK_NAME} {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Benchmark one OpenRouter model on the core test suite")
    run.add_argument("--model", required=True, help="OpenRouter model id, for example openai/gpt-6-luna")
    run.add_argument("--max-cost", type=_money, default=None, help="Hard cap in USD on the run's total spend, candidate plus judges (default 5.00; with --resume, the earlier cap)")
    run.add_argument("--epochs", type=int, default=None, help="Repeats per item (default 1)")
    run.add_argument("--limit", type=int, default=None, help="Items per test, for smoke runs")
    run.add_argument("--tests", nargs="+", default=None, metavar="NAME", help="Test names, or suite/test (default: core v2 suite)")
    run.add_argument("--all-tests", action="store_true", help="Run every discovered test, including retired v1 tests (lesson_exercises, round_trip, tonada/exercises)")
    run.add_argument("--reasoning-effort", choices=("minimal", "low", "medium", "high", "none", "default"), default=None, help="Reasoning effort for supporting models (default: low; use 'default' for provider default)")
    run.add_argument("--batch", action="store_true", help="Route openai/anthropic/google candidates through their direct 50%%-off Batch API (requires provider key and SDK)")
    run.add_argument("--direct-model", default=None, help="With --batch: override the direct provider Inspect model id (for example google/gemini-4-neon)")
    run.add_argument("--max-tokens", type=int, default=None, help="Override candidate max_tokens (default 16000, or 4096 in low-reasoning --batch mode)")
    run.add_argument("--output", type=Path, default=None, help="Results JSON path (default results/runs/<model>.json for full runs, results/samples/<model>.json for sample-only runs)")
    run.add_argument("--data-root", type=Path, default=REPO_ROOT, help="Folder holding data/private/ and samples/")
    run.add_argument("--log-dir", type=Path, default=None, help="Where Inspect writes its logs (default logs/<model>-<UTC time>/)")
    run.add_argument("--resume", action="store_true", help="Finish the earlier incomplete run in --output: reuse every scored sample-epoch, run the rest")
    run.add_argument("--rerun-truncated", action="store_true", help="With --resume, also on a complete run: ask again every sample-epoch whose answer stopped at a lower token limit than the current one")
    run.add_argument("--publish", action="store_true", help="After a complete full-set live run, commit and push the results and site")

    plan = sub.add_parser("resume-plan", help="Show what run --resume would reuse and run, and its estimated cost (read-only)")
    plan.add_argument("--model", required=True, help="OpenRouter model id of the incomplete run")
    plan.add_argument("--results-dir", type=Path, default=RESULTS, help="Folder holding runs/ (default results/)")
    plan.add_argument("--log-dir", type=Path, default=LOGS, help="Folder holding the run's log folders, or the run's log folder itself (default logs/)")
    plan.add_argument("--data-root", type=Path, default=REPO_ROOT, help="Folder holding data/private/ and samples/")
    plan.add_argument("--rerun-truncated", action="store_true", help="Plan for run --resume --rerun-truncated: count answers cut off by a lower token limit as missing")

    reexport = sub.add_parser("reexport", help="Rebuild a complete results file from saved Inspect scores, with no model calls")
    reexport.add_argument("--model", required=True, help="Model id of the complete run")
    reexport.add_argument("--results-dir", type=Path, default=RESULTS, help="Folder holding runs/ (default results/)")
    reexport.add_argument("--log-dir", type=Path, default=LOGS, help="Folder holding the run's log folders, or the log folder itself")
    reexport.add_argument("--data-root", type=Path, default=REPO_ROOT, help="Folder holding data/private/ and samples/")
    reexport.add_argument("--output", type=Path, help="Destination JSON (default: replace the existing results file)")

    board = sub.add_parser("leaderboard", help="Rebuild the leaderboard from results/runs/*.json")
    board.add_argument("--runs-dir", type=Path, default=RUNS)
    board.add_argument("--out-dir", type=Path, default=RESULTS)
    board.add_argument("--include-mock", action="store_true", help="Also read mock runs")

    check = sub.add_parser("validate", help="Check every dataset file")
    check.add_argument("--data-root", type=Path, default=REPO_ROOT)

    site = sub.add_parser("site", help="Build the static research site from results/runs")
    site.add_argument("--results-dir", type=Path, default=RESULTS, help="Folder holding runs/ (default results/)")
    site.add_argument("--out-dir", type=Path, default=REPO_ROOT / "site", help="Where the site is written (default site/)")

    publish = sub.add_parser("publish", help="Commit and push one complete run with the leaderboard and site")
    target = publish.add_mutually_exclusive_group(required=True)
    target.add_argument("--model", help="OpenRouter model id; publishes results/runs/<id with / as __>.json")
    target.add_argument("--results", type=Path, help="A results JSON file in results/runs/")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "validate":
        return _validate(args)
    if args.command == "leaderboard":
        return _leaderboard(args)
    if args.command == "site":
        return _site(args)
    if args.command == "publish":
        return _publish(args)
    if args.command == "resume-plan":
        return _resume_plan(args)
    if args.command == "reexport":
        return _reexport(args)
    return _run(args)


def _validate(args: argparse.Namespace) -> int:
    from teanga_bench.datasets import validate_all

    problems, checked = validate_all(args.data_root)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        print(f"{len(problems)} problem(s) in {checked} file(s)", file=sys.stderr)
        return EXIT_INCOMPLETE
    print(f"OK: {checked} dataset file(s) are valid")
    return EXIT_OK


def _leaderboard(args: argparse.Namespace) -> int:
    from teanga_bench.leaderboard import write_leaderboard

    # The default command rebuilds the v2 board from results/runs. When the
    # archive is present it also rebuilds that board, in its own directory.
    methodology = V2 if args.runs_dir.resolve() == RUNS.resolve() else None
    board = write_leaderboard(
        args.runs_dir, args.out_dir, include_mock=args.include_mock, methodology=methodology
    )
    ranked = sum(1 for entry in board["models"] if entry["ranked"])
    print(f"Wrote leaderboard in {args.out_dir} ({ranked} ranked, {len(board['models'])} runs)")
    archive = archive_runs_dir(args.out_dir if args.runs_dir.resolve() == RUNS.resolve() else args.runs_dir.parent)
    if args.runs_dir.resolve() == RUNS.resolve() and archive.is_dir():
        archived = write_leaderboard(archive, archive.parent, methodology=V1)
        archived_ranked = sum(1 for entry in archived["models"] if entry["ranked"])
        print(f"Wrote v1 archive leaderboard in {archive.parent} ({archived_ranked} ranked)")
    return EXIT_OK


def _site(args: argparse.Namespace) -> int:
    from teanga_bench.site import SiteError, build_site

    try:
        summary = build_site(args.results_dir, args.out_dir)
    except SiteError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INCOMPLETE
    ranked = ", ".join(f"{name} {info['ranked']} ranked" for name, info in summary["suites"].items())
    print(f"Wrote {len(summary['files'])} files in {args.out_dir} ({ranked})")
    return EXIT_OK


def _publish_file(run_file: Path) -> int:
    from teanga_bench.publish import PublishError, publish_run

    try:
        return publish_run(run_file)
    except PublishError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INCOMPLETE


def _publish(args: argparse.Namespace) -> int:
    run_file = args.results if args.results is not None else RUNS / f"{safe_name(args.model)}.json"
    if not run_file.exists():
        print(f"error: no results file at {run_file}", file=sys.stderr)
        return EXIT_USAGE
    return _publish_file(run_file)


def _resume_command(args: argparse.Namespace, document: dict) -> str:
    """The exact command that resumes this run."""
    parts = ["teanga-bench", "run", "--model", args.model, "--resume"]
    if args.rerun_truncated:
        parts.append("--rerun-truncated")
    if args.output is not None:
        parts += ["--output", str(args.output)]
    if args.data_root != REPO_ROOT:
        parts += ["--data-root", str(args.data_root)]
    if document["status"] == "cost_cap_reached":
        parts += ["--max-cost", f"{Decimal(str(document['cost']['cap_usd'])) * 2:.2f}"]
    if args.publish:
        parts.append("--publish")
    return shlex.join(parts)


def _reexport(args: argparse.Namespace) -> int:
    from teanga_bench.datasets import discover, select
    from teanga_bench.export import write_results
    from teanga_bench.resume import ResumeError, load_previous_run, reexport_document

    name = f"{safe_name(args.model)}.json"
    try:
        results = resolve_reexport_source(args.results_dir, name, args.output)
        previous = load_previous_run(results, args.model, [args.log_dir])
        datasets = select(discover(args.data_root), list(previous.config["tests"]))
        document = reexport_document(previous, datasets)
        output = args.output or results
        from teanga_bench.protocol import assert_compatible_destination

        assert_compatible_destination(document, results, output)
        write_results(document, output)
    except (ResumeError, KeyError, RuntimeError, ValueError, OSError) as exc:
        print(f"error: {exc.args[0] if exc.args else exc}", file=sys.stderr)
        return EXIT_INCOMPLETE
    print(f"Reexported {args.model}: all headline numbers reproduced; {output}")
    return EXIT_OK


def _resume_plan(args: argparse.Namespace) -> int:
    from teanga_bench.datasets import discover, select
    from teanga_bench.pricing import fetch_catalog
    from teanga_bench.resume import ResumeError, load_previous_run, resume_plan_report
    from teanga_bench.runner import is_mock

    name = f"{safe_name(args.model)}.json"
    candidates = result_candidates(args.results_dir, name)
    results = next((path for path in candidates if path.is_file()), candidates[0])
    try:
        previous = load_previous_run(results, args.model, [args.log_dir])
        datasets = select(discover(args.data_root), list(previous.config["tests"]))
        catalog = None if is_mock(args.model) else fetch_catalog()
    except (ResumeError, KeyError, RuntimeError) as exc:
        print(f"error: {exc.args[0] if exc.args else exc}", file=sys.stderr)
        return EXIT_USAGE
    lines, resumable = resume_plan_report(previous, datasets, catalog, rerun_truncated=args.rerun_truncated)
    print("\n".join(lines))
    return EXIT_OK if resumable else EXIT_INCOMPLETE


def _run(args: argparse.Namespace) -> int:
    from teanga_bench.export import REASON_CREDIT, write_results
    from teanga_bench.leaderboard import write_leaderboard
    from teanga_bench.report import build_report
    from teanga_bench.runner import (
        STATUS_CAP,
        STATUS_COMPLETE,
        RunError,
        RunOptions,
        is_mock,
        run_benchmark,
        select_datasets,
    )

    if args.publish:
        if is_mock(args.model):
            print("error: --publish refuses mock runs", file=sys.stderr)
            return EXIT_USAGE
        if args.limit is not None:
            print("error: --publish refuses smoke runs with --limit", file=sys.stderr)
            return EXIT_USAGE
        if args.output is not None and args.output.resolve().parent != RUNS.resolve():
            print("error: --publish needs the results in results/runs; drop --output", file=sys.stderr)
            return EXIT_USAGE
        if not args.resume:
            try:
                selected = select_datasets(args.data_root, args.tests, all_tests=args.all_tests)
            except KeyError as exc:
                print(f"error: {exc.args[0] if exc.args else exc}", file=sys.stderr)
                return EXIT_USAGE
            sample_only = [dataset.name for dataset in selected if dataset.kind != "full"]
            if sample_only:
                print(
                    "error: --publish requires full private datasets (data/private/ is missing for "
                    + ", ".join(sample_only)
                    + ")",
                    file=sys.stderr,
                )
                return EXIT_USAGE

    options = RunOptions(
        model=args.model,
        max_cost=args.max_cost,
        epochs=args.epochs,
        limit=args.limit,
        tests=args.tests,
        all_tests=args.all_tests,
        reasoning_effort=args.reasoning_effort,
        batch=args.batch,
        direct_model=args.direct_model,
        max_tokens=args.max_tokens,
        output=args.output,
        root=args.data_root,
        log_dir=args.log_dir,
        resume=args.resume,
        rerun_truncated=args.rerun_truncated,
    )
    try:
        result = run_benchmark(options)
    except (RunError, KeyError) as exc:
        print(f"error: {exc.args[0] if exc.args else exc}", file=sys.stderr)
        return EXIT_USAGE

    write_results(result.document, result.output)
    report_path = result.output.with_suffix(".md")
    report_path.write_text(build_report(result.document), encoding="utf-8")
    print(f"Wrote {result.output} and {report_path}")

    try:
        if is_mock(args.model):
            write_leaderboard(result.output.parent, result.output.parent / "board", include_mock=True)
        elif result.output.resolve().parent != RUNS.resolve():
            write_leaderboard(result.output.parent, result.output.parent / "board")
        else:
            write_leaderboard(RUNS, RESULTS)
    except Exception as exc:
        print(f"error: results were written, but the leaderboard failed: {exc}", file=sys.stderr)
        return EXIT_INCOMPLETE

    cost = result.document["cost"]
    print(f"Status: {result.status}. Spent ${cost['total_usd']:.4f} of ${cost['cap_usd']:.2f}.")
    resumed = result.document.get("resumed")
    if resumed:
        counts = resumed["attempts"][-1]["sample_epochs"]
        print(
            f"Resume {resumed['count']}: reused {counts['reused']} sample-epochs, rescored "
            f"{counts['rescored']}, ran {counts['run']} ({counts['rerun_truncated']} of them cut off "
            "by a lower token limit)."
        )
    if result.status == STATUS_COMPLETE:
        if args.publish:
            return _publish_file(result.output)
        return EXIT_OK
    if args.publish:
        print("Not published: only complete runs are published.", file=sys.stderr)
    command = _resume_command(args, result.document)
    if result.status == STATUS_CAP:
        print("The cost cap stopped the run. Results are partial.", file=sys.stderr)
        print(f"Raise --max-cost and finish the run with:\n  {command}", file=sys.stderr)
        return EXIT_COST_CAP
    if result.incomplete_reason == REASON_CREDIT:
        print(
            "OpenRouter kept refusing calls for lack of credit (HTTP 402) or rate (HTTP 429), so the run "
            "stopped. Add credit, then finish the run with:",
            file=sys.stderr,
        )
        print(f"  {command}", file=sys.stderr)
        return EXIT_NO_CREDIT
    print("Some tests did not finish. See incomplete_reason in the results.", file=sys.stderr)
    first_error = next(
        (
            test["first_error"]
            for suite in result.document["suites"].values()
            for test in suite["tests"].values()
            if test.get("first_error")
        ),
        None,
    )
    if first_error:
        print(f"First error: {first_error}", file=sys.stderr)
    print(f"Fix the cause, then finish the run with:\n  {command}", file=sys.stderr)
    return EXIT_INCOMPLETE


if __name__ == "__main__":
    raise SystemExit(main())
