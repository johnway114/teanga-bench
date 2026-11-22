"""Resuming an incomplete run, and the pause on exhausted credit. Mock models only."""

from __future__ import annotations

import asyncio
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from inspect_ai.model import ChatMessageUser, GenerateConfig, ModelOutput, get_model

from teanga_bench import cli
from teanga_bench.cost import CostGuard, CreditBackoff, CreditExhausted, is_credit_error
from teanga_bench.export import write_results
from teanga_bench.pricing import Pricing
from teanga_bench.runner import RunError, RunOptions, run_benchmark

FAKE = Pricing(prompt=Decimal("0.00001"), completion=Decimal("0.00002"))
EPOCHS = 2
TUTOR_OK = json.dumps(
    {"has_error": True, "error_span": "C", "correction": "", "corrected_sentence": "Cosnaíonn sé an teach.", "explanation": "Doubled C."}
)
PASS = '{"explanation_ok": true, "reason": "fine"}'
FAIL = '{"explanation_ok": false, "reason": "weak"}'

# Items whose first candidate call fails in the interrupted run, one epoch each.
FLAKY = ("Eclipse 'cat'", "The cat is here.", "Mae'r ci yn yn y ty", "She go to school", "Translate the following Welsh")


class Refused(Exception):
    """What the OpenAI client raises for an HTTP error status."""

    def __init__(self, code: int):
        super().__init__(f"Error code: {code} - This request would exceed your available credits.")
        self.status_code = code


def _prompt(messages) -> str:
    return "\n".join(m.text for m in messages if m.role == "user")


def _answer(prompt: str) -> str:
    if "ANSWER:" in prompt:
        return "ANSWER: bhean"
    if "JSON object" in prompt:
        return TUTOR_OK
    return "Tá an cat anseo."


class Candidate:
    """Answers from the prompt alone, so every run gets the same outputs.
    Records every prompt it was asked; ``flaky`` prompts fail on their first call."""

    def __init__(self, flaky=(), refuse_after=None):
        self.calls: Counter[str] = Counter()
        self.flaky = set(flaky)
        self.failed: set[str] = set()
        self.refuse_after = refuse_after

    def __call__(self, messages, tools, tool_choice, config):
        prompt = _prompt(messages)
        if self.refuse_after is not None and sum(self.calls.values()) >= self.refuse_after:
            raise Refused(402)
        for marker in self.flaky - self.failed:
            if marker in prompt:
                self.failed.add(marker)
                raise RuntimeError(f"connection reset ({marker})")
        self.calls[prompt] += 1
        return ModelOutput.from_content(model="mockllm/model", content=_answer(prompt))

    def model(self):
        return get_model("mockllm/model", custom_outputs=self, memoize=False)


class Judge:
    def __init__(self, refuse=False):
        self.calls = 0
        self.refuse = refuse

    def __call__(self, messages, tools, tool_choice, config):
        if self.refuse:
            raise Refused(402)
        self.calls += 1
        return ModelOutput.from_content(model="mockllm/model", content=PASS if "Cosna" in _prompt(messages) else FAIL)


class FakeClock:
    """A clock that only moves when someone sleeps on it."""

    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        target = self.now + seconds
        await asyncio.sleep(0)
        self.now = max(self.now, target)

    def backoff(self, **kwargs) -> CreditBackoff:
        return CreditBackoff(clock=self, sleep=self.sleep, **kwargs)


@pytest.fixture
def data_root(tmp_path, fixture_root) -> Path:
    root = tmp_path / "data"
    shutil.copytree(fixture_root, root)
    # Real ids look like "c6-l2-c1@vi:err": the colon must not read as a task selector.
    path = root / "samples" / "blas" / "mutations.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace('"fx-mut-01"', '"fx-mut-01@vi:err"'), encoding="utf-8")
    return root


@pytest.fixture
def judges(monkeypatch):
    import teanga_bench.runner as runner_module

    real = runner_module._judges_for_run
    state = {"judge": Judge()}

    def with_mock_judges(options, catalog):
        specs, choices, status = real(options, catalog)
        model = get_model("mockllm/model", custom_outputs=state["judge"], memoize=False)
        for spec in specs:
            spec.model = model
        return specs, choices, status

    monkeypatch.setattr(runner_module, "_judges_for_run", with_mock_judges)
    return state


def _options(root, output, log_dir, **kwargs):
    return RunOptions(
        model="mockllm/model",
        root=root,
        output=output,
        log_dir=log_dir,
        mock_pricing=FAKE,
        max_cost=Decimal("50"),
        **kwargs,
    )


def _run(root, tmp_path, name, candidate, **kwargs):
    output = tmp_path / name / "run.json"
    result = run_benchmark(
        _options(root, output, tmp_path / name / "logs", epochs=EPOCHS, **kwargs),
        inspect_model=candidate.model(),
    )
    write_results(result.document, result.output)
    return result


