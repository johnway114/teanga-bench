"""Command line for Teanga Bench.

``run`` benchmarks one model and writes its results. ``leaderboard`` rebuilds
the leaderboard from all runs. ``validate`` checks the dataset files. ``site``
builds the static research site, and ``publish`` commits and pushes one
finished run with the rebuilt leaderboard and site.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from teanga_bench import BENCHMARK_NAME, __version__
from teanga_bench.paths import REPO_ROOT, RESULTS, RUNS

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_USAGE = 2
EXIT_COST_CAP = 3


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

    run = sub.add_parser("run", help="Benchmark one OpenRouter model on every test")
    run.add_argument("--model", required=True, help="OpenRouter model id, for example openai/gpt-6-luna")
    run.add_argument("--max-cost", type=_money, default=Decimal("5.00"), help="Hard cap in USD, candidate plus judges (default 5.00)")
    run.add_argument("--epochs", type=int, default=3, help="Repeats per item (default 3)")
    run.add_argument("--limit", type=int, default=None, help="Items per test, for smoke runs")
    run.add_argument("--tests", nargs="+", default=None, metavar="NAME", help="Test names, or suite/test (default: all)")
    run.add_argument("--output", type=Path, default=None, help="Results JSON path (default results/runs/<model with / as __>.json)")
    run.add_argument("--data-root", type=Path, default=REPO_ROOT, help="Folder holding data/private/ and samples/")
    run.add_argument("--log-dir", type=Path, default=None, help="Where Inspect writes its logs (default logs/)")
    run.add_argument("--publish", action="store_true", help="After a complete live run, commit and push the results and site")

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

    board = write_leaderboard(args.runs_dir, args.out_dir, include_mock=args.include_mock)
    ranked = sum(1 for entry in board["models"] if entry["ranked"])
    print(f"Wrote leaderboard in {args.out_dir} ({ranked} ranked, {len(board['models'])} runs)")
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
    from teanga_bench.runner import safe_name

    run_file = args.results if args.results is not None else RUNS / f"{safe_name(args.model)}.json"
    if not run_file.exists():
        print(f"error: no results file at {run_file}", file=sys.stderr)
        return EXIT_USAGE
    return _publish_file(run_file)


def _run(args: argparse.Namespace) -> int:
    from teanga_bench.export import write_results
    from teanga_bench.leaderboard import write_leaderboard
    from teanga_bench.report import build_report
    from teanga_bench.runner import (
        STATUS_CAP,
        STATUS_COMPLETE,
        RunError,
        RunOptions,
        is_mock,
        run_benchmark,
    )

    if args.publish:
        if is_mock(args.model):
            print("error: --publish refuses mock runs", file=sys.stderr)
            return EXIT_USAGE
        if args.output is not None and args.output.resolve().parent != RUNS.resolve():
            print("error: --publish needs the results in results/runs; drop --output", file=sys.stderr)
            return EXIT_USAGE

    options = RunOptions(
        model=args.model,
        max_cost=args.max_cost,
        epochs=args.epochs,
        limit=args.limit,
        tests=args.tests,
        output=args.output,
        root=args.data_root,
        log_dir=args.log_dir,
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
        else:
            write_leaderboard(RUNS, RESULTS)
    except Exception as exc:
        print(f"error: results were written, but the leaderboard failed: {exc}", file=sys.stderr)
        return EXIT_INCOMPLETE

    cost = result.document["cost"]
    print(f"Status: {result.status}. Spent ${cost['total_usd']:.4f} of ${cost['cap_usd']:.2f}.")
    if result.status == STATUS_COMPLETE:
        if args.publish:
            return _publish_file(result.output)
        return EXIT_OK
    if args.publish:
        print("Not published: only complete runs are published.", file=sys.stderr)
    if result.status == STATUS_CAP:
        print("The cost cap stopped the run. Results are partial.", file=sys.stderr)
        return EXIT_COST_CAP
    print("Some tests did not finish. See incomplete_reason in the results.", file=sys.stderr)
    for suite in result.document["suites"].values():
        for test in suite["tests"].values():
            if test.get("first_error"):
                print(f"First error: {test['first_error']}", file=sys.stderr)
                return EXIT_INCOMPLETE
    return EXIT_INCOMPLETE


if __name__ == "__main__":
    raise SystemExit(main())
