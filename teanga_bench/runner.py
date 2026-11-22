"""Run every test on one model and write the results.

Tests run one after another. Every model call, candidate and judge, goes through
one cost guard, so ``--max-cost`` is a hard stop for the whole run. With
``resume`` the run continues an earlier attempt of the same model: see
``teanga_bench/resume.py``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from inspect_ai import eval as inspect_eval
from inspect_ai.model import Model

from teanga_bench.apikey import check_direct_batch_ready, export_api_key
from teanga_bench.context import (
    CANDIDATE_MAX_TOKENS,
    DEFAULT_REASONING_EFFORT,
    JUDGE_MAX_TOKENS,
    JUDGE_RETRIES,
    LEGACY_CANDIDATE_MAX_TOKENS,
    LOW_REASONING_MAX_TOKENS,
    REASONING_EFFORT_VALUES,
    REASONING_TOKEN_BUDGETS,
    JudgeSpec,
    Replay,
    RunContext,
    set_context,
)
from teanga_bench.cost import CostGuard, CreditBackoff
from teanga_bench.datasets import DatasetFile, discover, public_ids, read_items, select
from teanga_bench.export import (
    EXPLANATION_JUDGE_UNAVAILABLE,
    EXPLANATION_SAME_FAMILY,
    EXPLANATION_SCORED,
    REASON_CAP,
    REASON_CREDIT,
    REASON_ERRORS,
    TestRun,
    build_document,
    build_test_outcome,
    not_run_block,
    now_iso,
    score_of,
)
from teanga_bench.models_config import JudgeChoice, configured_default_tests, configured_judges, family_of
from teanga_bench.paths import LOGS, REPO_ROOT, RESULTS, RUNS, safe_name
from teanga_bench.pricing import MODELS_URL, Catalog, Pricing, fetch_catalog
from teanga_bench.protocol import V1, methodology_of, path_methodology
from teanga_bench.resume import (
    PreviousRun,
    ResumeError,
    TestPlan,
    carried_cost,
    check_datasets,
    dataset_hash,
    display_path,
    first_attempt,
    load_previous_run,
    merge_samples,
    plan_test,
)
from teanga_bench.stats import CONFIDENCE, RESAMPLES, SEED

MAX_CONNECTIONS = 8
BATCH_MAX_CONNECTIONS = 100
BATCH_DISCOUNT = Decimal("0.5")
MOCK_PREFIX = "mockllm/"
DEFAULT_MAX_COST = Decimal("5.00")
DEFAULT_EPOCHS = 1

STATUS_COMPLETE = "complete"
STATUS_CAP = "cost_cap_reached"
STATUS_INCOMPLETE = "incomplete"


class RunError(RuntimeError):
    """The run could not start (bad model id, no key, no datasets, refused resume)."""


@dataclass
class RunOptions:
    model: str
    max_cost: Decimal | None = None  # None: 5.00, or the earlier cap when resuming
    epochs: int | None = None  # None: 1, or the earlier value when resuming
    limit: int | None = None
    tests: list[str] | None = None
    all_tests: bool = False  # include retired v1 tests alongside the default core suite
    reasoning_effort: str | None = None  # None: "low", or the earlier value when resuming
    batch: bool = False  # route openai/anthropic/google through direct 50%-off Batch API
    direct_model: str | None = None  # explicit direct Inspect model id for --batch
    max_tokens: int | None = None  # optional override for candidate max_tokens
    output: Path | None = None
    root: Path = REPO_ROOT
    log_dir: Path | None = None
    mock_pricing: Pricing | None = None  # fake prices for mockllm, for tests
    resume: bool = False
    rerun_truncated: bool = False  # with resume: ask again what stopped at a lower answer limit
    logs_root: Path = LOGS  # where the log folders of earlier attempts are looked for


@dataclass
class RunResult:
    document: dict[str, Any]
    output: Path
    status: str
    outcomes: list[TestRun] = field(default_factory=list)

    @property
    def incomplete_reason(self) -> str | None:
        return self.document.get("incomplete_reason")


def is_mock(model: str) -> bool:
    return model.startswith(MOCK_PREFIX)


def refuse_protocol_overwrite(output: Path, *, resume: bool) -> None:
    """A new v2 run must not replace a v1 file or land in the v1 archive.

    Resuming the file that was loaded writes back to that same path.
    """
    if resume:
        return
    if path_methodology(output) == V1:
        raise RunError(
            f"{output} is in the v1 archive. New runs go to results/runs/; v2 must not overwrite v1."
        )
    if not output.is_file() or output.parent.name != "runs":
        return
    try:
        document = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if isinstance(document, dict) and methodology_of(document) == V1:
        raise RunError(
            f"{output} is a v1 result. Move it to results/v1-archive/runs/ before a v2 run; "
            "v2 must not overwrite v1."
        )


def default_output(model: str, *, sample_only: bool = False) -> Path:
    # Mock and public-sample runs never go to results/runs/, so they cannot reach the real leaderboard.
    if is_mock(model):
        folder = RESULTS / "mock"
    elif sample_only:
        folder = RESULTS / "samples"
    else:
        folder = RUNS
    return folder / f"{safe_name(model)}.json"


def select_datasets(
    root: Path, requested: list[str] | None, *, all_tests: bool = False
) -> list[DatasetFile]:
    """Select datasets to run: explicit list, all tests, or configured default core tests."""
    discovered = discover(root)
    if requested is not None:
        return select(discovered, requested)
    if all_tests:
        return select(discovered, None)
    defaults = configured_default_tests()
    known = {dataset.name for dataset in discovered.values()}
    if defaults and all(name in known for name in defaults):
        return select(discovered, defaults)
    return select(discovered, None)


def _resolve_reasoning(
    requested: str,
    model: str,
    catalog: Catalog | None,
    *,
    mock: bool,
    batch: bool,
) -> tuple[str | None, int | None, str]:
    """Return (reasoning_effort, reasoning_tokens, recorded_label) for candidate calls."""
    if requested == "default":
        return None, None, "default"
    if requested == "unsupported":
        return None, None, "unsupported"
    if requested.startswith("tokens:"):
        try:
            budget = int(requested.split(":", 1)[1])
        except ValueError as exc:
            raise RunError(f"invalid saved reasoning setting {requested!r}") from exc
        return None, budget, requested
    if requested not in REASONING_EFFORT_VALUES:
        allowed = ", ".join(REASONING_EFFORT_VALUES)
        raise RunError(f"--reasoning-effort must be one of {allowed} (got {requested!r})")
    if mock or batch:
        return requested, None, requested
    supported = catalog.supported_parameters(model) if catalog is not None else set()
    if not supported or "reasoning_effort" in supported:
        return requested, None, requested
    if "reasoning" in supported:
        budget = REASONING_TOKEN_BUDGETS.get(requested)
        if budget is not None:
            return None, budget, f"tokens:{budget}"
    return None, None, "unsupported"


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


@dataclass
class _Settings:
    epochs: int
    limit: int | None
    tests: list[str] | None
    all_tests: bool
    max_cost: Decimal
    reasoning_effort: str
    batch: bool
    candidate_max_tokens: int
    rerun_below: int | None = None  # rerun sample-epochs truncated under a lower answer limit


@dataclass
class _Attempt:
    """What a resume did, per test, for the ``resumed`` block."""

    counts: dict[str, dict[str, int]] = field(default_factory=dict)
    rerun_limits: set[int] = field(default_factory=set)  # limits the rerun truncated sample-epochs had


def _candidate_max_tokens(options: RunOptions, reasoning_effort: str, batch: bool) -> int:
    if options.max_tokens is not None:
        if options.max_tokens < 1:
            raise RunError("--max-tokens must be at least 1")
        return options.max_tokens
    if batch and reasoning_effort in ("minimal", "low", "none"):
        return LOW_REASONING_MAX_TOKENS
    return CANDIDATE_MAX_TOKENS


def _settings(options: RunOptions, previous: PreviousRun | None) -> _Settings:
    if options.rerun_truncated and previous is None:
        raise RunError("--rerun-truncated works only with --resume")
    if previous is None:
        effort = DEFAULT_REASONING_EFFORT if options.reasoning_effort is None else options.reasoning_effort
        return _Settings(
            epochs=DEFAULT_EPOCHS if options.epochs is None else options.epochs,
            limit=options.limit,
            tests=options.tests,
            all_tests=options.all_tests,
            max_cost=DEFAULT_MAX_COST if options.max_cost is None else options.max_cost,
            reasoning_effort=effort,
            batch=options.batch,
            candidate_max_tokens=_candidate_max_tokens(options, effort, options.batch),
        )
    config = previous.config
    if previous.document["status"] == STATUS_COMPLETE and not options.rerun_truncated:
        raise RunError(
            f"{previous.results_path} is already complete; there is nothing to resume "
            "(add --rerun-truncated to ask again the answers cut off by a lower token limit)"
        )
    saved_tests = list(config["tests"])
    saved_effort = str(config.get("reasoning_effort") or "default")
    saved_batch = bool(config.get("batch", False))
    conflicts = []
    if options.epochs is not None and options.epochs != config["epochs"]:
        conflicts.append(f"--epochs {options.epochs} (the run used {config['epochs']})")
    if options.limit is not None and options.limit != config.get("limit"):
        conflicts.append(f"--limit {options.limit} (the run used {config.get('limit')})")
    if options.reasoning_effort is not None and options.reasoning_effort != saved_effort:
        conflicts.append(
            f"--reasoning-effort {options.reasoning_effort} (the run used {saved_effort})"
        )
    if options.batch and not saved_batch:
        conflicts.append("--batch (the run did not use --batch)")
    if options.tests is not None:
        try:
            chosen = [d.name for d in select(discover(options.root), options.tests)]
        except KeyError:
            chosen = list(options.tests)
        if chosen != saved_tests:
            conflicts.append(f"--tests {' '.join(options.tests)} (the run used {' '.join(saved_tests)})")
    if conflicts:
        raise RunError("--resume keeps the settings of the first attempt; drop " + ", ".join(conflicts))
    max_tokens = _candidate_max_tokens(options, saved_effort, saved_batch)
    return _Settings(
        epochs=int(config["epochs"]),
        limit=config.get("limit"),
        tests=saved_tests,
        all_tests=False,
        max_cost=Decimal(str(config["max_cost_usd"])) if options.max_cost is None else options.max_cost,
        reasoning_effort=saved_effort,
        batch=saved_batch,
        candidate_max_tokens=max_tokens,
        rerun_below=max_tokens if options.rerun_truncated else None,
    )


def _check_same_judging(
    previous: PreviousRun, judge_ids: list[str], explanation_status: str, judge_specs: list[JudgeSpec]
) -> tuple[list[JudgeSpec], str]:
    """A resumed run keeps the judging of its first attempt, or refuses."""
    before = previous.document.get("explanation_status")
    if previous.document.get("judges") != judge_ids:
        raise RunError(
            f"the judge pair changed since the first attempt ({previous.document.get('judges')} then, "
            f"{judge_ids} now); explanation scores would not be comparable. Start a fresh run."
        )
    if before == explanation_status:
        return judge_specs, explanation_status
    if before == EXPLANATION_JUDGE_UNAVAILABLE:
        return [], before  # stay unscored, as the samples already done are
    raise RunError(
        f"the explanation was {before!r} in the first attempt but would be {explanation_status!r} now "
        "(a judge is missing from the live model list); resuming would mix the two."
    )


def run_benchmark(
    options: RunOptions,
    *,
    catalog: Catalog | None = None,
    inspect_model: str | Model | None = None,
    backoff: CreditBackoff | None = None,
) -> RunResult:
    """Run the benchmark. ``catalog``, ``inspect_model`` and ``backoff`` are for tests."""
    mock = is_mock(options.model)
    previous: PreviousRun | None = None
    output = options.output
    if options.resume:
        if output is None:
            candidate_out = default_output(options.model)
            sample_out = default_output(options.model, sample_only=True)
            output = candidate_out if candidate_out.is_file() or not sample_out.is_file() else sample_out
        search = ([options.log_dir] if options.log_dir is not None else []) + [options.logs_root]
        try:
            previous = load_previous_run(output, options.model, search)
        except ResumeError as exc:
            raise RunError(str(exc)) from exc
    settings = _settings(options, previous)
    if settings.epochs < 1:
        raise RunError("--epochs must be at least 1")
    if settings.max_cost <= 0:
        raise RunError("--max-cost must be above 0")

    datasets = select_datasets(options.root, settings.tests, all_tests=settings.all_tests)
    if not datasets:
        raise RunError(
            "No datasets found. Put full sets in data/private/<suite>/<test>.jsonl "
            "or samples in samples/<suite>/<test>.jsonl."
        )
    if output is None:
        sample_only = any(dataset.kind != "full" for dataset in datasets)
        output = default_output(options.model, sample_only=sample_only)
    refuse_protocol_overwrite(output, resume=previous is not None)
    dataset_check: str | None = None
    if previous is not None:
        try:
            dataset_check = check_datasets(previous, datasets, settings.limit)
        except ResumeError as exc:
            raise RunError(str(exc)) from exc

    prices: dict[str, Pricing] = {}
    model_block: dict[str, Any]
    if mock:
        model_pricing = options.mock_pricing
        if model_pricing is not None:
            if settings.batch:
                model_pricing = model_pricing.scaled(BATCH_DISCOUNT)
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
        if settings.batch:
            try:
                inspect_id = check_direct_batch_ready(options.model)
            except Exception as exc:
                raise RunError(str(exc)) from exc
            if options.direct_model:
                inspect_id = options.direct_model
            model_pricing = model_pricing.scaled(BATCH_DISCOUNT)
        else:
            inspect_id = f"openrouter/{options.model}"
        prices[options.model] = model_pricing
        pricing_block: dict[str, Any] = {
            **model_pricing.as_dict(),
            "source": catalog.source,
            "retrieved_at": catalog.retrieved_at,
        }
        if settings.batch:
            pricing_block["batch_discount"] = float(BATCH_DISCOUNT)
        model_block = {
            "id": options.model,
            "family": family_of(options.model),
            "inspect_id": inspect_id,
            "pricing": pricing_block,
        }

    reasoning_effort, reasoning_tokens, reasoning_label = _resolve_reasoning(
        settings.reasoning_effort, options.model, catalog, mock=mock, batch=settings.batch
    )

    try:
        judge_specs, judge_choices, explanation_status = _judges_for_run(options, catalog)
    except Exception as exc:
        raise RunError(str(exc)) from exc
    judge_ids = [choice.id for choice in judge_choices]
    if previous is not None:
        judge_specs, explanation_status = _check_same_judging(previous, judge_ids, explanation_status, judge_specs)
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

    needs_openrouter = (not settings.batch) or bool(judge_specs)
    if not mock and needs_openrouter:
        try:
            export_api_key()
        except Exception as exc:
            raise RunError(str(exc)) from exc

    guard = CostGuard(max_cost=settings.max_cost, prices=prices, backoff=backoff or CreditBackoff())
    carried_total = Decimal(0)
    if previous is not None:
        by_test, by_model, carried_total = carried_cost(previous.document)
        if carried_total >= settings.max_cost:
            raise RunError(
                f"the earlier attempts already spent ${carried_total:.2f} of the ${settings.max_cost} cap; "
                "pass a higher --max-cost"
            )
        guard.carry_forward(by_test, by_model, carried_total)
    context = RunContext(
        guard=guard,
        candidate_id=options.model,
        judges=judge_specs,
        max_tokens=settings.candidate_max_tokens,
        reasoning_effort=reasoning_effort,
        reasoning_tokens=reasoning_tokens,
        batch=settings.batch,
    )
    set_context(context)

    started_at = now_iso()
    log_dir = options.log_dir or LOGS / f"{safe_name(options.model)}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    model_arg = inspect_model if inspect_model is not None else model_block["inspect_id"]
    outcomes: list[TestRun] = []
    not_run: list[dict[str, Any]] = []
    attempt = _Attempt()
    try:
        from teanga_bench.tasks import build_task

        for dataset in datasets:
            n_items = len(read_items(dataset.path))
            if settings.limit is not None:
                n_items = min(n_items, settings.limit)
            if guard.stopped or guard.credit_exhausted:
                reason = REASON_CAP if guard.stopped else REASON_CREDIT
                not_run.append(not_run_block(dataset, n_items, settings.epochs, reason))
                if previous is not None:
                    attempt.counts[dataset.name] = {"reused": 0, "rescored": 0, "run": 0, "rerun_truncated": 0}
                continue
            log, samples = _run_test(
                dataset, previous, context, settings, explanation_status, model_arg, log_dir, attempt, build_task
            )
            outcome = build_test_outcome(
                samples,
                dataset,
                n_items_dataset=n_items,
                epochs=settings.epochs,
                guard=guard,
                public=public_ids(dataset),
                judges=judge_ids,
                explanation_status=explanation_status,
            )
            if log is not None and log.status != "success":
                detail = getattr(getattr(log, "error", None), "message", "") or str(log.status)
                outcome.block["status"] = "incomplete"
                outcome.block["incomplete_reason"] = f"eval_{log.status}: {detail}"
            outcomes.append(outcome)
    finally:
        set_context(None)

    if previous is not None and previous.document["status"] == STATUS_COMPLETE:
        asked = sum(c["run"] + c["rescored"] for c in attempt.counts.values())
        if asked == 0:
            raise RunError(
                f"nothing to re-run: no sample-epoch of {previous.results_path} stopped at an answer "
                f"limit below {settings.candidate_max_tokens} tokens"
            )

    all_blocks = [o.block for o in outcomes] + not_run
    if guard.stopped:
        status, incomplete_reason = STATUS_CAP, REASON_CAP
    elif guard.credit_exhausted:
        status, incomplete_reason = STATUS_INCOMPLETE, REASON_CREDIT
    elif all(block["status"] == "complete" for block in all_blocks):
        status, incomplete_reason = STATUS_COMPLETE, None
    else:
        status, incomplete_reason = STATUS_INCOMPLETE, REASON_ERRORS

    config = {
        "epochs": settings.epochs,
        "limit": settings.limit,
        "max_cost_usd": float(settings.max_cost),
        "max_tokens": {"candidate": settings.candidate_max_tokens, "judge": JUDGE_MAX_TOKENS},
        "reasoning_effort": reasoning_label,
        "batch": settings.batch,
        "temperature": "provider default",
        "bootstrap": {"seed": SEED, "resamples": RESAMPLES, "confidence": CONFIDENCE},
        "tests": [dataset.name for dataset in datasets],
        "pricing_source": MODELS_URL,
        "dataset_hashes": {dataset.name: dataset_hash(dataset.path) for dataset in datasets},
        "log_dir": display_path(log_dir),
    }
    resumed = None
    if previous is not None:
        before = previous.document.get("resumed")
        attempts = list(before["attempts"]) if before else [first_attempt(previous)]
        for earlier in attempts:
            # Attempts that did not record their limit ran before it changed.
            earlier.setdefault("candidate_max_tokens", LEGACY_CANDIDATE_MAX_TOKENS)
        config["log_dir"] = attempts[0]["log_dir"]
        totals = {
            name: sum(c[name] for c in attempt.counts.values())
            for name in ("reused", "rescored", "run", "rerun_truncated")
        }
        record: dict[str, Any] = {
            "started_at": started_at,
            "generated_at": None,  # set below, equal to the document's generated_at
            "status": status,
            "incomplete_reason": incomplete_reason,
            "cost_usd": float(guard.spent - carried_total),
            "log_dir": display_path(log_dir),
            "prices_retrieved_at": catalog.retrieved_at if catalog is not None and not mock else None,
            "candidate_max_tokens": settings.candidate_max_tokens,
            "dataset_check": dataset_check,
            "sample_epochs": totals,
            "tests": attempt.counts,
        }
        truncation_rerun = (before or {}).get("truncation_rerun")
        if totals["rerun_truncated"]:
            record["truncation_rerun"] = {
                "old_limit": min(attempt.rerun_limits),
                "new_limit": settings.candidate_max_tokens,
                "n_rerun": totals["rerun_truncated"],
            }
            # Over every attempt: a second rerun adds to the first.
            earlier = truncation_rerun or {"old_limit": min(attempt.rerun_limits), "n_rerun": 0}
            truncation_rerun = {
                "old_limit": min(earlier["old_limit"], min(attempt.rerun_limits)),
                "new_limit": settings.candidate_max_tokens,
                "n_rerun": earlier["n_rerun"] + totals["rerun_truncated"],
            }
        attempts.append(record)
        resumed = {"count": len(attempts) - 1, "attempts": attempts}
        if truncation_rerun:
            resumed["truncation_rerun"] = truncation_rerun
    document = build_document(
        # A run with --limit covers only part of each test. It is never ranked or published.
        run_kind="mock" if mock else ("smoke" if settings.limit is not None else "live"),
        status=status,
        incomplete_reason=incomplete_reason,
        model=model_block,
        config=config,
        judges=judge_ids,
        judge_info=judge_info,
        explanation_status=explanation_status,
        guard=guard,
        outcomes=outcomes,
        blocks_not_run=not_run,
        started_at=previous.document["started_at"] if previous is not None else started_at,
        resumed=resumed,
    )
    if resumed is not None:
        resumed["attempts"][-1]["generated_at"] = document["generated_at"]
        if "corrections" in previous.document:  # notes on hand edits stay with the file
            document["corrections"] = previous.document["corrections"]
        # A resume continues the protocol it started under. build_document stamps new runs as v2.
        document["methodology"] = methodology_of(previous.document)
    return RunResult(document=document, output=output, status=status, outcomes=outcomes)


def _run_test(
    dataset: DatasetFile,
    previous: PreviousRun | None,
    context: RunContext,
    settings: _Settings,
    explanation_status: str,
    model_arg: str | Model,
    log_dir: Path,
    attempt: _Attempt,
    build_task: Any,
) -> tuple[Any, list[Any]]:
    """Run one test, or in a resumed run only its missing sample-epochs.

    Returns the Inspect log of this attempt (None when nothing had to run) and
    the samples the results are built from."""
    eval_args: dict[str, Any] = dict(
        model=model_arg,
        log_dir=str(log_dir),
        log_format="json",
        display="none",
        fail_on_error=False,
        # One retry layer per failure kind: Inspect retries transient errors and
        # 429 inside each call (max_retries in the call config); the cost guard
        # pauses the whole run on 402 and on a 429 Inspect gave up on. Retrying
        # whole samples would repeat calls that already succeeded, so it is off.
        retry_on_error=0,
        max_connections=BATCH_MAX_CONNECTIONS if settings.batch else MAX_CONNECTIONS,
    )
    if previous is None:
        log = inspect_eval(build_task(dataset, settings.epochs), limit=settings.limit, **eval_args)[0]
        return log, list(log.samples or [])

    plan = plan_test(
        previous,
        dataset,
        epochs=settings.epochs,
        limit=settings.limit,
        explanation_scored=explanation_status == EXPLANATION_SCORED,
        rerun_below=settings.rerun_below,
    )
    attempt.counts[dataset.name] = plan.counts()
    attempt.rerun_limits.update(plan.truncated.values())
    to_eval = plan.items_to_eval()
    if not to_eval:
        return None, merge_samples(plan)
    pending = set(to_eval)
    context.replay = {
        key: Replay(sample=sample, score=score_of(sample))
        for key, sample in plan.reuse.items()
        if key[0] in pending
    }
    context.replay.update(
        {key: Replay(sample=sample, score=None) for key, sample in plan.rescore.items() if key[0] in pending}
    )
    try:
        task = build_task(dataset, settings.epochs)
        # Scoped as task:id, so an id with a colon in it is never read as a task selector.
        log = inspect_eval(task, sample_id=[f"{task.name}:{item}" for item in to_eval], **eval_args)[0]
    finally:
        context.replay = {}
    return log, merge_samples(plan, log)
