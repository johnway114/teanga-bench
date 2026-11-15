"""The run context: the cost guard, the candidate, and the judges.

Inspect builds solvers and scorers without arguments from the harness, so the
run's shared state sits in one module-level slot set by the runner (or a test)
before ``eval`` is called.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from inspect_ai.model import Model

from teanga_bench.cost import CostGuard

CANDIDATE_MAX_TOKENS = 2048
JUDGE_MAX_TOKENS = 1024
JUDGE_RETRIES = 3


@dataclass
class JudgeSpec:
    id: str
    family: str
    model: str | Model  # an Inspect model string, or a ready Model (tests)


@dataclass
class RunContext:
    guard: CostGuard
    candidate_id: str
    judges: list[JudgeSpec] = field(default_factory=list)
    max_tokens: int = CANDIDATE_MAX_TOKENS
    judge_max_tokens: int = JUDGE_MAX_TOKENS
    judge_retries: int = JUDGE_RETRIES


_CURRENT: RunContext | None = None


def set_context(context: RunContext | None) -> None:
    global _CURRENT
    _CURRENT = context


def current() -> RunContext:
    if _CURRENT is None:
        raise RuntimeError("No run context. Run benchmarks through `teanga-bench run`.")
    return _CURRENT
