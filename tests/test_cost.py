"""The cost cap is a hard stop over candidate and judge spend."""

import asyncio
from decimal import Decimal

import pytest
from inspect_ai.model import GenerateConfig, ModelOutput, ModelUsage, get_model

from teanga_bench.cost import CostCapReached, CostGuard
from teanga_bench.pricing import Pricing
from teanga_bench.runner import STATUS_CAP, RunOptions, run_benchmark

FAKE = Pricing(prompt=Decimal("0.00001"), completion=Decimal("0.00001"))


def _output(input_tokens=100, output_tokens=50):
    output = ModelOutput.from_content(model="mockllm/model", content="ok")
    output.usage = ModelUsage(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=input_tokens + output_tokens)
    return output


def _model(count=200, **usage):
    return get_model("mockllm/model", custom_outputs=[_output(**usage) for _ in range(count)], memoize=False)


def _call(guard, model, model_id, role, max_tokens=100):
    return asyncio.run(
        guard.call(
            model=model,
            model_id=model_id,
            role=role,
            test="t",
            messages="hello",
            config=GenerateConfig(max_tokens=max_tokens),
        )
    )


def test_candidate_and_judge_spend_share_one_total():
    guard = CostGuard(
        max_cost=Decimal("10"),
        prices={
            "cand": Pricing(Decimal("0.001"), Decimal("0.002")),
            "judge": Pricing(Decimal("0.0001"), Decimal("0.0002")),
        },
    )
    _call(guard, _model(input_tokens=1000, output_tokens=500), "cand", "candidate")
    _call(guard, _model(input_tokens=1000, output_tokens=500), "judge", "judge")
    assert guard.total(role="candidate").cost_usd == Decimal("2.0")  # 1000*0.001 + 500*0.002
    assert guard.total(role="judge").cost_usd == Decimal("0.2")
    assert guard.spent == Decimal("2.2")
    assert guard.reserved == 0


def test_cache_tokens_are_billed_at_cache_prices():
    price = Pricing(Decimal("0.001"), Decimal("0.002"), cache_read=Decimal("0.0001"), cache_write=Decimal("0.0005"))
    assert price.cost(10, 5, cache_read_tokens=100, cache_write_tokens=20) == Decimal("0.01") + Decimal("0.01") + Decimal("0.01") + Decimal("0.01")


def test_guard_stops_before_the_call_that_could_pass_the_cap():
    cap = Decimal("0.03")
    guard = CostGuard(max_cost=cap, prices={"cand": FAKE})
    model = _model()
    calls = 0
    with pytest.raises(CostCapReached):
        for _ in range(200):
            _call(guard, model, "cand", "candidate")
            calls += 1
            assert guard.spent <= cap
    assert 0 < calls < 200
    assert guard.stopped is True
    # Once stopped, nothing more is called, even a call that would fit.
    with pytest.raises(CostCapReached):
        _call(guard, model, "cand", "candidate", max_tokens=1)


def test_a_call_that_could_exceed_the_cap_alone_is_never_made():
    guard = CostGuard(max_cost=Decimal("0.01"), prices={"cand": FAKE})
    model = _model()
    with pytest.raises(CostCapReached):
        _call(guard, model, "cand", "candidate", max_tokens=100_000)  # worst case $1.00
    assert guard.spent == 0


def test_a_call_that_raises_releases_its_reservation():
    guard = CostGuard(max_cost=Decimal("1"), prices={"cand": FAKE})
    broken = get_model("mockllm/model", custom_outputs=[], memoize=False)
    with pytest.raises(Exception):
        _call(guard, broken, "cand", "candidate")
    assert guard.reserved == 0 and guard.spent == 0


def test_cap_stops_a_whole_run_and_marks_tests_incomplete(fixture_root, tmp_path):
    cap = Decimal("0.025")
    result = run_benchmark(
        RunOptions(
            model="mockllm/model",
            max_cost=cap,
            epochs=2,
            root=fixture_root,
            log_dir=tmp_path / "logs",
            mock_pricing=FAKE,
        )
    )
    document = result.document
    assert result.status == STATUS_CAP == document["status"]
    assert document["cost"]["cap_reached"] is True
    assert Decimal(str(document["cost"]["total_usd"])) <= cap
    tests = [b for s in document["suites"].values() for b in s["tests"].values()]
    assert tests and all(b["status"] == "incomplete" for b in tests)
    assert {b["incomplete_reason"] for b in tests} == {"cost_cap_reached"}
    assert document["overall"] is None  # no complete test, so no overall score


def test_a_generous_cap_lets_the_run_finish(fixture_root, tmp_path):
    result = run_benchmark(
        RunOptions(
            model="mockllm/model",
            max_cost=Decimal("50"),
            epochs=1,
            limit=2,
            root=fixture_root,
            log_dir=tmp_path / "logs",
            mock_pricing=FAKE,
        )
    )
    assert result.status == "complete"
    assert 0 < result.document["cost"]["total_usd"] < 50
    assert result.document["cost"]["cap_reached"] is False
