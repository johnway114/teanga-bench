"""The Inspect solver and scorer for every Teanga Bench item.

One solver and one scorer cover all items. They read ``metadata.scoring`` from
each sample: ``accept_list``, ``tutor``, ``translation``, or ``round_trip``.
All model calls go through the run's cost guard.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from inspect_ai.model import (
    ChatMessageSystem,
    ChatMessageUser,
    GenerateConfig,
    Model,
    get_model,
)
from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import Generate, TaskState, solver

from teanga_bench.context import (
    CANDIDATE_DONE_KEY,
    TOKEN_LIMIT_KEY,
    TRUNCATED_KEY,
    JudgeSpec,
    RunContext,
    current,
    stopped_at_limit,
)
from teanga_bench.cost import CostCapReached, CreditExhausted
from teanga_bench.scoring import (
    JUDGE_SYSTEM,
    chrf_score,
    extract_translation,
    judge_prompt,
    parse_judge_verdict,
    round_trip_prompt,
    score_closed_answer,
    score_tutor_rules,
    tutor_headline,
)

SYSTEM = (
    "You are taking Teanga Bench, a language benchmark. "
    "Follow the response format in the user message exactly. "
    "Do not reveal hidden reasoning as the answer."
)
CALL_TIMEOUT_SECONDS = 180
CALL_RETRIES = 3

PIVOT_KEY = "pivot_text"
BACK_KEY = "back_translation"


def _config(max_tokens: int, **extra: Any) -> GenerateConfig:
    return GenerateConfig(
        max_tokens=max_tokens, timeout=CALL_TIMEOUT_SECONDS, max_retries=CALL_RETRIES, **extra
    )


def spend_key(metadata: dict[str, Any]) -> str:
    """The ``suite/test`` name that spend is booked under."""
    return f"{metadata.get('suite', '')}/{metadata.get('test', '')}"


def _replay(state: TaskState) -> Any:
    return current().replay.get((str(state.sample_id), int(state.epoch)))


@solver
def teanga_solver():
    """Ask the candidate. Round-trip items take two calls in two conversations.

    The store records whether any candidate call stopped at the answer limit,
    and the limit. In a resumed run, a sample-epoch whose candidate output was
    saved by an earlier attempt is restored from it and the model is not called."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        context = current()
        saved = _replay(state)
        if saved is not None:
            state.messages = list(saved.sample.messages)
            state.output = saved.sample.output
            for key, value in (saved.sample.store or {}).items():
                state.store.set(key, value)
            state.store.set(CANDIDATE_DONE_KEY, True)
            return state
        metadata = state.metadata
        test = spend_key(metadata)
        model = get_model()
        config = _config(context.max_tokens)
        truncated = False

        async def ask(messages: list) -> Any:
            nonlocal truncated
            output = await context.guard.call(
                model=model,
                model_id=context.candidate_id,
                role="candidate",
                test=test,
                messages=[ChatMessageSystem(content=SYSTEM), *messages],
                config=config,
            )
            truncated = truncated or stopped_at_limit(output)
            return output

        def done() -> TaskState:
            state.store.set(TRUNCATED_KEY, truncated)
            state.store.set(TOKEN_LIMIT_KEY, context.max_tokens)
            state.store.set(CANDIDATE_DONE_KEY, True)
            return state

        if metadata.get("scoring") == "round_trip":
            source = str(metadata["source_text"])
            source_lang = str(metadata["source_lang"])
            pivot_lang = str(metadata["pivot_lang"])
            first = await ask([ChatMessageUser(content=round_trip_prompt(source_lang, pivot_lang, source))])
            pivot = extract_translation(first.completion)
            state.messages.append(first.message)
            state.output = first
            state.store.set(PIVOT_KEY, pivot)
            state.store.set(BACK_KEY, "")
            if pivot:
                # A fresh conversation: the model never sees the source text.
                second = await ask([ChatMessageUser(content=round_trip_prompt(pivot_lang, source_lang, pivot))])
                state.store.set(BACK_KEY, extract_translation(second.completion))
                state.output = second
            return done()

        output = await ask(list(state.messages))
        state.messages.append(output.message)
        state.output = output
        return done()

    return solve


@dataclass
class JudgeOutcome:
    explanation: int | None  # 1 both pass, 0 not both pass, None unscored
    agree: bool | None  # both judges gave a verdict and the verdicts match
    failures: int  # judge calls that still failed after retries
    verdicts: list[dict[str, Any]]


