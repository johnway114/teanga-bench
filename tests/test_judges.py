"""Judge selection by family, retries, and unscored explanations."""

import asyncio
import itertools
from decimal import Decimal

from inspect_ai.model import ModelOutput, get_model

from teanga_bench.context import JudgeSpec, RunContext
from teanga_bench.cost import CostGuard
from teanga_bench.models_config import configured_judges, family_of
from teanga_bench.scorers import judge_explanation
from teanga_bench.scoring import score_tutor_rules

PASS = '{"explanation_ok": true, "invented_extra_error": false, "reason": "fine"}'
FAIL = '{"explanation_ok": false, "invented_extra_error": false, "reason": "wrong"}'
JUNK = "no idea"


def _model(*texts):
    return get_model(
        "mockllm/model",
        custom_outputs=[ModelOutput.from_content(model="mockllm/model", content=t) for t in texts],
        memoize=False,
    )


def _repeat(text):
    return get_model(
        "mockllm/model",
        custom_outputs=itertools.repeat(ModelOutput.from_content(model="mockllm/model", content=text)),
        memoize=False,
    )


def _context(*judge_models):
    judges = [JudgeSpec(f"judge/{n}", f"fam{n}", model) for n, model in enumerate(judge_models)]
    return RunContext(guard=CostGuard(max_cost=Decimal("5")), candidate_id="cand/x", judges=judges)


def _rules():
    meta = {
        "has_error": True,
        "learner_sentence": "She go home.",
        "error_span": "go",
        "accept_spans": ["go"],
        "correction": "goes",
        "accept_corrections": ["goes"],
        "acceptable_sentences": ["She goes home."],
        "explanation_points": ["Third person singular takes -s."],
    }
    completion = (
        '{"has_error": true, "error_span": "go", "correction": "goes", '
        '"corrected_sentence": "She goes home.", "explanation": "Needs -s."}'
    )
    return meta, score_tutor_rules(completion, meta)


def _judge(context):
    meta, rules = _rules()
    return asyncio.run(judge_explanation(context, "tutor", meta, rules))


# --- the fixed pair ---------------------------------------------------------


def test_the_judge_pair_is_fixed_in_config():
    pair = configured_judges()
    assert [j.id for j in pair] == ["deepseek/deepseek-v4.1-flash-1017", "qwen/qwen3.8-flash"]
    assert [j.family for j in pair] == ["deepseek", "qwen"]


def test_family_map_uses_the_provider_prefix():
    assert family_of("meta-llama/llama-9") == "meta"
    assert family_of("~anthropic/claude-latest") == "anthropic"
    assert family_of("some-new-lab/model") == "some-new-lab"


# --- judging ----------------------------------------------------------------


def test_explanation_passes_only_when_both_judges_pass():
    both = _judge(_context(_model(PASS), _model(PASS)))
    assert (both.explanation, both.agree, both.failures) == (1, True, 0)
    split = _judge(_context(_model(PASS), _model(FAIL)))
    assert (split.explanation, split.agree) == (0, False)
    neither = _judge(_context(_model(FAIL), _model(FAIL)))
    assert (neither.explanation, neither.agree) == (0, True)


def test_judge_error_is_unscored_not_zero():
    context = _context(_model(PASS), _model())  # second judge raises on every call
    outcome = _judge(context)
    assert outcome.explanation is None
    assert outcome.agree is None
    assert outcome.failures == 1
    assert outcome.verdicts[1]["pass"] is None and "error" in outcome.verdicts[1]


def test_unusable_judge_reply_is_retried_then_unscored():
    context = _context(_model(PASS), _repeat(JUNK))
    outcome = _judge(context)
    assert outcome.explanation is None
    assert outcome.failures == 1
    # one good call, plus the first try and three retries of the broken judge
    assert context.guard.total(role="judge").calls == 1 + 4


def test_a_judge_that_recovers_within_three_retries_is_scored():
    context = _context(_model(PASS), _model(JUNK, JUNK, JUNK, PASS))
    outcome = _judge(context)
    assert (outcome.explanation, outcome.failures) == (1, 0)
    assert context.guard.total(role="judge").calls == 1 + 4
