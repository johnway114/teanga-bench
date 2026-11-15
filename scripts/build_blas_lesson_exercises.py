#!/usr/bin/env python3
"""Build ``blas/lesson_exercises`` (scoring ``accept_list``) from the Blas app's own lesson exercises.

Run: ``python3 scripts/build_blas_lesson_exercises.py`` (stdlib only; no network).

Sources, per language ``~/Documents/blas/data/content/<language>/``:

* ``grammar-lessons.json``  ``lessons[].sections[]`` with ``type == "drill"``; each
  ``drills[]`` entry carries ``prompt``, ``expectedAnswer``, optional ``acceptedAnswers``
  and optional ``options``.
* ``lesson-screens.json``   ``lessons.<id>.screens[]`` of kind ``choose`` (cloze with
  choices), ``build`` (tile ordering) and ``letter`` (mutation / initial change).
  ``drills`` screens only carry a count that points at the grammar-lessons drills, and
  ``explain``/``takeaway``/``contrast``/``compare`` carry no question, so they are not used.
* ``item-difficulty.json``  ``grammarLesson:<lessonId>`` score -> CEFR band.
* ``sentences.json`` ``clozeTargets`` / ``transformations`` are NOT used: see the report.

Exercise kinds built (``metadata.exercise_kind``):

``choice``       multiple-choice drill; options are shown in a seeded shuffled order.
``cloze_free``   drill with an explicit blank and an English gloss, no options.
``transform``    drill of the form ``a + b = ?`` (mutation / contraction / inflection).
``form``         drill asking for ``VN of 'x'`` or ``<tense/person> of 'x'``.
``screen_choose`` lesson-screen cloze with choices.
``screen_build`` lesson-screen tile ordering with decoys.
``screen_letter`` lesson-screen initial-change blank.

Gold strings are copied from the source records (``expectedAnswer``, ``acceptedAnswers``,
``acceptedAnswerSets.en``, screen ``answer``/``blank``/``word``). Nothing is invented.

``human_checked`` is true only when the lesson record itself says so: ``_meta.humanReviewed``
is true, or ``reviewStatus`` / ``_meta.reviewStatus`` equals ``approved``, or the drill has
``humanReviewed: true``. None of the current records do, so it is false everywhere.
"""

from __future__ import annotations

import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    BLAS_CONTENT, LANGUAGE_NAMES, LANGUAGES, SEED, in_bunamo, kaikki_forms,
    load_json, make_item, norm, unique, write_outputs,
)

SUITE = "blas"
TEST = "lesson_exercises"
PER_LANGUAGE = 60
NON_CHOICE_QUOTA = 24  # cloze / transform / form / build / letter items per language, when available
LICENCE = "private-blas"
SOURCE = "blas-app:lesson-exercises"

PLACEHOLDERS = {"", "-", "--", "—", "–", "n/a", "na", "none", "?", "tbd", "todo", "null"}
JUNK_OPTIONS = {"none", "other", "none of these", "none of the above", "n/a"}  # filler distractors in some Welsh drills

# Audio / pronunciation, and image-dependent exercises.
AUDIO_RE = re.compile(
    r"\b(listen|hear|hears|heard|audio|pronounc\w*|sounds?|recording|aloud|phonetic\w*|ipa|syllables?|"
    r"stress(?:ed)?|spoken|voice)\b|/[^/\s]{1,12}/",
    re.I,
)
IMAGE_RE = re.compile(
    r"\b(picture|pictures|pictured|image|images|photo|photograph|illustration|illustrated|icon|diagram|"
    r"drawing|emoji|camera|outline|arrow|label on|map shows|on screen|screenshot)\b",
    re.I,
)
# Questions that point at lesson material the prompt does not reproduce.
CONTEXT_RE = re.compile(
    r"\b(speaker|speakers|dialogue|conversation|excerpt|passage|reading|according to|cited|the source|"
    r"source line|source sentence|source record|shown|displayed|listed|the line|this line|that line|"
    r"the text|the story|the recorded|recorded|quoted|supplied|worked example|looking at|in this unit|"
    r"this lesson|the lesson|reviewed line|the comparison|the exact|the above|above|"
    r"without (?:the )?(?:choices|options|looking|list|labels?)|same (?:line|sentence)|"
    r"the previous (?:line|sentence|answer)|which of the two|in the separate|the earlier line|"
    r"in the (?:first|second|third|last) (?:line|sentence)|independently|"
    r"(?:woman|man|writer|author|narrator|councillor|child)['’]s (?:account|story|text|letter|message|note)|here\b)",
    re.I,
)
LANG_NAME_RE = re.compile(r"\b(irish|welsh|gaelic|gaeilge|manx|gaelg|breton|cornish|kernewek|brezhoneg|cymraeg)\b", re.I)
ENGLISH_ANSWER_STEM_RE = re.compile(r"^(what does|what do|which english|what is the english|english meaning|what is the meaning|which meaning)", re.I)
ENGLISH_STOPWORDS = {
    "the", "a", "an", "to", "he", "she", "i", "is", "was", "who", "that", "for", "of", "with", "in", "his",
    "her", "you", "we", "it", "they", "are", "be", "will", "my", "your", "our", "them", "him", "me", "have",
    "has", "do", "did", "not", "and", "at", "on", "this", "what", "where", "how", "there",
}


