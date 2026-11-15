"""Per-run Markdown report.

Short plain summary, one table per suite, one per-language table, and failure
examples. Failure examples are already limited to public sample items in the
results JSON, and this module checks the flag again before printing.
"""

from __future__ import annotations

from typing import Any

SNIPPET = 240


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def interval_text(ci: list[float] | None) -> str:
    return "n/a" if not ci else f"{ci[0] * 100:.1f}% to {ci[1] * 100:.1f}%"


def usd(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:.4f}" if value < 1 else f"${value:.2f}"


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _snippet(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= SNIPPET else text[: SNIPPET - 1] + "…"


def _test_label(block: dict[str, Any]) -> str:
    label = block["test"]
    if block.get("dataset") == "public_sample":
        label += " (public sample)"
    if block.get("status") != "complete":
        label += " (incomplete)"
    return label


def summary_sentences(document: dict[str, Any]) -> list[str]:
    model = document["model"]["id"]
    config = document["config"]
    cost = document["cost"]
    tests = [
        block
        for suite in document["suites"].values()
        for block in suite["tests"].values()
    ]
    done = [block for block in tests if block["status"] == "complete"]
    sentences = []
    status = document["status"]
    first = (
        f"{model} ran {len(done)} of {len(tests)} tests with {config['epochs']} "
        f"epochs per item, and the run status is {status}."
    )
    sentences.append(first)
    overall = document.get("overall")
    if overall:
        sentences.append(
            f"The overall score is {pct(overall['score'])} "
            f"(95% interval {interval_text(overall['ci95'])}), with each completed test weighted equally."
        )
    else:
        sentences.append("No test finished, so there is no overall score.")
    scored = [block for block in done if block["score"] is not None]
    if scored:
        best = max(scored, key=lambda block: block["score"])
        worst = min(scored, key=lambda block: block["score"])
        sentences.append(
            f"The best test was {best['suite']}/{best['test']} at {pct(best['score'])} "
            f"and the weakest was {worst['suite']}/{worst['test']} at {pct(worst['score'])}."
        )
    tutor = next((block for block in done if "tutor" in block), None)
    if tutor is not None:
        explanation = tutor["tutor"]["explanation"]
        if explanation["score"] is None:
            tail = f"the explanation was not scored ({explanation['status']})"
        else:
            tail = f"the explanation score is {pct(explanation['score'])} (judge-marked, not human-validated)"
        sentences.append(f"On the tutor test the rule-only headline is {pct(tutor['score'])}, and {tail}.")
    sentences.append(
        f"The run cost {usd(cost['total_usd'])} against a cap of {usd(cost['cap_usd'])}, "
        f"of which {usd(cost['judge_usd'])} was judge spend."
    )
    return sentences[:5]


def build_report(document: dict[str, Any]) -> str:
    lines = [f"# Teanga Bench report: {document['model']['id']}", ""]
    lines.append(" ".join(summary_sentences(document)))
    lines.append("")
    lines.append(
        f"Run kind: {document['run_kind']}. Status: {document['status']}. "
        f"Generated {document['generated_at']}."
    )
    if document["run_kind"] == "mock":
        lines += ["", "This is a mock run. The numbers are not model scores."]
    for suite_name, suite in sorted(document["suites"].items()):
        lines += ["", f"## Suite: {suite_name}", ""]
        lines.append("| Test | Score | 95% interval | Items | Cost (USD) |")
        lines.append("| --- | --- | --- | --- | --- |")
        for _name, block in sorted(suite["tests"].items()):
            lines.append(
                f"| {_cell(_test_label(block))} | {pct(block['score'])} | {interval_text(block['ci95'])} "
                f"| {block['n_items']} | {usd(block['cost_usd'])} |"
            )
    overall = document.get("overall")
    if overall and overall.get("by_language"):
        lines += ["", "## By language", ""]
        lines.append("| Language | Score | 95% interval | Items |")
        lines.append("| --- | --- | --- | --- |")
        for language, stat in sorted(overall["by_language"].items()):
            lines.append(
                f"| {_cell(language)} | {pct(stat['score'])} | {interval_text(stat['ci95'])} | {stat['n_items']} |"
            )
    lines += ["", "## Failure examples", ""]
    lines.append("Examples come only from items published in `samples/`.")
    for suite_name, suite in sorted(document["suites"].items()):
        for _name, block in sorted(suite["tests"].items()):
            examples = [ex for ex in block.get("failure_examples", []) if ex.get("public") is True]
            lines += ["", f"### {suite_name}/{block['test']}", ""]
            if not examples:
                lines.append("No public failure examples for this test.")
                continue
            for example in examples:
                lines.append(f"- `{example['id']}` score {example['score']:.2f}")
                lines.append(f"  - Prompt: {_snippet(example['input'])}")
                lines.append(f"  - Expected: {_snippet(example['expected'])}")
                lines.append(f"  - Model output: {_snippet(example['output'])}")
                if example.get("pivot_text"):
                    lines.append(f"  - Pivot text: {_snippet(example['pivot_text'])}")
    for block in (b for s in document["suites"].values() for b in s["tests"].values()):
        if "tutor" in block:
            tutor = block["tutor"]
            explanation = tutor["explanation"]
            lines += ["", f"## Tutor detail: {block['suite']}/{block['test']}", ""]
            lines.append(
                f"Headline ({tutor['headline']}): {pct(block['score'])}. "
                f"Found {pct(tutor['components']['found'])}, fixed {pct(tutor['components']['fixed'])}, "
                f"no over-correction {pct(tutor['components']['no_overcorrection'])}."
            )
            lines.append("")
            if explanation["score"] is None:
                lines.append(f"Explanation, {explanation['label']}: not scored ({explanation['status']}).")
            else:
                lines.append(
                    f"Explanation, {explanation['label']}: {pct(explanation['score'])} "
                    f"(95% interval {interval_text(explanation['ci95'])}). "
                    f"Judge agreement {pct(explanation['judge_agreement'])}. "
                    f"Judge failures {explanation['judge_failures']}. "
                    f"Judges: {', '.join(tutor['judges'])}."
                )
    lines.append("")
    return "\n".join(lines)