def _resume(root, tmp_path, name, candidate, logs="resume-logs", **kwargs):
    output = tmp_path / name / "run.json"
    result = run_benchmark(
        _options(root, output, tmp_path / name / logs, resume=True, **kwargs),
        inspect_model=candidate.model(),
    )
    write_results(result.document, result.output)
    return result


def _tests(document):
    return {f"{s}/{t}": block for s, body in document["suites"].items() for t, block in body["tests"].items()}


COST_FIELDS = {"cost_usd", "cost_per_correct_usd", "cost"}


def _statistics(document):
    return {
        name: {key: value for key, value in block.items() if key not in COST_FIELDS}
        for name, block in _tests(document).items()
    }


def _single_call_inputs(root: Path) -> dict[str, str]:
    """Item id -> prompt, for every item answered in one call."""
    inputs = {}
    for path in (root / "samples").glob("*/*.jsonl"):
        if path.stem == "round_trip":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            inputs[item["id"]] = item["input"]
    return inputs


# --- resume ---------------------------------------------------------------------


def test_resume_reuses_good_samples_and_matches_an_uninterrupted_run(data_root, tmp_path, judges):
    straight = _run(data_root, tmp_path, "straight", Candidate())
    assert straight.status == "complete"

    first = _run(data_root, tmp_path, "resumed", Candidate(flaky=FLAKY))
    assert first.status == "incomplete" and first.document["incomplete_reason"] == "errors"
    assert sum(block["n_errors"] for block in _tests(first.document).values()) == len(FLAKY)
    assert "resumed" not in first.document
    assert set(first.document["config"]["dataset_hashes"]) == set(first.document["config"]["tests"])

    judges["judge"] = Judge()
    again = Candidate()
    resumed = _resume(data_root, tmp_path, "resumed", again)
    document = resumed.document

    assert resumed.status == "complete" and document["incomplete_reason"] is None
    # Only the failed sample-epochs were asked again: one call for each failed
    # single-call item, and two for the failed round-trip (pivot and back).
    assert sum(again.calls.values()) == len(FLAKY) + 1
    flaky_inputs = {p for p in _single_call_inputs(data_root).values() if any(m in p for m in FLAKY)}
    good_inputs = set(_single_call_inputs(data_root).values()) - flaky_inputs
    assert not good_inputs & set(again.calls)
    assert all(again.calls[p] == 1 for p in flaky_inputs)
    # The judges (one mock for both) marked only the two re-run tutor sample-epochs.
    assert judges["judge"].calls == 2 * 2

    # Same statistics as the run that was never interrupted.
    assert _statistics(document) == _statistics(straight.document)
    assert document["overall"] == straight.document["overall"]
    # Cost is carried forward: the true total equals the uninterrupted run's.
    attempts = document["resumed"]["attempts"]
    assert document["resumed"]["count"] == 1 and len(attempts) == 2
    assert attempts[0]["cost_usd"] == pytest.approx(first.document["cost"]["total_usd"])
    assert document["cost"]["total_usd"] == pytest.approx(attempts[0]["cost_usd"] + attempts[1]["cost_usd"])
    assert document["cost"]["total_usd"] == pytest.approx(straight.document["cost"]["total_usd"])
    for name, block in _tests(document).items():
        assert block["cost_usd"] == pytest.approx(_tests(straight.document)[name]["cost_usd"]), name
    assert document["cost"]["by_model"]["mockllm/model"]["calls"] == straight.document["cost"]["by_model"]["mockllm/model"]["calls"]

    counts = attempts[1]["sample_epochs"]
    total = sum(block["n_items_dataset"] * EPOCHS for block in _tests(document).values())
    assert counts == {"reused": total - len(FLAKY), "rescored": 0, "run": len(FLAKY), "rerun_truncated": 0}
    assert attempts[1]["dataset_check"] == "dataset_hash"
    assert attempts[0]["log_dir"] == document["config"]["log_dir"]
    assert document["started_at"] == first.document["started_at"]

    # Same schema as a normal complete run, plus the resumed block.
    assert set(document) == set(straight.document) | {"resumed"}
    assert set(document["config"]) == set(straight.document["config"])


def test_resume_cli_prints_and_needs_an_incomplete_run(data_root, tmp_path, judges, monkeypatch, capsys):
    import teanga_bench.runner as runner_module

    first = _run(data_root, tmp_path, "cli", Candidate(flaky=FLAKY))
    real = runner_module.run_benchmark
    monkeypatch.setattr(
        runner_module, "run_benchmark", lambda options: real(options, inspect_model=Candidate().model())
    )
    args = ["run", "--model", "mockllm/model", "--output", str(first.output), "--data-root", str(data_root), "--log-dir", str(tmp_path / "cli" / "logs2")]
    assert cli.main(args + ["--resume"]) == 0
    out = capsys.readouterr().out
    assert "Status: complete" in out and f"ran {len(FLAKY)}" in out
    # A complete run cannot be resumed.
    assert cli.main(args + ["--resume"]) == 2
    assert "already complete" in capsys.readouterr().err


