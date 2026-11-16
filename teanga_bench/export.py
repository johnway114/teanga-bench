"""Build the results JSON for one run from Inspect logs and the cost ledger.

The schema is ``docs/results-schema.md``. Failure examples come only from
items that are published in ``samples/``; private items never appear.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import inspect_ai

from teanga_bench import BENCHMARK, BENCHMARK_NAME, __version__
from teanga_bench.cost import CostGuard
from teanga_bench.datasets import DatasetFile
from teanga_bench.stats import ItemResult, breakdown, group_stats, pooled

SCHEMA_VERSION = "2.0.0"
FAILURE_LIMIT = 3
TEXT_LIMIT = 500
ATTRIBUTES = ("language", "l1", "phenomenon", "cefr", "evidence")
BREAKDOWN_KEYS = {
    "language": "by_language",
    "l1": "by_l1",
    "phenomenon": "by_phenomenon",
    "cefr": "by_cefr",
    "evidence": "by_evidence",
}
EXPLANATION_LABEL = "judge-marked, not human-validated"
CAP_MARKER = "CostCapReached"
CREDIT_MARKER = "CreditExhausted"
REASON_CAP = "cost_cap_reached"
REASON_CREDIT = "insufficient_credit"
REASON_ERRORS = "errors"
EXPLANATION_SCORED = "scored"
EXPLANATION_SAME_FAMILY = "not_scored_same_family_as_judge"
EXPLANATION_JUDGE_UNAVAILABLE = "not_scored_judge_unavailable"


@dataclass
class TestRun:
    """One test's result block plus the item scores used for pooling."""

    block: dict[str, Any]
    items: list[ItemResult]
    cap_hit: bool


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clip(text: str) -> str:
    text = (text or "").replace("\r\n", "\n")
    return text if len(text) <= TEXT_LIMIT else text[: TEXT_LIMIT - 1] + "…"


def _attribute(value: Any) -> str:
    return "unspecified" if value is None else str(value)


def score_of(sample: Any) -> Any:
    scores = sample.scores or {}
    return scores.get("teanga_scorer") or (next(iter(scores.values())) if scores else None)


def _error_text(sample: Any) -> str:
    error = getattr(sample, "error", None)
    if error is None:
        return ""
    return f"{getattr(error, 'message', '')}\n{getattr(error, 'traceback', '')}"


def not_run_block(dataset: DatasetFile, n_items: int, epochs: int, reason: str) -> dict[str, Any]:
    return {
        "suite": dataset.suite,
        "test": dataset.test,
        "dataset": dataset.kind,
        "status": "incomplete",
        "incomplete_reason": reason,
        "n_items": 0,
        "n_items_dataset": n_items,
        "epochs": epochs,
        "score": None,
        "ci95": None,
        "consistency": None,
        "cost_usd": 0.0,
        "cost_per_correct_usd": None,
    }


