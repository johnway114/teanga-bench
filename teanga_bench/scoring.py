"""Pure scoring functions.

Inspect scorers call these. Unit tests call them with mocked completions and
never touch a model provider.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from sacrebleu.metrics import CHRF

from teanga_bench.normalize import normalize_answer, normalize_text

JUDGE_SYSTEM = (
    "You are the Teanga Bench tutor judge. You grade only the explanation. "
    "The error span and the corrected sentence have already been checked by a rule. "
    "Reply with one JSON object and nothing else."
)

_CHRF = CHRF(word_order=2)  # chrF++


@dataclass
class ClosedScore:
    correct: int
    answer: str
    expected: list[str]
    detail: str


@dataclass
class TutorRules:
    parsed: bool
    found: int
    fixed: int
    no_overcorrection: int
    error_span: str = ""
    correction: str = ""
    corrected_sentence: str = ""
    explanation: str = ""
    detail: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


def score_closed_answer(completion: str, metadata: dict[str, Any]) -> ClosedScore:
    """Exact match of the normalized answer against the gold accept list."""
    answer = normalize_answer(completion)
    expected = [normalize_text(item) for item in metadata.get("accept") or []]
    if not expected and metadata.get("target"):
        expected = [normalize_text(str(metadata["target"]))]
    correct = int(answer in expected and answer != "")
    if correct:
        detail = "exact match against gold"
    elif not answer:
        detail = "no answer extracted"
    else:
        detail = "normalized answer is not in the gold accept list"
    return ClosedScore(correct=correct, answer=answer, expected=expected, detail=detail)


def extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    blob = fenced.group(1) if fenced else None
    if blob is None:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            blob = text[start : end + 1]
    if blob is None:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def score_tutor_rules(completion: str, metadata: dict[str, Any]) -> TutorRules:
    """Rule-score span, correction, and over-correction. Explanation is separate.

    Clean items (``has_error`` false) are correct only when the model reports
    no error and leaves the sentence unchanged.
    """
    parsed = extract_json_object(completion)
    if parsed is None:
        return TutorRules(
            parsed=False,
            found=0,
            fixed=0,
            no_overcorrection=0,
            detail="response was not a JSON object",
        )
    error_span = _as_text(parsed.get("error_span"))
    correction = _as_text(parsed.get("correction"))
    corrected = _as_text(parsed.get("corrected_sentence"))
    explanation = _as_text(parsed.get("explanation"))
    spans = [normalize_text(item) for item in metadata.get("accept_spans") or []]
    corrections = [normalize_text(item) for item in metadata.get("accept_corrections") or []]
    sentences = [normalize_text(item) for item in metadata.get("acceptable_sentences") or []]
    has_error = metadata.get("has_error", True)
    if not has_error:
        sentence_same = normalize_text(corrected) in sentences and normalize_text(corrected) != ""
        says_clean = parsed.get("has_error") is False or (
            parsed.get("has_error") is None and not error_span.strip() and not correction.strip()
        )
        found = int(says_clean and sentence_same)
        fixed = int(sentence_same)
        no_over = int(sentence_same)
    else:
        found = int(normalize_text(error_span) in spans and normalize_text(error_span) != "")
        if parsed.get("has_error") is False:
            found = 0
        # An empty correction is valid when the recorded edit deletes the span.
        fixed = int(normalize_text(correction) in corrections)
        no_over = int(normalize_text(corrected) in sentences and normalize_text(corrected) != "")
    return TutorRules(
        parsed=True,
        found=found,
        fixed=fixed,
        no_overcorrection=no_over,
        error_span=error_span,
        correction=correction,
        corrected_sentence=corrected,
        explanation=explanation,
        detail="rule checks against the gold rubric",
        raw=parsed,
    )


def tutor_headline(rules: TutorRules) -> int:
    """Rule-only headline: the error was found, fixed, and not over-corrected.

    A clean item scores 1 when the model reports no error and leaves the
    sentence unchanged. The explanation is scored separately and never enters
    this number.
    """
    return int(rules.found == 1 and rules.fixed == 1 and rules.no_overcorrection == 1)


def judge_prompt(metadata: dict[str, Any], rules: TutorRules) -> str:
    points = metadata.get("explanation_points") or []
    bullet = "\n".join(f"- {point}" for point in points) or (
        "- (none listed: judge whether the explanation is correct for the gold error)"
    )
    if metadata.get("has_error", True):
        gold = (
            f"Gold error span: {metadata.get('error_span', '')}\n"
            f"Gold correction: {metadata.get('correction', '')}\n"
        )
    else:
        gold = "The learner sentence is correct as written; the right reply is that it has no error.\n"
    return (
        "Grade whether the explanation covers the rubric and does not invent a second error.\n"
        f"Learner sentence: {metadata.get('learner_sentence', '')}\n"
        f"{gold}"
        f"Gold sentence: {(metadata.get('acceptable_sentences') or [''])[0]}\n"
        "Rubric points the explanation must cover:\n"
        f"{bullet}\n"
        f"Model error span: {rules.error_span}\n"
        f"Model correction: {rules.correction}\n"
        f"Model corrected sentence: {rules.corrected_sentence}\n"
        f"Model explanation: {rules.explanation}\n"
        'Reply with JSON: {"explanation_ok": true or false, '
        '"invented_extra_error": true or false, "reason": "one sentence"}'
    )


def parse_judge_verdict(text: str) -> tuple[int, str] | None:
    """Return (1 or 0, reason), or None when the reply is not a usable verdict.

    The verdict is 1 only when the explanation is adequate and the judge found
    no invented second error. None is treated as a judge error by the caller.
    """
    data = extract_json_object(text)
    if data is None or not isinstance(data.get("explanation_ok"), bool):
        return None
    reason = _as_text(data.get("reason")) or "no reason given"
    extra = data.get("invented_extra_error")
    if data["explanation_ok"] is True and extra is not True:
        return 1, reason
    return 0, reason


def chrf_score(hypothesis: str, references: list[str]) -> float:
    """chrF++ in 0..1 against the best-matching reference."""
    refs = [ref for ref in references if ref and ref.strip()]
    if not refs or not (hypothesis or "").strip():
        return 0.0
    return float(_CHRF.sentence_score(hypothesis.strip(), refs).score) / 100.0


_LABEL = re.compile(r"^\s*(?:answer|translation)\s*:\s*", re.IGNORECASE)


def extract_translation(completion: str) -> str:
    """The translation text: drop a leading ``ANSWER:`` or ``Translation:`` label."""
    text = (completion or "").strip()
    text = _LABEL.sub("", text, count=1)
    return text.strip().strip("\"`*_").strip()


def round_trip_prompt(source_lang: str, target_lang: str, text: str) -> str:
    return (
        f"Translate the following {source_lang} text into {target_lang}.\n"
        "Reply with the translation only, with no notes and no explanation.\n\n"
        f"{text}"
    )
