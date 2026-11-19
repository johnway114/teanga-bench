"""Build blas/tutor_accuracy: one-error (or no-error) sentence checks, six languages.

Error sources, in order of preference (a later source fills only what an
earlier one cannot reach, and never beyond its cap):

1. ``exercise-distractor``: BLAS grammar-lesson cloze drills and lesson-screen
   "choose" screens. A distractor the exercise marks wrong is put in the blank;
   the correct fill is the gold sentence. See ``is_grammatical_pair`` for the
   filter that keeps rule-governed distractors and drops vocabulary/meaning
   choices (those can yield a valid but different sentence).
2. ``app-error-variant`` (Irish only, cap 15): ``sentences.json`` errorVariants
   of sentences whose verificationStatus starts with ``approved``.
3. ``mechanical-typo`` (cap 8 per language): doubled-letter rows from
   sealed-celtic-clean-600-v3.

Clean sentences: half from approved app sentences (sentences.json), half from the
correct fills of exercises not used for errors.

Gold strings are copied from the source files or derived by the rules above.
Nothing here calls a network or a paid API.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    BLAS_CONTENT,
    GEC_ARTIFACTS,
    LANGUAGE_NAMES,
    SEED,
    home_relative,
    kaikki_forms,
    make_item,
    norm,
    stratified_sample,
    unique,
    write_outputs,
)

SUITE = "blas"
TEST = "tutor_accuracy"
LANGUAGES = ["irish", "welsh", "scots-gaelic"]
EXCLUDED_LANGUAGES = ["manx", "breton", "cornish"]
PER_LANGUAGE = 60
ERRORS_PER_LANGUAGE = 40
CLEAN_PER_LANGUAGE = 20
CAP_APP_VARIANT = 15
CAP_TYPO = 8
MIN_WORDS, MAX_WORDS = 4, 30
SEALED = GEC_ARTIFACTS / "sealed-celtic-clean-600-v3"
CEFR = {"A1", "A2", "B1", "B2", "C1", "C2"}

PROMPT = (
    "Check this {name} learner sentence for at most one error.\n"
    "Sentence: {sentence}\n"
    "If wrong: fix only that error (exact error_span, correction, corrected_sentence). "
    "If correct: set has_error false, leave error_span and correction empty, repeat sentence as corrected_sentence.\n"
    "Reply with one JSON object only:\n"
    '{{"has_error": true|false, "error_span": "...", "correction": "...", '
    '"corrected_sentence": "...", "explanation": "..."}}\n'
)

# ---------------------------------------------------------------- text helpers

BLANK = re.compile(r"_{2,}")
QUOTES = {"'": ["'"], '"': ['"'], "\u2018": ["\u2019", "'"], "\u201c": ["\u201d"], "\u00ab": ["\u00bb"]}
EDGE_PUNCT = ".,;:!?\"\u201c\u201d\u2018()[]\u2026\u2014\u2013"
ENGLISH_STOP = {"the", "is", "are", "to", "of", "and", "in", "you", "was", "that", "this", "it", "for"}
# Explanation vocabulary that signals a rule (mutation, government, agreement...).
RULE_WORDS = re.compile(
    r"lenit|eclips|mutat|soft|aspirate|nasal|prothe|article|genitive|dative|"
    r"nominative|vocative|agree|gender|feminine|masculine|\bafter\b|\bbefore\b|follow|"
    r"\btakes?\b|requires?|governs?|particle|verbal noun|verbal adjective|vowel|plural|"
    r"singular|ending|preposition|negative|copula|word order|relative|conjunction|"
    r"irregular|dependent|independent|impersonal|participle|comparative|unchanged|"
    r"infinitive|emphatic|linker",
    re.I,
)
# A rule that governs the choice (used for same-stem inflection and closed-class swaps).
GOVERNED = re.compile(
    r"\b(after|before|follows?|followed|requires?|governs?|needs|agree\w*|genitive|dative|nominative|"
    r"verbal (noun|adjective)|imperative|addressed|particle|linker)\b",
    re.I,
)
# Explanation names a mutation or a mutation-like prefix.
MUTATION_WORDS = re.compile(r"lenit|eclips|mutat|soft|aspirat|nasal|prothe|\bt-|\bh-|\bn-|\bd'", re.I)
# Choices decided by meaning (a different word or person gives a valid sentence).
MEANING_WORDS = re.compile(
    r"\bmeans?\b|\bmeaning\b|literally|stands? for|translates?|\bwould mean\b|"
    r"\bfor (me|you|him|her|us|them)\b|first person|second person|third person|"
    r"\u201c(we|I|you|he|she|they)\u201d|\"(we|I|you|he|she|they)\"|'(we|I|you|he|she|they)'|"
    r"\bEnglish\b|translat|\bthe subject (is|are)\b|\bsubject is\b|"
    r"^\s*['\u2018\u201c\"]",  # explanation opens with an English gloss, e.g. "'Her' becomes a"
    re.I,
)
# Choices decided by tense, aspect or time words, or by register: valid either way.
TENSE_WORDS = re.compile(
    r"\b(past|present|future|conditional|habitual|yesterday|tomorrow|now|today|will|would|"
    r"literary|formal|colloquial|register|spoken|written|dialect|northern|southern)\b",
    re.I,
)
# Instruction text that leaks into an extracted sentence.
TEMPLATE_JUNK = re.compile(
    r"\b(or|and|the|of|with|Choose|Complete|Fill|Pick|Select|Which|Hint|form|sentence)\b|[\u2192()=:\u2014\u2013\"\u201c\u201d]|[.?!]\s+[A-Z\u00c0-\u00de]"
)

# Closed-class words (letters only, no diacritics): articles, particles, prepositions,
# conjunctions, possessives and be-forms that carry no tense or person. A swap inside
# this set is decided by a rule, not by the English gloss.
FUNCTION_WORDS = {
    "irish": "a an ar as de den do don faoi go gur i in is le leis ag chun mar na sa san sna ná ní níor nár nach "
    "ó ón thar trí roimh idir um os os cionn gan ach agus nó nuair má dá mura sula ós mo do ár bhur a "
    "ba bu nó seo sin siúd",
    "welsh": "a ag â ac am ar at gan er heb hyd i o tan tua wrth gyda gyda'r yn y yr 'r na nad nac ni nid ond neu "
    "os pan bod fod mai taw mae sydd sy fy dy ei ein eich eu fe mi fel ym yng",
    "scots-gaelic": "a a' an am ann air aig ri ris le leis do dha de bho o à gu gun gur gum nach nan nam cha chan "
    "ach agus no na mar mu mun ma nuair airson eadar fo thar tro mo do ar bhur tha bi is bu bheil eil an",
    "manx": "ny y yn er ec ayns da dy dys jeh lesh voish rish fo my as agh cha nagh nel vel va",
    "breton": "a e en an ar al ur ul un da war gant eus evit dre ez ne ket n' ho hor ma ha hag pe o",
    "cornish": "ow yn a an y dhe war rag gans orth dhyworth hag ha ny nyns na ev ow",
}


def function_words(language: str) -> set[str]:
    return {letters_only(token) for token in FUNCTION_WORDS[language].split()}


def snake(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "unknown"


def squash(text: str) -> str:
    """Collapse every whitespace run (including no-break spaces) to one space."""
    return re.sub(r"\s+", " ", text).strip()


def strip_edge(word: str) -> str:
    return word.strip(EDGE_PUNCT)


def word_count(text: str) -> int:
    return len(text.split())


def short_id(*parts: str) -> str:
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:10]


def plain(text: str) -> str:
    """Drop ``{...}`` markup braces from app feedback text; nothing else changes."""
    return text.replace("{", "").replace("}", "").strip()


def split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+(?=[A-Z\u201c\"'])", text) if part.strip()]


def looks_english(sentence: str) -> bool:
    tokens = re.findall(r"[a-z']+", sentence.lower())
    return sum(1 for token in tokens if token in ENGLISH_STOP) >= 2


def letters_only(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    return re.sub(r"[^a-z]", "", "".join(ch for ch in text if not unicodedata.combining(ch)))


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


GOIDELIC = {"irish", "scots-gaelic", "manx"}
ECLIPSIS = {"mb", "gc", "nd", "ng", "bp", "dt", "bf"}
# Brythonic initials -> radical consonants they can derive from (soft, nasal, aspirate mutation).
BRYTHONIC_INITIALS = [
    ("ngh", ["c"]), ("mh", ["p"]), ("nh", ["t"]), ("ph", ["p"]), ("th", ["t"]), ("ch", ["c"]),
    ("dd", ["d", "dd"]), ("ng", ["g"]), ("ll", ["ll"]), ("rh", ["rh"]), ("gw", ["gw"]),
    ("l", ["l", "ll", "gl"]), ("r", ["r", "rh", "gr"]), ("w", ["w", "gw"]), ("g", ["g", "c"]),
    ("b", ["b", "p"]), ("d", ["d", "t"]), ("f", ["f", "b", "m"]), ("m", ["m", "b"]), ("n", ["n", "d"]),
]


def radicals(language: str, word: str) -> set[str]:
    """Unmutated spellings a word could come from (itself included)."""
    w = word.casefold().replace("\u2019", "'")
    if language in GOIDELIC:
        w = re.sub(r"^(d'|b'|m'|t-|n-|h-)", "", w)
        w = letters_only(w)
        out = {w}
        if len(w) > 2 and w[1] == "h":
            out.add(w[0] + w[2:])
        for form in list(out):
            if form[:2] in ECLIPSIS and len(form) > 3:
                out.add(form[1:])
            if form[:2] == "ts" or (form[:1] in "hn" and form[1:2] in "aeiou"):
                out.add(form[1:])
        return out
    w = letters_only(w)
    out = {w}
    for prefix, rads in BRYTHONIC_INITIALS:
        if w.startswith(prefix):
            out |= {rad + w[len(prefix) :] for rad in rads}
            break
    else:
        if w[:1] in "aeiou":
            out |= {"g" + w}
        if w[:1] == "h" and w[1:2] in "aeiou":
            out.add(w[1:])
    return out


def mutation_only(language: str, a: str, b: str) -> bool:
    """True when the two forms differ only by initial mutation (or t-, h-, n-, d' prefix)."""
    ta, tb = a.split(), b.split()
    if len(ta) != len(tb):
        return False
    differs = False
    for x, y in zip(ta, tb):
        if letters_only(x) == letters_only(y):
            continue
        shared = radicals(language, x) & radicals(language, y)
        if not any(len(item) >= 3 for item in shared):
            return False
        differs = True
    return differs


def same_stem(language: str, a: str, b: str) -> bool:
    """True when two forms look like inflections or mutations of one word.

    Per word: a shared radical (mutation), or the same radical initial letter
    plus a long shared stem. Different initial letters are different words.
    """
    ta, tb = a.split(), b.split()
    if len(ta) != len(tb):
        return False
    for x, y in zip(ta, tb):
        rx, ry = radicals(language, x), radicals(language, y)
        if rx & ry:
            continue
        ok = False
        for u in rx:
            for v in ry:
                if not u or not v or u[0] != v[0]:
                    continue
                prefix = 0
                for cu, cv in zip(u, v):
                    if cu != cv:
                        break
                    prefix += 1
                if (prefix >= 3 and prefix >= 0.6 * min(len(u), len(v))) or (
                    min(len(u), len(v)) >= 4 and levenshtein(u, v) <= 2
                ):
                    ok = True
        if not ok:
            return False
    return True


def is_grammatical_pair(language: str, answer: str, distractor: str, explanation: str) -> tuple[bool, str]:
    """Keep only rule-governed distractors. Returns (keep, reason).

    - mutation-only (initial consonant change, t-, h-, d'): ungrammatical wherever the rule applies;
    - same-stem inflection (case, gender, verbal adjective, ...): kept only when the explanation gives a
      rule and no tense/time/register cue, because tense and person are chosen by meaning;
    - closed-class swap (particle, preposition, article, possessive): same conditions.
    Every pair is dropped when the explanation rests on word meaning.
    """
    text = explanation or ""
    if MEANING_WORDS.search(text):
        return False, "meaning-dependent"
    if not RULE_WORDS.search(text):
        return False, "no-rule-in-explanation"
    if mutation_only(language, answer, distractor) and MUTATION_WORDS.search(text):
        return True, "mutation-only"
    if TENSE_WORDS.search(text):
        return False, "tense-or-register-cue"
    if not GOVERNED.search(text):
        return False, "no-governing-rule"
    if same_stem(language, answer, distractor):
        return True, "same-stem-inflection"
    closed = function_words(language)
    tokens = [letters_only(token) for token in (answer + " " + distractor).split()]
    if all(token in closed for token in tokens):
        return True, "closed-class-swap"
    return False, "unrelated-word"


# ----------------------------------------------------------------- span logic


def token_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def minimal_char_edit(learner: str, gold: str) -> tuple[str, str]:
    """Prefix/suffix-trimmed char edit; widened by one char when one side is empty."""
    prefix = 0
    limit = min(len(learner), len(gold))
    while prefix < limit and learner[prefix] == gold[prefix]:
        prefix += 1
    suffix = 0
    while (
        suffix < limit - prefix
        and learner[len(learner) - 1 - suffix] == gold[len(gold) - 1 - suffix]
    ):
        suffix += 1
    a = learner[prefix : len(learner) - suffix]
    b = gold[prefix : len(gold) - suffix]
    if not a or not b:
        if prefix > 0:
            a, b = learner[prefix - 1] + a, gold[prefix - 1] + b
        elif suffix > 0:
            a, b = a + learner[len(learner) - suffix], b + gold[len(gold) - suffix]
    return a, b


def _window_pair(
    learner: str, gold: str, lt: list[tuple[int, int]], gt: list[tuple[int, int]], lo: int, hi: int, glo: int, ghi: int
) -> tuple[str, str]:
    """Learner/gold text over a word window, minus punctuation shared at both outer edges."""
    span = learner[lt[lo][0] : lt[hi - 1][1]]
    corr = gold[gt[glo][0] : gt[ghi - 1][1]]
    lead = 0
    while lead < min(len(span), len(corr)) - 1 and span[lead] == corr[lead] and span[lead] in EDGE_PUNCT:
        lead += 1
    trail = 0
    while (
        trail < min(len(span), len(corr)) - lead - 1
        and span[-1 - trail] == corr[-1 - trail]
        and span[-1 - trail] in EDGE_PUNCT
    ):
        trail += 1
    return span[lead : len(span) - trail], corr[lead : len(corr) - trail]


def edit_spans(learner: str, gold: str) -> dict[str, Any] | None:
    """Locate the single edit between learner and gold sentences.

    The primary span/correction is the whole-word window around the edit,
    widened with neighbouring words until the span occurs once in the learner
    sentence. ``accept_spans``/``accept_corrections`` are parallel lists: the
    primary pair, the unwidened whole-word pair and the minimal character edit.
    """
    lt, gt = token_spans(learner), token_spans(gold)
    lw = [learner[s:e] for s, e in lt]
    gw = [gold[s:e] for s, e in gt]
    i = 0
    while i < min(len(lw), len(gw)) and lw[i] == gw[i]:
        i += 1
    j = 0
    while j < min(len(lw), len(gw)) - i and lw[-1 - j] == gw[-1 - j]:
        j += 1
    lo, hi = i, len(lw) - j
    glo, ghi = i, len(gw) - j
    if lo >= hi and glo >= ghi:
        return None
    if lo == hi or glo == ghi:  # a whole word added or removed: anchor on a neighbour
        if lo > 0:
            lo, glo = lo - 1, glo - 1
        elif hi < len(lw):
            hi, ghi = hi + 1, ghi + 1
        else:
            return None
    word_span, word_corr = _window_pair(learner, gold, lt, gt, lo, hi, glo, ghi)
    if not word_span or not word_corr:
        return None
    pairs = [(word_span, word_corr)]
    char_a, char_b = minimal_char_edit(word_span, word_corr)
    if char_a and char_b:
        pairs.append((char_a, char_b))
    wlo, whi, wglo, wghi = lo, hi, glo, ghi
    span, corr = word_span, word_corr
    while learner.count(span) != 1:
        if whi < len(lw):
            whi, wghi = whi + 1, wghi + 1
        elif wlo > 0:
            wlo, wglo = wlo - 1, wglo - 1
        else:
            return None
        span, corr = _window_pair(learner, gold, lt, gt, wlo, whi, wglo, wghi)
    pairs.insert(0, (span, corr))
    ordered: list[tuple[str, str]] = []
    for pair in pairs:
        if pair not in ordered:
            ordered.append(pair)
    return {
        "error_span": span,
        "correction": corr,
        "accept_spans": [pair[0] for pair in ordered],
        "accept_corrections": [pair[1] for pair in ordered],
    }


def check_single_edit(learner: str, gold: str, spans: dict[str, Any]) -> None:
    span, corr = spans["error_span"], spans["correction"]
    assert learner.count(span) == 1, (learner, span)
    index = learner.index(span)
    rebuilt = learner[:index] + corr + learner[index + len(span) :]
    assert rebuilt == gold, (learner, gold, span, corr, rebuilt)
    assert norm(learner) != norm(gold), (learner, gold)
    for a, b in zip(spans["accept_spans"], spans["accept_corrections"]):
        if learner.count(a) == 1:
            k = learner.index(a)
            assert learner[:k] + b + learner[k + len(a) :] == gold, (learner, gold, a, b)


# ------------------------------------------------------------- exercise parsing


def extract_template(prompt: str) -> str | None:
    """Target-language sentence containing exactly one blank, taken from a cloze prompt."""
    blanks = list(BLANK.finditer(prompt))
    if len(blanks) != 1:
        return None
    pos = blanks[0].start()
    region_start = 0
    for m in re.finditer(r":\s+", prompt[:pos]):
        region_start = m.end()
    region = prompt[region_start:].strip()
    if region and region[0] in QUOTES:
        closers = QUOTES[region[0]]
        best = -1
        for closer in closers:
            for m in re.finditer(re.escape(closer) + r"(?=\s*(\(|$|\)))", region[1:]):
                best = max(best, m.start())
        if best < 0:
            return None
        sentence = region[1 : best + 1]
    else:
        # sentence runs up to a trailing parenthetical gloss, if any
        m = re.search(r"\s+\([^()]*(\([^()]*\))?[^()]*\)\s*$", region)
        sentence = region[: m.start()] if m else region
        sentence = sentence.strip()
        if sentence[:1] in QUOTES or sentence[-1:] in "\"'\u201d\u2019":
            if sentence[:1] not in QUOTES:
                return None
    sentence = sentence.strip()
    if len(BLANK.findall(sentence)) != 1 or "..." in sentence or "\u2026" in sentence:
        return None
    if TEMPLATE_JUNK.search(sentence):
        return None
    if looks_english(sentence.replace("_", " ")):
        return None
    if not MIN_WORDS <= word_count(sentence) <= MAX_WORDS:
        return None
    return sentence


def fill(template: str, value: str, capital_from: str | None = None) -> str:
    match = BLANK.search(template)
    assert match
    if capital_from and match.start() == 0 and capital_from[:1].isupper() and value[:1].islower():
        value = value[:1].upper() + value[1:]
    return template[: match.start()] + value + template[match.end() :]


def explanation_points(texts: list[str], distractor: str) -> list[str]:
    sentences: list[str] = []
    for text in texts:
        sentences.extend(split_sentences(text))
    sentences = [s for s in sentences if s]
    if not sentences:
        return []
    key = norm(distractor)
    mentions = [s for s in sentences if key and key in norm(s)]
    chosen = unique(([sentences[0]] if sentences else []) + mentions[:1])
    order = {s: i for i, s in enumerate(sentences)}
    return sorted(chosen, key=lambda s: order[s])[:2]


def lesson_status(lesson: dict[str, Any], file_meta: dict[str, Any]) -> tuple[str, str]:
    meta = lesson.get("_meta") or {}
    for field in ("reviewStatus", "candidateStatus"):
        if meta.get(field):
            return str(meta[field]), f"lesson._meta.{field}"
    native = meta.get("nativeReview")
    if isinstance(native, dict) and native.get("status"):
        return str(native["status"]), "lesson._meta.nativeReview.status"
    if file_meta.get("reviewStatus"):
        return str(file_meta["reviewStatus"]), "_meta.reviewStatus"
    return "none-recorded", "none"


def load_exercises(language: str) -> list[dict[str, Any]]:
    """Every cloze exercise with a correct fill and its wrong options."""
    path = BLAS_CONTENT / language / "grammar-lessons.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    file_meta = data.get("_meta") or {}
    out: list[dict[str, Any]] = []
    for lesson in sorted(data["lessons"], key=lambda x: x["id"]):
        status, status_field = lesson_status(lesson, file_meta)
        for si, section in enumerate(lesson.get("sections", [])):
            if section.get("type") != "drill":
                continue
            for di, drill in enumerate(section.get("drills", [])):
                template = extract_template(drill.get("prompt", ""))
                options = drill.get("options") or []
                answer = drill.get("expectedAnswer")
                if not template or not options or not answer:
                    continue
                accepted = list(drill.get("acceptedAnswers") or [])
                for value in (drill.get("expectedAnswers") or {}).values():
                    accepted.append(value)
                for values in (drill.get("acceptedAnswerSets") or {}).values():
                    accepted.extend(values)
                explanation = plain(drill.get("explanation") or (drill.get("explanations") or {}).get("en") or "")
                out.append(
                    {
                        "kind": "grammar-lessons",
                        "key": f"{lesson['id']}/sections[{si}]/drills[{di}]",
                        "file": path,
                        "template": template,
                        "answer": answer,
                        "accepted": accepted,
                        "options": options,
                        "explanation": explanation,
                        "feedback": [],
                        "category": lesson.get("category") or "unknown",
                        "cefr": lesson.get("cefrLevel") if lesson.get("cefrLevel") in CEFR else None,
                        "status": status,
                        "status_field": status_field,
                    }
                )
    return out


def load_choose_screens(language: str) -> list[dict[str, Any]]:
    lessons = {
        x["id"]: x
        for x in json.loads((BLAS_CONTENT / language / "grammar-lessons.json").read_text(encoding="utf-8"))["lessons"]
    }
    path = BLAS_CONTENT / language / "lesson-screens.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    for lesson_id in sorted(data["lessons"]):
        entry = data["lessons"][lesson_id]
        parent = lessons.get(lesson_id, {})
        for index, screen in enumerate(entry.get("screens", [])):
            if screen.get("kind") != "choose":
                continue
            answer_sentence = screen.get("answer") or ""
            blank = screen.get("blank") or ""
            choices = screen.get("choices") or []
            matches = list(re.finditer(r"(?<!\w)" + re.escape(blank) + r"(?!\w)", answer_sentence)) if blank else []
            if len(matches) != 1 or not MIN_WORDS <= word_count(answer_sentence) <= MAX_WORDS:
                continue
            m = matches[0]
            template = answer_sentence[: m.start()] + "___" + answer_sentence[m.end() :]
            wrong = (screen.get("wrong") or {}).get("en") or ""
            correct = (screen.get("correct") or {}).get("en") or ""
            out.append(
                {
                    "kind": "lesson-screens",
                    "key": f"{lesson_id}/screens[{index}]",
                    "file": path,
                    "template": template,
                    "answer": blank,
                    "accepted": [],
                    "options": choices,
                    "explanation": plain(wrong),
                    "feedback": [plain(wrong)],
                    "gold_sentence": answer_sentence,
                    "category": parent.get("category") or "unknown",
                    "cefr": parent.get("cefrLevel") if parent.get("cefrLevel") in CEFR else None,
                    "status": str(entry.get("status") or "none-recorded"),
                    "status_field": "lessons.<id>.status",
                }
            )
    return out


def usable_gold(exercise: dict[str, Any]) -> str | None:
    if exercise["answer"] not in exercise["options"] and norm(exercise["answer"]) not in {
        norm(o) for o in exercise["options"]
    }:
        return None
    if len(exercise["answer"].split()) > 3:
        return None
    gold = exercise.get("gold_sentence") or fill(exercise["template"], exercise["answer"])
    if not MIN_WORDS <= word_count(gold) <= MAX_WORDS:
        return None
    return gold


def distractor_candidates(language: str, exercise: dict[str, Any], gold: str, stats: Counter) -> list[dict[str, Any]]:
    accepted = {norm(a) for a in exercise["accepted"]} | {norm(exercise["answer"])}
    out = []
    for option in unique(exercise["options"]):
        if norm(option) == norm(exercise["answer"]):
            continue
        if norm(option) in accepted:
            stats["distractor-in-accepted-answers"] += 1
            continue
        if len(option.split()) > 3:
            stats["distractor-too-long"] += 1
            continue
        learner = fill(exercise["template"], option, capital_from=exercise["answer"])
        if norm(learner) == norm(gold):
            stats["distractor-equals-answer-after-norm"] += 1
            continue
        keep, reason = is_grammatical_pair(language, exercise["answer"], option, exercise["explanation"])
        if not keep:
            stats[f"filtered:{reason}"] += 1
            continue
        stats[f"kept:{reason}"] += 1
        out.append({"learner": learner, "distractor": option, "reason": reason})
    return out


def tutor_prompt(language: str, sentence: str) -> str:
    return PROMPT.format(name=LANGUAGE_NAMES[language], sentence=sentence)


def tutor_item(
    *,
    language: str,
    item_id: str,
    learner: str,
    gold: str,
    origin: str,
    phenomenon: str,
    cefr: str | None,
    source: str,
    source_id: str,
    source_path: Path,
    licence: str,
    evidence: str,
    points: list[str],
    extra: dict[str, Any],
) -> dict[str, Any]:
    learner, gold = squash(learner), squash(gold)
    if origin == "none":
        spans = {"error_span": "", "correction": "", "accept_spans": [], "accept_corrections": []}
        assert learner == gold
        has_error = False
    else:
        spans = edit_spans(learner, gold)
        assert spans is not None, (learner, gold)
        check_single_edit(learner, gold, spans)
        has_error = True
    assert MIN_WORDS <= word_count(learner) <= MAX_WORDS, learner
    return make_item(
        id=item_id,
        prompt=tutor_prompt(language, learner),
        target=gold,
        suite=SUITE,
        test=TEST,
        scoring="tutor",
        language=language,
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
        error_span=spans["error_span"],
        correction=spans["correction"],
        accept_spans=spans["accept_spans"],
        accept_corrections=spans["accept_corrections"],
        acceptable_sentences=[gold],
        explanation_points=points,
        real_learner_error=False,
        error_origin=origin,
        **extra,
    )


# ---------------------------------------------------------------- item builders


def exercise_items(language: str, stats: Counter) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(error items, exercise records usable for clean items)."""
    exercises = load_exercises(language) + load_choose_screens(language)
    stats["exercises_with_blank"] = len(exercises)
    rng = random.Random(f"{SEED}-{language}-distractor")
    errors: list[dict[str, Any]] = []
    cleans: list[dict[str, Any]] = []
    seen_gold: set[str] = set()
    for ex in exercises:
        gold = usable_gold(ex)
        if gold is None:
            stats["exercise-unusable-gold"] += 1
            continue
        key = norm(gold)
        if key in seen_gold:
            stats["exercise-duplicate-gold"] += 1
            continue
        seen_gold.add(key)
        ex["gold"] = gold
        cleans.append(ex)
        cands = distractor_candidates(language, ex, gold, stats)
        if not cands:
            continue
        pick = cands[rng.randrange(len(cands))]
        spans_ok = edit_spans(pick["learner"], gold)
        if spans_ok is None:
            stats["exercise-no-single-edit-span"] += 1
            continue
        feedback = ex["feedback"] or [ex["explanation"]]
        points = explanation_points(feedback, pick["distractor"])
        errors.append(
            tutor_item(
                language=language,
                item_id=f"blas-tutor-{language}-exd-{short_id(ex['key'], pick['distractor'])}",
                learner=pick["learner"],
                gold=gold,
                origin="exercise-distractor",
                phenomenon=snake(ex["category"]),
                cefr=ex["cefr"],
                source=f"blas-{ex['kind']}",
                source_id=f"{ex['kind']}.json#{ex['key']}",
                source_path=ex["file"],
                licence="private-blas",
                evidence="distractor-derived-unverified",
                points=points,
                extra={
                    "source_status": ex["status"],
                    "source_status_field": ex["status_field"],
                    "distractor": pick["distractor"],
                    "answer_fill": ex["answer"],
                    "accepted_answers": unique([ex["answer"], *ex["accepted"]]),
                    "distractor_filter": pick["reason"],
                },
            )
        )
    stats["exercise-error-candidates"] = len(errors)
    return errors, cleans


def app_variant_items(language: str, stats: Counter) -> list[dict[str, Any]]:
    if language != "irish":
        return []
    path = BLAS_CONTENT / "irish" / "sentences.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    for sentence in sorted(data["sentences"], key=lambda s: s["id"]):
        status = str(sentence.get("verificationStatus") or "")
        if not status.startswith("approved"):
            continue
        source = sentence.get("source")
        if source not in ("sentence-bank", "tatoeba"):
            stats["app-variant-source-skipped"] += 1
            continue
        gold = sentence["native"]
        if not MIN_WORDS <= word_count(gold) <= MAX_WORDS:
            continue
        for number, variant in enumerate(sentence.get("errorVariants") or []):
            learner = variant.get("errorSentence")
            if not learner or edit_spans(learner, gold) is None:
                stats["app-variant-no-single-edit"] += 1
                continue
            if len(token_spans(learner)) != len(token_spans(gold)):
                stats["app-variant-word-count-differs"] += 1
                continue
            if variant.get("correction") and variant["correction"] not in gold:
                stats["app-variant-correction-not-in-gold"] += 1
                continue
            explanation = variant.get("explanation") or ""
            out.append(
                tutor_item(
                    language=language,
                    item_id=f"blas-tutor-irish-var-{short_id(sentence['id'], str(number))}",
                    learner=learner,
                    gold=gold,
                    origin="app-error-variant",
                    phenomenon=snake(variant.get("errorType") or "mutation"),
                    cefr=sentence.get("cefrLevel") if sentence.get("cefrLevel") in CEFR else None,
                    source="blas-sentences",
                    source_id=f"sentences.json#{sentence['id']}/errorVariants[{number}]",
                    source_path=path,
                    licence="private-blas",
                    evidence="blas-app-only",
                    points=split_sentences(explanation)[:2],
                    extra={
                        "source_status": status,
                        "source_status_field": "sentences[].verificationStatus",
                        "upstream_source": source,
                        "error_type": variant.get("errorType"),
                    },
                )
            )
    stats["app-variant-candidates"] = len(out)
    return out


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def corpus_vocab(language: str) -> set[str]:
    vocab: set[str] = set()
    for name in ("clean", "error"):
        for row in read_jsonl(SEALED / f"{language}-{name}.jsonl"):
            text = row.get("correction") if name == "error" else row.get("text")
            vocab.update(norm(strip_edge(token)) for token in (text or "").split())
    for forms in kaikki_forms(language).values():
        vocab.update(forms)
    return vocab


def typo_items(language: str, stats: Counter) -> list[dict[str, Any]]:
    path = SEALED / f"{language}-error.jsonl"
    vocab = corpus_vocab(language)
    out: list[dict[str, Any]] = []
    for row in sorted(read_jsonl(path), key=lambda r: r["id"]):
        learner, gold = row["text"], row["correction"]
        if not MIN_WORDS <= word_count(gold) <= MAX_WORDS or "\n" in gold:
            stats["typo-length"] += 1
            continue
        lw, gw = learner.split(), gold.split()
        if len(lw) != len(gw) or sum(1 for a, b in zip(lw, gw) if a != b) != 1:
            stats["typo-not-single-word"] += 1
            continue
        bad = next(a for a, b in zip(lw, gw) if a != b)
        if norm(strip_edge(bad)) in vocab:
            stats["typo-token-is-a-real-word"] += 1
            continue
        if edit_spans(learner, gold) is None:
            stats["typo-no-span"] += 1
            continue
        if row.get("license") != "CC BY-SA 4.0":
            stats["typo-licence-not-ccbysa"] += 1
            continue
        out.append(
            tutor_item(
                language=language,
                item_id=f"blas-tutor-{language}-typo-{short_id(row['id'])}",
                learner=learner,
                gold=gold,
                origin="mechanical-typo",
                phenomenon="orthography_doubled_letter",
                cefr=None,
                source="sealed-celtic-clean-600-v3",
                source_id=f"{language}-error.jsonl#{row['id']}",
                source_path=path,
                licence="CC BY-SA 4.0",
                evidence="planted-typo",
                points=[],
                extra={
                    "source_status": str(row.get("reviewStatus")),
                    "source_status_field": "reviewStatus",
                    "source_url": row.get("sourceUrl"),
                    "error_family": row.get("errorFamily"),
                },
            )
        )
    stats["typo-candidates"] = len(out)
    return out


def app_clean_items(language: str, count: int, taken: set[str], stats: Counter) -> list[dict[str, Any]]:
    """Clean sentences from the app's sentence bank (approved, unblocked, no quality flags)."""
    path = BLAS_CONTENT / language / "sentences.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    pool: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sentence in sorted(data["sentences"], key=lambda r: r["id"]):
        text = squash(sentence.get("native") or "")
        status = str(sentence.get("verificationStatus") or "")
        if (
            not status.startswith("approved")
            or sentence.get("_blocked")
            or sentence.get("qualityFlags")
            or not MIN_WORDS <= word_count(text) <= MAX_WORDS
        ):
            stats["app-clean-rejected"] += 1
            continue
        key = norm(text)
        if key in taken or key in seen:
            stats["app-clean-duplicate-or-used"] += 1
            continue
        seen.add(key)
        sentence = {**sentence, "native": text}
        pool.append(sentence)
    stats["app-clean-pool"] = len(pool)
    items = [
        tutor_item(
            language=language,
            item_id=f"blas-tutor-{language}-clean-sent-{short_id(row['id'])}",
            learner=row["native"],
            gold=row["native"],
            origin="none",
            phenomenon="clean",
            cefr=row.get("cefrLevel") if row.get("cefrLevel") in CEFR else None,
            source="blas-sentences",
            source_id=f"sentences.json#{row['id']}",
            source_path=path,
            licence="private-blas",
            evidence="blas-app-only",
            points=[],
            extra={
                "source_status": str(row.get("verificationStatus")),
                "source_status_field": "sentences[].verificationStatus",
                "verification_status": str(row.get("verificationStatus")),
                "upstream_source": row.get("source") or ",".join(x.get("name", "") for x in row.get("sources") or []),
            },
        )
        for row in pool
    ]
    return stratified_sample(items, count, keys=("language", "cefr"))


def exercise_clean_items(language: str, pool: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    items = []
    for ex in pool:
        items.append(
            tutor_item(
                language=language,
                item_id=f"blas-tutor-{language}-clean-ex-{short_id(ex['key'])}",
                learner=ex["gold"],
                gold=ex["gold"],
                origin="none",
                phenomenon=snake(ex["category"]),
                cefr=ex["cefr"],
                source=f"blas-{ex['kind']}",
                source_id=f"{ex['kind']}.json#{ex['key']}",
                source_path=ex["file"],
                licence="private-blas",
                evidence="blas-app-only",
                points=[],
                extra={
                    "source_status": ex["status"],
                    "source_status_field": ex["status_field"],
                    "answer_fill": ex["answer"],
                },
            )
        )
    return stratified_sample(items, count)


# ------------------------------------------------------------------------ main


def build_language(language: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stats: Counter = Counter()
    ex_errors, ex_pool = exercise_items(language, stats)
    chosen = stratified_sample(ex_errors, ERRORS_PER_LANGUAGE)
    used_keys = {item["metadata"]["source_id"] for item in chosen}
    used_gold = {norm(item["target"]) for item in chosen}
    sources_used = {"exercise-distractor": len(chosen)}

    app_candidates = app_variant_items(language, stats)
    typo_candidates = typo_items(language, stats)
    shortfall_before_fill = max(0, ERRORS_PER_LANGUAGE - len(chosen))

    app_taken: list[dict[str, Any]] = []
    if len(chosen) < ERRORS_PER_LANGUAGE and app_candidates:
        need = min(CAP_APP_VARIANT, ERRORS_PER_LANGUAGE - len(chosen))
        app_taken = stratified_sample(
            [i for i in app_candidates if norm(i["target"]) not in used_gold], need, keys=("language", "phenomenon")
        )
        chosen += app_taken
        used_gold |= {norm(i["target"]) for i in app_taken}
    sources_used["app-error-variant"] = len(app_taken)

    typo_taken: list[dict[str, Any]] = []
    if len(chosen) < ERRORS_PER_LANGUAGE:
        need = min(CAP_TYPO, ERRORS_PER_LANGUAGE - len(chosen))
        typo_taken = stratified_sample(
            [i for i in typo_candidates if norm(i["target"]) not in used_gold], need, keys=("language", "phenomenon")
        )
        chosen += typo_taken
        used_gold |= {norm(i["target"]) for i in typo_taken}
    sources_used["mechanical-typo"] = len(typo_taken)

    n_errors = len(chosen)
    n_clean = CLEAN_PER_LANGUAGE
    n_sentences = n_clean // 2
    n_exercise = n_clean - n_sentences
    exercise_pool = [
        ex
        for ex in ex_pool
        if f"{ex['kind']}.json#{ex['key']}" not in used_keys and norm(ex["gold"]) not in used_gold
    ]
    clean_ex = exercise_clean_items(language, exercise_pool, n_exercise)
    used_gold |= {norm(i["target"]) for i in clean_ex}
    clean_sent = app_clean_items(language, n_clean - len(clean_ex), used_gold, stats)
    clean = clean_ex + clean_sent
    if len(clean) < n_clean:  # sentence pool ran short: top up from unused exercise fills
        used_ex = {i["metadata"]["source_id"] for i in clean_ex}
        rest = [
            ex
            for ex in exercise_pool
            if f"{ex['kind']}.json#{ex['key']}" not in used_ex and norm(ex["gold"]) not in {norm(i["target"]) for i in clean}
        ]
        extra_ex = exercise_clean_items(language, rest, n_clean - len(clean))
        clean_ex += extra_ex
        clean += extra_ex

    items = chosen + clean
    report = {
        "errors_built": n_errors,
        "errors_target": ERRORS_PER_LANGUAGE,
        "error_shortfall": ERRORS_PER_LANGUAGE - n_errors,
        "clean_built": len(clean),
        "clean_from_exercises": len(clean_ex),
        "clean_from_app_sentences": len(clean_sent),
        "clean_target": n_clean,
        "clean_shortfall": n_clean - len(clean),
        "usable_cloze_exercises": stats["exercises_with_blank"],
        "error_candidates": {
            "exercise-distractor": len(ex_errors),
            "app-error-variant": len(app_candidates),
            "mechanical-typo": len(typo_candidates),
        },
        "errors_by_source_used": sources_used,
        "typo_available_beyond_cap_not_used": max(0, len(typo_candidates) - len(typo_taken))
        if shortfall_before_fill
        else len(typo_candidates),
        "filter_stats": dict(sorted(stats.items())),
    }
    return items, report


def main() -> None:
    items: list[dict[str, Any]] = []
    per_language: dict[str, Any] = {}
    for language in LANGUAGES:
        built, report = build_language(language)
        items.extend(built)
        per_language[language] = report
    excluded: dict[str, Any] = {}
    for language in EXCLUDED_LANGUAGES:
        _, found = build_language(language)  # counted only; no item is written
        excluded[language] = {
            "reason": (
                "Too few rule-governed exercise distractors to build a usable error sample: the 40-item target "
                "could only be approached with mechanical doubled-letter typos, capped at 8, which is not a usable "
                "sample. Removed from the test."
            ),
            "usable_cloze_exercises": found["usable_cloze_exercises"],
            "candidates": found["error_candidates"],
            "typo_candidates_total": found["error_candidates"]["mechanical-typo"],
            "typo_cap": CAP_TYPO,
            "errors_that_would_have_been_built": found["errors_built"],
            "errors_target": ERRORS_PER_LANGUAGE,
        }
    for item in items:
        meta = item["metadata"]
        if meta["error_origin"] == "exercise-distractor":
            blocked = {norm(a) for a in meta["accepted_answers"]} | {norm(meta["answer_fill"])}
            assert norm(meta["distractor"]) not in blocked, (item["id"], meta["distractor"])
            assert norm(meta["distractor"]) != norm(meta["answer_fill"]), item["id"]
            assert meta["evidence"] == "distractor-derived-unverified", item["id"]
        elif meta["error_origin"] == "mechanical-typo":
            assert meta["evidence"] == "planted-typo", item["id"]
    provenance = json.loads((SEALED / "provenance.json").read_text(encoding="utf-8"))
    counts = Counter(i["metadata"]["language"] for i in items)
    shortfalls = {
        language: {
            "errors": per_language[language]["error_shortfall"],
            "clean": per_language[language]["clean_shortfall"],
            "total": PER_LANGUAGE - counts[language],
        }
        for language in LANGUAGES
        if counts[language] < PER_LANGUAGE
    }
    by_origin = Counter(i["metadata"]["error_origin"] for i in items)
    by_lang_origin: dict[str, dict[str, int]] = defaultdict(dict)
    for language in LANGUAGES:
        by_lang_origin[language] = dict(
            sorted(Counter(i["metadata"]["error_origin"] for i in items if i["metadata"]["language"] == language).items())
        )
    report = {
        "target_per_language": PER_LANGUAGE,
        "errors_per_language_target": ERRORS_PER_LANGUAGE,
        "clean_per_language_target": CLEAN_PER_LANGUAGE,
        "caps": {"app-error-variant": CAP_APP_VARIANT, "mechanical-typo": CAP_TYPO},
        "excluded_languages": excluded,
        "by_error_origin": dict(sorted(by_origin.items())),
        "by_language_and_error_origin": dict(by_lang_origin),
        "by_has_error": dict(Counter(str(i["metadata"]["has_error"]) for i in items)),
        "shortfalls": shortfalls,
        "per_language": per_language,
        "typo_source_licence": {
            "provenance_license": provenance.get("license"),
            "licenseUrl": provenance.get("licenseUrl"),
            "provenance_file": home_relative(SEALED / "provenance.json"),
            "note": (
                "provenance.json rowCount/sha256 do not match the files on disk (it lists 600 clean and 0 error rows "
                "per language; disk has about 300 clean and 250 error rows). Each typo row carries its own "
                "license field 'CC BY-SA 4.0', which the build checks."
            ),
        },
        "residual_risk_note": (
            "The rate of exercise-distractor items whose distractor is also grammatical in the sentence is not "
            "known. A machine reading of 30 random items, not a reading by a speaker, found 2 (a genitive plural "
            "equal to the nominative plural, and a superlative where a comparative was gold). For 2 of 30 the "
            "95 percent interval is about 1 to 22 percent."
        ),
        "clean_sources": (
            "Half from correct fills of exercises not used for error items; half from sentences.json records with "
            "verificationStatus starting 'approved', no _blocked, empty qualityFlags, 4-30 words, not used elsewhere "
            "in this test. No Wikipedia clean sentences."
        ),
        "filter": (
            "Exercise distractors kept only when the explanation states a rule, does not rest on word meaning, "
            "tense or a person, and the distractor is a mutation-only or same-stem variant of the answer or both "
            "are closed-class words."
        ),
    }
    write_outputs(SUITE, TEST, items, report)


if __name__ == "__main__":
    main()
