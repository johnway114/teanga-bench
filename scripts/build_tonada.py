#!/usr/bin/env python3
"""Build the Tonada tests ``exercises`` (accept_list) and ``tutor_accuracy`` (tutor).

Sources (read-only, all local, no network, no paid calls):

- ``~/Documents/blas-english/data/content/english/grammar-lessons.json`` and
  ``lesson-screens.json`` with their machine-review sidecars ``*.review.json``
  (licence ``private-tonada``).
- ``~/Documents/blas/blas-gec-artifacts/sealed-candidates/english/`` (WikiEdits-MultiGEC
  revision pairs, licence per its ``manifest.json``).
- ``~/Documents/blas-english/data/sources/tatoeba/eng_sentences_detailed.tsv.bz2``
  (CC BY 2.0 FR) is used as lookup only: it counts short word windows so that a wrong
  choice which forms an attested English sentence is rejected. No corpus text is copied
  into any output.

Run: ``python3 scripts/build_tonada.py``. The output is byte-identical between runs.
"""

from __future__ import annotations

import bz2
import difflib
import json
import random
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from _common import (
    BLAS_ENGLISH,
    GEC_ARTIFACTS,
    SEED,
    home_relative,
    load_json,
    make_item,
    norm,
    stratified_sample,
    unique,
    write_outputs,
)

SUITE = "tonada"
CONTENT = BLAS_ENGLISH / "data" / "content" / "english"
GRAMMAR = CONTENT / "grammar-lessons.json"
GRAMMAR_REVIEW = CONTENT / "grammar-lessons.review.json"
SCREENS = CONTENT / "lesson-screens.json"
SCREENS_REVIEW = CONTENT / "lesson-screens.review.json"
WIKI_DIR = GEC_ARTIFACTS / "sealed-candidates" / "english"
WIKI_ERROR = WIKI_DIR / "english-error.jsonl"
WIKI_CLEAN = WIKI_DIR / "english-clean.jsonl"
WIKI_MANIFEST = WIKI_DIR / "manifest.json"
TATOEBA = BLAS_ENGLISH / "data" / "sources" / "tatoeba" / "eng_sentences_detailed.tsv.bz2"

APP_LICENCE = "private-tonada"
L1_LOCALE = {
    "portuguese": "pt-BR",
    "spanish": "es-419",
    "vietnamese": "vi",
    "japanese": "ja",
}
L1_NAME = {"portuguese": "Portuguese", "spanish": "Spanish", "vietnamese": "Vietnamese", "japanese": "Japanese"}
L1S = list(L1_LOCALE)  # fixed order

EXERCISE_PER_L1 = 100
EXERCISE_DRILLS_PER_L1 = 60  # remainder from choose screens; shortfalls are refilled from the other kind
TUTOR_PER_L1 = 90
TUTOR_CLEAN_PER_L1 = 30
TUTOR_WIKI_ERROR_MAX = 20
TUTOR_WIKI_CLEAN_PER_L1 = 10  # at most; about half the wiki error count so the Wikipedia domain is not a cue
TUTOR_DISTRACTOR_MIN = 40
WIKI_LICENCE = (
    "CC BY-SA 4.0 (Wikipedia text); MIT (WikiEdits-MultiGEC dataset, "
    "https://huggingface.co/datasets/lang-uk/WikiEdits-MultiGEC)"
)
TATOEBA_REJECT_COUNT = 1  # wrong-choice window seen this often in Tatoeba => may be valid English

# --------------------------------------------------------------------------------------
# Generic helpers
# --------------------------------------------------------------------------------------

def rng_for(tag: str) -> random.Random:
    return random.Random(f"{SEED}:{tag}")


def snake(text: str, limit: int = 64) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return text[:limit].rstrip("_") or "untitled"


def clean_markup(text: str) -> str:
    """Learner-locale text marks English words as ``{word}``; show them as quoted words."""
    return re.sub(r"\{([^{}]*)\}", lambda m: "\u201c" + m.group(1) + "\u201d", text).strip()


def n_words(text: str) -> int:
    return len(text.split())




def count_word_occurrences(sentence: str, blank: str) -> list[tuple[int, int]]:
    pattern = r"(?<![\w'\u2019])" + re.escape(blank) + r"(?![\w\u2019]|'\w)"
    return [(m.start(), m.end()) for m in re.finditer(pattern, sentence)]


# Lessons whose subject is letters, spelling or pronunciation: not exercises for this test.
PRONUNCIATION_RE = re.compile(
    r"letter names|spelling|alphabet|vowel|consonant|pronunc|phonic|\bsounds?\b|stress|intonation|"
    r"rhythm|syllable|rhyme|minimal pair|katakana|schwa|weak forms?|silent|cognates:",
    re.I,
)
AUDIO_PROMPT_RE = re.compile(
    r"ou[cç]a|ouve\b|escuch|nghe|聞|音声|listen|hear|audio|áudio|\bbản ghi|recording|record",
    re.I,
)
NON_ENGLISH_RE = re.compile(r"[^\x00-\x7f\u2018\u2019\u201c\u201d\u2013\u2014\u2026\u00a3\u20ac\u00b0\u00d7]")
IPA_RE = re.compile(r"/[^/\s]{1,6}/")

# --------------------------------------------------------------------------------------
# Source loading
# --------------------------------------------------------------------------------------

class Source:
    def __init__(self) -> None:
        grammar = load_json(GRAMMAR)
        self.lessons: dict[str, dict[str, Any]] = {lesson["id"]: lesson for lesson in grammar["lessons"]}
        self.grammar_review: dict[str, Any] = load_json(GRAMMAR_REVIEW)["strings"]
        screens = load_json(SCREENS)
        self.screen_lessons: dict[str, dict[str, Any]] = screens["lessons"]
        self.screen_review: dict[str, Any] = load_json(SCREENS_REVIEW)["strings"]

    def lesson_label(self, lesson_id: str) -> tuple[str, str | None]:
        lesson = self.lessons.get(lesson_id) or {}
        title = lesson.get("titleEnglish") or lesson.get("title") or lesson_id
        return title, lesson.get("cefrLevel")

    def is_pronunciation_lesson(self, lesson_id: str) -> bool:
        lesson = self.lessons.get(lesson_id) or {}
        title = lesson.get("titleEnglish") or ""
        return lesson_id.startswith("en-fnd-") or bool(PRONUNCIATION_RE.search(title))

    def drill_state(self, lesson_id: str, drill_id: str, locale: str) -> str | None:
        record = self.grammar_review.get(f"{lesson_id}/{drill_id}", {}).get(locale)
        return record["state"] if record else None

    def screen_state(self, screen_id: str, locale: str) -> str | None:
        record = self.screen_review.get(screen_id, {}).get(locale)
        return record["state"] if record else None

    def drills(self):
        for lesson_id in sorted(self.lessons):
            lesson = self.lessons[lesson_id]
            for section in lesson["sections"]:
                for drill in section.get("drills", []):
                    yield lesson, drill

    def screens(self, kind: str):
        for lesson_id in sorted(self.screen_lessons):
            lesson = self.screen_lessons[lesson_id]
            for screen in lesson["screens"]:
                if screen.get("kind") == kind:
                    yield lesson_id, lesson, screen


def assign_l1(candidates: dict[str, list[str]], tag: str) -> dict[str, str]:
    """Give each source id one l1 among the ones it is eligible for (least loaded first)."""
    rng = rng_for(f"assign:{tag}")
    load: Counter[str] = Counter()
    out: dict[str, str] = {}
    # most constrained first, then a seeded shuffle for the rest
    keys = sorted(candidates)
    rng.shuffle(keys)
    keys.sort(key=lambda key: len(candidates[key]))
    for key in keys:
        options = sorted(candidates[key], key=lambda l1: (load[l1], rng.random()))
        out[key] = options[0]
        load[options[0]] += 1
    return out


# --------------------------------------------------------------------------------------
# tonada/exercises
# --------------------------------------------------------------------------------------

def drill_skip_reason(src: Source, lesson: dict[str, Any], drill: dict[str, Any]) -> str | None:
    """Why an exact-answer option drill is not an English exercise for this test (None when usable)."""
    if drill.get("listenFirst") or drill.get("nativeAudioText") or drill.get("audioSource") or drill.get("assetDependencies"):
        return "audio"
    if drill.get("responseLocale") not in (None, "en"):
        return "response_not_english"
    if src.is_pronunciation_lesson(lesson["id"]) or PRONUNCIATION_RE.search(drill.get("objectiveId") or ""):
        return "letters_spelling_pronunciation"
    if drill.get("source") and (drill["source"].get("kind") != "passage" or drill["source"].get("assetRequired")):
        return "source_needs_asset"
    answer, options = drill["expectedAnswer"], drill["options"]
    if answer not in options:
        return "answer_not_in_options"
    if len(set(options)) != len(options):
        return "duplicate_options"
    if any(NON_ENGLISH_RE.search(text) or IPA_RE.search(text) for text in options + [answer]):
        return "non_english_or_ipa_option"
    return None


