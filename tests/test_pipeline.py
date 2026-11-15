"""End-to-end runs against fixture datasets with mock models. No network."""

import json

import pytest
from inspect_ai.log import list_eval_logs, read_eval_log
from inspect_ai.model import ModelOutput, get_model

from teanga_bench import cli
from teanga_bench.datasets import discover, select
from teanga_bench.runner import RunError, RunOptions, run_benchmark
from teanga_bench.scoring import chrf_score


def _outputs(*texts):
    return get_model(
        "mockllm/model",
        custom_outputs=[ModelOutput.from_content(model="mockllm/model", content=t) for t in texts],
        memoize=False,
    )


def _options(root, tmp_path, **kwargs):
    kwargs.setdefault("epochs", 1)
    return RunOptions(model="mockllm/model", root=root, log_dir=tmp_path / "logs", **kwargs)


def test_data_driven_discovery_and_public_sample_fallback(private_root):
    files = discover(private_root)
    assert {name for name in (f.name for f in files.values())} == {
        "blas/mutations", "blas/round_trip", "blas/translation", "blas/tutor", "tonada/tutor",
    }
    assert files[("blas", "mutations")].kind == "full"
    assert files[("blas", "translation")].kind == "public_sample"
    assert [f.name for f in select(files, ["translation", "tonada/tutor"])] == ["blas/translation", "tonada/tutor"]
    with pytest.raises(KeyError):
        select(files, ["no_such_test"])


def test_dataset_kind_is_recorded_per_test(private_root, tmp_path):
    document = run_benchmark(_options(private_root, tmp_path, limit=1)).document
    kinds = {
        f"{suite}/{test}": block["dataset"]
        for suite, body in document["suites"].items()
        for test, block in body["tests"].items()
    }
    assert kinds["blas/mutations"] == "full"
    assert kinds["blas/translation"] == "public_sample"
    assert kinds["tonada/tutor"] == "public_sample"


def test_private_items_never_appear_in_failure_examples_or_the_report(private_root, tmp_path):
    from teanga_bench.report import build_report

    # The mock model answers nothing useful, so every item fails.
    result = run_benchmark(_options(private_root, tmp_path, tests=["mutations"]))
    block = result.document["suites"]["blas"]["tests"]["mutations"]
    assert block["n_items"] == 6  # 4 public + 2 private-only
    assert block["failure_examples"]
    public = {"fx-mut-00", "fx-mut-01", "fx-mut-02", "fx-mut-03"}
    assert all(example["public"] is True for example in block["failure_examples"])
    assert {example["id"] for example in block["failure_examples"]} <= public
    published = json.dumps(result.document, ensure_ascii=False) + build_report(result.document)
    for secret in ("private-only", "PRIVATE PROMPT", "private-answer", "zzqq"):
        assert secret not in published


def test_a_private_only_failure_set_gives_no_examples(private_root, tmp_path):
    # Drop the public sample for mutations: nothing is public, so nothing may be shown.
    (private_root / "samples" / "blas" / "mutations.jsonl").unlink()
    block = run_benchmark(_options(private_root, tmp_path, tests=["mutations"])).document["suites"]["blas"]["tests"]["mutations"]
    assert block["dataset"] == "full"
    assert block["failure_examples"] == []


def test_accept_list_and_translation_scoring_through_the_solver(fixture_root, tmp_path):
    model = _outputs("ANSWER: bhean", "Tá an cat anseo.")
    document = run_benchmark(_options(fixture_root, tmp_path, tests=["mutations", "translation"], limit=1), inspect_model=model).document
    assert document["suites"]["blas"]["tests"]["mutations"]["score"] == 1.0
    assert document["suites"]["blas"]["tests"]["translation"]["score"] == pytest.approx(1.0)


def test_round_trip_makes_two_calls_in_two_conversations(fixture_root, tmp_path):
    pivot, back = "The cat is here.", "Tá an cat ann."
    model = _outputs(pivot, back)
    result = run_benchmark(_options(fixture_root, tmp_path, tests=["round_trip"], limit=1), inspect_model=model)
    block = result.document["suites"]["blas"]["tests"]["round_trip"]
    assert block["score"] == pytest.approx(chrf_score(back, ["Tá an cat anseo."]))
    assert 0 < block["score"] < 1
    example = block["failure_examples"][0]
    assert example["pivot_text"] == pivot  # the pivot text is stored
    assert example["output"] == back
    assert result.document["cost"]["by_model"]["mockllm/model"]["calls"] == 2

    log = read_eval_log(list_eval_logs(str(tmp_path / "logs"))[0].name, resolve_attachments=True)
    model_events = [event for event in log.samples[0].events if event.event == "model"]
    assert len(model_events) == 2
    first_input = "\n".join(m.text for m in model_events[0].input)
    second_input = "\n".join(m.text for m in model_events[1].input)
    assert "Tá an cat anseo." in first_input  # the source goes to the pivot call
    assert pivot in second_input  # the pivot goes to the back-translation call
    assert "Tá an cat anseo." not in second_input  # and the source does not
    assert pivot not in first_input
    assert len(model_events[1].input) == 2  # system + user only: a fresh conversation


