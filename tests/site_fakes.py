"""Fake results files for the site tests. Shaped like docs/results-schema.md.

``nine_models()`` gives a realistic leaderboard for previewing the site:
nine complete runs with spread-out scores and costs, plus one run the cost
cap stopped.
"""

from __future__ import annotations

import random
from typing import Any

from teanga_bench.models_config import configured_judges

BLAS_TESTS = {
    "lesson_exercises": "accept_list",
    "morphology": "accept_list",
    "translation": "translation",
    "round_trip": "round_trip",
    "tutor_accuracy": "tutor",
}
TONADA_TESTS = {"exercises": "accept_list", "tutor_accuracy": "tutor"}
# Some tests are harder than others for every model.
TEST_OFFSET = {
    "lesson_exercises": 0.08, "morphology": 0.0, "translation": -0.08, "round_trip": -0.12,
    "tutor_accuracy": -0.05, "exercises": 0.1,
}
BLAS_LANGUAGES = ["irish", "welsh", "scots-gaelic", "manx", "breton", "cornish"]
L1S = ["portuguese", "spanish", "vietnamese", "japanese"]
# Item counts per level and topic are the same for every model, as in real runs.
# C1 has too few items to plot; "unspecified" is not a level.
CEFR_ITEMS = {"A1": 60, "A2": 60, "B1": 50, "B2": 40, "C1": 12, "unspecified": 18}
TOPICS = [
    "verb_present", "verb_past", "verb_future", "noun_plural", "copula", "prepositions",
    "mutations", "articles", "word_order", "numbers", "pronouns", "negation",
]
TOPIC_ITEMS = [30, 31, 23, 22, 40, 8, 4, 25, 30, 12, 50, 20]
DIRECTIONS = {"to_english": (100, 0.05), "from_english": (100, -0.06), "legal_or_administrative": (40, -0.02)}
# Evidence label: (items, score offset). Weaker gold scores a little lower here.
EVIDENCE = {
    "blas": {"blas-app+kaikki": (70, 0.03), "blas-app-only": (130, 0.0), "blas-app-unverified": (33, -0.05), "blas-app+bunamo": (7, 0.0)},
    "tonada": {
        "tonada-app-answer-machine-reviewed": (70, 0.08),
        "tonada-app-distractor-machine-reviewed": (130, 0.0),
        "wikipedia-revision-silver-unreviewed": (40, -0.35),
    },
}
JUDGES = [judge.id for judge in configured_judges()]


def _stat(rng: random.Random, centre: float, n: int, epochs: int) -> dict[str, Any]:
    score = max(0.0, min(1.0, centre + rng.uniform(-0.12, 0.12)))
    half = 0.9 / max(n, 1) ** 0.5 * 0.5
    return {
        "score": round(score, 4),
        "ci95": [round(max(0.0, score - half), 4), round(min(1.0, score + half), 4)],
        "n_items": n,
        "epochs": epochs,
        "consistency": round(rng.uniform(0.7, 0.98), 4),
    }


def _block(rng, suite, test, scoring, centre, epochs, output_text, cost_scale, dataset) -> dict[str, Any]:
    groups = BLAS_LANGUAGES if suite == "blas" else L1S
    per_group = 40 if suite == "blas" else 60
    n_items = per_group * len(groups)
    block = {
        "suite": suite, "test": test, "scoring": scoring, "dataset": dataset, "status": "complete",
        "incomplete_reason": None, "n_items_dataset": n_items, "n_errors": 0,
        **_stat(rng, centre, n_items, epochs),
    }
    block["ci95"] = [round(max(0.0, block["score"] - 0.04), 4), round(min(1.0, block["score"] + 0.04), 4)]
    candidate = round(rng.uniform(0.02, 0.4) * (centre + 0.5) * cost_scale, 4)
    judge = round(rng.uniform(0.02, 0.06), 4) if scoring == "tutor" else 0.0
    block["cost_usd"] = round(candidate + judge, 4)
    block["cost_per_correct_usd"] = block["cost_usd"] / (block["score"] * n_items * epochs) if block["score"] else None
    block["cost"] = {"candidate": {"cost_usd": candidate, "calls": n_items * epochs}, "judge": {"cost_usd": judge}}
    block["n_human_checked"] = 0
    language_key = "by_language" if suite == "blas" else "by_l1"
    block[language_key] = {g: _stat(rng, centre - 0.2 * i / len(groups), per_group, epochs) for i, g in enumerate(groups)}
    if suite == "blas":
        block["by_l1"] = {"none": _stat(rng, centre, n_items, epochs)}
    else:
        block["by_language"] = {"english": _stat(rng, centre, n_items, epochs)}
    block["by_cefr"] = {c: _stat(rng, centre + 0.05 - 0.03 * i, n, epochs) for i, (c, n) in enumerate(CEFR_ITEMS.items())}
    if scoring == "translation":
        block["by_phenomenon"] = {d: _stat(rng, centre + shift, n, epochs) for d, (n, shift) in DIRECTIONS.items()}
    else:
        block["by_phenomenon"] = {
            t: _stat(rng, centre + 0.1 - 0.02 * i, n, epochs) for i, (t, n) in enumerate(zip(TOPICS, TOPIC_ITEMS))
        }
    block["by_evidence"] = {label: _stat(rng, centre + shift, n, epochs) for label, (n, shift) in EVIDENCE[suite].items()}
    if scoring == "tutor":
        block["tutor"] = {
            "headline": "rule-only: found AND fixed AND no over-correction",
            "judges": list(JUDGES),
            "components": {"found": round(centre + 0.1, 3), "fixed": round(centre + 0.05, 3), "no_overcorrection": 0.9},
            "explanation": {
                "label": "judge-marked, not human-validated",
                "status": "scored",
                "score": round(centre * 0.9, 4), "ci95": [round(centre * 0.85, 4), round(centre * 0.95, 4)],
                "n_items": n_items, "epochs": epochs, "judged_item_epochs": n_items * epochs - 3,
                "unscored_item_epochs": 3, "judge_agreement": 0.87, "judge_failures": 4,
            },
        }
    language = groups[0] if suite == "blas" else "english"
    l1 = "none" if suite == "blas" else groups[0]
    block["failure_examples"] = [
        {
            "id": f"{suite}-{test}-{k}", "public": True, "language": language, "l1": l1, "phenomenon": TOPICS[k],
            "input": f"Give the plural of 'cat' in {language}.\nReply with the answer on one line, in this exact form:\nANSWER: <answer>",
            "expected": "cait", "output": output_text if k == 0 else "ANSWER: cats", "score": 0.0,
        }
        for k in range(2)
    ]
    if scoring == "round_trip":
        block["failure_examples"][0]["pivot_text"] = "The cats are on the wall."
    return block


