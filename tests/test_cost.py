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


class SlowModel:
    """Answers after a pause, so calls overlap. Records the most calls in flight."""

    def __init__(self, output_tokens: int):
        self.output_tokens = output_tokens
        self.in_flight = 0
        self.peak = 0
        self.calls = 0

    async def generate(self, messages, config):
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1
        self.calls += 1
        return _output(input_tokens=200, output_tokens=self.output_tokens)


def _overlapping(guard, model, n, max_tokens):
    async def run():
        return await asyncio.gather(
            *(
                guard.call(
                    model=model, model_id="cand", role="candidate", test="t", messages="hello",
                    config=GenerateConfig(max_tokens=max_tokens),
                )
                for _ in range(n)
            ),
            return_exceptions=True,
        )

    return asyncio.run(run())


def test_the_new_limit_does_not_stop_an_expensive_model_under_the_default_cap():
    """GPT-6 Astra prices with the 16000-token limit: one call's worst case is
    about $0.80, so eight in flight would be $6.40, more than the default $5 cap.
    The calls that do not fit wait for room; none is refused and the run goes on."""
    from teanga_bench.context import CANDIDATE_MAX_TOKENS
    from teanga_bench.runner import DEFAULT_MAX_COST

    astra = Pricing(Decimal("0.00001"), Decimal("0.00005"))
    guard = CostGuard(max_cost=DEFAULT_MAX_COST, prices={"cand": astra})
    model = SlowModel(output_tokens=600)  # a realistic answer: about $0.03
    results = _overlapping(guard, model, 8, CANDIDATE_MAX_TOKENS)
    assert not any(isinstance(result, Exception) for result in results)
    assert model.calls == 8 and not guard.stopped
    worst = guard.worst_case("cand", "hello", CANDIDATE_MAX_TOKENS)
    assert model.peak == int(DEFAULT_MAX_COST / worst) == 6  # never more in flight than the cap covers
    assert guard.reserved == 0 and guard.in_flight == 0
    assert guard.spent == 8 * astra.cost(200, 600)


def test_waiting_calls_stop_when_even_one_call_no_longer_fits():
    """Spend stays under the cap: near the end calls run one at a time, and the
    run stops once a single worst case no longer fits."""
    cap = Decimal("1.00")
    price = Pricing(Decimal("0"), Decimal("0.00005"))
    guard = CostGuard(max_cost=cap, prices={"cand": price})
    model = SlowModel(output_tokens=4000)  # $0.20 a call; worst case $0.80
    results = _overlapping(guard, model, 6, 16000)
    # $0.80 fits alone; the second call fits once the first settles at $0.20;
    # after it, $0.40 + $0.80 does not, so the four waiting calls are refused.
    assert sum(isinstance(result, CostCapReached) for result in results) == 4
    assert guard.stopped and model.calls == 2 and model.peak == 1
    assert guard.spent == Decimal("0.40") <= cap
    assert guard.reserved == 0 and guard.in_flight == 0
