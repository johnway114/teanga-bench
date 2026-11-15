"""Run every test on one model and write the results.

Tests run one after another. Every model call, candidate and judge, goes through
one cost guard, so ``--max-cost`` is a hard stop for the whole run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from inspect_ai import eval as inspect_eval
from inspect_ai.model import Model

from teanga_bench.apikey import export_api_key
from teanga_bench.context import (
    CANDIDATE_MAX_TOKENS,
    JUDGE_MAX_TOKENS,
    JUDGE_RETRIES,
    JudgeSpec,
    RunContext,
    set_context,
)
from teanga_bench.cost import CostGuard
from teanga_bench.datasets import discover, public_ids, read_items, select
from teanga_bench.export import (
    EXPLANATION_JUDGE_UNAVAILABLE,
    EXPLANATION_SAME_FAMILY,
    EXPLANATION_SCORED,
    TestRun,
    build_document,
    build_test_outcome,
    not_run_block,
    now_iso,
)
from teanga_bench.models_config import JudgeChoice, configured_judges, family_of
from teanga_bench.paths import LOGS, REPO_ROOT, RESULTS, RUNS
from teanga_bench.pricing import MODELS_URL, Catalog, Pricing, fetch_catalog
from teanga_bench.stats import CONFIDENCE, RESAMPLES, SEED

MAX_CONNECTIONS = 8
MOCK_PREFIX = "mockllm/"

STATUS_COMPLETE = "complete"
STATUS_CAP = "cost_cap_reached"
STATUS_INCOMPLETE = "incomplete"


class RunError(RuntimeError):
    """The run could not start (bad model id, no key, no datasets)."""


@dataclass
class RunOptions:
    model: str
    max_cost: Decimal = Decimal("5.00")
    epochs: int = 3
    limit: int | None = None
    tests: list[str] | None = None
    output: Path | None = None
    root: Path = REPO_ROOT
    log_dir: Path | None = None
    mock_pricing: Pricing | None = None  # fake prices for mockllm, for tests


@dataclass
class RunResult:
    document: dict[str, Any]
    output: Path
    status: str
    outcomes: list[TestRun] = field(default_factory=list)


def is_mock(model: str) -> bool:
    return model.startswith(MOCK_PREFIX)


def safe_name(model: str) -> str:
    return model.replace("/", "__")


def default_output(model: str) -> Path:
    # Mock runs never go to results/runs/, so they cannot reach the real leaderboard.
    return (RESULTS / "mock" if is_mock(model) else RUNS) / f"{safe_name(model)}.json"


def _judges_for_run(
    options: RunOptions, catalog: Catalog | None
) -> tuple[list[JudgeSpec], list[JudgeChoice], str]:
    """The fixed judge pair, the specs to call, and the explanation status.

    The specs are empty when the explanation is not scored for this run.
    """
    if is_mock(options.model):
        specs = [
            JudgeSpec(id="mockllm/judge-1", family="mock-1", model="mockllm/model"),
            JudgeSpec(id="mockllm/judge-2", family="mock-2", model="mockllm/model"),
        ]
        return specs, [JudgeChoice(spec.id, spec.family) for spec in specs], EXPLANATION_SCORED
    assert catalog is not None
    choices = configured_judges()
    if family_of(options.model) in {choice.family for choice in choices}:
        return [], choices, EXPLANATION_SAME_FAMILY
    if any(choice.id not in catalog.entries for choice in choices):
        return [], choices, EXPLANATION_JUDGE_UNAVAILABLE
    return [JudgeSpec(c.id, c.family, f"openrouter/{c.id}") for c in choices], choices, EXPLANATION_SCORED


def run_benchmark(
    options: RunOptions,
    *,
    catalog: Catalog | None = None,
    inspect_model: str | Model | None = None,
) -> RunResult:
    """Run the benchmark. ``catalog`` and ``inspect_model`` are for tests."""
    if options.epochs < 1:
        raise RunError("--epochs must be at least 1")
    if options.max_cost <= 0:
        raise RunError("--max-cost must be above 0")
    mock = is_mock(options.model)

    datasets = select(discover(options.root), options.tests)
    if not datasets:
        raise RunError(
            "No datasets found. Put full sets in data/private/<suite>/<test>.jsonl "
            "or samples in samples/<suite>/<test>.jsonl."
        )

    prices: dict[str, Pricing] = {}
    model_block: dict[str, Any]
    if mock:
        model_pricing = options.mock_pricing
        if model_pricing is not None:
            prices[options.model] = model_pricing
        model_block = {
            "id": options.model,
            "family": "mock",
            "inspect_id": options.model,
            "pricing": None,
        }
    else:
        try:
            catalog = catalog or fetch_catalog()
            model_pricing = catalog.pricing(options.model)
        except Exception as exc:
            raise RunError(str(exc)) from exc
        prices[options.model] = model_pricing
        model_block = {
            "id": options.model,
            "family": family_of(options.model),
            "inspect_id": f"openrouter/{options.model}",
            "pricing": {
                **model_pricing.as_dict(),
                "source": catalog.source,
                "retrieved_at": catalog.retrieved_at,
            },
        }

    try:
        judge_specs, judge_choices, explanation_status = _judges_for_run(options, catalog)
    except Exception as exc:
        raise RunError(str(exc)) from exc
    judge_ids = [choice.id for choice in judge_choices]
    judge_info: dict[str, Any] = {
        "called": bool(judge_specs),
        "families": {choice.id: choice.family for choice in judge_choices},
        "rule": (
            "One fixed judge pair for every run. Judges mark only the explanation of tutor "
            "items, and the explanation passes only when both judges pass it. When the "
            "candidate is in the family of either judge, or a judge is missing from the live "
            "model list, the explanation is not scored."
        ),
        "retries_per_call": JUDGE_RETRIES,
        "pricing": {},
    }
    for spec in judge_specs:
        if not mock:
            assert catalog is not None
            prices[spec.id] = catalog.pricing(spec.id)
            judge_info["pricing"][spec.id] = {
                **prices[spec.id].as_dict(),
                "retrieved_at": catalog.retrieved_at,
            }

    if not mock:
        try:
            export_api_key()
        except Exception as exc:
            raise RunError(str(exc)) from exc

    guard = CostGuard(max_cost=options.max_cost, prices=prices)
    context = RunContext(guard=guard, candidate_id=options.model, judges=judge_specs)
    set_context(context)

    started_at = now_iso()
    log_dir = options.log_dir or LOGS / f"{safe_name(options.model)}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    model_arg = inspect_model if inspect_model is not None else model_block["inspect_id"]
    outcomes: list[TestRun] = []
    not_run: list[dict[str, Any]] = []
    try:
        from teanga_bench.tasks import build_task

        for dataset in datasets:
            n_items = len(read_items(dataset.path))
            if options.limit is not None:
                n_items = min(n_items, options.limit)
            if guard.stopped:
                not_run.append(not_run_block(dataset, n_items, options.epochs, "cost_cap_reached"))
                continue
            logs = inspect_eval(
                build_task(dataset, options.epochs),
                model=model_arg,
                log_dir=str(log_dir),
                log_format="json",
                display="none",
                limit=options.limit,
                fail_on_error=False,
                max_connections=MAX_CONNECTIONS,
            )
            log = logs[0]
            outcome = build_test_outcome(
                log,
                dataset,
                n_items_dataset=n_items,
                epochs=options.epochs,
                guard=guard,
                public=public_ids(dataset),
                judges=judge_ids,
                explanation_status=explanation_status,
            )
            if log.status != "success":
                detail = getattr(getattr(log, "error", None), "message", "") or str(log.status)
                outcome.block["status"] = "incomplete"
                outcome.block["incomplete_reason"] = f"eval_{log.status}: {detail}"
            outcomes.append(outcome)
    finally:
        set_context(None)

    all_blocks = [o.block for o in outcomes] + not_run
    if guard.stopped:
        status = STATUS_CAP
    elif all(block["status"] == "complete" for block in all_blocks):
        status = STATUS_COMPLETE
    else:
        status = STATUS_INCOMPLETE

    config = {
        "epochs": options.epochs,
        "limit": options.limit,
        "max_cost_usd": float(options.max_cost),
        "max_tokens": {"candidate": CANDIDATE_MAX_TOKENS, "judge": JUDGE_MAX_TOKENS},
        "temperature": "provider default",
        "bootstrap": {"seed": SEED, "resamples": RESAMPLES, "confidence": CONFIDENCE},
        "tests": [dataset.name for dataset in datasets],
        "pricing_source": MODELS_URL,
    }
    document = build_document(
        run_kind="mock" if mock else "live",
        status=status,
        model=model_block,
        config=config,
        judges=judge_ids,
        judge_info=judge_info,
        explanation_status=explanation_status,
        guard=guard,
        outcomes=outcomes,
        blocks_not_run=not_run,
        started_at=started_at,
    )
    return RunResult(document=document, output=options.output or default_output(options.model), status=status, outcomes=outcomes)