def fake_document(
    model: str,
    centre: float,
    *,
    seed: int = 1,
    status: str = "complete",
    run_kind: str = "live",
    generated_at: str = "2026-11-14T10:00:00+00:00",
    output_text: str = "ANSWER: cats",
    epochs: int = 3,
    cost_scale: float = 1.0,
    dataset: str = "full",
) -> dict[str, Any]:
    rng = random.Random(f"{model}-{seed}")
    suites = {}
    total = 0.0
    for suite, tests in (("blas", BLAS_TESTS), ("tonada", TONADA_TESTS)):
        blocks = {
            test: _block(
                rng, suite, test, scoring, centre + TEST_OFFSET.get(test, 0.0) + rng.uniform(-0.06, 0.06),
                epochs, output_text, cost_scale, dataset,
            )
            for test, scoring in tests.items()
        }
        mean = sum(b["score"] for b in blocks.values()) / len(blocks)
        suites[suite] = {
            "overall": {"score": round(mean, 4), "ci95": [round(mean - 0.03, 4), round(mean + 0.03, 4)], "n_tests": len(blocks), "n_items": sum(b["n_items"] for b in blocks.values())},
            "tests": blocks,
        }
        total += sum(b["cost_usd"] for b in blocks.values())
    overall_score = round(
        sum(b["score"] for s in suites.values() for b in s["tests"].values()) / 7, 4
    )
    pricing = {
        "prompt_usd_per_token": 0.0000004 * cost_scale, "completion_usd_per_token": 0.0000016 * cost_scale,
        "cache_read_usd_per_token": None, "cache_write_usd_per_token": None,
        "source": "https://openrouter.ai/api/v1/models", "retrieved_at": generated_at,
    }
    return {
        "schema_version": "2.0.0", "benchmark": "teanga-bench", "benchmark_name": "Teanga Bench",
        "benchmark_version": "0.2.0", "started_at": generated_at, "generated_at": generated_at,
        "run_kind": run_kind, "status": status,
        "model": {"id": model, "family": model.split("/")[0], "inspect_id": f"openrouter/{model}", "pricing": pricing},
        "config": {"epochs": epochs, "limit": None, "max_cost_usd": 5.0},
        "judges": list(JUDGES),
        "explanation_status": "scored",
        "judge_info": {"called": True, "pricing": {judge: pricing for judge in JUDGES}},
        "gold": {"note": "sourced"},
        "cost": {"cap_usd": 5.0, "total_usd": round(total, 4), "candidate_usd": round(total * 0.9, 4), "judge_usd": round(total * 0.1, 4), "cap_reached": False, "by_model": {}},
        "overall": {
            "score": overall_score, "ci95": [overall_score - 0.03, overall_score + 0.03], "n_tests": 7, "n_items": 2000,
            "by_language": {},
        },
        "suites": suites,
        "tool_versions": {"inspect_ai": "0.3.0"},
    }


# (OpenRouter id, centre score, cost scale) for a realistic preview leaderboard.
NINE_MODELS = (
    ("anthropic/claude-opus-5", 0.84, 6.0),
    ("openai/gpt-6-astra", 0.83, 4.0),
    ("google/gemini-3.5-pro", 0.81, 3.0),
    ("openai/gpt-6-luna", 0.78, 1.0),
    ("x-ai/grok-5", 0.75, 2.5),
    ("moonshotai/kimi-k3", 0.71, 0.6),
    ("mistralai/mistral-large-3", 0.66, 0.8),
    ("meta-llama/llama-5-maverick", 0.6, 0.35),
    ("google/gemma-4-27b", 0.52, 0.12),
)


def nine_models() -> dict[str, dict[str, Any]]:
    """File stem to results document: nine complete runs and one capped run."""
    documents = {}
    for day, (model, centre, scale) in enumerate(NINE_MODELS):
        documents[model.replace("/", "__")] = fake_document(
            model, centre, cost_scale=scale, generated_at=f"2026-11-{10 + day:02d}T09:00:00+00:00"
        )
    documents["z-ai__glm-5"] = fake_document("z-ai/glm-5", 0.7, status="cost_cap_reached")
    return documents


def twenty_models() -> dict[str, dict[str, Any]]:
    """File stem to results document: twenty-two complete runs, for layout at scale."""
    makers = ("openai", "anthropic", "google", "deepseek", "qwen", "mistralai", "x-ai", "moonshotai", "z-ai", "meta-llama", "cohere")
    documents = {}
    for i in range(22):
        model = f"{makers[i % len(makers)]}/model-{i + 1:02d}"
        centre = 0.9 - i * 0.02
        documents[model.replace("/", "__")] = fake_document(model, centre, cost_scale=8.0 / (1 + i * 0.6))
    return documents