def build_test_outcome(
    samples: Iterable[Any],
    dataset: DatasetFile,
    *,
    n_items_dataset: int,
    epochs: int,
    guard: CostGuard,
    public: set[str],
    judges: list[str],
    explanation_status: str = EXPLANATION_SCORED,
) -> TestRun:
    """Turn the Inspect samples of one test into the per-test block. The samples
    come from one log, or, in a resumed run, from the logs of every attempt."""
    key = dataset.name
    per_item: dict[str, dict[int, Any]] = defaultdict(dict)
    meta_of: dict[str, dict[str, Any]] = {}
    sample_of: dict[tuple[str, int], Any] = {}
    n_errors = 0
    cap_hit = False
    credit_out = False
    scoring = ""
    first_error: str | None = None
    for sample in samples:
        item_id = str(sample.id)
        meta_of[item_id] = dict(sample.metadata or {})
        scoring = scoring or str(meta_of[item_id].get("scoring", ""))
        score = score_of(sample)
        if getattr(sample, "error", None) is not None or score is None:
            n_errors += 1
            if first_error is None and getattr(sample, "error", None) is not None:
                first_error = str(getattr(sample.error, "message", ""))[:300]
            error_text = _error_text(sample)
            if CAP_MARKER in error_text:
                cap_hit = True
            elif CREDIT_MARKER in error_text:
                credit_out = True
            continue
        per_item[item_id][int(sample.epoch)] = score
        sample_of[(item_id, int(sample.epoch))] = sample

    items: list[ItemResult] = []
    for item_id, by_epoch in sorted(per_item.items()):
        if len(by_epoch) != epochs:
            continue  # incomplete item: every epoch must have a score
        meta = meta_of[item_id]
        items.append(
            ItemResult(
                id=item_id,
                epoch_scores=tuple(float(by_epoch[e].value) for e in sorted(by_epoch)),
                attributes={name: _attribute(meta.get(name)) for name in ATTRIBUTES},
            )
        )

    candidate = guard.total(test=key, role="candidate")
    judge = guard.total(test=key, role="judge")
    cost = candidate.cost_usd + judge.cost_usd
    stats = group_stats(items, key, epochs)
    correct_equivalents = (stats["score"] or 0.0) * len(items) * epochs
    cost_per_correct = float(cost) / correct_equivalents if correct_equivalents > 0 else None

    complete = len(items) == n_items_dataset and n_errors == 0
    reason = None
    if not complete:
        if cap_hit:
            reason = REASON_CAP
        elif credit_out:
            reason = REASON_CREDIT
        else:
            reason = REASON_ERRORS if n_errors else "missing_samples"
    block: dict[str, Any] = {
        "suite": dataset.suite,
        "test": dataset.test,
        "scoring": scoring,
        "dataset": dataset.kind,
        "status": "complete" if complete else "incomplete",
        "incomplete_reason": reason,
        "first_error": first_error,
        "n_items_dataset": n_items_dataset,
        "n_errors": n_errors,
        **stats,
        "cost_usd": float(cost),
        "cost_per_correct_usd": cost_per_correct,
        "cost": {
            "candidate": candidate.as_dict(),
            "judge": judge.as_dict(),
        },
        "n_human_checked": sum(1 for item in items if meta_of[item.id].get("human_checked") is True),
    }
    for attribute, field in BREAKDOWN_KEYS.items():
        block[field] = breakdown(items, attribute, key, epochs)
    if scoring == "tutor":
        block["tutor"] = _tutor_block(items, per_item, key, epochs, judges, explanation_status)
    block["failure_examples"] = _failure_examples(items, per_item, sample_of, meta_of, public)
    return TestRun(block=block, items=items, cap_hit=cap_hit)


def _tutor_block(
    items: list[ItemResult],
    per_item: dict[str, dict[int, Any]],
    key: str,
    epochs: int,
    judges: list[str],
    explanation_status: str,
) -> dict[str, Any]:
    component_scores: dict[str, list[float]] = {"found": [], "fixed": [], "no_overcorrection": []}
    explanation_items: list[ItemResult] = []
    judged = unscored = agree = failures = 0
    for item in items:
        by_epoch = per_item[item.id]
        for name in component_scores:
            values = [float(by_epoch[e].metadata[name]) for e in by_epoch]
            component_scores[name].append(sum(values) / len(values))
        if explanation_status != EXPLANATION_SCORED:
            continue
        scored: list[float] = []
        for score in by_epoch.values():
            meta = score.metadata
            failures += int(meta.get("judge_failures") or 0)
            if meta.get("explanation") is None:
                unscored += 1
                continue
            scored.append(float(meta["explanation"]))
            if meta.get("judge_agree") is not None:
                judged += 1
                agree += int(bool(meta["judge_agree"]))
        if scored:
            explanation_items.append(
                ItemResult(item.id, tuple(scored), item.attributes)
            )
    if explanation_status != EXPLANATION_SCORED:
        explanation = {"score": None, "ci95": None, "n_items": 0, "epochs": epochs}
    else:
        explanation = group_stats(explanation_items, f"{key}|explanation", epochs)
        explanation.pop("consistency", None)
    return {
        "headline": "rule-only: found AND fixed AND no over-correction",
        "judges": judges,
        "components": {
            name: (sum(values) / len(values) if values else None)
            for name, values in component_scores.items()
        },
        "explanation": {
            "label": EXPLANATION_LABEL,
            "status": explanation_status,
            **explanation,
            "judged_item_epochs": judged,
            "unscored_item_epochs": unscored,
            "judge_agreement": (agree / judged) if judged else None,
            "judge_failures": failures,
        },
    }