def test_round_trip_with_an_empty_pivot_scores_zero_without_a_second_call(fixture_root, tmp_path):
    model = _outputs("")
    result = run_benchmark(_options(fixture_root, tmp_path, tests=["round_trip"], limit=1), inspect_model=model)
    assert result.document["suites"]["blas"]["tests"]["round_trip"]["score"] == 0.0
    assert result.document["cost"]["by_model"]["mockllm/model"]["calls"] == 1


def test_epochs_repeat_items_and_report_consistency(fixture_root, tmp_path):
    result = run_benchmark(_options(fixture_root, tmp_path, tests=["mutations"], epochs=3, limit=2))
    block = result.document["suites"]["blas"]["tests"]["mutations"]
    assert (block["n_items"], block["epochs"], block["consistency"]) == (2, 3, 1.0)
    assert result.document["cost"]["by_model"]["mockllm/model"]["calls"] == 6
    assert set(block["by_language"]) == {"irish"} and block["by_phenomenon"] and block["by_cefr"] and block["by_evidence"] and block["by_l1"]


def test_tutor_headline_is_rule_only_and_explanation_is_judge_marked(fixture_root, tmp_path, monkeypatch):
    tutor_ok = json.dumps(
        {"has_error": True, "error_span": "C", "correction": "", "corrected_sentence": "Cosnaíonn sé an teach.", "explanation": "Doubled C."}
    )
    verdicts = iter(
        [ModelOutput.from_content(model="mockllm/model", content='{"explanation_ok": false, "reason": "weak"}')] * 2
    )
    judge = get_model("mockllm/model", custom_outputs=verdicts, memoize=False)
    import teanga_bench.runner as runner_module

    real = runner_module._judges_for_run

    def with_mock_judges(options, catalog):
        specs, choices, status = real(options, catalog)
        for spec in specs:
            spec.model = judge
        return specs, choices, status

    monkeypatch.setattr(runner_module, "_judges_for_run", with_mock_judges)
    result = run_benchmark(_options(fixture_root, tmp_path, tests=["blas/tutor"], limit=1), inspect_model=_outputs(tutor_ok))
    block = result.document["suites"]["blas"]["tests"]["tutor"]
    assert block["score"] == 1.0  # headline: found, fixed, no over-correction; the judges said no
    explanation = block["tutor"]["explanation"]
    assert explanation["score"] == 0.0
    assert explanation["label"] == "judge-marked, not human-validated"
    assert explanation["judge_agreement"] == 1.0
    assert explanation["judge_failures"] == 0
    by_model = result.document["cost"]["by_model"]
    assert sum(usage["calls"] for usage in by_model.values()) == 3  # candidate + two judges
    assert result.document["cost"]["judge_usd"] == 0.0 and by_model["mockllm/judge-1"]["calls"] == 1


def test_cli_mock_run_writes_json_report_leaderboard_and_charts(fixture_root, tmp_path, capsys):
    output = tmp_path / "out" / "run.json"
    code = cli.main(
        [
            "run", "--model", "mockllm/model", "--limit", "2", "--epochs", "2",
            "--data-root", str(fixture_root), "--output", str(output), "--log-dir", str(tmp_path / "logs"),
        ]
    )
    assert code == 0
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["schema_version"] == "2.0.0" and document["status"] == "complete"
    assert output.with_suffix(".md").read_text(encoding="utf-8").startswith("# Teanga Bench report")
    board = tmp_path / "out" / "board"
    assert (board / "leaderboard.json").is_file() and (board / "leaderboard.md").is_file()
    charts = {path.name for path in (board / "charts").glob("*.svg")}
    assert {"suite-blas.svg", "suite-tonada.svg", "score-vs-cost.svg", "language-irish.svg"} <= charts
    assert "OPENROUTER" not in output.read_text(encoding="utf-8")


def test_unknown_model_is_a_clear_error(fixture_root):
    from teanga_bench.pricing import Catalog

    catalog = Catalog(entries={"a/b": {"pricing": {"prompt": "0.1", "completion": "0.2"}}}, retrieved_at="now")
    with pytest.raises(RunError, match="not in the live OpenRouter model list"):
        run_benchmark(RunOptions(model="nope/missing", root=fixture_root), catalog=catalog)