def test_resume_refuses_a_changed_dataset(data_root, tmp_path, judges):
    _run(data_root, tmp_path, "changed", Candidate(flaky=FLAKY))
    path = data_root / "samples" / "blas" / "mutations.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace("Lenite", "Lenite the noun"), encoding="utf-8")
    with pytest.raises(RunError, match="changed since the first attempt: blas/mutations"):
        _resume(data_root, tmp_path, "changed", Candidate())


def test_resume_refuses_other_settings(data_root, tmp_path, judges):
    _run(data_root, tmp_path, "settings", Candidate(flaky=FLAKY))
    with pytest.raises(RunError, match="--epochs 3"):
        _resume(data_root, tmp_path, "settings", Candidate(), epochs=3)


def test_resume_of_a_results_file_without_dataset_hashes(data_root, tmp_path, judges):
    """Files written before the hash existed: logs found by folder name, items
    compared by id and count, and per-test cost booked by bare test name."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    logs_root = tmp_path / "logs-root"
    output = tmp_path / "legacy" / "run.json"
    first = run_benchmark(
        _options(data_root, output, logs_root / f"mockllm__model-{stamp}", epochs=EPOCHS),
        inspect_model=Candidate(flaky=FLAKY).model(),
    ).document
    legacy = json.loads(json.dumps(first))
    for key in ("dataset_hashes", "log_dir"):
        del legacy["config"][key]
    del legacy["incomplete_reason"]
    # The old ledger booked spend by bare test name: tonada/tutor also counted blas/tutor.
    later = legacy["suites"]["tonada"]["tests"]["tutor"]
    earlier = legacy["suites"]["blas"]["tests"]["tutor"]
    later["cost_usd"] += earlier["cost_usd"]
    for role in ("candidate", "judge"):
        for field in later["cost"][role]:
            later["cost"][role][field] += earlier["cost"][role][field]
    write_results(legacy, output)

    resumed = run_benchmark(
        RunOptions(
            model="mockllm/model", root=data_root, output=output, log_dir=tmp_path / "legacy" / "logs2",
            mock_pricing=FAKE, resume=True, logs_root=logs_root,
        ),
        inspect_model=Candidate().model(),
    ).document
    assert resumed["status"] == "complete"
    attempts = resumed["resumed"]["attempts"]
    assert attempts[1]["dataset_check"] == "item_ids_and_count"
    assert attempts[1]["sample_epochs"]["run"] == len(FLAKY)
    assert attempts[0]["incomplete_reason"] == "errors"
    assert attempts[0]["log_dir"].endswith(f"mockllm__model-{stamp}")
    assert resumed["config"]["max_cost_usd"] == 50.0  # the earlier cap carries over
    assert set(resumed["config"]["dataset_hashes"]) == set(resumed["config"]["tests"])
    # Undoing the old double booking makes the per-test costs add up to the total again.
    assert resumed["cost"]["total_usd"] == pytest.approx(
        sum(block["cost_usd"] for block in _tests(resumed).values())
    )
    assert legacy["cost"]["total_usd"] < sum(block.get("cost_usd", 0) for block in _tests(legacy).values())


def test_a_legacy_file_corrected_by_hand_is_not_corrected_twice():
    from teanga_bench.resume import carried_cost

    def block(calls, cost):
        return {"cost_usd": cost, "cost": {"candidate": {"calls": calls, "cost_usd": cost}, "judge": {}}}

    document = {
        "config": {"tests": ["blas/tutor", "tonada/tutor"]},
        "cost": {"total_usd": 3.0, "by_model": {}},
        "suites": {"blas": {"tests": {"tutor": block(10, 1.0)}}, "tonada": {"tests": {"tutor": block(20, 2.0)}}},
    }
    by_test, _, total = carried_cost(document)  # per-test costs add up to the total: kept
    assert by_test[("tonada/tutor", "candidate")].calls == 20 and total == Decimal("3.0")
    document["suites"]["tonada"]["tests"]["tutor"] = block(30, 3.0)  # double-booked: undone
    by_test, _, _ = carried_cost(document)
    assert by_test[("tonada/tutor", "candidate")].calls == 20
    assert by_test[("tonada/tutor", "candidate")].cost_usd == Decimal("2.0")


def test_legacy_resume_refuses_changed_item_ids(data_root, tmp_path, judges):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    logs_root = tmp_path / "logs-root"
    output = tmp_path / "legacy" / "run.json"
    document = run_benchmark(
        _options(data_root, output, logs_root / f"mockllm__model-{stamp}", epochs=EPOCHS),
        inspect_model=Candidate(flaky=FLAKY).model(),
    ).document
    del document["config"]["dataset_hashes"], document["config"]["log_dir"]
    write_results(document, output)
    path = data_root / "samples" / "blas" / "mutations.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace("fx-mut-03", "fx-mut-99"), encoding="utf-8")
    with pytest.raises(RunError, match="blas/mutations item ids differ"):
        run_benchmark(
            RunOptions(model="mockllm/model", root=data_root, output=output, log_dir=tmp_path / "l2", resume=True, logs_root=logs_root),
            inspect_model=Candidate().model(),
        )


# --- credit exhaustion ------------------------------------------------------------


def _guarded_call(guard, model):
    return asyncio.run(
        guard.call(
            model=model,
            model_id="cand",
            role="candidate",
            test="blas/t",
            messages=[ChatMessageUser(content="hello")],
            config=GenerateConfig(max_tokens=10),
        )
    )


class Script:
    """Raises the listed errors in order, then answers."""

    def __init__(self, *errors):
        self.errors = list(errors)
        self.calls = 0

    def __call__(self, messages, tools, tool_choice, config):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return ModelOutput.from_content(model="mockllm/model", content="ok")


def test_402_and_429_back_off_and_then_succeed():
    clock = FakeClock()
    script = Script(Refused(402), Refused(402), Refused(429))
    guard = CostGuard(max_cost=Decimal("1"), prices={"cand": FAKE}, backoff=clock.backoff())
    output = _guarded_call(guard, get_model("mockllm/model", custom_outputs=script, memoize=False))
    assert output.completion == "ok"
    assert script.calls == 4
    assert clock.sleeps == [15, 30, 60]
    assert guard.backoff.waited == 105 and not guard.credit_exhausted
    assert guard.total().calls == 1 and guard.reserved == 0  # refused calls are not billed


def test_concurrent_refusals_share_one_pause():
    clock = FakeClock()
    backoff = clock.backoff()
    script = Script(Refused(402), Refused(402), Refused(402))
    guard = CostGuard(max_cost=Decimal("1"), prices={"cand": FAKE}, backoff=backoff)
    model = get_model("mockllm/model", custom_outputs=script, memoize=False)

    async def three():
        return await asyncio.gather(
            *(
                guard.call(model=model, model_id="cand", role="candidate", test="t", messages="hi", config=GenerateConfig(max_tokens=5))
                for _ in range(3)
            )
        )

    outputs = asyncio.run(three())
    assert [o.completion for o in outputs] == ["ok"] * 3
    assert backoff.pauses == 1 and backoff.waited == 15 and clock.now == 15


def test_the_wait_budget_ends_in_credit_exhausted():
    clock = FakeClock()
    script = Script(*[Refused(402)] * 100)
    guard = CostGuard(max_cost=Decimal("1"), prices={"cand": FAKE}, backoff=clock.backoff())
    with pytest.raises(CreditExhausted):
        _guarded_call(guard, get_model("mockllm/model", custom_outputs=script, memoize=False))
    assert clock.sleeps[:5] == [15, 30, 60, 120, 120]
    assert max(clock.sleeps) == 120
    assert guard.backoff.waited == 20 * 60 and sum(clock.sleeps) == 20 * 60
    assert guard.credit_exhausted
    calls = script.calls
    with pytest.raises(CreditExhausted):  # later calls fail at once, without a request
        _guarded_call(guard, get_model("mockllm/model", custom_outputs=script, memoize=False))
    assert script.calls == calls


def test_other_errors_are_not_credit_errors():
    assert is_credit_error(Refused(402)) and is_credit_error(Refused(429))
    assert not is_credit_error(Refused(500)) and not is_credit_error(RuntimeError("boom"))
    wrapped = RuntimeError("sample failed")
    wrapped.__cause__ = Refused(402)
    assert is_credit_error(wrapped)


def test_exhausted_credit_stops_the_run_and_resume_finishes_it(data_root, tmp_path, judges, monkeypatch, capsys):
    import teanga_bench.runner as runner_module

    # The candidate is fine but the judges are refused: tutor items keep their
    # candidate output and only need judging on resume.
    judges["judge"] = Judge(refuse=True)
    clock = FakeClock()
    real = runner_module.run_benchmark
    candidate = Candidate()
    monkeypatch.setattr(
        runner_module,
        "run_benchmark",
        lambda options: real(options, inspect_model=candidate.model(), backoff=clock.backoff(budget=60)),
    )
    output = tmp_path / "credit" / "run.json"
    args = ["run", "--model", "mockllm/model", "--epochs", "1", "--tests", "blas/tutor", "tonada/tutor", "blas/mutations",
            "--output", str(output), "--data-root", str(data_root), "--log-dir", str(tmp_path / "credit" / "logs")]
    assert cli.main(args) == cli.EXIT_NO_CREDIT
    err = capsys.readouterr().err
    assert "Add credit" in err
    assert f"teanga-bench run --model mockllm/model --resume --output {output} --data-root {data_root}" in err
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["status"] == "incomplete" and document["incomplete_reason"] == "insufficient_credit"
    tests = _tests(document)
    assert tests["blas/tutor"]["incomplete_reason"] == "insufficient_credit"
    assert tests["tonada/tutor"]["incomplete_reason"] == "insufficient_credit"  # never started
    assert tests["blas/mutations"]["incomplete_reason"] == "insufficient_credit"
    assert clock.now == 60
    asked = sum(candidate.calls.values())

    # Credit is back. Resume: the tutor answers are reused and only judged.
    judges["judge"] = Judge()
    clock.now = 0
    args = ["run", "--model", "mockllm/model", "--resume", "--output", str(output), "--data-root", str(data_root),
            "--log-dir", str(tmp_path / "credit" / "logs2")]
    assert cli.main(args) == 0
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["status"] == "complete"
    counts = document["resumed"]["attempts"][1]["tests"]
    assert counts["blas/tutor"]["rescored"] >= 1 and counts["blas/tutor"]["run"] == 0
    assert counts["tonada/tutor"] == {"reused": 0, "rescored": 0, "run": 2, "rerun_truncated": 0}
    blas_tutor_prompts = {p for p in candidate.calls if "Sentence: CCosna" in p or "Mae'r ci yn yn" in p or "Sentence: Tá an cat" in p}
    assert all(candidate.calls[p] == 1 for p in blas_tutor_prompts)  # not asked again
    assert sum(candidate.calls.values()) == asked + 2 + 4  # tonada/tutor and blas/mutations only
    assert judges["judge"].calls >= 2


# --- resume-plan ----------------------------------------------------------------


def test_resume_plan_counts_without_running_anything(data_root, tmp_path, judges, capsys):
    first = _run(data_root, tmp_path, "plan", Candidate(flaky=FLAKY))
    results = tmp_path / "plan-results"
    (results / "runs").mkdir(parents=True)
    shutil.copy(first.output, results / "runs" / "mockllm__model.json")
    before = first.output.read_text(encoding="utf-8")
    code = cli.main(
        ["resume-plan", "--model", "mockllm/model", "--results-dir", str(results),
         "--log-dir", str(tmp_path / "plan" / "logs"), "--data-root", str(data_root)]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Datasets: unchanged (sha256 of each file)" in out
    rows = {line.split()[0]: line.split()[1:4] for line in out.splitlines() if line.startswith(("blas/", "tonada/"))}
    assert rows["blas/mutations"] == ["7", "0", "1"]
    assert rows["blas/round_trip"] == ["3", "0", "1"]
    assert rows["blas/tutor"] == ["5", "0", "1"]
    all_tests = next(line for line in out.splitlines() if line.startswith("all tests")).split()
    assert all_tests[2:5] == ["21", "0", str(len(FLAKY))]
    assert first.output.read_text(encoding="utf-8") == before  # read-only


# --- answers cut off by the token limit ------------------------------------------

# One item each in blas/mutations, blas/tutor and blas/round_trip (the first,
# Irish-to-English call) has a long answer that a small limit cuts off.
LONG = ("Eclipse 'cat'", "Mae'r ci yn yn y ty", "Translate the following Irish text into English")
LONG_TESTS = ("blas/mutations", "blas/tutor", "blas/round_trip")
OLD_LIMIT = 512


class Wordy(Candidate):
    """Like ``Candidate``, but under a limit below 1000 tokens a LONG prompt
    gets an empty reply that stopped at the limit, as a reasoning model does."""

    def __call__(self, messages, tools, tool_choice, config):
        prompt = _prompt(messages)
        if config.max_tokens < 1000 and any(marker in prompt for marker in LONG):
            self.calls[prompt] += 1
            return ModelOutput.from_content(model="mockllm/model", content="", stop_reason="max_tokens")
        return super().__call__(messages, tools, tool_choice, config)


def _old_limit_run(data_root, tmp_path, name, monkeypatch):
    import teanga_bench.runner as runner_module

    monkeypatch.setattr(runner_module, "CANDIDATE_MAX_TOKENS", OLD_LIMIT)
    first = _run(data_root, tmp_path, name, Wordy())
    monkeypatch.setattr(runner_module, "CANDIDATE_MAX_TOKENS", 16000)
    return first


def test_truncated_answers_are_counted_and_scored_normally(data_root, tmp_path, judges, monkeypatch):
    from teanga_bench.leaderboard import build_leaderboard

    straight = _run(data_root, tmp_path, "straight", Candidate())
    first = _old_limit_run(data_root, tmp_path, "cut", monkeypatch)
    document = first.document
    assert first.status == "complete"
    assert document["config"]["max_tokens"]["candidate"] == OLD_LIMIT
    tests = _tests(document)
    for name, block in tests.items():
        assert block["n_truncated_item_epochs"] == (EPOCHS if name in LONG_TESTS else 0), name
    # The empty answers are scored by the normal rules, so they score 0.
    assert tests["blas/round_trip"]["score"] < _tests(straight.document)["blas/round_trip"]["score"]
    assert document["overall"]["score"] < straight.document["overall"]["score"]
    truncation = document["truncation"]
    total = sum(block["n_items_dataset"] * EPOCHS for block in tests.values())
    assert truncation["max_tokens"] == OLD_LIMIT
    assert truncation["n_truncated_item_epochs"] == 3 * EPOCHS and truncation["n_item_epochs"] == total
    assert straight.document["truncation"]["n_truncated_item_epochs"] == 0

    board = build_leaderboard([{**document, "_file": "cut.json"}, {**straight.document, "_file": "straight.json"}], [], [])
    share = {entry["run_file"]: entry["truncated_share"] for entry in board["models"]}
    assert share == {"cut.json": pytest.approx(3 * EPOCHS / total), "straight.json": 0.0}


def test_rerun_truncated_asks_again_only_the_cut_off_answers(data_root, tmp_path, judges, monkeypatch):
    straight = _run(data_root, tmp_path, "straight", Candidate())
    first = _old_limit_run(data_root, tmp_path, "rerun", monkeypatch)
    assert first.status == "complete"
    # A note on a hand edit stays with the file.
    write_results({**first.document, "corrections": ["a hand edit"]}, first.output)

    # A complete run is still refused without the flag, and the flag needs --resume.
    with pytest.raises(RunError, match="already complete"):
        _resume(data_root, tmp_path, "rerun", Wordy())
    with pytest.raises(RunError, match="only with --resume"):
        run_benchmark(_options(data_root, tmp_path / "x.json", tmp_path / "x", rerun_truncated=True))

    judges["judge"] = Judge()
    again = Wordy()
    resumed = _resume(data_root, tmp_path, "rerun", again, rerun_truncated=True)
    document = resumed.document
    assert resumed.status == "complete"

    # Only the cut-off sample-epochs were asked again: one call each for the
    # mutation and tutor item, two for the round trip (pivot and back).
    assert sum(again.calls.values()) == EPOCHS * (1 + 1 + 2)
    assert all(any(marker in prompt for marker in LONG) or "English text into Irish" in prompt for prompt in again.calls)
    # The re-run tutor answers were judged: two sample-epochs, two judges (one mock).
    assert judges["judge"].calls == EPOCHS * 2

    # The statistics are those of a run that was never cut off.
    assert _statistics(document) == _statistics(straight.document)
    assert document["overall"] == straight.document["overall"]
    assert document["truncation"] == {**straight.document["truncation"], "max_tokens": 16000}
    assert document["config"]["max_tokens"]["candidate"] == 16000

    resumed_block = document["resumed"]
    assert resumed_block["truncation_rerun"] == {"old_limit": OLD_LIMIT, "new_limit": 16000, "n_rerun": 3 * EPOCHS}
    assert document["corrections"] == ["a hand edit"]
    attempts = resumed_block["attempts"]
    assert [a["candidate_max_tokens"] for a in attempts] == [OLD_LIMIT, 16000]
    total = sum(block["n_items_dataset"] * EPOCHS for block in _tests(document).values())
    assert attempts[1]["sample_epochs"] == {
        "reused": total - 3 * EPOCHS, "rescored": 0, "run": 3 * EPOCHS, "rerun_truncated": 3 * EPOCHS
    }
    assert attempts[1]["tests"]["blas/translation"] == {"reused": 2 * EPOCHS, "rescored": 0, "run": 0, "rerun_truncated": 0}

    # Cost is carried forward: the first attempt plus what the re-run spent.
    assert attempts[0]["cost_usd"] == pytest.approx(first.document["cost"]["total_usd"])
    assert attempts[1]["cost_usd"] > 0
    assert document["cost"]["total_usd"] == pytest.approx(attempts[0]["cost_usd"] + attempts[1]["cost_usd"])
    for name, block in _tests(document).items():
        before = _tests(first.document)[name]["cost_usd"]
        assert block["cost_usd"] > before if name in LONG_TESTS else block["cost_usd"] == pytest.approx(before), name

    # Nothing is left to re-run.
    with pytest.raises(RunError, match="nothing to re-run"):
        _resume(data_root, tmp_path, "rerun", Wordy(), logs="third-logs", rerun_truncated=True)


def test_resume_plan_with_rerun_truncated(data_root, tmp_path, judges, monkeypatch, capsys):
    first = _old_limit_run(data_root, tmp_path, "plan-cut", monkeypatch)
    results = tmp_path / "plan-cut-results"
    (results / "runs").mkdir(parents=True)
    shutil.copy(first.output, results / "runs" / "mockllm__model.json")
    before = first.output.read_text(encoding="utf-8")
    args = ["resume-plan", "--model", "mockllm/model", "--results-dir", str(results),
            "--log-dir", str(tmp_path / "plan-cut" / "logs"), "--data-root", str(data_root)]

    assert cli.main(args) == cli.EXIT_INCOMPLETE
    assert "The run is complete. Nothing to resume." in capsys.readouterr().out

    assert cli.main(args + ["--rerun-truncated"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    rows = {line.split()[0]: line.split()[1:6] for line in out.splitlines() if line.startswith(("blas/", "tonada/"))}
    assert rows["blas/mutations"] == ["6", "0", "2", "2", "8"]
    assert rows["blas/tutor"] == ["4", "0", "2", "2", "6"]
    assert rows["blas/translation"] == ["4", "0", "0", "0", "4"]
    assert "cost 3 times that average" in out and f"lower answer limit ({OLD_LIMIT} tokens)" in out
    assert first.output.read_text(encoding="utf-8") == before  # read-only


def _reexport_source(first):
    first.output = first.output.rename(first.output.with_name("mockllm__model.json"))
    return first


def _reexport_args(first, data_root, output=None):
    args = [
        "reexport", "--model", "mockllm/model",
        "--results-dir", str(first.output.parent),
        "--log-dir", str(first.output.parent),
        "--data-root", str(data_root),
    ]
    if output is not None:
        args += ["--output", str(output)]
    return args


def _forbid_reexport_calls(monkeypatch):
    from unittest.mock import Mock

    from inspect_ai.model import Model

    forbidden = Mock(side_effect=AssertionError("reexport must not call a model or network"))
    monkeypatch.setattr(Model, "generate", forbidden)
    monkeypatch.setattr("teanga_bench.runner.inspect_eval", forbidden)
    monkeypatch.setattr("teanga_bench.pricing.fetch_catalog", forbidden)
    monkeypatch.setattr("teanga_bench.apikey.export_api_key", forbidden)
    return forbidden


@pytest.mark.parametrize("legacy", [False, True])
def test_reexport_recomputes_all_scores_without_model_calls(data_root, tmp_path, judges, monkeypatch, capsys, legacy):
    _run(data_root, tmp_path, "reexport", Candidate(flaky=FLAKY))
    first = _reexport_source(_resume(data_root, tmp_path, "reexport", Candidate()))
    original = first.document
    original["schema_version"] = "2.0.0" if legacy else "2.1.0"
    original["corrections"] = ["Preserve this hand correction."]
    if legacy:
        del original["config"]["dataset_hashes"]
        del original["truncation"]
    for block in _tests(original).values():
        block.pop("by_language_phenomenon", None)
        block.pop("by_l1_phenomenon", None)
        # An obsolete derived score must be rebuilt, not just copied.
        block["by_phenomenon"] = {}
    write_results(original, first.output)
    before = first.output.read_bytes()
    forbidden = _forbid_reexport_calls(monkeypatch)
    output = tmp_path / "rebuilt.json"
    assert cli.main(_reexport_args(first, data_root, output)) == cli.EXIT_OK
    forbidden.assert_not_called()
    rebuilt = json.loads(output.read_text(encoding="utf-8"))
    assert first.output.read_bytes() == before
    assert "all headline numbers reproduced" in capsys.readouterr().out
    assert rebuilt["schema_version"] == "2.2.0"
    assert rebuilt["reexported"]["from_schema"] == original["schema_version"]
    assert rebuilt["reexported"]["to_schema"] == "2.2.0"
    assert rebuilt["reexported"]["at"]
    assert rebuilt["overall"] == original["overall"]
    for field in ("config", "resumed", "corrections", "cost"):
        assert rebuilt[field] == original[field]
    assert rebuilt.get("truncation") == original.get("truncation")
    assert ("truncation" in rebuilt) == ("truncation" in original)
    for name, block in _tests(rebuilt).items():
        field = "by_l1_phenomenon" if name.startswith("tonada/") else "by_language_phenomenon"
        assert field in block
        assert block["by_phenomenon"]
        for headline in ("score", "ci95", "n_items", "cost_usd", "cost", "cost_per_correct_usd"):
            assert block[headline] == _tests(original)[name][headline]


def test_reexport_refuses_a_missing_sample_epoch(data_root, tmp_path, judges, monkeypatch, capsys):
    first = _reexport_source(_run(data_root, tmp_path, "run", Candidate()))
    log_path = next((first.output.parent / "logs").glob("*.json"))
    log = json.loads(log_path.read_text(encoding="utf-8"))
    log["samples"].pop()
    log_path.write_text(json.dumps(log), encoding="utf-8")
    before = first.output.read_bytes()
    forbidden = _forbid_reexport_calls(monkeypatch)
    output = tmp_path / "missing.json"
    assert cli.main(_reexport_args(first, data_root, output)) == cli.EXIT_INCOMPLETE
    forbidden.assert_not_called()
    assert "missing scored sample-epochs" in capsys.readouterr().err
    assert not output.exists()
    assert first.output.read_bytes() == before


@pytest.mark.parametrize("field", ["score", "ci95", "n_items", "cost_usd", "overall", "suite_overall"])
def test_reexport_refuses_headline_mismatches(data_root, tmp_path, judges, monkeypatch, capsys, field):
    first = _reexport_source(_run(data_root, tmp_path, "run", Candidate()))
    block = next(iter(_tests(first.document).values()))
    if field == "overall":
        first.document["overall"]["score"] += 0.1
    elif field == "suite_overall":
        first.document["suites"]["blas"]["overall"]["ci95"][0] += 0.1
    elif field == "ci95":
        block[field][0] += 0.1
    else:
        block[field] += 1
    write_results(first.document, first.output)
    before = first.output.read_bytes()
    forbidden = _forbid_reexport_calls(monkeypatch)
    # Default destination is the original file: mismatches must not touch it.
    assert cli.main(_reexport_args(first, data_root)) == cli.EXIT_INCOMPLETE
    forbidden.assert_not_called()
    error = capsys.readouterr().err
    assert "headline mismatch; nothing written" in error
    assert "existing" in error and "recomputed" in error
    assert first.output.read_bytes() == before


def test_reexport_refuses_dataset_changes(data_root, tmp_path, judges, monkeypatch, capsys):
    first = _reexport_source(_run(data_root, tmp_path, "run", Candidate()))
    path = data_root / "samples" / "blas" / "mutations.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    forbidden = _forbid_reexport_calls(monkeypatch)
    output = tmp_path / "changed.json"
    assert cli.main(_reexport_args(first, data_root, output)) == cli.EXIT_INCOMPLETE
    forbidden.assert_not_called()
    assert "dataset file(s) changed" in capsys.readouterr().err
    assert not output.exists()


def test_reexport_updates_archived_v1_and_refuses_to_cover_v2(data_root, tmp_path, judges, monkeypatch, capsys):
    first = _reexport_source(_run(data_root, tmp_path, "reexport-archive", Candidate()))
    results = first.output.parent
    archive = results / "v1-archive" / "runs"
    archive.mkdir(parents=True)
    archived = archive / first.output.name
    document = json.loads(first.output.read_text(encoding="utf-8"))
    document["methodology"] = "v1"
    original_overall = document["overall"]
    archived.write_text(json.dumps(document), encoding="utf-8")
    first.output.unlink()
    runs_path = results / "runs" / first.output.name
    forbidden = _forbid_reexport_calls(monkeypatch)
    args = [
        "reexport", "--model", "mockllm/model",
        "--results-dir", str(results),
        "--log-dir", str(results),
        "--data-root", str(data_root),
    ]
    assert cli.main(args) == cli.EXIT_OK
    forbidden.assert_not_called()
    assert not runs_path.exists()
    rebuilt = json.loads(archived.read_text(encoding="utf-8"))
    assert rebuilt["methodology"] == "v1"
    assert rebuilt["overall"] == original_overall

    runs_path.parent.mkdir(parents=True)
    v2 = json.loads(json.dumps(rebuilt))
    v2["methodology"] = "v2"
    v2_bytes = json.dumps(v2).encode("utf-8")
    runs_path.write_bytes(v2_bytes)
    archive_bytes = archived.read_bytes()
    assert cli.main(args) == cli.EXIT_INCOMPLETE
    assert "pass --output" in capsys.readouterr().err
    assert runs_path.read_bytes() == v2_bytes
    assert archived.read_bytes() == archive_bytes

    runs_path.unlink()
    assert cli.main(args + ["--output", str(runs_path)]) == cli.EXIT_INCOMPLETE
    assert "refusing to write a v1 reexport" in capsys.readouterr().err
    assert not runs_path.exists()
    assert archived.read_bytes() == archive_bytes


def test_reexport_refuses_an_incomplete_run(data_root, tmp_path, judges, monkeypatch, capsys):
    first = _reexport_source(_run(data_root, tmp_path, "run", Candidate(flaky=FLAKY)))
    forbidden = _forbid_reexport_calls(monkeypatch)
    output = tmp_path / "incomplete.json"
    assert cli.main(_reexport_args(first, data_root, output)) == cli.EXIT_INCOMPLETE
    forbidden.assert_not_called()
    assert "requires a complete run" in capsys.readouterr().err
    assert not output.exists()
