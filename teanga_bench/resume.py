"""Resume an unfinished run: reuse every scored sample-epoch, run only the rest.

The results file of a run names its tests, settings, spend and log folders, and
its Inspect logs hold every sample-epoch. For each test, a resume sorts each
sample-epoch of the current dataset into one of three groups:

- ``reuse``: an earlier attempt scored it (for tutor items, with the judges'
  verdicts). Nothing is called again.
- ``rescore``: the candidate output is complete but the scoring is not, for
  example a judge was refused for lack of credit. The saved candidate output is
  reused and the item is scored again, judges included.
- ``run``: everything else, asked from scratch.

Inspect's own ``eval_retry`` is not used. It rebuilds tasks from the registry,
which the data-driven tasks here are not in, keeps a sample whenever it has no
error even when a judge was refused for credit, and knows nothing of the cost
already spent. The merge here is small and keeps those rules in one place.

A resume refuses to run when a dataset file changed since the first attempt.
Results files record a sha256 of each dataset file in ``config.dataset_hashes``.
Older files have no hash, so their item ids and count are compared instead.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from inspect_ai.log import EvalSample, read_eval_log

from teanga_bench.context import CANDIDATE_DONE_KEY
from teanga_bench.cost import Usage
from teanga_bench.datasets import DatasetFile, read_items
from teanga_bench.export import EXPLANATION_SCORED, REASON_CAP, REASON_CREDIT, REASON_ERRORS, score_of
from teanga_bench.paths import REPO_ROOT, safe_name
from teanga_bench.pricing import Catalog, PricingError

REUSE = "reuse"
RESCORE = "rescore"
RUN = "run"

DATASET_CHECK_HASH = "dataset_hash"
DATASET_CHECK_IDS = "item_ids_and_count"

# Logs created this long before the first attempt started, or after the last
# attempt wrote its results, belong to some other run.
LOG_WINDOW = timedelta(minutes=2)
_DIR_STAMP = re.compile(r"^(?P<model>.+)-(?P<stamp>\d{8}T\d{6}Z)$")
_CREDIT_TEXT = re.compile(r"Error code: (402|429)\b|CreditExhausted")
_PROVIDER_PREFIX = "openrouter/"
# Fewer completed sample-epochs than this in a test: estimate from the whole run instead.
MIN_SAMPLES_FOR_ESTIMATE = 10


class ResumeError(RuntimeError):
    """The run cannot be resumed."""


def dataset_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def display_path(path: Path) -> str:
    """A path for the results file: relative to the repo when inside it."""
    resolved = path.resolve()
    return str(resolved.relative_to(REPO_ROOT)) if resolved.is_relative_to(REPO_ROOT) else str(resolved)


def item_ids(dataset: DatasetFile, limit: int | None) -> list[str]:
    ids = [str(item["id"]) for item in read_items(dataset.path)]
    return ids if limit is None else ids[:limit]


def _when(text: str) -> datetime:
    return datetime.fromisoformat(text)


@dataclass
class LogRef:
    path: Path
    created: datetime
    test: str  # suite/test
    filtered: bool  # ran on a subset of sample ids (a resume attempt)
    sample_ids: list[str]


@dataclass
class PreviousRun:
    results_path: Path
    document: dict[str, Any]
    log_dirs: list[Path]
    logs: dict[str, list[LogRef]]  # suite/test -> logs, oldest first

    @property
    def config(self) -> dict[str, Any]:
        return self.document["config"]

    def block(self, name: str) -> dict[str, Any] | None:
        suite, test = name.split("/", 1)
        return self.document.get("suites", {}).get(suite, {}).get("tests", {}).get(test)


def load_previous_run(results_path: Path, model: str, search_dirs: list[Path]) -> PreviousRun:
    """Read the results file of ``model`` and find its Inspect logs.

    Log folders recorded in the results are used first. Results written before
    folders were recorded fall back to ``<model>-<UTC stamp>`` folders under
    ``search_dirs`` whose stamp falls inside the run, or a search dir that holds
    the logs itself."""
    if not results_path.is_file():
        raise ResumeError(f"no results file at {results_path} to resume")
    document = json.loads(results_path.read_text(encoding="utf-8"))
    if document.get("model", {}).get("id") != model:
        raise ResumeError(f"{results_path} is a run of {document.get('model', {}).get('id')!r}, not {model!r}")
    dirs = _log_dirs(document, model, search_dirs)
    return PreviousRun(results_path=results_path, document=document, log_dirs=dirs, logs=_index_logs(dirs, document))


def _recorded_dirs(document: dict[str, Any]) -> list[str]:
    recorded = [document.get("config", {}).get("log_dir")]
    recorded += [attempt.get("log_dir") for attempt in (document.get("resumed") or {}).get("attempts", [])]
    return [entry for entry in recorded if entry]


def _log_dirs(document: dict[str, Any], model: str, search_dirs: list[Path]) -> list[Path]:
    found: list[Path] = []
    recorded = _recorded_dirs(document)
    for entry in recorded:
        path = Path(entry)
        options = [path] if path.is_absolute() else [REPO_ROOT / path]
        options += [directory / path.name for directory in search_dirs]
        options += [directory for directory in search_dirs if directory.name == path.name]
        found += [option for option in options if option.is_dir()]
    if not recorded:
        low = _when(document["started_at"]) - LOG_WINDOW
        high = _when(document["generated_at"]) + LOG_WINDOW
        for directory in search_dirs:
            if not directory.is_dir():
                continue
            if any(directory.glob("*.json")) or any(directory.glob("*.eval")):
                found.append(directory)
            for sub in sorted(directory.iterdir()):
                match = _DIR_STAMP.match(sub.name)
                if not (sub.is_dir() and match and match["model"] == safe_name(model)):
                    continue
                stamp = datetime.strptime(match["stamp"], "%Y%m%dT%H%M%SZ").replace(tzinfo=low.tzinfo)
                if low <= stamp <= high:
                    found.append(sub)
    unique: dict[Path, Path] = {}
    for path in found:
        unique.setdefault(path.resolve(), path)
    return list(unique.values())


def _index_logs(dirs: list[Path], document: dict[str, Any]) -> dict[str, list[LogRef]]:
    inspect_id = document["model"]["inspect_id"]
    tests = set(document["config"]["tests"])
    low = _when(document["started_at"]) - LOG_WINDOW
    high = _when(document["generated_at"]) + LOG_WINDOW
    logs: dict[str, list[LogRef]] = defaultdict(list)
    seen: set[Path] = set()
    for directory in dirs:
        for path in sorted([*directory.glob("*.json"), *directory.glob("*.eval")]):
            if path.resolve() in seen:
                continue
            seen.add(path.resolve())
            try:
                header = read_eval_log(str(path), header_only=True)
            except Exception:
                continue  # not an Inspect log
            meta = header.eval.metadata or {}
            name = f"{meta.get('suite')}/{meta.get('test')}"
            created = _when(header.eval.created)
            if header.eval.model != inspect_id or name not in tests or not low <= created <= high:
                continue
            logs[name].append(
                LogRef(
                    path=path,
                    created=created,
                    test=name,
                    filtered=header.eval.config.sample_id is not None,
                    sample_ids=[str(i) for i in (header.eval.dataset.sample_ids or [])],
                )
            )
    for refs in logs.values():
        refs.sort(key=lambda ref: ref.created)
    return dict(logs)


def check_datasets(previous: PreviousRun, datasets: list[DatasetFile], limit: int | None) -> str:
    """Refuse when a dataset changed since the first attempt. Returns how it was checked."""
    hashes = previous.config.get("dataset_hashes")
    if hashes is not None:
        changed = [d.name for d in datasets if hashes.get(d.name) != dataset_hash(d.path)]
        if changed:
            raise ResumeError(
                "dataset file(s) changed since the first attempt: "
                + ", ".join(changed)
                + ". Results from different datasets cannot be merged; start a fresh run without --resume."
            )
        return DATASET_CHECK_HASH
    problems: list[str] = []
    for dataset in datasets:
        current = item_ids(dataset, limit)
        block = previous.block(dataset.name)
        if block is not None:
            if block.get("dataset") != dataset.kind:
                problems.append(f"{dataset.name} was {block.get('dataset')}, now {dataset.kind}")
            if block.get("n_items_dataset") != len(current):
                problems.append(f"{dataset.name} had {block.get('n_items_dataset')} items, now {len(current)}")
        first = [ref for ref in previous.logs.get(dataset.name, []) if not ref.filtered]
        if first:
            earlier = set().union(*(set(ref.sample_ids) for ref in first))
            everything = set(item_ids(dataset, None))
            if earlier not in (set(current), everything):
                problems.append(f"{dataset.name} item ids differ from the first attempt")
    if problems:
        raise ResumeError(
            "the datasets changed since the first attempt (no dataset hash was recorded then, "
            "so item ids and counts were compared): " + "; ".join(problems)
            + ". Start a fresh run without --resume."
        )
    return DATASET_CHECK_IDS


def _judge_refused(score: Any) -> bool:
    verdicts = (score.metadata or {}).get("judge_verdicts") or []
    return any(_CREDIT_TEXT.search(str(verdict.get("error") or "")) for verdict in verdicts)


def classify(sample: EvalSample, explanation_scored: bool) -> str:
    score = score_of(sample)
    if sample.error is None and score is not None:
        if explanation_scored and _judge_refused(score):
            return RESCORE
        return REUSE
    if (sample.store or {}).get(CANDIDATE_DONE_KEY) and sample.output is not None:
        return RESCORE
    return RUN


@dataclass
class TestPlan:
    name: str
    item_ids: list[str]
    epochs: int
    reuse: dict[tuple[str, int], EvalSample | None] = field(default_factory=dict)
    rescore: dict[tuple[str, int], EvalSample | None] = field(default_factory=dict)
    usage: dict[str, Usage] = field(default_factory=lambda: defaultdict(Usage))
    usage_samples: int = 0  # reused sample-epochs that called the candidate, behind ``usage``

    def keys(self) -> list[tuple[str, int]]:
        return [(item, epoch) for item in self.item_ids for epoch in range(1, self.epochs + 1)]

    @property
    def run(self) -> list[tuple[str, int]]:
        return [key for key in self.keys() if key not in self.reuse and key not in self.rescore]

    def counts(self) -> dict[str, int]:
        return {"reused": len(self.reuse), "rescored": len(self.rescore), "run": len(self.run)}

    def items_to_eval(self) -> list[str]:
        pending = set(self.rescore) | set(self.run)
        return [item for item in self.item_ids if any((item, e) in pending for e in range(1, self.epochs + 1))]


def _slim(sample: EvalSample) -> EvalSample:
    return sample.model_copy(update={"events": [], "attachments": {}, "events_data": None})


def plan_test(
    previous: PreviousRun,
    dataset: DatasetFile,
    *,
    epochs: int,
    limit: int | None,
    explanation_scored: bool,
    keep_samples: bool = True,
) -> TestPlan:
    """Sort every sample-epoch of one test into reuse, rescore and run.

    Later logs win over earlier ones, and a reusable sample over one to rescore."""
    plan = TestPlan(name=dataset.name, item_ids=item_ids(dataset, limit), epochs=epochs)
    wanted = set(plan.item_ids)
    candidate_model = previous.document["model"]["inspect_id"]
    for ref in previous.logs.get(dataset.name, []):
        log = read_eval_log(str(ref.path), resolve_attachments="core")
        for sample in log.samples or []:
            key = (str(sample.id), int(sample.epoch))
            if key[0] not in wanted or not 1 <= key[1] <= epochs:
                continue
            kind = classify(sample, explanation_scored)
            kept = _slim(sample) if keep_samples else None
            if kind == REUSE:
                plan.rescore.pop(key, None)
                plan.reuse[key] = kept
                if candidate_model in (sample.model_usage or {}):
                    plan.usage_samples += 1
                    for model_name, usage in sample.model_usage.items():
                        plan.usage[model_name].add(
                            Usage(
                                calls=0,
                                input_tokens=int(usage.input_tokens or 0),
                                output_tokens=int(usage.output_tokens or 0),
                                cache_read_tokens=int(usage.input_tokens_cache_read or 0),
                                cache_write_tokens=int(usage.input_tokens_cache_write or 0),
                            )
                        )
            elif kind == RESCORE and key not in plan.reuse:
                plan.rescore[key] = kept
        del log
    return plan


def carried_cost(document: dict[str, Any]) -> tuple[dict[tuple[str, str], Usage], dict[str, Usage], Decimal]:
    """Spend of the earlier attempts: by (suite/test, role), by model, and in total.

    Results written before dataset hashes were recorded booked spend under the
    bare test name, so a later test with the same name (tonada/tutor_accuracy
    after blas/tutor_accuracy) also counted the earlier one. That is undone here."""
    config = document["config"]
    legacy = "dataset_hashes" not in config
    by_test: dict[tuple[str, str], Usage] = {}
    cumulative: dict[tuple[str, str], Usage] = {}
    for name in config["tests"]:
        suite, test = name.split("/", 1)
        block = document.get("suites", {}).get(suite, {}).get("tests", {}).get(test) or {}
        cost = block.get("cost")
        if not cost:
            continue
        for role in ("candidate", "judge"):
            usage = Usage.from_dict(cost.get(role) or {})
            if legacy:
                earlier = cumulative.get((test, role))
                cumulative[(test, role)] = usage
                if earlier is not None:
                    usage = usage.minus(earlier)
            by_test[(name, role)] = usage
    by_model = {name: Usage.from_dict(usage) for name, usage in document["cost"].get("by_model", {}).items()}
    return by_test, by_model, Decimal(str(document["cost"]["total_usd"]))


def first_attempt(previous: PreviousRun) -> dict[str, Any]:
    """The attempt record for a results file that was never resumed."""
    document = previous.document
    reason = document.get("incomplete_reason")
    if "incomplete_reason" not in document and document["status"] != "complete":
        # Written before the run-level reason existed.
        errors = " ".join(
            str(block.get("first_error") or "")
            for suite in document.get("suites", {}).values()
            for block in suite.get("tests", {}).values()
        )
        if document["status"] == "cost_cap_reached":
            reason = REASON_CAP
        elif _CREDIT_TEXT.search(errors):
            reason = REASON_CREDIT
        else:
            reason = REASON_ERRORS
    log_dir = document["config"].get("log_dir")
    if log_dir is None and previous.log_dirs:
        log_dir = display_path(previous.log_dirs[0])
    pricing = document["model"].get("pricing") or {}
    return {
        "started_at": document["started_at"],
        "generated_at": document["generated_at"],
        "status": document["status"],
        "incomplete_reason": reason,
        "cost_usd": document["cost"]["total_usd"],
        "log_dir": log_dir,
        "prices_retrieved_at": pricing.get("retrieved_at"),
    }


# --- resume-plan -------------------------------------------------------------


def _price_per_sample(
    usage: dict[str, Usage], samples: int, candidate_model: str, catalog: Catalog | None
) -> tuple[Decimal, Decimal, list[str]]:
    """Average candidate and judge cost of one sample-epoch at live prices."""
    candidate = judge = Decimal(0)
    missing: list[str] = []
    if samples == 0:
        return candidate, judge, missing
    for model_name, total in usage.items():
        model_id = model_name.removeprefix(_PROVIDER_PREFIX)
        if catalog is None:
            continue
        try:
            price = catalog.pricing(model_id)
        except PricingError:
            missing.append(model_id)
            continue
        cost = price.cost(total.input_tokens, total.output_tokens, total.cache_read_tokens, total.cache_write_tokens)
        if model_name == candidate_model:
            candidate += cost / samples
        else:
            judge += cost / samples
    return candidate, judge, missing


def _usd(value: Decimal | float) -> str:
    amount = float(value)
    return f"${amount:,.4f}" if abs(amount) < 1 else f"${amount:,.2f}"


def resume_plan_report(
    previous: PreviousRun, datasets: list[DatasetFile], catalog: Catalog | None
) -> tuple[list[str], bool]:
    """Lines describing what ``run --resume`` would do, and whether it may run."""
    document = previous.document
    config = previous.config
    epochs, limit = int(config["epochs"]), config.get("limit")
    lines = [
        f"Resume plan for {document['model']['id']}",
        f"Results: {previous.results_path} (status {document['status']}, spent "
        f"{_usd(document['cost']['total_usd'])} of the {_usd(document['cost']['cap_usd'])} cap)",
    ]
    n_logs = sum(len(refs) for refs in previous.logs.values())
    lines.append(f"Logs: {n_logs} file(s) in " + (", ".join(str(d) for d in previous.log_dirs) or "no folder found"))
    if document["status"] == "complete":
        lines.append("The run is complete. Nothing to resume.")
        return lines, False
    try:
        check = check_datasets(previous, datasets, limit)
    except ResumeError as exc:
        lines.append(f"Resume would be refused: {exc}")
        return lines, False
    lines.append(
        "Datasets: unchanged (sha256 of each file)"
        if check == DATASET_CHECK_HASH
        else "Datasets: item ids and counts match the first attempt (no dataset hash was recorded then)"
    )
    lines.append(
        "Prices: " + (f"live, read {catalog.retrieved_at}" if catalog is not None else "none (mock run)")
    )
    explanation_scored = document.get("explanation_status") == EXPLANATION_SCORED
    candidate_model = document["model"]["inspect_id"]
    plans = [
        plan_test(previous, dataset, epochs=epochs, limit=limit, explanation_scored=explanation_scored, keep_samples=False)
        for dataset in datasets
    ]
    pooled: dict[str, Usage] = defaultdict(Usage)
    for plan in plans:
        for model_name, usage in plan.usage.items():
            pooled[model_name].add(usage)
    pooled_samples = sum(plan.usage_samples for plan in plans)

    header = f"{'test':<26}{'reuse':>7}{'rescore':>9}{'run':>7}{'total':>7}{'est. cost':>12}"
    lines += ["", header, "-" * len(header)]
    totals = defaultdict(int)
    estimate = Decimal(0)
    missing: set[str] = set()
    fallback = False
    for plan in plans:
        usage, samples, mark = plan.usage, plan.usage_samples, ""
        if samples < MIN_SAMPLES_FOR_ESTIMATE and (plan.run or plan.rescore):
            usage, samples, mark, fallback = pooled, pooled_samples, "*", True
        candidate, judge, gone = _price_per_sample(usage, samples, candidate_model, catalog)
        missing.update(gone)
        cost = (candidate + judge) * len(plan.run) + judge * len(plan.rescore)
        estimate += cost
        counts = plan.counts()
        for name, value in counts.items():
            totals[name] += value
        totals["total"] += len(plan.keys())
        lines.append(
            f"{plan.name:<26}{counts['reused']:>7}{counts['rescored']:>9}{counts['run']:>7}"
            f"{len(plan.keys()):>7}{_usd(cost) + mark:>12}"
        )
    lines.append("-" * len(header))
    lines.append(
        f"{'all tests':<26}{totals['reused']:>7}{totals['rescored']:>9}{totals['run']:>7}"
        f"{totals['total']:>7}{_usd(estimate):>12}"
    )
    lines.append("")
    lines.append(
        "reuse: scored before, not called again. rescore: candidate output reused, scored again "
        "(judges included). run: asked from scratch."
    )
    lines.append(
        "est. cost: sample-epochs to run times the average candidate plus judge cost of a completed "
        "sample-epoch of that test, from its logged tokens at live prices; rescores count the judge part only."
    )
    if fallback:
        lines.append(
            f"* fewer than {MIN_SAMPLES_FOR_ESTIMATE} completed sample-epochs in this test, so the "
            "average over all tests of the run is used."
        )
    if missing:
        lines.append(f"Not priced (missing from the live model list): {', '.join(sorted(missing))}")
    spent = Decimal(str(document["cost"]["total_usd"]))
    cap = Decimal(str(document["cost"]["cap_usd"]))
    lines.append(
        f"Spent so far {_usd(spent)}; estimated total after resume {_usd(spent + estimate)} "
        f"against the {_usd(cap)} cap."
    )
    if spent + estimate > cap:
        lines.append("The estimate passes the cap: pass a higher --max-cost to the resume.")
    return lines, True