def drill_candidates(src: Source) -> tuple[list[dict[str, Any]], Counter]:
    """Eligible exact-answer option drills, one record per (drill, locale)."""
    skipped: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    for lesson, drill in src.drills():
        if drill.get("answerPolicy") != "exact" or not drill.get("options"):
            continue
        title, cefr = src.lesson_label(lesson["id"])
        reason = drill_skip_reason(src, lesson, drill)
        if reason:
            skipped[reason] += 1
            continue
        for l1 in L1S:
            locale = L1_LOCALE[l1]
            prompt = (drill.get("prompts") or {}).get(locale)
            if not prompt:
                skipped["no_locale_prompt"] += 1
                continue
            if AUDIO_PROMPT_RE.search(prompt) or IPA_RE.search(prompt):
                skipped["audio_or_ipa_prompt"] += 1
                continue
            state = src.drill_state(lesson["id"], drill["id"], locale)
            if state != "verified":
                skipped[f"review_state_{state}"] += 1
                continue
            records.append(
                {
                    "kind": "drill",
                    "key": drill["id"],
                    "l1": l1,
                    "locale": locale,
                    "lesson": lesson,
                    "drill": drill,
                    "prompt": clean_markup(prompt),
                    "state": state,
                    "title": title,
                    "cefr": cefr,
                }
            )
    return records, skipped


def screen_exercise_candidates(src: Source) -> tuple[list[dict[str, Any]], Counter]:
    skipped: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    for lesson_id, lesson, screen in src.screens("choose"):
        title, cefr = src.lesson_label(lesson_id)
        if src.is_pronunciation_lesson(lesson_id):
            skipped["letters_spelling_pronunciation"] += 1
            continue
        blank, answer, choices = screen["blank"], screen["answer"], screen["choices"]
        spans = count_word_occurrences(answer, blank)
        if len(spans) != 1:
            skipped["blank_not_unique_in_answer"] += 1
            continue
        if blank not in choices or len(set(choices)) != len(choices):
            skipped["choices_inconsistent"] += 1
            continue
        if NON_ENGLISH_RE.search(answer) or any(NON_ENGLISH_RE.search(choice) for choice in choices):
            skipped["non_english"] += 1
            continue
        lead = screen.get("lead") or screen.get("prompt") or {}
        for l1 in L1S:
            locale = L1_LOCALE[l1]
            text = lead.get(locale)
            if not text:
                skipped["no_locale_prompt"] += 1
                continue
            if AUDIO_PROMPT_RE.search(text):
                skipped["audio_prompt"] += 1
                continue
            state = src.screen_state(screen["id"], locale)
            if state != "verified":
                skipped[f"review_state_{state}"] += 1
                continue
            records.append(
                {
                    "kind": "screen",
                    "key": screen["id"],
                    "l1": l1,
                    "locale": locale,
                    "lesson": lesson_id,
                    "screen": screen,
                    "span": spans[0],
                    "prompt": clean_markup(text),
                    "state": state,
                    "title": title,
                    "cefr": cefr,
                    "lesson_status": lesson["status"],
                }
            )
    return records, skipped


def exercise_prompt(l1: str, instruction: str, body: str) -> str:
    return (
        f"This is an exercise from an English course for {L1_NAME[l1]} speakers. "
        f"The learner sees the instruction in {L1_NAME[l1]}; the answer is in English.\n\n"
        f"Instruction ({L1_NAME[l1]}): {instruction}\n\n{body}"
    )


def build_drill_item(rec: dict[str, Any], source_path: Path) -> dict[str, Any]:
    drill, lesson = rec["drill"], rec["lesson"]
    options = list(drill["options"])
    rng_for(f"options:{drill['id']}@{rec['locale']}").shuffle(options)
    answer = drill["expectedAnswer"]
    assert answer in options, drill["id"]
    parts = []
    source = drill.get("source")
    if source:
        parts.append(f"Text: {source['text']}")
    parts.append("Options:\n" + "\n".join(f"- {option}" for option in options))
    parts.append("Reply with exactly one of the options, copied as written.")
    accept = unique([answer] + (drill.get("acceptedAnswers") or []))
    return make_item(
        id=f"{drill['id']}@{rec['locale']}",
        prompt=exercise_prompt(rec["l1"], rec["prompt"], "\n\n".join(parts)),
        target=answer,
        suite=SUITE,
        test="exercises",
        scoring="accept_list",
        language="english",
        l1=rec["l1"],
        phenomenon=snake(rec["title"]),
        cefr=rec["cefr"],
        source="tonada-grammar-lessons",
        source_id=f"{lesson['id']}/{drill['id']}",
        source_path=source_path,
        licence=APP_LICENCE,
        evidence="tonada-app-machine-reviewed",
        human_checked=False,
        accept=accept,
        locale=rec["locale"],
        source_status=rec["state"],
        exercise_type="drill_options",
        objective_id=drill.get("objectiveId"),
        options=options,
    )


def build_screen_item(rec: dict[str, Any], source_path: Path) -> dict[str, Any]:
    screen = rec["screen"]
    start, end = rec["span"]
    sentence = screen["answer"][:start] + "____" + screen["answer"][end:]
    choices = list(screen["choices"])
    rng_for(f"choices:{screen['id']}@{rec['locale']}").shuffle(choices)
    assert screen["blank"] in choices, screen["id"]
    body = (
        f"Sentence: {sentence}\nChoices: " + " / ".join(choices)
        + "\n\nGive the choice that fills the blank (____), or write out the whole completed sentence."
    )
    return make_item(
        id=f"{screen['id']}@{rec['locale']}",
        prompt=exercise_prompt(rec["l1"], rec["prompt"], body),
        target=screen["blank"],
        suite=SUITE,
        test="exercises",
        scoring="accept_list",
        language="english",
        l1=rec["l1"],
        phenomenon=snake(rec["title"]),
        cefr=rec["cefr"],
        source="tonada-lesson-screens",
        source_id=screen["id"],
        source_path=source_path,
        licence=APP_LICENCE,
        evidence="tonada-app-machine-reviewed",
        human_checked=False,
        accept=[screen["blank"], screen["answer"]],
        locale=rec["locale"],
        source_status=rec["state"],
        lesson_status=rec["lesson_status"],
        exercise_type="choose_blank",
        options=choices,
    )


def pick_per_l1(records: list[dict[str, Any]], tag: str) -> dict[str, list[dict[str, Any]]]:
    """Partition records over l1 so that each source id serves one l1 only."""
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        by_key[rec["key"]].append(rec)
    assignment = assign_l1({key: [rec["l1"] for rec in recs] for key, recs in by_key.items()}, tag)
    pools: dict[str, list[dict[str, Any]]] = {l1: [] for l1 in L1S}
    for key, l1 in assignment.items():
        pools[l1].extend(rec for rec in by_key[key] if rec["l1"] == l1)
    return pools


def build_exercises(src: Source) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    drill_recs, drill_skipped = drill_candidates(src)
    screen_recs, screen_skipped = screen_exercise_candidates(src)
    drill_pools = pick_per_l1(drill_recs, "exercise-drills")
    screen_pools = pick_per_l1(screen_recs, "exercise-screens")
    items: list[dict[str, Any]] = []
    shortfalls: dict[str, Any] = {}
    for l1 in L1S:
        drill_items = [build_drill_item(rec, GRAMMAR) for rec in drill_pools[l1]]
        screen_items = [build_screen_item(rec, SCREENS) for rec in screen_pools[l1]]
        quota_screens = EXERCISE_PER_L1 - EXERCISE_DRILLS_PER_L1
        chosen_drills = stratified_sample(drill_items, EXERCISE_DRILLS_PER_L1, keys=("l1", "phenomenon"))
        chosen_screens = stratified_sample(screen_items, quota_screens, keys=("l1", "phenomenon"))
        # Refill from the other kind if one ran short.
        if len(chosen_screens) < quota_screens:
            chosen_drills = stratified_sample(drill_items, EXERCISE_PER_L1 - len(chosen_screens), keys=("l1", "phenomenon"))
        elif len(chosen_drills) < EXERCISE_DRILLS_PER_L1:
            chosen_screens = stratified_sample(screen_items, EXERCISE_PER_L1 - len(chosen_drills), keys=("l1", "phenomenon"))
        picked = chosen_drills + chosen_screens
        if len(picked) < EXERCISE_PER_L1:
            shortfalls[l1] = {"target": EXERCISE_PER_L1, "got": len(picked)}
        items.extend(picked)
    # Check programmatically that the options include the answer.
    for item in items:
        meta = item["metadata"]
        if meta["exercise_type"] == "drill_options":
            assert item["target"] in meta["options"], item["id"]
        else:
            assert meta["accept"][0] in meta["options"], item["id"]
    report = {
        "shortfalls": shortfalls,
        "candidates_by_l1": {l1: len(drill_pools[l1]) + len(screen_pools[l1]) for l1 in L1S},
        "candidate_drills_by_l1": {l1: len(drill_pools[l1]) for l1 in L1S},
        "candidate_screens_by_l1": {l1: len(screen_pools[l1]) for l1 in L1S},
        "skipped_drills": dict(sorted(drill_skipped.items())),
        "skipped_screens": dict(sorted(screen_skipped.items())),
        "unique_source_ids": len({item["metadata"]["source_id"] for item in items}),
        "sources": [home_relative(GRAMMAR), home_relative(SCREENS), home_relative(GRAMMAR_REVIEW), home_relative(SCREENS_REVIEW)],
        "licence_note": "Tonada content is private-tonada. Review states come from the machine-review sidecars; nothing is human checked.",
    }
    return items, report


