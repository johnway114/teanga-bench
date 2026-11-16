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

CANDIDATE_MAX_TOKENS = 2048
JUDGE_MAX_TOKENS = 1024
JUDGE_RETRIES = 3

# Store key the solver sets once every candidate call of a sample has returned.
# A resumed run reuses the candidate output of an errored sample only when it is set.
CANDIDATE_DONE_KEY = "teanga_candidate_done"


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
    replay: dict[tuple[str, int], Replay] = field(default_factory=dict)


_CURRENT: RunContext | None = None


def set_context(context: RunContext | None) -> None:
    global _CURRENT
    _CURRENT = context


def current() -> RunContext:
    if _CURRENT is None:
        raise RuntimeError("No run context. Run benchmarks through `teanga-bench run`.")
    return _CURRENT