def _failure_examples(
    items: list[ItemResult],
    per_item: dict[str, dict[int, Any]],
    sample_of: dict[tuple[str, int], Any],
    meta_of: dict[str, dict[str, Any]],
    public: set[str],
) -> list[dict[str, Any]]:
    """Lowest-scoring public items. Items not in samples/ are never listed."""
    candidates = sorted(
        (item for item in items if item.id in public and item.score < 1.0),
        key=lambda item: (item.score, item.id),
    )
    examples = []
    for item in candidates[:FAILURE_LIMIT]:
        epoch = min(per_item[item.id], key=lambda e: (float(per_item[item.id][e].value), e))
        sample = sample_of[(item.id, epoch)]
        score = per_item[item.id][epoch]
        target = sample.target[0] if isinstance(sample.target, list) and sample.target else sample.target
        example = {
            "id": item.id,
            "public": True,
            "language": meta_of[item.id].get("language"),
            "l1": meta_of[item.id].get("l1"),
            "phenomenon": meta_of[item.id].get("phenomenon"),
            "input": _clip(sample.input if isinstance(sample.input, str) else str(sample.input)),
            "expected": _clip(str(target)),
            "output": _clip((sample.output.completion if sample.output else "") or score.answer or ""),
            "score": float(score.value),
        }
        if "pivot_text" in (score.metadata or {}):
            example["pivot_text"] = _clip(str(score.metadata["pivot_text"]))
        examples.append(example)
    return examples


def pool_overall(outcomes: list[TestRun]) -> dict[str, Any] | None:
    """Score over complete tests, each test weighted equally."""
    done = [o for o in outcomes if o.block["status"] == "complete" and o.items]
    parts = [([i.score for i in o.items], o.block["suite"] + "/" + o.block["test"]) for o in done]
    result = pooled(parts)
    if result is None:
        return None
    languages = sorted({i.attributes["language"] for o in done for i in o.items})
    by_language = {}
    for language in languages:
        language_parts = [
            (
                [i.score for i in o.items if i.attributes["language"] == language],
                f"{o.block['suite']}/{o.block['test']}|language={language}",
            )
            for o in done
        ]
        stat = pooled(language_parts)
        if stat is not None:
            by_language[language] = stat
    return {**result, "by_language": by_language}


def pool_suite(outcomes: list[TestRun], suite: str) -> dict[str, Any] | None:
    result = pool_overall([o for o in outcomes if o.block["suite"] == suite])
    if result is not None:
        result.pop("by_language", None)
    return result


def build_document(
    *,
    run_kind: str,
    status: str,
    incomplete_reason: str | None,
    model: dict[str, Any],
    config: dict[str, Any],
    judges: list[str],
    judge_info: dict[str, Any],
    explanation_status: str,
    guard: CostGuard,
    outcomes: list[TestRun],
    blocks_not_run: list[dict[str, Any]],
    started_at: str,
    resumed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    suites: dict[str, dict[str, Any]] = {}
    for block in [o.block for o in outcomes] + blocks_not_run:
        suites.setdefault(block["suite"], {"tests": {}})["tests"][block["test"]] = block
    for suite_name, suite in suites.items():
        suite["overall"] = pool_suite(outcomes, suite_name)
    candidate = guard.total(role="candidate")
    judge = guard.total(role="judge")
    document = {
        "schema_version": SCHEMA_VERSION,
        "benchmark": BENCHMARK,
        "benchmark_name": BENCHMARK_NAME,
        "benchmark_version": __version__,
        "started_at": started_at,
        "generated_at": now_iso(),
        "run_kind": run_kind,
        "status": status,
        "incomplete_reason": incomplete_reason,
        "model": model,
        "config": config,
        "judges": judges,
        "judge_info": judge_info,
        "explanation_status": explanation_status,
        "gold": {
            "note": (
                "Gold comes from the source files named on each item. Teanga Bench did not "
                "have native-speaker review. An item counts as human-checked only when its "
                "source file records human review. Judge marks on tutor explanations are "
                "made by models and are not human-validated."
            ),
        },
        "cost": {
            "cap_usd": float(guard.max_cost),
            "total_usd": float(guard.spent),
            "candidate_usd": float(candidate.cost_usd),
            "judge_usd": float(judge.cost_usd),
            "cap_reached": guard.stopped,
            "by_model": {name: usage.as_dict() for name, usage in sorted(guard.by_model().items())},
        },
        "overall": pool_overall(outcomes),
        "suites": suites,
        "tool_versions": {"inspect_ai": inspect_ai.__version__},
    }
    if resumed is not None:
        document["resumed"] = resumed
    return document


def write_results(document: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

