"""The run context: the cost guard, the candidate, the judges, and replays.

Inspect builds solvers and scorers without arguments from the harness, so the
run's shared state sits in one module-level slot set by the runner (or a test)
before ``eval`` is called.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from inspect_ai.model import Model

from teanga_bench.cost import CostGuard

CANDIDATE_MAX_TOKENS = 16000
LOW_REASONING_MAX_TOKENS = 4096
JUDGE_MAX_TOKENS = 1024
JUDGE_RETRIES = 3

REASONING_EFFORT_VALUES = ("minimal", "low", "medium", "high", "none", "default")
DEFAULT_REASONING_EFFORT = "low"
# Fallback reasoning token budgets for models that expose OpenRouter's
# `reasoning` parameter without `reasoning_effort` (for example qwen3.8-flash).
REASONING_TOKEN_BUDGETS = {
    "minimal": 256,
    "low": 512,
    "medium": 2048,
    "high": 8192,
}

# Store key the solver sets once every candidate call of a sample has returned.
# A resumed run reuses the candidate output of an errored sample only when it is set.
CANDIDATE_DONE_KEY = "teanga_candidate_done"
# Store keys the solver sets with it: whether any candidate call of the sample
# stopped at the answer limit, and the limit the calls were made with.
TRUNCATED_KEY = "teanga_candidate_truncated"
TOKEN_LIMIT_KEY = "teanga_candidate_max_tokens"
# Stop reasons that mean the answer limit cut the reply short. Inspect reports
# "max_tokens"; "length" is the OpenAI-style name some providers pass through.
TRUNCATION_STOP_REASONS = frozenset({"max_tokens", "length"})
# The candidate limit of every run before the limit was recorded per sample-epoch.
LEGACY_CANDIDATE_MAX_TOKENS = 2048


def stopped_at_limit(output: Any) -> bool:
    """True when a model output stopped because it reached its max_tokens."""
    return output is not None and output.stop_reason in TRUNCATION_STOP_REASONS


@dataclass
class JudgeSpec:
    id: str
    family: str
    model: str | Model  # an Inspect model string, or a ready Model (tests)


@dataclass
class Replay:
    """A sample-epoch from an earlier attempt of a resumed run.

    The solver restores its candidate output instead of calling the model.
    The scorer returns ``score`` when it is set; when it is None (the judges
    or the scorer did not finish) the sample is scored again.
    """

    sample: Any  # inspect_ai.log.EvalSample
    score: Any | None  # inspect_ai.scorer.Score


@dataclass
class RunContext:
    guard: CostGuard
    candidate_id: str
    judges: list[JudgeSpec] = field(default_factory=list)
    max_tokens: int = CANDIDATE_MAX_TOKENS
    judge_max_tokens: int = JUDGE_MAX_TOKENS
    judge_retries: int = JUDGE_RETRIES
    reasoning_effort: str | None = None
    reasoning_tokens: int | None = None
    batch: bool = False
    replay: dict[tuple[str, int], Replay] = field(default_factory=dict)


_CURRENT: RunContext | None = None


def set_context(context: RunContext | None) -> None:
    global _CURRENT
    _CURRENT = context


def current() -> RunContext:
    if _CURRENT is None:
        raise RuntimeError("No run context. Run benchmarks through `teanga-bench run`.")
    return _CURRENT