# --------------------------------------------------------------------------------------
# tonada/tutor_accuracy: edit machinery
# --------------------------------------------------------------------------------------

def is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch in "_'\u2019-"


WORD = r"[\w'\u2019-]+"


def edit_fields(learner: str, corrected: str) -> dict[str, Any] | None:
    """Derive one contiguous error span from a single-edit pair.

    The span is made of whole words. A pure insertion is anchored on the next word (the
    previous word is an alternative); a pure deletion is anchored on the previous word (the
    next word is an alternative), so the correction is never empty. The span is widened by
    neighbouring words until it occurs exactly once in ``learner``.
    """
    if learner == corrected:
        return None
    limit = min(len(learner), len(corrected))
    p = 0
    while p < limit and learner[p] == corrected[p]:
        p += 1
    s = 0
    while s < limit - p and learner[-1 - s] == corrected[-1 - s]:
        s += 1
    x = learner[p : len(learner) - s]
    y = corrected[p : len(corrected) - s]
    lo, hi = p, len(learner) - s
    edge_first, edge_last = (x or y)[:1], (x or y)[-1:]

    # Widen to whole words when the edit touches a word.
    if lo > 0 and is_word_char(learner[lo - 1]) and edge_first and is_word_char(edge_first):
        while lo > 0 and is_word_char(learner[lo - 1]):
            lo -= 1
    if hi < len(learner) and is_word_char(learner[hi]) and edge_last and is_word_char(edge_last):
        while hi < len(learner) and is_word_char(learner[hi]):
            hi += 1

    def pair(a: int, b: int) -> tuple[str, str]:
        return learner[a:b], corrected[a : len(corrected) - (len(learner) - b)]

    anchors: list[tuple[int, int]] = []
    if lo == hi:
        # Pure insertion between words.
        right = re.match(r"\s*(" + WORD + ")", learner[hi:])
        left = re.search("(" + WORD + r")\s*$", learner[:lo])
        if right:
            anchors.append((hi + right.start(1), hi + right.end(1)))
        if left:
            anchors.append((left.start(1), left.end(1)))
    else:
        while lo < hi and learner[lo].isspace():
            lo += 1
        while hi > lo and learner[hi - 1].isspace():
            hi -= 1
        if not pair(lo, hi)[1].strip():
            # Pure deletion: anchor on a neighbouring word.
            left = re.search("(" + WORD + r")\W*$", learner[:lo])
            right = re.match(r"\W*(" + WORD + ")", learner[hi:])
            if left:
                anchors.append((left.start(1), hi))
            if right:
                anchors.append((lo, hi + right.end(1)))
        else:
            anchors.append((lo, hi))
    if not anchors:
        return None

    def widen(a: int, b: int) -> tuple[int, int] | None:
        span = learner[a:b]
        grow = 0
        while learner.count(span) != 1 and grow < 4:
            right = re.match(r"\W*" + WORD, learner[b:])
            left = re.search(WORD + r"\W*$", learner[:a])
            if grow % 2 == 0 and right:
                b += right.end()
            elif left:
                a = left.start()
            elif right:
                b += right.end()
            else:
                return None
            span = learner[a:b]
            grow += 1
        if learner.count(span) != 1:
            return None
        return a, b

    spans: list[str] = []
    corrections: list[str] = []
    primary: tuple[int, int] | None = None
    for a, b in anchors:
        region = widen(a, b)
        if region is None:
            continue
        span, correction = pair(*region)
        if not span.strip() or not correction.strip() or n_words(span) > 6:
            continue
        if learner[: region[0]] + correction + learner[region[1] :] != corrected:
            continue
        if primary is None:
            primary = region
        spans.append(span)
        corrections.append(correction)
    if primary is None:
        return None
    # Character-level minimal edit inside one word (an affix change on a stable stem of 3+ letters).
    word_start = p
    while word_start > 0 and is_word_char(learner[word_start - 1]):
        word_start -= 1
    if x and y and not re.search(r"\s", x + y) and p - word_start >= 3:
        spans.append(x)
        corrections.append(y)
    if x.strip() and not y.strip():
        a = p + len(x) - len(x.lstrip())
        b = a + len(x.strip())
        if (a == 0 or not is_word_char(learner[a - 1])) and (b >= len(learner) or not is_word_char(learner[b])):
            spans.append(x.strip())
    span, correction = pair(*primary)
    return {
        "error_span": span,
        "correction": correction,
        "accept_spans": unique(spans),
        "accept_corrections": unique(corrections),
        "start": primary[0],
        "end": primary[1],
    }


def assert_single_edit(item: dict[str, Any]) -> None:
    meta = item["metadata"]
    if not meta["has_error"]:
        assert meta["acceptable_sentences"] == [meta["learner_sentence"]]
        assert meta["error_span"] == "" and meta["correction"] == ""
        return
    learner = meta["learner_sentence"]
    span, correction = meta["error_span"], meta["correction"]
    assert learner.count(span) == 1, (item["id"], "span not unique")
    assert learner.replace(span, correction, 1) == meta["acceptable_sentences"][0], (item["id"], "replacement mismatch")
    assert span in meta["accept_spans"] and correction in meta["accept_corrections"], item["id"]
    assert 4 <= n_words(learner) <= 30, item["id"]


def tutor_prompt(l1: str, sentence: str) -> str:
    name = L1_NAME[l1]
    return (
        f"A learner of English whose first language is {name} wrote the English sentence below. "
        "The sentence may contain one error, or it may be correct.\n\n"
        f"Sentence: {sentence}\n\n"
        "Decide whether the sentence has an error. If it does, give the exact words that are wrong (error_span), "
        "the words that should replace them (correction) and the whole corrected sentence (corrected_sentence). "
        "If the sentence is correct, set has_error to false, leave error_span and correction empty, and copy the "
        "sentence into corrected_sentence. "
        f"Write the explanation in {name}, in one or two short sentences saying what is wrong and why, or why the "
        "sentence is correct. Every other field stays in English.\n\n"
        "Reply with one JSON object and nothing else, in this form:\n"
        '{"has_error": true|false, "error_span": "...", "correction": "...", "corrected_sentence": "...", "explanation": "..."}\n'
    )


def tutor_item(
    *,
    id: str,
    l1: str,
    learner: str,
    corrected: str,
    has_error: bool,
    phenomenon: str,
    cefr: str | None,
    source: str,
    source_id: str,
    source_path: Path,
    licence: str,
    evidence: str,
    error_origin: str | None,
    explanation_points: list[str],
    **extra: Any,
) -> dict[str, Any] | None:
    if has_error:
        fields = edit_fields(learner, corrected)
        if fields is None:
            return None
        edit = {
            "error_span": fields["error_span"],
            "correction": fields["correction"],
            "accept_spans": fields["accept_spans"],
            "accept_corrections": fields["accept_corrections"],
        }
    else:
        edit = {"error_span": "", "correction": "", "accept_spans": [], "accept_corrections": []}
    item = make_item(
        id=id,
        prompt=tutor_prompt(l1, learner),
        target=corrected,
        suite=SUITE,
        test="tutor_accuracy",
        scoring="tutor",
        language="english",
        l1=l1,
        phenomenon=phenomenon,
        cefr=cefr,
        source=source,
        source_id=source_id,
        source_path=source_path,
        licence=licence,
        evidence=evidence,
        human_checked=False,
        learner_sentence=learner,
        has_error=has_error,
        acceptable_sentences=[corrected],
        explanation_points=explanation_points,
        real_learner_error=False,
        error_origin=error_origin,
        locale=L1_LOCALE[l1],
        **edit,
        **extra,
    )
    assert_single_edit(item)
    return item


# --------------------------------------------------------------------------------------
# Grammatical-contrast filter for choose-screen distractors
# --------------------------------------------------------------------------------------

TOKEN_RE = re.compile(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)*|\d+")


def tokens(text: str) -> list[str]:
    return [tok.lower().replace("\u2019", "'") for tok in TOKEN_RE.findall(text)]