def english_gloss(stem: str) -> bool:
    """True when the exercise shows an English gloss: a parenthetical, quoted phrase or lead-in before ':'."""
    segments = re.findall(r"\(([^()]*)\)", stem) + re.findall(r"[‘“\"]([^’”\"]{4,}?)[’”\"]", stem)
    if ":" in stem:
        segments.append(stem.split(":", 1)[0])
    for seg in segments:
        if BLANK_RE.search(seg):
            continue
        if sum(1 for w in re.findall(r"[A-Za-z']+", seg) if w.lower() in ENGLISH_STOPWORDS) >= 2:
            return True
    return False
GENERIC_PHENOMENA = {"irish", "welsh", "scots_gaelic", "manx", "breton", "cornish", "none", ""}

BLANK_RE = re.compile(r"_{2,}")
TRANSFORM_RE = re.compile(r"^(?P<left>[^=→?]{1,60}?)\s*\+\s*(?P<right>[^=→?]{1,60}?)\s*(?:=|→)\s*\?\s*$")
FORM_RE = re.compile(
    r"^(?:What is the )?(?:VN|verbal noun|3sg \w+|[123](?:sg|pl) \w+|conditional|autonomous \w+|negative|"
    r"imperative|comparative|superlative|plural|genitive)\b[^?'‘“\"]{0,25}\bof\s+['‘“\"][^'’”\"]{1,40}['’”\"]"
    r"(?:\s*\([^)]{1,60}\))?(?::\s*['‘“\"][^'’”\"]{1,60}['’”\"])?\s*\??$",
    re.I,
)


class Rejects:
    """Counts of rejected candidates by (language, kind, reason)."""

    def __init__(self) -> None:
        self.counts: Counter[tuple[str, str, str]] = Counter()

    def add(self, language: str, kind: str, reason: str) -> None:
        self.counts[(language, kind, reason)] += 1

    def as_dict(self) -> dict[str, dict[str, dict[str, int]]]:
        out: dict[str, dict[str, dict[str, int]]] = {}
        for (language, kind, reason), n in sorted(self.counts.items()):
            out.setdefault(language, {}).setdefault(kind, {})[reason] = n
        return out


def snake(text: str) -> str:
    text = re.sub(r"[^0-9a-zA-Z]+", "_", (text or "").strip().lower()).strip("_")
    return text


def en(value: Any) -> Any:
    return value.get("en") if isinstance(value, dict) else value