def _catalog(*names):
    from teanga_bench.pricing import Catalog

    pricing = {"prompt": "0.000001", "completion": "0.000002", "input_cache_read": "0.0000001"}
    entries = {name: {"id": name, "pricing": pricing} for name in names}
    return Catalog(entries=entries, retrieved_at="2026-11-15T00:00:00+00:00")


JUDGES = ["deepseek/deepseek-v4.1-flash-1017", "qwen/qwen3.8-flash"]


def _live(fixture_root, tmp_path, monkeypatch, model, catalog, outputs):
    import teanga_bench.runner as runner_module

    monkeypatch.setattr(runner_module, "export_api_key", lambda: None)
    return run_benchmark(
        RunOptions(model=model, root=fixture_root, epochs=1, limit=1, tests=["blas/tutor"], log_dir=tmp_path / "logs"),
        catalog=catalog,
        inspect_model=_outputs(*outputs),
    )


TUTOR_OK = json.dumps(
    {"has_error": True, "error_span": "C", "correction": "", "corrected_sentence": "Cosnaíonn sé an teach.", "explanation": "Doubled C."}
)


def test_live_path_records_prices_and_the_fixed_judge_pair(fixture_root, tmp_path, monkeypatch):
    import teanga_bench.scorers as scorers_module

    verdict = ModelOutput.from_content(model="mockllm/model", content='{"explanation_ok": true, "reason": "ok"}')
    judge = get_model("mockllm/model", custom_outputs=[verdict, verdict], memoize=False)
    real_get_model = scorers_module.get_model
    monkeypatch.setattr(scorers_module, "get_model", lambda model=None, **kw: real_get_model(model, **kw) if model is None else judge)
    catalog = _catalog("openai/gpt-6-luna", *JUDGES)
    document = _live(fixture_root, tmp_path, monkeypatch, "openai/gpt-6-luna", catalog, [TUTOR_OK]).document
    assert document["run_kind"] == "live"
    assert document["model"]["family"] == "openai"
    assert document["model"]["pricing"]["completion_usd_per_token"] == pytest.approx(2e-6)
    assert document["model"]["pricing"]["cache_read_usd_per_token"] == pytest.approx(1e-7)
    assert document["model"]["pricing"]["retrieved_at"] == "2026-11-15T00:00:00+00:00"
    assert document["judges"] == JUDGES
    assert document["explanation_status"] == "scored"
    tutor = document["suites"]["blas"]["tests"]["tutor"]["tutor"]
    assert tutor["judges"] == JUDGES
    assert tutor["explanation"]["status"] == "scored" and tutor["explanation"]["score"] == 1.0
    assert set(document["judge_info"]["pricing"]) == set(JUDGES)
    assert document["cost"]["judge_usd"] > 0 and document["cost"]["cap_usd"] == 5.0


@pytest.mark.parametrize("candidate", ["deepseek/deepseek-v4.1-pro", "qwen/qwen3.8-max", "~qwen/latest"])
def test_candidate_in_a_judge_family_gets_no_judge_calls(fixture_root, tmp_path, monkeypatch, candidate):
    catalog = _catalog(candidate, *JUDGES)
    result = _live(fixture_root, tmp_path, monkeypatch, candidate, catalog, [TUTOR_OK])
    document = result.document
    assert document["explanation_status"] == "not_scored_same_family_as_judge"
    assert document["judges"] == JUDGES
    block = document["suites"]["blas"]["tests"]["tutor"]
    assert block["score"] == 1.0  # the headline never needs a judge
    explanation = block["tutor"]["explanation"]
    assert explanation["score"] is None and explanation["status"] == "not_scored_same_family_as_judge"
    assert document["cost"]["judge_usd"] == 0 and document["status"] == "complete"
    assert set(document["cost"]["by_model"]) == {candidate}


def test_missing_judge_in_the_live_list_means_no_explanation_but_the_run_completes(fixture_root, tmp_path, monkeypatch):
    catalog = _catalog("openai/gpt-6-luna", JUDGES[0])  # qwen judge absent
    document = _live(fixture_root, tmp_path, monkeypatch, "openai/gpt-6-luna", catalog, [TUTOR_OK]).document
    assert document["explanation_status"] == "not_scored_judge_unavailable"
    assert document["status"] == "complete"
    block = document["suites"]["blas"]["tests"]["tutor"]
    assert block["score"] == 1.0
    assert block["tutor"]["explanation"]["score"] is None
    assert block["tutor"]["explanation"]["status"] == "not_scored_judge_unavailable"
    assert document["cost"]["judge_usd"] == 0