async def _judge_once(context: RunContext, spec: JudgeSpec, test: str, prompt: str) -> dict[str, Any]:
    model: Model = spec.model if isinstance(spec.model, Model) else get_model(spec.model)
    config = _config(context.judge_max_tokens, temperature=0)
    last_error = "no attempt"
    for _attempt in range(1 + context.judge_retries):
        try:
            output = await context.guard.call(
                model=model,
                model_id=spec.id,
                role="judge",
                test=test,
                messages=JUDGE_SYSTEM + "\n\n" + prompt,
                config=config,
            )
        except (CostCapReached, CreditExhausted):
            raise
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue
        verdict = parse_judge_verdict(output.completion)
        if verdict is not None:
            return {"judge": spec.id, "family": spec.family, "pass": bool(verdict[0]), "reason": verdict[1]}
        last_error = "reply was not a usable verdict"
    return {"judge": spec.id, "family": spec.family, "pass": None, "error": last_error}


async def judge_explanation(
    context: RunContext, test: str, metadata: dict[str, Any], rules: Any
) -> JudgeOutcome:
    """Both judges must pass the explanation. Any judge that fails after its
    retries makes the explanation unscored, never 0."""
    prompt = judge_prompt(metadata, rules)
    verdicts = await asyncio.gather(
        *(_judge_once(context, spec, test, prompt) for spec in context.judges)
    )
    failures = sum(1 for verdict in verdicts if verdict["pass"] is None)
    if failures:
        return JudgeOutcome(None, None, failures, list(verdicts))
    passes = [verdict["pass"] for verdict in verdicts]
    return JudgeOutcome(
        explanation=int(all(passes)),
        agree=len(set(passes)) == 1,
        failures=0,
        verdicts=list(verdicts),
    )


@scorer(metrics=[mean()])
def teanga_scorer():
    """Score one item by its ``metadata.scoring`` kind."""

    async def score(state: TaskState, target: Target) -> Score:
        saved = _replay(state)
        if saved is not None and saved.score is not None:
            return saved.score
        metadata = dict(state.metadata or {})
        kind = metadata.get("scoring")
        completion = state.output.completion if state.output else ""
        if kind == "accept_list":
            decision = score_closed_answer(completion, metadata)
            return Score(
                value=float(decision.correct),
                answer=decision.answer,
                explanation=decision.detail,
                metadata={"scoring": kind, "expected": decision.expected},
            )
        if kind == "translation":
            hypothesis = extract_translation(completion)
            value = chrf_score(hypothesis, list(metadata.get("references") or []))
            return Score(
                value=value,
                answer=hypothesis,
                explanation="chrF++ against the best reference",
                metadata={"scoring": kind},
            )
        if kind == "round_trip":
            pivot = str(state.store.get(PIVOT_KEY, ""))
            back = str(state.store.get(BACK_KEY, ""))
            value = chrf_score(back, [str(metadata.get("source_text", ""))])
            return Score(
                value=value,
                answer=back,
                explanation="chrF++ of the back-translation against the source text",
                metadata={"scoring": kind, "pivot_text": pivot},
            )
        if kind == "tutor":
            return await _score_tutor(state, metadata, completion)
        raise ValueError(f"Unknown metadata.scoring {kind!r} on item {state.sample_id}")

    return score


async def _score_tutor(state: TaskState, metadata: dict[str, Any], completion: str) -> Score:
    context = current()
    rules = score_tutor_rules(completion, metadata)
    # With no judges (same family as a judge, or a judge unavailable) the
    # explanation is not scored at all. The headline never needs a judge.
    explanation: int | None = 0 if context.judges else None
    agree: bool | None = None
    failures = 0
    verdicts: list[dict[str, Any]] = []
    if context.judges and rules.parsed and rules.explanation:
        outcome = await judge_explanation(context, spend_key(metadata), metadata, rules)
        explanation, agree, failures, verdicts = (
            outcome.explanation,
            outcome.agree,
            outcome.failures,
            outcome.verdicts,
        )
    return Score(
        value=float(tutor_headline(rules)),
        answer=rules.corrected_sentence or rules.detail,
        explanation=rules.detail,
        metadata={
            "scoring": "tutor",
            "found": rules.found,
            "fixed": rules.fixed,
            "no_overcorrection": rules.no_overcorrection,
            "parsed": rules.parsed,
            "explanation": explanation,
            "judge_agree": agree,
            "judge_failures": failures,
            "judge_verdicts": verdicts,
        },
    )