ART = {"a", "an", "the"}
PREP = {
    "at", "on", "in", "to", "for", "of", "with", "from", "by", "about", "into", "over", "under", "since",
    "during", "until", "before", "after", "between", "through", "across", "around", "behind", "near", "off",
    "up", "down", "out", "against", "among", "without", "within", "toward", "towards", "past", "beside",
    "opposite", "along", "onto", "upon",
}
PRES_BE = {"am", "is", "are"}
PAST_BE = {"was", "were"}
NONFIN_BE = {"be", "been", "being"}
BE = PRES_BE | PAST_BE | NONFIN_BE
DO_P = {"do", "does"}
HAVE_P = {"have", "has"}
AUX_LEFT = BE | DO_P | HAVE_P | {
    "did", "had", "having", "to", "will", "would", "can", "could", "shall", "should", "may", "might", "must",
    "not", "n't", "got", "don't", "doesn't", "didn't",
}
FUNC_FOR_STEM = ART | BE | DO_P | HAVE_P | {"did", "had", "having", "to", "not", "n't", "will", "would", "can", "could", "shall", "should", "may", "might", "must"}
DET_PAIRS = {
    frozenset(pair)
    for pair in [
        ("much", "many"), ("much", "few"), ("many", "little"), ("few", "little"), ("less", "fewer"), ("less", "many"),
        ("much", "fewer"), ("enough", "many"), ("another", "other"), ("another", "others"), ("this", "these"),
        ("that", "those"), ("this", "those"), ("that", "these"), ("a few", "a little"), ("many", "few"),
        ("much", "little"),
    ]
}
SUBJ = {"i", "you", "he", "she", "it", "we", "they"}
OBJ = {"me", "him", "her", "us", "them"}
POSS_DET = {"my", "your", "his", "her", "its", "our", "their"}
POSS_PRON = {"mine", "yours", "hers", "ours", "theirs"}
REFL = {"myself", "yourself", "himself", "herself", "itself", "ourselves", "yourselves", "themselves"}
PRON_CATS = [SUBJ, OBJ, POSS_DET, POSS_PRON, REFL]
RELATIVE = {"who", "which", "whose", "whom", "what"}
IRREGULAR = {
    "go": "went gone goes going", "be": "am is are was were been being", "have": "has had having",
    "do": "does did done doing", "see": "saw seen", "take": "took taken", "make": "made", "give": "gave given",
    "write": "wrote written", "eat": "ate eaten", "come": "came", "know": "knew known", "get": "got gotten",
    "say": "said", "tell": "told", "buy": "bought", "bring": "brought", "think": "thought", "leave": "left",
    "lead": "led", "run": "ran", "begin": "began begun", "break": "broke broken", "drive": "drove driven",
    "speak": "spoke spoken", "choose": "chose chosen", "find": "found", "keep": "kept", "lose": "lost",
    "meet": "met", "pay": "paid", "send": "sent", "sit": "sat", "stand": "stood", "teach": "taught", "win": "won",
    "wear": "wore worn", "fall": "fell fallen", "feel": "felt", "hear": "heard", "hold": "held", "put": "put",
    "read": "read", "sell": "sold", "sleep": "slept", "spend": "spent", "swim": "swam swum", "throw": "threw thrown",
    "understand": "understood", "wake": "woke woken", "build": "built", "catch": "caught", "cut": "cut",
    "draw": "drew drawn", "drink": "drank drunk", "fly": "flew flown", "forget": "forgot forgotten",
    "grow": "grew grown", "hide": "hid hidden", "sing": "sang sung", "steal": "stole stolen", "ring": "rang rung",
    "rise": "rose risen", "show": "showed shown", "lend": "lent", "lay": "laid", "mean": "meant",
    "shoot": "shot", "shut": "shut", "tear": "tore torn", "good": "better best", "bad": "worse worst",
    "man": "men", "woman": "women", "child": "children", "person": "people", "foot": "feet", "tooth": "teeth",
}
IRREGULAR_PAST = set()
LEMMA: dict[str, str] = {}
for _base, _forms in IRREGULAR.items():
    LEMMA.setdefault(_base, _base)
    for _form in _forms.split():
        LEMMA.setdefault(_form, _base)
        if not _form.endswith(("ing", "s")) or _form in {"has", "does", "goes"}:
            IRREGULAR_PAST.add(_form)
IRREGULAR_PAST -= {"has", "does", "goes", "put", "read", "cut", "shut"}
SUBJUNCTIVE_TRIGGERS = {"suggest", "suggested", "recommend", "recommended", "insist", "insisted", "demand", "demanded", "essential", "vital", "imperative", "request", "requested", "propose", "proposed", "provided", "if", "wish"}
SUBJUNCTIVE_STRICT = SUBJUNCTIVE_TRIGGERS - {"if", "wish", "provided"}
PREP_MEANING_PAIRS = {frozenset(pair) for pair in [("by", "to"), ("by", "on"), ("by", "at"), ("by", "for")]}
NUMBER_WORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "twenty", "thirty", "forty", "fifty", "sixty", "hundred"}
NP_START = {"the", "a", "an", "my", "your", "his", "her", "our", "their", "its", "this", "that", "these", "those", "some", "any", "each", "every", "all", "no"}
COLLECTIVE_NOUNS = {
    "company", "team", "board", "staff", "family", "government", "committee", "group", "class", "council", "band",
    "police", "crew", "audience", "club", "school", "panel", "jury", "firm", "department", "public", "majority",
    "couple", "orchestra", "university", "community", "society", "union", "association", "organisation", "organization",
}
MODAL_LEFT = {"will", "would", "can", "could", "should", "must", "may", "might", "shall"}