def clean(text: str) -> str:
    """Drop the app's ``{focus}`` markup and tidy whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[{}]", "", text or "")).strip()


def phenomenon_of(category: str | None) -> str:
    value = snake(category or "")
    if value in GENERIC_PHENOMENA:
        return "general"
    if len(value) > 40 or value.count("_") > 3:
        return "other"
    return value


def contains_word(haystack: str, needle: str) -> bool:
    needle_n = norm(needle)
    if not needle_n:
        return False
    return re.search(r"(?<!\w)" + re.escape(needle_n) + r"(?!\w)", norm(haystack)) is not None


def leaks(stem: str, answers: list[str]) -> bool:
    return any(len(norm(a)) >= 3 and contains_word(stem, a) for a in answers)


def band_of(score: float, bands: dict[str, list[float]]) -> str | None:
    for level, bounds in bands.items():
        if bounds[0] <= score < bounds[1]:
            return level
    top = max(bands.items(), key=lambda kv: kv[1][1])
    return top[0] if score >= top[1][1] else None


def lesson_cefr(lesson: dict[str, Any], difficulty: dict[str, Any]) -> tuple[str | None, str]:
    level = lesson.get("cefrLevel")
    if level:
        return level, "lesson.cefrLevel"
    score = difficulty["items"].get(f"grammarLesson:{lesson['id']}")
    if isinstance(score, (int, float)):
        level = band_of(score, difficulty["bands"])
        if level:
            return level, "item-difficulty"
    return None, "none"


def human_reviewed(lesson: dict[str, Any], drill: dict[str, Any] | None = None) -> bool:
    meta = lesson.get("_meta") if isinstance(lesson.get("_meta"), dict) else {}
    if meta.get("humanReviewed") is True or lesson.get("humanReviewed") is True:
        return True
    if str(meta.get("reviewStatus", "")).lower() == "approved" or str(lesson.get("reviewStatus", "")).lower() == "approved":
        return True
    if drill and (drill.get("humanReviewed") is True or str(drill.get("reviewStatus", "")).lower() == "approved"):
        return True
    return False


def lesson_skip_reason(lesson: dict[str, Any]) -> str | None:
    if lesson.get("_blocked"):
        return "lesson_blocked"
    if lesson.get("supersededByLessonId") or lesson.get("retiredFromInstruction"):
        return "lesson_retired_or_superseded"
    if lesson.get("qualityFlags"):
        return "lesson_quality_flags"
    return None


# --- evidence ---------------------------------------------------------------------------

_KAIKKI_ALL: dict[str, set[str]] = {}


def kaikki_all(language: str) -> set[str]:
    if language not in _KAIKKI_ALL:
        union: set[str] = set()
        for forms in kaikki_forms(language).values():
            union |= forms
        _KAIKKI_ALL[language] = union
    return _KAIKKI_ALL[language]


def evidence_for(language: str, gold: str, gold_is_target: bool) -> str:
    if not gold_is_target:
        return "blas-app-only"
    words = re.findall(r"[^\W\d_]+(?:['-][^\W\d_]+)*", norm(gold))
    if language == "irish" and in_bunamo(gold):
        return "blas-app+bunamo"
    if language in ("irish", "manx", "cornish", "scots-gaelic") and words:
        known = kaikki_all(language)
        if all(word in known for word in words):
            return "blas-app+kaikki"
    return "blas-app-only"


# --- candidate builders -----------------------------------------------------------------


def drill_fields(drill: dict[str, Any]) -> dict[str, Any]:
    prompt = drill.get("prompt") or en(drill.get("prompts")) or ""
    expected = drill.get("expectedAnswer") or en(drill.get("expectedAnswers")) or ""
    options = drill.get("options") or en(drill.get("optionSets")) or []
    accepted = list(drill.get("acceptedAnswers") or []) + list(en(drill.get("acceptedAnswerSets")) or [])
    return {
        "prompt": clean(prompt) if isinstance(prompt, str) else "",
        "expected": expected.strip() if isinstance(expected, str) else "",
        "options": [o for o in options if isinstance(o, str)] if isinstance(options, list) else [],
        "accepted": [a for a in accepted if isinstance(a, str)],
    }


def shuffled(values: list[str], key: str) -> list[str]:
    rng = random.Random(f"{SEED}:{key}")
    out = list(values)
    rng.shuffle(out)
    return out


def gold_is_target_for_choice(stem: str, expected: str) -> bool:
    if BLANK_RE.search(stem):
        return True
    if ENGLISH_ANSWER_STEM_RE.match(stem):
        return False
    if LANG_NAME_RE.search(stem) and re.search(r"\b(in|the|choose the|which)\s+(irish|welsh|gaelic|manx|breton|cornish)\b", stem, re.I):
        return True
    return False


def build_drill_candidates(
    language: str, lesson: dict[str, Any], status: str | None, ctx: dict[str, Any], rejects: Rejects,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    lang_name = LANGUAGE_NAMES[language]
    section_no = 0
    for section in lesson.get("sections", []):
        if section.get("type") != "drill":
            continue
        section_no += 1
        drills = section.get("drills")
        if not isinstance(drills, list):
            continue
        for di, drill in enumerate(drills):
            if not isinstance(drill, dict):
                continue
            f = drill_fields(drill)
            stem, expected = f["prompt"], f["expected"]
            has_options = len(f["options"]) > 0
            kind = "choice" if has_options else "free"

            def reject(reason: str, k: str = kind) -> None:
                rejects.add(language, k, reason)

            if drill.get("qualityFlags"):
                reject("drill_quality_flags"); continue
            if drill.get("practiceMode") == "reflection":
                reject("reflection_practice_mode"); continue
            if drill.get("autoGrade") is False:
                reject("autoGrade_false"); continue
            policy = str(drill.get("evaluationPolicy") or "")
            if re.search(r"automatic|formative|open (?:welsh|interpretation)", policy, re.I):
                reject("evaluation_policy_not_auto_graded"); continue
            if drill.get("listenFirst") or drill.get("nativeAudioText") and AUDIO_RE.search(stem):
                reject("audio_dependent"); continue
            if not stem:
                reject("no_prompt"); continue
            if not expected or norm(expected) in PLACEHOLDERS:
                reject("empty_or_placeholder_gold"); continue
            if AUDIO_RE.search(stem):
                reject("audio_or_pronunciation"); continue
            if IMAGE_RE.search(stem):
                reject("image_dependent"); continue
            if CONTEXT_RE.search(stem):
                reject("needs_unseen_lesson_context"); continue
            if re.search(r"correct form\??$", stem, re.I):
                reject("generic_prompt_no_target"); continue
            if re.match(r"(?:sort|match|pair|group|classify)\b", stem, re.I):
                reject("multi_part_matching_task"); continue

            tag = f"s{section_no}d{di}"
            base = {
                "lesson": lesson, "status": status, "ctx": ctx, "tag": tag,
                "source_id": f"{lesson['id']}#{tag}",
                "practice_mode": drill.get("practiceMode"),
                "human": human_reviewed(lesson, drill),
            }

            if has_options:
                opts = [o for o in unique(f["options"]) if norm(o) not in JUNK_OPTIONS]
                if len(opts) < 2:
                    reject("fewer_than_two_options"); continue
                opt_norms = [norm(o) for o in opts]
                if norm(expected) not in opt_norms:
                    reject("expected_not_in_options"); continue
                accept = unique([expected] + f["accepted"])
                if any(norm(a) in opt_norms and norm(a) != norm(expected) for a in accept):
                    reject("accepted_answer_is_another_option"); continue
                if sum(len(o) for o in opts) > 600 or len(stem) > 400:
                    reject("too_long"); continue
                if leaks(stem, accept):
                    reject("answer_appears_in_question"); continue
                item_id = f"blx-{language}-{snake(lesson['id'])}-{tag}"
                order = shuffled(opts, item_id)
                option_block = "\n".join(f"- {o}" for o in order)
                prompt = (
                    f"This is a multiple-choice exercise from the {lang_name} course of a language-learning app.\n\n"
                    f"Question: {stem}\n\nOptions:\n{option_block}\n\n"
                    "Choose the one correct option and give its text exactly as written above."
                )
                out.append({**base, "id": item_id, "kind": "choice", "prompt": prompt, "accept": accept,
                            "gold_is_target": gold_is_target_for_choice(stem, expected)})
                continue

            # Free-answer drills: only formal exercise shapes with a definite answer.
            accept = unique([expected] + f["accepted"])
            if len(accept) > 8 or any(len(a.split()) > 6 or ";" in a or "=" in a for a in accept):
                reject("free_answer_not_definite_or_too_long"); continue
            if re.search(r"\(or |\bor\b.*\bor\b|/", expected):
                reject("free_answer_has_alternatives_in_one_string"); continue
            item_id = f"blx-{language}-{snake(lesson['id'])}-{tag}"
            m = TRANSFORM_RE.match(stem)
            if m:
                if leaks(stem, accept):
                    reject("answer_appears_in_question", "transform"); continue
                prompt = (
                    f"This is an exercise from the {lang_name} course of a language-learning app. Combine the two parts into the single correct "
                    f"{lang_name} form, applying whatever mutation, contraction, agreement or inflection the grammar "
                    f"requires. Parts: {stem[:-1].rstrip(' =→').rstrip()}\n"
                    "Give the combined form only."
                )
                out.append({**base, "id": item_id, "kind": "transform", "prompt": prompt, "accept": accept,
                            "gold_is_target": True})
                continue
            if BLANK_RE.search(stem):
                if not english_gloss(stem):
                    reject("cloze_without_english_gloss", "cloze_free"); continue
                if any(len(a.split()) > 1 for a in accept):
                    reject("cloze_multiword_answer_variants_unlisted", "cloze_free"); continue
                if leaks(stem, accept):
                    reject("answer_appears_in_question", "cloze_free"); continue
                prompt = (
                    f"This is a fill-in-the-blank exercise from the {lang_name} course of a language-learning app. Supply the missing "
                    f"{lang_name} word(s) for the blank (____); the English in the exercise tells you what is meant.\n\n"
                    f"Exercise: {stem}"
                )
                out.append({**base, "id": item_id, "kind": "cloze_free", "prompt": prompt, "accept": accept,
                            "gold_is_target": True})
                continue
            if FORM_RE.match(stem) and len(stem) <= 90:
                if leaks(stem, accept):
                    reject("answer_appears_in_question", "form"); continue
                prompt = (
                    f"This is a grammar exercise from the {lang_name} course of a language-learning app. Give the {lang_name} form asked for.\n\n"
                    f"Exercise: {stem}"
                )
                out.append({**base, "id": item_id, "kind": "form", "prompt": prompt, "accept": accept,
                            "gold_is_target": True})
                continue
            reject("free_answer_shape_not_definite")
    return out


def build_screen_candidates(
    language: str, lesson: dict[str, Any], screens_entry: dict[str, Any], ctx: dict[str, Any], rejects: Rejects,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    lang_name = LANGUAGE_NAMES[language]
    status = screens_entry.get("status")
    for si, screen in enumerate(screens_entry.get("screens", [])):
        kind = screen.get("kind")
        if kind not in ("choose", "build", "letter"):
            continue
        tag = f"sc{si}"
        item_id = f"blx-{language}-{snake(lesson['id'])}-{tag}"
        base = {
            "lesson": lesson, "status": status, "ctx": ctx, "tag": tag,
            "source_id": f"{lesson['id']}#screen{si}:{kind}",
            "practice_mode": None, "human": human_reviewed(lesson), "id": item_id,
        }
        kname = f"screen_{kind}"

        def reject(reason: str) -> None:
            rejects.add(language, kname, reason)

        if screen.get("qualityFlags"):
            reject("screen_quality_flags"); continue
        meaning = clean(en(screen.get("meaning")) or "")
        if kind == "choose":
            answer, blank = (screen.get("answer") or "").strip(), (screen.get("blank") or "").strip()
            choices = unique([c for c in screen.get("choices") or [] if isinstance(c, str)])
            question = clean(en(screen.get("prompt")) or "")
            if not answer or not blank or norm(blank) in PLACEHOLDERS:
                reject("empty_or_placeholder_gold"); continue
            if norm(blank) not in [norm(c) for c in choices] or len(choices) < 2:
                reject("blank_not_in_choices"); continue
            text = question + " " + meaning
            if AUDIO_RE.search(text):
                reject("audio_or_pronunciation"); continue
            if IMAGE_RE.search(text):
                reject("image_dependent"); continue
            pattern = re.compile(r"(?<!\w)" + re.escape(blank) + r"(?!\w)", re.I)
            if len(pattern.findall(answer)) == 0:
                reject("blank_not_found_in_sentence"); continue
            sentence = pattern.sub("____", answer)
            if norm(sentence) == "____":
                sentence = None
            stem_parts = [f"Task: {question}"] if question else []
            if sentence:
                stem_parts.append(f"Sentence: {sentence}")
            if meaning:
                stem_parts.append(f"English meaning: {meaning}")
            stem = "\n".join(stem_parts)
            if leaks(stem, [blank]):
                reject("answer_appears_in_question"); continue
            if not meaning and not question:
                reject("no_prompt"); continue
            order = shuffled(choices, item_id)
            prompt = (
                f"This is a multiple-choice exercise from the {lang_name} course of a language-learning app.\n\n{stem}\n\nOptions:\n"
                + "\n".join(f"- {c}" for c in order)
                + "\n\nChoose the correct option and give its text exactly as written above."
            )
            out.append({**base, "kind": kname, "prompt": prompt, "accept": [blank], "gold_is_target": True})
        elif kind == "build":
            answer = (screen.get("answer") or "").strip()
            decoys = [d for d in screen.get("decoys") or [] if isinstance(d, str)]
            if not answer or norm(answer) in PLACEHOLDERS or not meaning:
                reject("empty_or_placeholder_gold"); continue
            words = answer.split()
            if len(words) < 3:
                reject("fewer_than_three_words"); continue
            tiles = shuffled(words + decoys, item_id)
            tries = 0
            while [norm(t) for t in tiles if t in words] == [norm(w) for w in words] and tries < 20 and len(set(words)) > 1:
                tries += 1
                tiles = shuffled(words + decoys, f"{item_id}:{tries}")
            prompt = (
                f"This is a sentence-building exercise from the {lang_name} course of a language-learning app. Arrange the tiles into the "
                f"{lang_name} phrase that means “{meaning}”. Use the tiles in the right order"
                + (" (some tiles are decoys and do not belong in the phrase)" if decoys else "")
                + f".\n\nTiles: {' | '.join(tiles)}\n\nGive the finished phrase."
            )
            out.append({**base, "kind": kname, "prompt": prompt, "accept": [answer], "gold_is_target": True})
        else:  # letter
            phrase, word, root = (screen.get("phrase") or "").strip(), (screen.get("word") or "").strip(), (screen.get("base") or "").strip()
            if not phrase or not word or norm(word) in PLACEHOLDERS or not root:
                reject("empty_or_placeholder_gold"); continue
            if norm(word) == norm(root):
                reject("form_unchanged"); continue
            pattern = re.compile(r"(?<!\w)" + re.escape(word) + r"(?!\w)", re.I)
            if len(pattern.findall(phrase)) != 1:
                reject("word_not_found_once_in_phrase"); continue
            blanked = pattern.sub("____", phrase)
            caption = screen.get("caption") if isinstance(screen.get("caption"), dict) else {}
            caption_native = (caption.get("native") or "") if caption else ""
            root_gloss = clean(en(caption.get("meaning")) or "") if norm(caption_native) == norm(root) else ""
            if not meaning:
                reject("no_prompt"); continue
            stem = blanked + " " + meaning + " " + root
            if leaks(stem, [word]):
                reject("answer_appears_in_question"); continue
            prompt = (
                f"This is an exercise from the {lang_name} course of a language-learning app on how a word changes in a phrase (mutation or other "
                f"change to its beginning or form). The word in its basic form is “{root}”"
                + (f" ({root_gloss})" if root_gloss else "")
                + f". Fill the blank with the form this word takes here.\n\nPhrase: {blanked}\n"
                f"English meaning: {meaning}\n\nGive only the word that fills the blank."
            )
            out.append({**base, "kind": kname, "prompt": prompt, "accept": [word], "gold_is_target": True})
    return out


# --- census -----------------------------------------------------------------------------


def census(language: str, lessons: list[dict[str, Any]], screens: dict[str, Any]) -> dict[str, Any]:
    sections: Counter[str] = Counter()
    drills = with_options = with_expected = with_accepted = 0
    modes: Counter[str] = Counter()
    fields: Counter[str] = Counter()
    for lesson in lessons:
        for section in lesson.get("sections", []):
            sections[str(section.get("type"))] += 1
            if section.get("type") != "drill" or not isinstance(section.get("drills"), list):
                continue
            for drill in section["drills"]:
                drills += 1
                fields.update(k for k in ("acceptedAnswers", "acceptedAnswerSets", "options", "optionSets", "hint", "nativeAudioText") if drill.get(k))
                with_options += bool(drill.get("options") or en(drill.get("optionSets")))
                with_expected += bool(drill.get("expectedAnswer") or en(drill.get("expectedAnswers")))
                with_accepted += bool(drill.get("acceptedAnswers") or en(drill.get("acceptedAnswerSets")))
                modes[str(drill.get("practiceMode"))] += 1
    kinds: Counter[str] = Counter()
    status: Counter[str] = Counter()
    answer_keys: dict[str, Counter[str]] = defaultdict(Counter)
    for entry in screens.values():
        status[str(entry.get("status"))] += 1
        for screen in entry.get("screens", []):
            kinds[str(screen.get("kind"))] += 1
            if screen.get("kind") in ("choose", "build", "letter"):
                answer_keys[screen["kind"]].update(k for k in ("answer", "blank", "choices", "decoys", "word", "base", "phrase", "meaning") if k in screen)
    return {
        "lessons": len(lessons),
        "section_types": dict(sorted(sections.items())),
        "drill_items": drills,
        "drill_items_with_options": with_options,
        "drill_items_with_expectedAnswer": with_expected,
        "drill_items_with_alternative_answers(acceptedAnswers|acceptedAnswerSets)": with_accepted,
        "drill_practice_modes": dict(sorted(modes.items())),
        "drill_answer_related_fields": dict(sorted(fields.items())),
        "screen_lesson_status": dict(sorted(status.items())),
        "screen_kinds": dict(sorted(kinds.items())),
        "screen_answer_fields_by_kind": {k: dict(v) for k, v in sorted(answer_keys.items())},
    }


# --- sampling ---------------------------------------------------------------------------

STATUS_RANK = {"reviewed": 0, None: 1, "draft": 2}


def phenomenon_pools(cands: list[dict[str, Any]], rng: random.Random, seen_prompts: set[str]) -> dict[str, list[dict[str, Any]]]:
    """Per phenomenon, an ordered pool that alternates exercise kinds, reviewed lessons first."""
    by_phen: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for c in sorted(cands, key=lambda c: c["id"]):
        key = norm((exercise_stem(c["prompt"], c["kind"]) or "") + "|" + c["accept"][0])
        if key in seen_prompts:
            continue
        seen_prompts.add(key)
        by_phen[c["phenomenon"]][c["kind"]].append(c)
    pools: dict[str, list[dict[str, Any]]] = {}
    for phen in sorted(by_phen):
        kinds = by_phen[phen]
        for kind in sorted(kinds):
            rng.shuffle(kinds[kind])
            kinds[kind].sort(key=lambda c: STATUS_RANK.get(c["status"], 1))  # stable: reviewed first
        order: list[dict[str, Any]] = []
        depth = 0
        while True:
            added = False
            for kind in sorted(kinds):
                if depth < len(kinds[kind]):
                    order.append(kinds[kind][depth]); added = True
            if not added:
                break
            depth += 1
        pools[phen] = order
    return pools


def draw(pools: dict[str, list[dict[str, Any]]], n: int, taken: Counter[str], rng: random.Random) -> list[dict[str, Any]]:
    """Take up to n items, always from the phenomenon with the fewest items chosen so far."""
    chosen: list[dict[str, Any]] = []
    cursor: Counter[str] = Counter()
    while len(chosen) < n:
        open_phen = [p for p in sorted(pools) if cursor[p] < len(pools[p])]
        if not open_phen:
            break
        low = min(taken[p] for p in open_phen)
        phen = rng.choice([p for p in open_phen if taken[p] == low])
        chosen.append(pools[phen][cursor[phen]])
        cursor[phen] += 1
        taken[phen] += 1
    return chosen


def select(cands: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    """Stratify by phenomenon. Non-choice exercises are taken first (up to NON_CHOICE_QUOTA) so the set
    is not all multiple-choice vocabulary; multiple-choice fills the rest."""
    rng = random.Random(f"{SEED}:{language}")
    seen: set[str] = set()
    special = phenomenon_pools([c for c in cands if c["kind"] != "choice"], rng, seen)
    plain = phenomenon_pools([c for c in cands if c["kind"] == "choice"], rng, seen)
    taken: Counter[str] = Counter()
    chosen = draw(special, NON_CHOICE_QUOTA, taken, rng)
    chosen += draw(plain, PER_LANGUAGE - len(chosen), taken, rng)
    if len(chosen) < PER_LANGUAGE:  # not enough multiple-choice: top up with the rest of the others
        used = {c["id"] for c in chosen}
        rest = {p: [c for c in pool if c["id"] not in used] for p, pool in special.items()}
        chosen += draw(rest, PER_LANGUAGE - len(chosen), taken, rng)
    return chosen


# --- main -------------------------------------------------------------------------------


def exercise_stem(prompt: str, kind: str) -> str | None:
    """The learner-facing question text (without the fixed template wording and without the option list)."""
    if kind == "screen_build":
        return None  # the answer is made of the tiles by design
    if kind in ("choice", "screen_choose"):
        head = prompt.split("\n\nOptions:")[0]
        return head.split("Question: ", 1)[1] if "Question: " in head else head.split("app.\n\n", 1)[1]
    if kind == "transform":
        return prompt.split("Parts: ", 1)[1].split("\nGive", 1)[0]
    if kind in ("cloze_free", "form"):
        return prompt.split("Exercise: ", 1)[1]
    if kind == "screen_letter":
        return prompt.split("Phrase: ", 1)[1].split("\n\nGive only", 1)[0]
    raise ValueError(kind)


def main() -> None:
    rejects = Rejects()
    items: list[dict[str, Any]] = []
    census_all: dict[str, Any] = {}
    candidate_counts: dict[str, dict[str, int]] = {}
    lesson_skips: dict[str, Counter[str]] = {}
    for language in LANGUAGES:
        base_dir = BLAS_CONTENT / language
        lessons_file = base_dir / "grammar-lessons.json"
        screens_file = base_dir / "lesson-screens.json"
        difficulty = load_json(base_dir / "item-difficulty.json")
        lessons = load_json(lessons_file)["lessons"]
        screens = load_json(screens_file)["lessons"]
        census_all[language] = census(language, lessons, screens)
        skips: Counter[str] = Counter()
        cands: list[dict[str, Any]] = []
        for lesson in lessons:
            reason = lesson_skip_reason(lesson)
            if reason:
                skips[reason] += 1
                continue
            cefr, cefr_source = lesson_cefr(lesson, difficulty)
            category_raw = lesson.get("category")
            ctx = {
                "cefr": cefr, "cefr_source": cefr_source, "category_raw": category_raw,
                "phenomenon": phenomenon_of(category_raw),
            }
            entry = screens.get(lesson["id"])
            status = entry.get("status") if entry else None
            cands.extend(build_drill_candidates(language, lesson, status, ctx, rejects))
            if entry:
                cands.extend(build_screen_candidates(language, lesson, entry, ctx, rejects))
        lesson_skips[language] = skips
        candidate_counts[language] = dict(sorted(Counter(c["kind"] for c in cands).items()))
        for cand in cands:
            cand["phenomenon"] = cand["ctx"]["phenomenon"]
        for cand in select(cands, language):
            lesson, ctx = cand["lesson"], cand["ctx"]
            accept = cand["accept"]
            stem = exercise_stem(cand["prompt"], cand["kind"])
            if stem is not None and leaks(stem, accept):
                raise AssertionError(f"{cand['id']}: accepted answer appears in the prompt stem")
            gold = unique(accept)[0]
            items.append(make_item(
                id=cand["id"], prompt=cand["prompt"], target=gold, suite=SUITE, test=TEST, scoring="accept_list",
                language=language, phenomenon=cand["phenomenon"], cefr=ctx["cefr"],
                source=SOURCE, source_id=cand["source_id"],
                source_path=BLAS_CONTENT / language / ("lesson-screens.json" if cand["kind"].startswith("screen_") else "grammar-lessons.json"),
                licence=LICENCE, evidence=evidence_for(language, gold, cand["gold_is_target"]),
                human_checked=cand["human"], accept=accept,
                exercise_kind=cand["kind"], lesson_id=lesson["id"], lesson_type=lesson.get("lessonType"),
                category_raw=ctx["category_raw"], cefr_source=ctx["cefr_source"],
                source_status=cand["status"], practice_mode=cand["practice_mode"],
            ))

    by_language = Counter(i["metadata"]["language"] for i in items)
    report = {
        "source_files": ["grammar-lessons.json", "lesson-screens.json", "item-difficulty.json", "sentences.json (inspected, not used)"],
        "per_language_target": PER_LANGUAGE,
        "shortfalls": {lang: PER_LANGUAGE - by_language.get(lang, 0) for lang in LANGUAGES if by_language.get(lang, 0) < PER_LANGUAGE},
        "census": census_all,
        "lessons_skipped": {lang: dict(c) for lang, c in lesson_skips.items()},
        "candidates_by_kind_before_sampling": candidate_counts,
        "rejected_by_language_kind_reason": rejects.as_dict(),
        "exercise_kinds_used": ["choice", "cloze_free", "transform", "form", "screen_choose", "screen_build", "screen_letter"],
        "exercise_kinds_not_used": {
            "grammar-lessons section types explanation/examples/rule/recap": "teaching text, no question",
            "lesson-screens drills": "only a count; the questions are the grammar-lessons drills",
            "lesson-screens explain/takeaway/contrast/compare": "teaching text, no question or answer",
            "drills with practiceMode reflection or autoGrade false": "open-ended, not auto-gradable",
            "free-answer drills other than blank, 'a + b = ?' and 'VN/tense of x'": "translation or recall prompts have synonyms and lesson-context dependence; gold not definite",
            "sentences.json clozeTargets": "lists several candidate words per sentence with no designated blank and no per-slot answer; any blank would be an unlisted gold",
            "sentences.json transformations": "empty in every language",
        },
        "by_exercise_kind": dict(sorted(Counter(i["metadata"]["language"] + ":" + i["metadata"]["exercise_kind"] for i in items).items())),
        "by_source_status": dict(sorted(Counter((i["metadata"]["language"] + ":" + str(i["metadata"]["source_status"])) for i in items).items())),
        "by_language_phenomenon": dict(sorted(Counter(i["metadata"]["language"] + ":" + i["metadata"]["phenomenon"] for i in items).items())),
        "by_language_evidence": dict(sorted(Counter(i["metadata"]["language"] + ":" + i["metadata"]["evidence"] for i in items).items())),
        "human_checked_field_used": "lesson _meta.humanReviewed == true, or reviewStatus/_meta.reviewStatus == 'approved', or drill humanReviewed == true; none present, so false everywhere",
        "cefr_rule": "lesson cefrLevel when present; else item-difficulty.json grammarLesson:<id> score mapped to its band; else null (cefr_source in metadata)",
        "skipped_lesson_rules": "_blocked, supersededByLessonId, retiredFromInstruction, non-empty qualityFlags",
        "gold_quality_notes": [
            "Lesson content is largely AI-authored and provisional (lesson _meta: humanReviewed false, candidateStatus provisional-unapproved, reviewStatus pending); gold is the app's own answer, not independently verified.",
            "evidence blas-app+bunamo / blas-app+kaikki only confirms every word of the gold is a known word form; it does not confirm the grammatical slot.",
            "Free-answer gold (cloze_free, transform, form) lists only the variants the app records; dialect or spelling variants the app omits would be marked wrong.",
            "screen_build checks one tile order; free-word-order languages may allow other valid orders.",
            "Multiple-choice vocabulary distractors can be near-synonyms of the gold in some lessons.",
        ],
    }
    full = write_outputs(SUITE, TEST, items, report)
    print(f"wrote {full['n_items']} items; by language {full['by_language']}")
    print("evidence:", full["by_evidence"])


if __name__ == "__main__":
    main()
