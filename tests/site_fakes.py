"""Fake results files for the site tests. Shaped like docs/results-schema.md."""

from __future__ import annotations

import random
from typing import Any

BLAS_TESTS = {
    "lesson_exercises": "accept_list",
    "morphology": "accept_list",
    "translation": "translation",
    "round_trip": "round_trip",
    "tutor_accuracy": "tutor",
}
TONADA_TESTS = {"exercises": "accept_list", "tutor_accuracy": "tutor"}
BLAS_LANGUAGES = ["irish", "welsh", "scots-gaelic", "manx", "breton", "cornish"]
L1S = ["portuguese", "spanish", "vietnamese", "japanese"]
CEFR = ["A1", "A2", "B1", "B2", "unspecified"]
TOPICS = [
    "verb_present", "verb_past", "verb_future", "noun_plural", "copula", "prepositions",
    "mutations", "articles", "word_order", "numbers", "pronouns", "negation",
]


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


def _block(rng, suite, test, scoring, centre, epochs, output_text) -> dict[str, Any]:
    groups = BLAS_LANGUAGES if suite == "blas" else L1S
    per_group = 40 if suite == "blas" else 60
    n_items = per_group * len(groups)
    block = {
        "suite": suite, "test": test, "scoring": scoring, "dataset": "full", "status": "complete",
        "incomplete_reason": None, "n_items_dataset": n_items, "n_errors": 0,
        **_stat(rng, centre, n_items, epochs),
    }
    block["ci95"] = [round(max(0.0, block["score"] - 0.04), 4), round(min(1.0, block["score"] + 0.04), 4)]
    candidate = round(rng.uniform(0.02, 0.4) * (centre + 0.5), 4)
    judge = round(candidate * 0.3, 4) if scoring == "tutor" else 0.0
    block["cost_usd"] = round(candidate + judge, 4)
    block["cost_per_correct_usd"] = block["cost_usd"] / (block["score"] * n_items * epochs) if block["score"] else None
    block["cost"] = {"candidate": {"cost_usd": candidate, "calls": n_items * epochs}, "judge": {"cost_usd": judge}}
    block["n_human_checked"] = 0
    language_key = "by_language" if suite == "blas" else "by_l1"
    block[language_key] = {g: _stat(rng, centre - 0.1 * i / len(groups), per_group, epochs) for i, g in enumerate(groups)}
    if suite == "blas":
        block["by_l1"] = {"none": _stat(rng, centre, n_items, epochs)}
    else:
        block["by_language"] = {"english": _stat(rng, centre, n_items, epochs)}
    block["by_cefr"] = {c: _stat(rng, centre + 0.05 - 0.03 * i, n_items // len(CEFR), epochs) for i, c in enumerate(CEFR)}
    block["by_phenomenon"] = {
        t: _stat(rng, centre, rng.choice([2, 4, 8, 15, 30]), epochs) for t in TOPICS
    }
    block["by_evidence"] = {"blas-app-only": _stat(rng, centre, n_items, epochs)}
    if scoring == "tutor":
        block["tutor"] = {
            "headline": "rule-only: found AND fixed AND no over-correction",
            "judges": ["google/gemini-judge", "mistralai/mistral-judge"],
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
) -> dict[str, Any]:
    rng = random.Random(f"{model}-{seed}")
    suites = {}
    total = 0.0
    for suite, tests in (("blas", BLAS_TESTS), ("tonada", TONADA_TESTS)):
        blocks = {
            test: _block(rng, suite, test, scoring, centre + rng.uniform(-0.15, 0.1), epochs, output_text)
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
        "prompt_usd_per_token": 0.0000004, "completion_usd_per_token": 0.0000016,
        "cache_read_usd_per_token": None, "cache_write_usd_per_token": None,
        "source": "https://openrouter.ai/api/v1/models", "retrieved_at": generated_at,
    }
    return {
        "schema_version": "2.0.0", "benchmark": "teanga-bench", "benchmark_name": "Teanga Bench",
        "benchmark_version": "0.2.0", "started_at": generated_at, "generated_at": generated_at,
        "run_kind": run_kind, "status": status,
        "model": {"id": model, "family": model.split("/")[0], "inspect_id": f"openrouter/{model}", "pricing": pricing},
        "config": {"epochs": epochs, "limit": None, "max_cost_usd": 5.0},
        "judges": ["google/gemini-judge", "mistralai/mistral-judge"],
        "explanation_status": "scored",
        "judge_info": {"called": True, "pricing": {"google/gemini-judge": pricing, "mistralai/mistral-judge": pricing}},
        "gold": {"note": "sourced"},
        "cost": {"cap_usd": 5.0, "total_usd": round(total, 4), "candidate_usd": round(total * 0.9, 4), "judge_usd": round(total * 0.1, 4), "cap_reached": False, "by_model": {}},
        "overall": {
            "score": overall_score, "ci95": [overall_score - 0.03, overall_score + 0.03], "n_tests": 7, "n_items": 2000,
            "by_language": {},
        },
        "suites": suites,
        "tool_versions": {"inspect_ai": "0.3.0"},
    }