def stem(word: str) -> str:
    word = word.lower()
    if word in LEMMA:
        return LEMMA[word]
    for suffix, replacement in (("ies", "y"), ("ied", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", ""), ("est", ""), ("er", ""), ("ly", "")):
        if word.endswith(suffix) and len(word) - len(suffix) >= 2:
            base = word[: -len(suffix)] + replacement
            if len(base) > 2 and base[-1] == base[-2] and suffix in ("ing", "ed", "er", "est"):
                base = base[:-1]
            return LEMMA.get(base, base)
    return word


def form_type(word: str) -> str:
    word = word.lower()
    if word in IRREGULAR_PAST or (word.endswith("ed") and len(word) > 3):
        return "ed"
    if word.endswith("ing") and len(word) > 4:
        return "ing"
    if word.endswith("ly") and len(word) > 4:
        return "ly"
    if word.endswith("est") and len(word) > 4:
        return "est"
    if word.endswith("er") and len(word) > 4:
        return "er"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 2:
        return "s"
    return "base"


def vowel_sound(word: str) -> bool:
    word = word.lower()
    if word.startswith(("hour", "honest", "honor", "honour", "heir")):
        return True
    if word.startswith(("uni", "use", "usu", "uti", "eu", "one", "once", "ubi")):
        return False
    return word[:1] in "aeiou"


def _classify_swap(blank: str, wrong: str, answer: str, left: str | None, right: str | None) -> str | None:
    """Return the grammatical phenomenon if swapping ``blank`` for ``wrong`` is necessarily an error.

    Vocabulary swaps, tense swaps and anything that may give another valid sentence return None.
    """
    bt, wt = tokens(blank), tokens(wrong)
    if not bt or not wt or bt == wt:
        return None
    answer_tokens = set(tokens(answer))
    if sorted(bt) == sorted(wt):
        return "word_order"
    both = bt + wt
    if set(both) <= ART:
        if len(wt) == 1 and wt[0] in {"a", "an"} and right:
            if wt[0] == "an" and not vowel_sound(right):
                return "article"
            if wt[0] == "a" and vowel_sound(right):
                return "article"
        return None
    if set(both) <= PREP:
        if len(bt) == len(wt) == 1:
            pair = frozenset((bt[0], wt[0]))
            if pair in PREP_MEANING_PAIRS:
                return None  # both words are fine here, only the meaning differs
            if wt[0] == "in" and right and (right.isdigit() or right in NUMBER_WORDS):
                return None  # "in seven" = in seven minutes
            if pair == frozenset(("to", "for")) and (right is None or right in NP_START or right.isdigit()):
                return None  # "to/for + noun phrase" are both fine
        return "preposition"
    if set(both) <= BE | DO_P | HAVE_P and len(bt) == len(wt) == 1:
        b, w = bt[0], wt[0]
        if (b in PRES_BE and w in PRES_BE) or (b in DO_P and w in DO_P) or (b in HAVE_P and w in HAVE_P):
            return "agreement" if left != "there" else None
        if b in PAST_BE and w in PAST_BE and not (answer_tokens & SUBJUNCTIVE_TRIGGERS):
            return "agreement" if left != "there" else None
        if (b in NONFIN_BE) != (w in NONFIN_BE) and b in BE and w in BE:
            return "verb_form"
        if b in NONFIN_BE and w in NONFIN_BE:
            return "verb_form"
        return None
    if len(bt) == len(wt) == 1 and frozenset((bt[0], wt[0])) in DET_PAIRS:
        return "determiner_quantifier"
    if " ".join(bt) and frozenset((" ".join(bt), " ".join(wt))) in DET_PAIRS:
        return "determiner_quantifier"
    if len(bt) == len(wt) == 1:
        b, w = bt[0], wt[0]
        if b in RELATIVE and w in RELATIVE:
            return "relative_pronoun"
        cat_b = {i for i, cat in enumerate(PRON_CATS) if b in cat}
        cat_w = {i for i, cat in enumerate(PRON_CATS) if w in cat}
        poss_pron_vs_person = (b in POSS_PRON and w in SUBJ | OBJ) or (w in POSS_PRON and b in SUBJ | OBJ)
        if cat_b and cat_w and not (cat_b & cat_w) and not poss_pron_vs_person:
            return "pronoun_form"
        if b in REFL and w in REFL:
            return "pronoun_form"
    # Same word, different form.
    core_b = [stem(tok) for tok in bt if tok not in FUNC_FOR_STEM]
    core_w = [stem(tok) for tok in wt if tok not in FUNC_FOR_STEM]
    if core_b and core_b == core_w and ("to" in bt) != ("to" in wt):
        return None  # to-infinitive vs -ing changes meaning but both can be valid
    if core_b and core_b == core_w and ("having" in bt) != ("having" in wt):
        return None  # perfect participle vs -ing: both are valid sentences
    if core_b and core_b == core_w and len(bt) != len(wt) and left not in AUX_LEFT:
        return None  # periphrastic vs simple tense: both can be valid
    if core_b and core_b == core_w:
        if [t for t in bt if t not in ART] == [t for t in wt if t not in ART]:
            return None  # only an article differs: both may be valid
        last_b = [tok for tok in bt if tok not in FUNC_FOR_STEM][-1]
        last_w = [tok for tok in wt if tok not in FUNC_FOR_STEM][-1]
        type_b, type_w = form_type(last_b), form_type(last_w)
        pair = {type_b, type_w}
        if pair == {"ing", "ed"} and (left in BE or (left or "").endswith(("'s", "'re", "'m"))):
            return None  # participial adjectives (annoying/annoyed): both can be valid
        if "ing" in pair and pair != {"ing"}:
            return "verb_form"
        if "ed" in pair and left in AUX_LEFT:
            return "verb_form"
        if pair == {"base", "s"} and not (answer_tokens & SUBJUNCTIVE_TRIGGERS):
            return "agreement_or_plural"
        if pair <= {"er", "est", "base"} and len(pair) == 2 and "base" not in pair:
            return "comparison"
        if "ly" in pair and pair != {"ly"} and left is not None and form_type(last_w) == "ly":
            return "word_class"  # an adverb where an adjective is needed (flat adverbs are not used)
    return None


def classify_swap(blank: str, wrong: str, answer: str, left: str | None, right: str | None) -> str | None:
    kind = _classify_swap(blank, wrong, answer, left, right)
    answer_tokens = set(tokens(answer))
    if kind in {"agreement", "agreement_or_plural"} and answer_tokens & COLLECTIVE_NOUNS:
        return None  # British English allows plural agreement with collective nouns
    if kind in {"agreement", "agreement_or_plural", "verb_form"} and answer_tokens & SUBJUNCTIVE_STRICT:
        return None  # mandative subjunctive: the base form is also correct
    return kind


def is_full_sentence(text: str) -> bool:
    text = text.strip()
    return bool(re.match(r"[A-Z0-9\"']", text)) and text[-1:] in ".?!" and "(" not in text and ")" not in text


class DistractorCandidate:
    __slots__ = (
        "source", "key", "obj", "lesson_id", "lesson_status", "wrong", "correct", "kind", "learner", "corrected", "window", "count",
    )

    def __init__(self, source, key, obj, lesson_id, lesson_status, wrong, correct, kind, learner, corrected, window):
        self.source, self.key, self.obj = source, key, obj
        self.lesson_id, self.lesson_status = lesson_id, lesson_status
        self.wrong, self.correct, self.kind = wrong, correct, kind
        self.learner, self.corrected, self.window = learner, corrected, window
        self.count = 0


def window_tokens(text: str, start: int, end: int, pad: int = 1) -> tuple[str, ...]:
    """The words in text[start:end] with ``pad`` neighbouring words on each side, lowercased.

    For an empty region (a deletion) the window is the ``pad`` words on either side of the gap.
    """
    spans = [(m.start(), m.end(), m.group(0)) for m in TOKEN_RE.finditer(text)]
    if end > start:
        inside = [i for i, (a, b, _t) in enumerate(spans) if a < end and b > start]
        if not inside:
            return ()
        lo, hi = max(0, inside[0] - pad), min(len(spans), inside[-1] + 1 + pad)
    else:
        after = [i for i, (a, _b, _t) in enumerate(spans) if a >= start]
        index = after[0] if after else len(spans)
        lo, hi = max(0, index - pad), min(len(spans), index + pad)
    return tuple(t.lower().replace("\u2019", "'") for _a, _b, t in spans[lo:hi])


def screen_distractor_candidates(src: Source, skipped: Counter) -> list[DistractorCandidate]:
    out: list[DistractorCandidate] = []
    for lesson_id, lesson, screen in src.screens("choose"):
        if src.is_pronunciation_lesson(lesson_id):
            skipped["screen_pronunciation_lesson"] += 1
            continue
        answer, blank = screen["answer"], screen["blank"]
        if not is_full_sentence(answer):
            skipped["screen_answer_not_a_full_sentence"] += 1
            continue
        spans = count_word_occurrences(answer, blank)
        if len(spans) != 1:
            skipped["screen_blank_not_unique"] += 1
            continue
        start, end = spans[0]
        left_tokens = tokens(answer[:start])
        right_tokens = tokens(answer[end:])
        left = left_tokens[-1] if left_tokens else None
        right = right_tokens[0] if right_tokens else None
        for wrong in screen["choices"]:
            if wrong == blank:
                continue
            kind = classify_swap(blank, wrong, answer, left, right)
            if kind is None:
                skipped["screen_not_a_grammatical_contrast"] += 1
                continue
            learner = answer[:start] + wrong + answer[end:]
            if start == 0 and wrong[:1].isalpha() and answer[:1].isupper() and not wrong[:1].isupper():
                skipped["screen_sentence_start_case"] += 1
                continue
            if not 4 <= n_words(learner) <= 30:
                skipped["screen_length_out_of_range"] += 1
                continue
            window = window_tokens(learner, start, start + len(wrong))
            if len(window) < 2:
                skipped["screen_no_window"] += 1
                continue
            out.append(DistractorCandidate("screen", screen["id"], screen, lesson_id, lesson["status"], wrong, blank, kind, learner, answer, window))
    return out


def drill_distractor_candidates(src: Source, skipped: Counter) -> list[DistractorCandidate]:
    """Wrong full-sentence options of exact-answer drills that differ from the answer by one edit."""
    out: list[DistractorCandidate] = []
    for lesson, drill in src.drills():
        if drill.get("answerPolicy") != "exact" or not drill.get("options"):
            continue
        if drill_skip_reason(src, lesson, drill):
            skipped["drill_excluded_like_exercises"] += 1
            continue
        correct = drill["expectedAnswer"]
        if not 4 <= n_words(correct) <= 30 or correct not in drill["options"] or not is_full_sentence(correct):
            skipped["drill_answer_not_a_sentence"] += 1
            continue
        cspans = [(m.start(), m.end(), m.group(0)) for m in WIKI_TOKEN_RE.finditer(correct)]
        ctoks = [t for _a, _b, t in cspans]
        for wrong in drill["options"]:
            if wrong == correct:
                continue
            wspans = [(m.start(), m.end(), m.group(0)) for m in WIKI_TOKEN_RE.finditer(wrong)]
            wtoks = [t for _a, _b, t in wspans]
            ops = [op for op in difflib.SequenceMatcher(None, ctoks, wtoks, autojunk=False).get_opcodes() if op[0] != "equal"]
            if not ops:
                continue
            i1, i2, j1, j2 = ops[0][1], ops[-1][2], ops[0][3], ops[-1][4]
            old, new = ctoks[i1:i2], wtoks[j1:j2]
            word = r"[^\W\d_]+(?:['\u2019-][^\W\d_]+)*"
            if len(old) > 5 or len(new) > 5 or any(not re.fullmatch(word, t) for t in old + new):
                skipped["drill_edit_not_small_words"] += 1
                continue
            lower_old, lower_new = [t.lower() for t in old], [t.lower() for t in new]
            left_words = [t.lower() for t in ctoks[:i1] if re.fullmatch(word, t)]
            right_words = [t.lower() for t in ctoks[i2:] if re.fullmatch(word, t)]
            left = left_words[-1] if left_words else None
            right = right_words[0] if right_words else None
            pad = 1
            if len(ops) > 1:
                # several opcodes: acceptable only as one reordering of the same words
                if sorted(lower_old) != sorted(lower_new):
                    skipped["drill_multi_edit"] += 1
                    continue
                kind = "word_order"
            elif not new:
                copula_gap = len(lower_old) == 1 and lower_old[0] in {"am", "is", "are"} and left in SUBJ and bool(right) and right.endswith("ing")
                have_gap = lower_old == ["have"] and left in MODAL_LEFT
                if not (copula_gap or have_gap):
                    skipped["drill_omission_not_auxiliary"] += 1
                    continue
                kind = "omitted_auxiliary"
                pad = 2
            elif not old:
                skipped["drill_insertion"] += 1
                continue
            elif len(old) > 3 or len(new) > 3:
                skipped["drill_edit_too_long"] += 1
                continue
            else:
                kind = classify_swap(" ".join(old), " ".join(new), correct, left, right)
                if kind is None:
                    skipped["drill_not_a_grammatical_contrast"] += 1
                    continue
            if old and new and old[0][:1].isupper() != new[0][:1].isupper() and i1 == 0:
                skipped["drill_sentence_start_case"] += 1
                continue
            if not 4 <= n_words(wrong) <= 30:
                skipped["drill_length_out_of_range"] += 1
                continue
            start = wspans[j1][0] if j1 < len(wspans) else len(wrong)
            end = wspans[j2 - 1][1] if j2 > j1 else start
            window = window_tokens(wrong, start, end, pad)
            if len(window) < (3 if pad == 2 else 2):
                skipped["drill_no_window"] += 1
                continue
            out.append(DistractorCandidate("drill", drill["id"], drill, lesson["id"], None, wrong, correct, kind, wrong, correct, window))
    return out


def count_windows(windows: set[tuple[str, ...]]) -> Counter:
    """Count word windows in the Tatoeba English sentences (lookup only)."""
    if not TATOEBA.is_file():
        raise FileNotFoundError(f"{TATOEBA} is needed for the wrong-choice validity check")
    by_first: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    for window in windows:
        by_first[window[0]].append(window)
    counts: Counter = Counter()
    with bz2.open(TATOEBA, "rt", encoding="utf-8") as handle:
        for line in handle:
            parts = line.split("\t", 3)
            if len(parts) < 3:
                continue
            words = tokens(parts[2])
            for index, word in enumerate(words):
                options = by_first.get(word)
                if not options:
                    continue
                for window in options:
                    end = index + len(window)
                    if end <= len(words) and tuple(words[index:end]) == window:
                        counts[window] += 1
    return counts


# --------------------------------------------------------------------------------------
# Wiki revision pairs
# --------------------------------------------------------------------------------------

WIKI_TOKEN_RE = re.compile(r"[^\W\d_]+(?:['\u2019-][^\W\d_]+)*|\d+(?:[.,]\d+)*|[^\w\s]")
WIKI_MARKUP_RE = re.compile(r"\{\{|\[\[|<ref|\||==|[{}\[\]<>]")
SENTENCE_BREAK_RE = re.compile(r"[.!?][\"')\]\u201d]*\s+[A-Z\"\u201c(]")
WIKI_FUNC = ART | {"of", "to", "in", "on", "at", "for", "with", "by", "from"} | BE | DO_P | HAVE_P | {"did", "had", "having"}
MONTHS_DAYS = {
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
    "december", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
}
TYPO_OLD_MAX = 2  # a wiki spelling fix needs the old word (almost) unattested in Tatoeba ...
TYPO_NEW_MIN = 20  # ... and the new word common there


def regional_key(word: str) -> str:
    """Canonical form that merges British/American spellings (centre/center, afterward/afterwards, paediatric/pediatric)."""
    word = word.lower()
    for pattern, replacement in (
        (r"isation", "ization"), (r"ise\b", "ize"), (r"ised\b", "ized"), (r"ising\b", "izing"), (r"yse\b", "yze"),
        (r"our", "or"), (r"re\b", "er"), (r"ence\b", "ense"), (r"ae", "e"), (r"oe", "e"), (r"wards\b", "ward"),
        (r"ogue\b", "og"), (r"(.)\1", r"\1"),
    ):
        word = re.sub(pattern, replacement, word)
    return word


def a_an_violations(sentence: str) -> int:
    words = TOKEN_RE.findall(sentence)
    count = 0
    for current, following in zip(words, words[1:]):
        if current.lower() == "a" and vowel_sound(following) and following.isalpha() and not following.isupper():
            count += 1
        if current.lower() == "an" and not vowel_sound(following) and following.isalpha() and not following.isupper():
            count += 1
    return count


def wiki_edit_category(text: str, correction: str) -> tuple[str, str, tuple[str, str] | None] | None:
    """(phenomenon, rule, typo probe) when the pair is a single small language correction, else None.

    The probe is ``(old, new)`` for a possible typo fix: the build keeps it only when the old
    word is (almost) unattested and the new word is common in Tatoeba.
    """
    a = WIKI_TOKEN_RE.findall(text)
    b = WIKI_TOKEN_RE.findall(correction)
    ops = [op for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op[0] != "equal"]
    if len(ops) != 1:
        return None
    _tag, i1, i2, j1, j2 = ops[0]
    old, new = a[i1:i2], b[j1:j2]
    if len(old) > 3 or len(new) > 3 or not (old or new):
        return None
    # Only alphabetic words may change: no punctuation, digits, symbols, possessives.
    if any(not re.fullmatch(r"[^\W\d_]+(?:['\u2019-][^\W\d_]+)*", tok) or tok.endswith(("'s", "\u2019s")) for tok in old + new):
        return None
    lower_old = [t.lower() for t in old]
    lower_new = [t.lower() for t in new]
    # Names: capitalised words that are not at the start of the sentence.
    if i1 > 0 and old and new and all(t[:1].isupper() for t in old + new):
        return None
    if a_an_violations(correction) > a_an_violations(text):
        return None  # the revision itself breaks the a/an rule
    if lower_old == lower_new:
        if len(old) == 1 and lower_old[0] in MONTHS_DAYS:
            return "capitalisation", "month_or_day_case", None
        return None
    if all(t in WIKI_FUNC for t in lower_old + lower_new):
        word_set = set(lower_old + lower_new)
        after = a[i2].lower() if i2 < len(a) else ""
        if not new and word_set & {"a", "an"}:
            return None  # deleting a/an usually removes a needed article
        if not new and lower_old == ["on"] and after in MONTHS_DAYS:
            return None  # "born on August 6" / "born August 6": a style choice
        if word_set <= ART:
            return "article", "function_words", None
        if word_set <= PREP:
            return "preposition", "function_words", None
        if not old or not new:
            left_word = a[i1 - 1].lower() if i1 > 0 else ""
            if not old and word_set <= BE and left_word in SUBJ:
                return "function_word", "copula_insertion_after_pronoun", None
            return None  # inserting/deleting auxiliaries or mixed function words changes voice or style
        return "function_word", "function_words", None
    if len(old) == 1 and len(new) == 1 and len(old[0]) >= 3 and len(new[0]) >= 3:
        if regional_key(old[0]) == regional_key(new[0]):
            return None  # regional spelling variant, not an error
        if stem(lower_old[0]) == stem(lower_new[0]):
            pair = {form_type(lower_old[0]), form_type(lower_new[0])}
            if pair == {"base", "s"}:
                return "agreement_or_plural", "same_stem", None
            if "ing" in pair and len(pair) == 2:
                return "verb_form", "same_stem", None
            return None  # tense swaps (worked/works) are style edits
        if difflib.SequenceMatcher(None, lower_old[0], lower_new[0]).ratio() >= 0.7:
            return "spelling", "typo_probe", (lower_old[0], lower_new[0])
        return None
    core_old = [stem(t) for t in lower_old if t not in WIKI_FUNC]
    core_new = [stem(t) for t in lower_new if t not in WIKI_FUNC]
    if core_old and core_old == core_new and len(old) == len(new):
        return "verb_form", "same_stem", None
    return None


def wiki_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


ABBREVIATIONS = {
    "dr", "mr", "mrs", "ms", "st", "jr", "sr", "vs", "no", "inc", "ltd", "co", "prof", "mt", "fr", "gen", "col", "sen",
    "rep", "gov", "rev", "capt", "lt", "sgt", "dept", "est", "approx", "cf", "al", "etc", "ft", "sq",
}


def split_sentences(text: str) -> list[str]:
    """Conservative sentence splitter: breaks at . ! ? plus a capital letter, except after abbreviations and initials."""
    pieces: list[str] = []
    start = 0
    for match in re.finditer(r"([.!?][\"')\]\u201d]*)\s+(?=[A-Z\"\u201c(])", text):
        previous = text[start : match.start()].split()
        last = previous[-1] if previous else ""
        if match.group(1).startswith(".") and (re.fullmatch(r"[A-Z]", last) or last.lower().rstrip(".") in ABBREVIATIONS or "." in last):
            continue
        pieces.append(text[start : match.end(1)])
        start = match.end()
    pieces.append(text[start:])
    return pieces


def wiki_sentence_ok(text: str) -> bool:
    if "\n" in text or WIKI_MARKUP_RE.search(text):
        return False
    if not 6 <= n_words(text) <= 30:
        return False
    if not re.search(r"[.!?][\"')\u201d]*$", text) or not re.match(r"[A-Z\"\u201c(]", text):
        return False  # fragment: no capital start or no closing punctuation
    return not SENTENCE_BREAK_RE.search(text)


def edited_sentence_pair(text: str, correction: str) -> tuple[str, str, bool] | None:
    """The one sentence pair that differs, and whether it was cut out of a longer paragraph."""
    before, after = split_sentences(text), split_sentences(correction)
    if len(before) != len(after):
        return None
    changed = [i for i in range(len(before)) if before[i] != after[i]]
    if len(changed) != 1:
        return None
    i = changed[0]
    return before[i].strip(), after[i].strip(), len(before) > 1


def wiki_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def wiki_error_candidates() -> tuple[list[dict[str, Any]], Counter]:
    skipped: Counter[str] = Counter()
    out = []
    for row in wiki_rows(WIKI_ERROR):
        pair = edited_sentence_pair(row["text"].strip(), row["correction"].strip())
        if pair is None:
            skipped["edit_not_confined_to_one_sentence"] += 1
            continue
        text, correction, extracted = pair
        if not (wiki_sentence_ok(text) and wiki_sentence_ok(correction)):
            skipped["not_one_clean_sentence_6_30_words"] += 1
            continue
        if re.search(r"\b(\w+)\s+\1\b", correction, re.I) and not re.search(r"\b(\w+)\s+\1\b", text, re.I):
            skipped["correction_repeats_a_word"] += 1
            continue
        category = wiki_edit_category(text, correction)
        if category is None:
            skipped["not_a_single_small_language_edit"] += 1
            continue
        fields = edit_fields(text, correction)
        if fields is None:
            skipped["no_unique_span"] += 1
            continue
        out.append({"row": row, "text": text, "correction": correction, "category": category, "extracted": extracted})
    return out, skipped


def wiki_clean_candidates() -> list[dict[str, Any]]:
    """One clean sentence per row of english-clean.jsonl (seeded pick among the sentences that pass)."""
    out = []
    rng = rng_for("wiki-clean-sentence")
    for row in wiki_rows(WIKI_CLEAN):
        sentences = split_sentences(row["text"].strip())
        ok = [s.strip() for s in sentences if wiki_sentence_ok(s.strip()) and s.strip()[:1].isupper()]
        if ok:
            out.append({"row": row, "text": rng.choice(ok), "extracted": len(sentences) > 1})
    return out


# --------------------------------------------------------------------------------------
# tonada/tutor_accuracy
# --------------------------------------------------------------------------------------

def fresh_pool(pool: list[dict[str, Any]], used: set[str]) -> list[dict[str, Any]]:
    """Items whose gold sentence is not in ``used``, one per distinct sentence (by id order)."""
    seen = set(used)
    out = []
    for item in sorted(pool, key=lambda entry: entry["id"]):
        key = norm(item["metadata"]["acceptable_sentences"][0])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def explanation_points_for(cand: DistractorCandidate, locale: str) -> list[str]:
    """The English rule when the source has one, else the learner-locale feedback text."""
    if cand.source == "screen":
        text = (cand.obj.get("wrong") or {}).get(locale)
    else:
        text = (cand.obj.get("explanations") or {}).get(locale)
    return [clean_markup(text)] if text else []


def distractor_locale_ok(src: Source, cand: DistractorCandidate, locale: str, skipped: Counter) -> bool:
    if cand.source == "screen":
        state = src.screen_state(cand.key, locale)
        lead = cand.obj.get("lead") or cand.obj.get("prompt") or {}
        has_text = bool(lead.get(locale))
    else:
        state = src.drill_state(cand.lesson_id, cand.key, locale)
        prompts = cand.obj.get("prompts") or {}
        has_text = bool(prompts.get(locale)) and not AUDIO_PROMPT_RE.search(prompts.get(locale) or "")
    if state != "verified":
        skipped[f"{cand.source}_distractor_review_state_{state}"] += 1
        return False
    if not has_text or not explanation_points_for(cand, locale):
        skipped[f"{cand.source}_distractor_no_locale_text"] += 1
        return False
    return True


def build_tutor(src: Source) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    skipped: Counter[str] = Counter()
    candidates = screen_distractor_candidates(src, skipped) + drill_distractor_candidates(src, skipped)
    wiki_errors, wiki_skipped = wiki_error_candidates()
    probe_windows = {(word,) for cand in wiki_errors if cand["category"][2] for word in cand["category"][2]}
    counts = count_windows({cand.window for cand in candidates} | probe_windows)
    typo_checked = []
    for cand in wiki_errors:
        probe = cand["category"][2]
        if probe and not (counts[(probe[0],)] <= TYPO_OLD_MAX and counts[(probe[1],)] >= TYPO_NEW_MIN):
            wiki_skipped["similar_word_not_a_typo_fix"] += 1
            continue
        typo_checked.append(cand)
    wiki_errors = typo_checked
    kept: list[DistractorCandidate] = []
    for cand in candidates:
        cand.count = counts[cand.window]
        if cand.count >= TATOEBA_REJECT_COUNT:
            skipped[f"{cand.source}_wrong_choice_window_attested_in_tatoeba"] += 1
            continue
        kept.append(cand)

    # One wrong choice per source item (seeded), then one l1 per source item.
    by_key: dict[tuple[str, str], list[DistractorCandidate]] = defaultdict(list)
    for cand in kept:
        by_key[(cand.source, cand.key)].append(cand)
    chosen_wrong: dict[tuple[str, str], DistractorCandidate] = {}
    for key in sorted(by_key):
        options = sorted(by_key[key], key=lambda c: c.wrong)
        chosen_wrong[key] = rng_for(f"wrong:{key[0]}:{key[1]}").choice(options)

    distractor_pools: dict[str, dict[str, list[dict[str, Any]]]] = {l1: {"screen": [], "drill": []} for l1 in L1S}
    for source_kind in ("screen", "drill"):
        eligible: dict[str, list[str]] = {}
        for (kind, key), cand in sorted(chosen_wrong.items()):
            if kind != source_kind:
                continue
            locales = [l1 for l1 in L1S if distractor_locale_ok(src, cand, L1_LOCALE[l1], skipped)]
            if locales:
                eligible[key] = locales
        assignment = assign_l1(eligible, f"tutor-distractors-{source_kind}")
        for key in sorted(assignment):
            l1 = assignment[key]
            cand = chosen_wrong[(source_kind, key)]
            locale = L1_LOCALE[l1]
            title, cefr = src.lesson_label(cand.lesson_id)
            is_screen = source_kind == "screen"
            item = tutor_item(
                id=f"{key}@{locale}:err",
                l1=l1,
                learner=cand.learner,
                corrected=cand.corrected,
                has_error=True,
                phenomenon=cand.kind,
                cefr=cefr,
                source="tonada-lesson-screens" if is_screen else "tonada-grammar-lessons",
                source_id=key if is_screen else f"{cand.lesson_id}/{key}",
                source_path=SCREENS if is_screen else GRAMMAR,
                licence=APP_LICENCE,
                evidence="tonada-app-distractor-machine-reviewed",
                error_origin="exercise-distractor",
                explanation_points=explanation_points_for(cand, locale),
                explanation_locale=locale,
                source_status=src.screen_state(key, locale) if is_screen else src.drill_state(cand.lesson_id, key, locale),
                lesson_status=cand.lesson_status,
                lesson_topic=snake(title),
                distractor_source="choose_screen" if is_screen else "drill_option",
                wrong_choice=cand.wrong,
                correct_choice=cand.correct,
                tatoeba_window_count=cand.count,
            )
            if item is not None:
                distractor_pools[l1][source_kind].append(item)
            else:
                skipped[f"{source_kind}_distractor_no_unique_span"] += 1

    # Wiki revision edits: different rows per l1.
    rng_for("wiki-errors").shuffle(wiki_errors)
    wiki_pools: dict[str, list[dict[str, Any]]] = {l1: [] for l1 in L1S}
    for index, cand in enumerate(sorted(wiki_errors, key=lambda c: c["row"]["id"])):
        wiki_pools[L1S[index % len(L1S)]].append(cand)
    manifest = load_json(WIKI_MANIFEST)
    wiki_licence = WIKI_LICENCE

    used_sentences: set[str] = set()
    items: list[dict[str, Any]] = []
    per_l1_counts: dict[str, dict[str, int]] = {}
    for l1 in L1S:
        locale = L1_LOCALE[l1]
        wiki_items: list[dict[str, Any]] = []
        for cand in wiki_pools[l1][:TUTOR_WIKI_ERROR_MAX]:
            row = cand["row"]
            item = tutor_item(
                id=f"{row['id']}@{locale}",
                l1=l1,
                learner=cand["text"],
                corrected=cand["correction"],
                has_error=True,
                phenomenon=cand["category"][0],
                cefr=None,
                source="wikiedits-multigec-en",
                source_id=row["id"],
                source_path=WIKI_ERROR,
                licence=wiki_licence,
                evidence="wikipedia-revision-silver-unreviewed",
                error_origin="real-revision-edit",
                explanation_points=[],
                explanation_locale=None,
                source_status=row.get("reviewStatus"),
                edit_rule=cand["category"][1],
                sentence_cut_from_paragraph=cand["extracted"],
                provenance=row.get("provenance"),
            )
            if item is not None:
                wiki_items.append(item)
        n_errors_target = TUTOR_PER_L1 - TUTOR_CLEAN_PER_L1
        n_wiki = min(len(wiki_items), TUTOR_WIKI_ERROR_MAX)
        n_distractor = n_errors_target - n_wiki
        picked_distractors = stratified_sample(
            fresh_pool(distractor_pools[l1]["screen"], used_sentences), n_distractor, keys=("l1", "phenomenon")
        )
        if len(picked_distractors) < n_distractor:
            taken = {norm(item["metadata"]["acceptable_sentences"][0]) for item in picked_distractors}
            picked_distractors += stratified_sample(
                fresh_pool(distractor_pools[l1]["drill"], used_sentences | taken),
                n_distractor - len(picked_distractors),
                keys=("l1", "phenomenon"),
            )
        picked_errors = picked_distractors + wiki_items[:n_wiki]
        for item in picked_errors:
            used_sentences.add(norm(item["metadata"]["acceptable_sentences"][0]))
        items.extend(picked_errors)
        per_l1_counts[l1] = {
            "screen_distractor_candidates": len(distractor_pools[l1]["screen"]),
            "drill_distractor_candidates": len(distractor_pools[l1]["drill"]),
            "wiki_candidates": len(wiki_pools[l1]),
            "distractors_used": len(picked_distractors),
            "wiki_errors_used": len(picked_errors) - len(picked_distractors),
        }

    # Clean items.
    clean_pool = clean_candidates(src, used_sentences, skipped)
    wiki_clean = wiki_clean_candidates()
    wiki_clean_by_l1: dict[str, list[dict[str, Any]]] = {l1: [] for l1 in L1S}
    for index, cand in enumerate(sorted(wiki_clean, key=lambda c: c["row"]["id"])):
        wiki_clean_by_l1[L1S[index % len(L1S)]].append(cand)
    for l1 in L1S:
        rng_for(f"wiki-clean:{l1}").shuffle(wiki_clean_by_l1[l1])
    n_wiki_errors = {l1: per_l1_counts[l1]["wiki_errors_used"] for l1 in L1S}
    for l1 in L1S:
        locale = L1_LOCALE[l1]
        n_wiki_clean = min(TUTOR_WIKI_CLEAN_PER_L1, n_wiki_errors[l1] // 2) if n_wiki_errors[l1] else 0
        wiki_clean_items = []
        for cand in [c for c in wiki_clean_by_l1[l1] if norm(c["text"]) not in used_sentences][:n_wiki_clean]:
            row = cand["row"]
            item = tutor_item(
                id=f"{row['id']}@{locale}",
                l1=l1,
                learner=cand["text"],
                corrected=cand["text"],
                has_error=False,
                phenomenon="no_error",
                cefr=None,
                source="wikiedits-multigec-en",
                source_id=row["id"],
                source_path=WIKI_CLEAN,
                licence=wiki_licence,
                evidence="wikipedia-revision-silver-unreviewed",
                error_origin=None,
                explanation_points=[],
                explanation_locale=None,
                source_status=row.get("reviewStatus"),
                clean_basis=row.get("controlBasis"),
                sentence_cut_from_paragraph=cand["extracted"],
            )
            wiki_clean_items.append(item)
        n_screen_clean = TUTOR_CLEAN_PER_L1 - len(wiki_clean_items)
        screen_clean = stratified_sample(fresh_pool(clean_pool[l1], used_sentences), n_screen_clean, keys=("l1", "phenomenon"))
        for item in wiki_clean_items + screen_clean:
            used_sentences.add(norm(item["metadata"]["acceptable_sentences"][0]))
        items.extend(wiki_clean_items + screen_clean)
        per_l1_counts[l1]["clean_wiki"] = len(wiki_clean_items)
        per_l1_counts[l1]["clean_screens"] = len(screen_clean)
        per_l1_counts[l1]["clean_screen_candidates"] = len(clean_pool[l1])

    # A sentence may appear only once in the test (error gold or clean).
    seen: set[str] = set()
    final: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda entry: entry["id"]):
        key = norm(item["metadata"]["acceptable_sentences"][0])
        if key in seen:
            skipped["duplicate_sentence_dropped"] += 1
            continue
        seen.add(key)
        final.append(item)
    for item in final:
        assert_single_edit(item)

    shortfalls = {}
    for l1 in L1S:
        have = [it for it in final if it["metadata"]["l1"] == l1]
        errors = [it for it in have if it["metadata"]["has_error"]]
        distractors = [it for it in errors if it["metadata"]["error_origin"] == "exercise-distractor"]
        shortfalls[l1] = {
            "total": {"target": TUTOR_PER_L1, "got": len(have)},
            "errors": {"target": TUTOR_PER_L1 - TUTOR_CLEAN_PER_L1, "got": len(errors)},
            "clean": {"target": TUTOR_CLEAN_PER_L1, "got": len(have) - len(errors)},
            "distractor_errors": {"minimum": TUTOR_DISTRACTOR_MIN, "got": len(distractors)},
            "real_revision_errors": {"max": TUTOR_WIKI_ERROR_MAX, "got": len(errors) - len(distractors)},
        }
    report = {
        "per_l1_sources": per_l1_counts,
        "shortfalls": shortfalls,
        "by_l1_error_origin": nested_count(final, "error_origin"),
        "by_l1_source_status": nested_count(final, "source_status"),
        "by_l1_has_error": nested_count(final, "has_error"),
        "skipped": dict(sorted(skipped.items())),
        "wiki_error_candidates_passing_filters": len(wiki_errors),
        "wiki_error_filter_skipped": dict(sorted(wiki_skipped.items())),
        "tatoeba_reject_count": TATOEBA_REJECT_COUNT,
        "wiki_manifest": {key: manifest[key] for key in ("source", "sourceId", "license", "licenseUrl", "reviewStatus", "evidenceBasis", "promotionEligibility")},
        "sources": [
            home_relative(SCREENS), home_relative(SCREENS_REVIEW), home_relative(WIKI_ERROR),
            home_relative(WIKI_CLEAN), home_relative(WIKI_MANIFEST), home_relative(TATOEBA),
        ],
        "licence_note": (
            "Wikipedia pair items carry the licence in WIKI_LICENCE: the text is Wikipedia revision text (CC BY-SA 4.0, "
            "attribution and share-alike apply) and the WikiEdits-MultiGEC dataset is MIT; the pairs are silver-unreviewed "
            "and evaluation-only. Tatoeba (CC BY 2.0 FR) is used for lookup counts only."
        ),
    }
    return final, report


def nested_count(items: list[dict[str, Any]], field: str) -> dict[str, dict[str, int]]:
    out: dict[str, Counter] = defaultdict(Counter)
    for item in items:
        out[item["metadata"]["l1"]][str(item["metadata"].get(field))] += 1
    return {l1: dict(sorted(counter.items())) for l1, counter in sorted(out.items())}


def clean_candidates(src: Source, used_sentences: set[str], skipped: Counter) -> dict[str, list[dict[str, Any]]]:
    """Correct sentences from screens that were not used for errors, one l1 each."""
    records: list[dict[str, Any]] = []
    for kind in ("choose", "build"):
        for lesson_id, lesson, screen in src.screens(kind):
            if src.is_pronunciation_lesson(lesson_id):
                continue
            sentence = screen["answer"].strip()
            if not is_full_sentence(sentence) or not 4 <= n_words(sentence) <= 30 or NON_ENGLISH_RE.search(sentence) or norm(sentence) in used_sentences:
                continue
            if re.search(r"\b[A-Z](?:-[A-Z]){2,}\b|/", sentence):
                continue
            lead = screen.get("lead") or {}
            for l1 in L1S:
                locale = L1_LOCALE[l1]
                if not lead.get(locale) or src.screen_state(screen["id"], locale) != "verified":
                    continue
                title, cefr = src.lesson_label(lesson_id)
                records.append({"key": screen["id"], "l1": l1, "screen": screen, "lesson_id": lesson_id, "kind": kind,
                                "sentence": sentence, "title": title, "cefr": cefr, "lesson_status": lesson["status"]})
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        by_key[rec["key"]].append(rec)
    assignment = assign_l1({key: [rec["l1"] for rec in recs] for key, recs in by_key.items()}, "tutor-clean")
    pools: dict[str, list[dict[str, Any]]] = {l1: [] for l1 in L1S}
    for key, l1 in assignment.items():
        rec = next(r for r in by_key[key] if r["l1"] == l1)
        locale = L1_LOCALE[l1]
        item = tutor_item(
            id=f"{key}@{locale}:ok",
            l1=l1,
            learner=rec["sentence"],
            corrected=rec["sentence"],
            has_error=False,
            phenomenon="no_error",
            cefr=rec["cefr"],
            source="tonada-lesson-screens",
            source_id=key,
            source_path=SCREENS,
            licence=APP_LICENCE,
            evidence="tonada-app-answer-machine-reviewed",
            error_origin=None,
            explanation_points=[],
            explanation_locale=None,
            source_status=src.screen_state(key, locale),
            lesson_status=rec["lesson_status"],
            lesson_topic=snake(rec["title"]),
            screen_kind=rec["kind"],
        )
        pools[l1].append(item)
    return pools


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------

def main() -> None:
    src = Source()
    exercises, exercise_report = build_exercises(src)
    exercise_report["by_l1_source_status"] = nested_count(exercises, "source_status")
    exercise_report["by_l1_exercise_type"] = nested_count(exercises, "exercise_type")
    write_outputs(SUITE, "exercises", exercises, exercise_report)
    tutor, tutor_report = build_tutor(src)
    write_outputs(SUITE, "tutor_accuracy", tutor, tutor_report)
    for name, items in (("exercises", exercises), ("tutor_accuracy", tutor)):
        print(name, len(items), dict(sorted(Counter(i["metadata"]["l1"] for i in items).items())))


if __name__ == "__main__":
    main()
