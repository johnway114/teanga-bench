"""Build suites/blas/morphology.jsonl: closed-form inflection items from the Blas app content.

Test ``blas/morphology``, scoring ``accept_list``. Stdlib only, but ``scripts/_common.py``
needs nothing else either, so run it with::

    python3 scripts/build_blas_morphology.py

Source: ``~/Documents/blas/data/content/<language>/`` for irish, welsh, scots-gaelic, manx,
breton and cornish (private app content, licence ``private-blas``). Files used per language:
``declensions.json``, ``conjugations.json``, ``prepositional-pronouns.json``,
``numbers.json``, ``gender-practice.json``, ``copula-drills.json``, ``vocabulary.json`` (bare noun for gender practice) and ``item-difficulty.json``
(CEFR). ``mutation-rules.json`` is not read: it only guides the phenomenon names.

Phenomena (one per tense for verbs): ``noun_genitive``, ``noun_plural``, ``noun_vocative``,
``verb_<tense>``, ``prepositional_pronoun``, ``number_<kind>``, ``article_gender_mutation``,
``copula``.

Gold strings are copied from the source files, or derived by the rules documented next to
each builder (stripping a trailing subject pronoun, splitting ``a/b`` alternatives,
adding variants the record itself lists). Nothing is typed in by hand except the
exclusion tables that drop records the app itself marks wrong or disputed.

Skipped records: ``_blocked`` records, records with non-empty ``qualityFlags`` (no
record in these files has that field), gender-practice items with ``eligible: false``,
and AI-audit verdicts ``wrong``/``major`` (Cornish confidence below MEDIUM-HIGH).

Human review: ``human_checked`` is true only when a record has ``reviewStatus == "approved"``
or ``humanReviewed == true``. No record in the six languages has either field, so every
item is false. (``approved: true`` on Manx gender-practice ``alternatives`` is a per-variant
publishing flag, not a record-level human review, and is not used.)

Sampling: 60 items per language. Phenomenon counts come from ``stratified_sample`` over
phenomena (even spread, small phenomena give all they have). Inside a phenomenon the picks
are ``stratified_sample`` over CEFR, so the full difficulty range is kept. The candidate
pool prefers forms confirmed by BÚNaMo (Irish) or Kaikki (Irish, Manx, Cornish, Scottish
Gaelic) and, for nouns, entries linked to the app vocabulary (``wordId``); it falls back to
the remaining records when that pool is too small.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    BLAS_CONTENT,
    LANGUAGE_NAMES,
    LANGUAGES,
    SEED,
    home_relative,
    in_bunamo,
    kaikki_forms,
    load_json,
    make_item,
    norm,
    stratified_sample,
    unique,
    write_outputs,
)

SUITE = "blas"
TEST = "morphology"
PER_LANGUAGE = 60
LICENCE = "private-blas"
GLOSS_REJECT = re.compile(
    r"\b(superseded|obsolete|archaic|dated|alternative (form|spelling)|variant|misspelling|"
    r"nonstandard|non-standard|verbal noun of|plural of|inflection of|form of|abbreviation|"
    r"initialism|acronym|surname|given name|diminutive of|eye dialect|rare)\b",
    re.IGNORECASE,
)
STOP_TOKENS = {
    # articles and particles
    "an", "na", "a", "y", "yr", "r", "ar", "al", "am", "yn", "'n", "n",
    # subject pronouns that sit after a verb or inside a form
    "mé", "tú", "sé", "sí", "sibh", "siad", "muid", "mi", "thu", "e", "i", "iad", "sinn",
    "mee", "oo", "eh", "ee", "ad", "shin", "shiu",
}
PERSON_TEXT = {
    "1s": "1st person singular",
    "2s": "2nd person singular (one person addressed)",
    "3s": "3rd person singular",
    "3sm": "3rd person singular masculine",
    "3sf": "3rd person singular feminine",
    "1p": "1st person plural",
    "2p": "2nd person plural (several people addressed)",
    "3p": "3rd person plural",
    "autonomous": "autonomous (impersonal) form",
}
PERSON_TEXT_PP = {
    "1sg": "1st person singular",
    "2sg": "2nd person singular",
    "3sg_masc": "3rd person singular masculine",
    "3sg_fem": "3rd person singular feminine",
    "1pl": "1st person plural",
    "2pl": "2nd person plural",
    "3pl": "3rd person plural",
}
IRISH_PRONOUN = {"1s": "mé", "2s": "tú", "3s": "sé", "1p": "muid", "2p": "sibh", "3p": "siad"}
IRISH_PRONOUNS = set(IRISH_PRONOUN.values())
MANX_PRONOUN = {"1s": "mee", "2s": "oo", "3s": "eh", "1p": "shin", "2p": "shiu", "3p": "ad"}

# Records the app's own audit marks wrong or disputed, or where the record lists a second
# valid form that it does not store. Dropped, never "fixed" by hand.
NUMBER_EXCLUDE: dict[tuple[str, str, str], str] = {
    ("breton", "br-num-21", "cardinal"): "audit verdict wrong",
    ("breton", "br-num-21", "ordinal"): "audit verdict wrong",
    ("breton", "br-num-40", "ordinal"): "disputed vigesimal ordinal",
    ("breton", "br-num-60", "ordinal"): "disputed vigesimal ordinal",
    ("breton", "br-num-70", "ordinal"): "disputed vigesimal ordinal",
    ("breton", "br-num-80", "ordinal"): "disputed vigesimal ordinal",
    ("breton", "br-num-90", "ordinal"): "disputed vigesimal ordinal",
    ("cornish", "kw-num-2", "ordinal"): "audit: second attested ordinal 'eyl' not stored",
    ("cornish", "kw-num-4", "ordinal"): "audit verdict wrong",
    ("scots-gaelic", "gd-num-1", "ordinal"): "ordinal stored with article and lenition",
    ("scots-gaelic", "gd-num-30", "cardinal"): "audit verdict major",
    ("scots-gaelic", "gd-num-30", "ordinal"): "audit verdict major",
    ("scots-gaelic", "gd-num-6", "personal"): "audit: second attested form 'sèisear' not stored",
}

CONTENT = BLAS_CONTENT

EXCLUSIONS: Counter = Counter()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def content_path(language: str, name: str) -> Path:
    return CONTENT / language / f"{name}.json"


def band_for(score: float | None, bands: dict[str, list[float]]) -> str | None:
    if score is None:
        return None
    best: str | None = None
    for level, bounds in bands.items():
        if score >= bounds[0]:
            best = level
    return best


class Difficulty:
    def __init__(self, language: str) -> None:
        data = load_json(content_path(language, "item-difficulty"))
        self.items: dict[str, float] = data["items"]
        self.bands: dict[str, list[float]] = data["bands"]

    def lookup(self, key: str, fallback_level: str | None = None) -> tuple[str | None, float | None]:
        score = self.items.get(key)
        if score is not None:
            return band_for(score, self.bands), score
        return fallback_level, None


def review_flag(record: dict[str, Any]) -> bool:
    return record.get("reviewStatus") == "approved" or record.get("humanReviewed") is True


def blocked(record: dict[str, Any]) -> bool:
    if record.get("_blocked"):
        return True
    return bool(record.get("qualityFlags"))


def source_label(record: dict[str, Any]) -> str:
    """``blas-app`` plus any third-party source name the record itself names."""
    names: list[str] = []
    for entry in record.get("sources") or []:
        if isinstance(entry, dict):
            name = entry.get("name")
            if not name and entry.get("url"):
                name = re.sub(r"^https?://(www\.)?", "", entry["url"]).split("/")[0]
            if name:
                names.append(str(name))
    raw = record.get("_source")
    if isinstance(raw, dict):
        for entry in raw.get("sources") or []:
            if isinstance(entry, dict) and entry.get("name"):
                names.append(str(entry["name"]))
    names = sorted(set(names))
    return "blas-app:" + "+".join(names) if names else "blas-app"


def clean_gloss(text: str | None) -> str | None:
    if not text:
        return None
    text = text.strip()
    if GLOSS_REJECT.search(text):
        return None
    if len(text) > 60:
        for sep in (";", ","):
            if sep in text:
                text = text.split(sep)[0].strip()
                break
    if not text or len(text) > 60 or GLOSS_REJECT.search(text):
        return None
    return text


def content_tokens(form: str) -> list[str]:
    tokens = [token for token in norm(form).split(" ") if token]
    return [token for token in tokens if token not in STOP_TOKENS]


def strip_clitic(token: str) -> str:
    return re.sub(r"^(d|dh)'", "", token)


def evidence_for(language: str, lemma: str, gold: str, *, check: bool = True) -> str:
    """BÚNaMo (Irish) first, then Kaikki, else the app alone."""
    if not check:
        return "blas-app-only"
    if language == "irish":
        plain = " ".join(strip_clitic(token) for token in norm(gold).split(" "))
        if in_bunamo(gold) or in_bunamo(plain):
            return "blas-app+bunamo"
    index = kaikki_forms(language)
    if index:
        forms = index.get(norm(lemma), set())
        tokens = content_tokens(gold)
        if tokens:
            candidates = {" ".join(tokens), " ".join(strip_clitic(token) for token in tokens)}
            candidates.update(tokens if len(tokens) == 1 else [])
            for candidate in candidates:
                if candidate in forms or candidate in index:
                    return "blas-app+kaikki"
    return "blas-app-only"


def evidence_bonus(label: str) -> bool:
    return label != "blas-app-only"


class Builder:
    """Collects candidate items for one language."""

    def __init__(self, language: str) -> None:
        self.language = language
        self.name = LANGUAGE_NAMES[language]
        self.difficulty = Difficulty(language)
        self.items: list[dict[str, Any]] = []
        self.skipped: Counter = Counter()

    def add(
        self,
        *,
        id_parts: list[str],
        task: list[str],
        gold: list[str],
        phenomenon: str,
        source_file: str,
        source_id: str,
        record: dict[str, Any],
        diff_key: str | None,
        fallback_level: str | None = None,
        lemma: str,
        evidence_check: bool = True,
        preferred: bool = True,
        extra: dict[str, Any] | None = None,
    ) -> None:
        gold = unique(gold)
        gold = [value for value in gold if value and value not in {"-", "n/a", "—"}]
        if not gold:
            self.skipped["empty gold"] += 1
            return
        cefr, score = self.difficulty.lookup(diff_key, fallback_level) if diff_key else (fallback_level, None)
        label = evidence_for(self.language, lemma, gold[0], check=evidence_check)
        prompt = "\n".join([f"Language: {self.name}", *task])
        item = make_item(
            id="blas-morph:" + ":".join([self.language, *id_parts]),
            prompt=prompt,
            target=gold[0],
            suite=SUITE,
            test=TEST,
            scoring="accept_list",
            language=self.language,
            phenomenon=phenomenon,
            cefr=cefr,
            source=source_label(record),
            source_id=f"{source_file}#{source_id}",
            source_path=content_path(self.language, source_file.removesuffix(".json")),
            licence=LICENCE,
            evidence=label,
            human_checked=review_flag(record),
            accept=gold,
            lemma=lemma,
            difficulty_score=score,
            **(extra or {}),
        )
        item["metadata"]["_preferred"] = bool(preferred and (evidence_bonus(label) or not evidence_check))
        self.items.append(item)


# ---------------------------------------------------------------------------
# nouns
# ---------------------------------------------------------------------------

IRISH_NOUN_SLOTS = {
    "genitiveSingular": (
        "noun_genitive",
        "Give the genitive singular of the noun below, including the definite article "
        "(an or na) before the noun.",
    ),
    "nominativePlural": (
        "noun_plural",
        "Give the nominative plural of the noun below, including the definite article (na) "
        "before the noun.",
    ),
    "vocativeSingular": (
        "noun_vocative",
        "Give the vocative singular of the noun below, including the vocative particle (a) "
        "before the noun.",
    ),
}


def usable_noun_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip()
    if not value or value in {"-", "n/a"} or re.search(r"\d", value):
        return False
    return True


def simple_lemma(lemma: str) -> bool:
    return bool(lemma) and " " not in lemma and lemma[0].islower() and not re.search(r"\d", lemma)


def ordinal(n: int) -> str:
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


def build_nouns(builder: Builder) -> None:
    language = builder.language
    data = load_json(content_path(language, "declensions"))
    for noun in data["nouns"]:
        if blocked(noun):
            builder.skipped["noun blocked"] += 1
            continue
        lemma = noun.get("lemma", "")
        gloss = clean_gloss((noun.get("glosses") or {}).get("en") or noun.get("english"))
        gender = noun.get("gender")
        if not simple_lemma(lemma) or not gloss or noun.get("isProperNoun"):
            builder.skipped["noun lemma/gloss unusable"] += 1
            continue
        if noun.get("collective") or noun.get("singulative"):
            builder.skipped["collective or singulative noun"] += 1
            continue
        in_vocab = bool(noun.get("wordId"))
        record_id = noun["id"]
        fallback = noun.get("cefrLevel")
        base = [
            f"Noun: {lemma}",
            f"Meaning: {gloss}",
        ]
        if gender:
            base.append(f"Gender: {gender}")
        if language == "irish":
            declension = noun.get("declensionClass")
            if isinstance(declension, int) and 1 <= declension <= 5:
                base[-1] = f"Gender: {gender} ({ordinal(declension)} declension)"
            forms = noun.get("forms") or {}
            for key, (phenomenon, task) in IRISH_NOUN_SLOTS.items():
                gold = forms.get(key)
                if not usable_noun_text(gold):
                    continue
                bare = " ".join(gold.split()[1:]) if " " in gold else gold
                if phenomenon != "noun_vocative" and norm(bare) == norm(lemma):
                    builder.skipped["invariant form"] += 1
                    continue
                if norm(gold) == norm(lemma):
                    continue
                builder.add(
                    id_parts=[phenomenon, record_id],
                    task=[f"Task: {task}", *base],
                    gold=[gold],
                    phenomenon=phenomenon,
                    source_file="declensions.json",
                    source_id=f"{record_id}:{key}",
                    record=noun,
                    diff_key=f"declension:{record_id}:{key}",
                    fallback_level=fallback,
                    lemma=lemma,
                    preferred=in_vocab,
                    extra={"form_key": key},
                )
            continue
        # languages without article-bearing forms
        if language == "welsh":
            plurals = [form for form in noun.get("pluralForms") or [] if usable_noun_text(form)]
            plurals = [form for form in plurals if " " not in form and norm(form) != norm(lemma)]
            if not plurals:
                continue
            builder.add(
                id_parts=["noun_plural", record_id],
                task=[
                    "Task: Give the plural of the noun below. Several plurals may exist; "
                    "any attested plural is accepted.",
                    *base,
                ],
                gold=plurals,
                phenomenon="noun_plural",
                source_file="declensions.json",
                source_id=f"{record_id}:pluralForms",
                record=noun,
                diff_key=f"declension:{record_id}:plural",
                fallback_level=fallback,
                lemma=lemma,
                evidence_check=False,
                preferred=in_vocab,
                extra={"form_key": "pluralForms"},
            )
            continue
        forms = noun.get("forms") or {}
        singular = forms.get("nominativeSingular")
        if not usable_noun_text(singular) or norm(singular) != norm(lemma):
            continue
        slots = [("nominativePlural", "noun_plural", "Give the plural (nominative plural) of the noun below.")]
        if language == "scots-gaelic":
            slots.append(
                (
                    "genitiveSingular",
                    "noun_genitive",
                    "Give the genitive singular of the noun below, as a bare noun without the article.",
                )
            )
            if not gender:
                continue
        for key, phenomenon, task in slots:
            gold = forms.get(key)
            if not usable_noun_text(gold) or " " in gold.strip() or norm(gold) == norm(lemma):
                if usable_noun_text(gold) and norm(gold) == norm(lemma):
                    builder.skipped["invariant form"] += 1
                continue
            builder.add(
                id_parts=[phenomenon, record_id],
                task=[f"Task: {task}", *base],
                gold=[gold],
                phenomenon=phenomenon,
                source_file="declensions.json",
                source_id=f"{record_id}:{key}",
                record=noun,
                diff_key=f"declension:{record_id}:{key}",
                fallback_level=fallback,
                lemma=lemma,
                preferred=in_vocab,
                extra={"form_key": key},
            )


# ---------------------------------------------------------------------------
# verbs
# ---------------------------------------------------------------------------

TENSE_TEXT = {
    "present": "present",
    "past": "past",
    "future": "future",
    "conditional": "conditional",
    "imperative": "imperative",
    "imperfect": "imperfect",
    "preterite": "preterite",
    "pluperfect": "pluperfect",
    "subjunctive": "subjunctive",
    "pastConditional": "past conditional",
    "futureIndicative": "future (independent)",
    "pastParticiple": "past participle",
}


def verb_header(lemma: str, gloss: str) -> list[str]:
    return [f"Verb: {lemma}", f"Meaning: {gloss}"]


def usable_verb_form(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip() not in {"-", "n/a"} and not re.search(
        r"[/,;()?]|\d", value
    )


def verb_difficulty_key(verb: dict[str, Any], tense: str) -> str:
    return f"conjugation:{verb['id']}:{tense}"


def build_verbs_irish(builder: Builder, verb: dict[str, Any], gloss: str) -> None:
    lemma = verb["lemma"]
    for tense, persons in (verb.get("tenses") or {}).items():
        if not isinstance(persons, dict):
            continue
        for person, cell in persons.items():
            form = cell.get("analytic") if isinstance(cell, dict) else None
            if not usable_verb_form(form):
                continue
            tokens = form.split()
            if person == "autonomous":
                if len(tokens) != 1:
                    continue
                how = "Write the single-word autonomous (impersonal) form, with no pronoun."
            elif tense == "imperative":
                if person not in {"2s", "2p"} or len(tokens) != 1:
                    continue
                how = "Write the imperative form on its own, with no pronoun."
            else:
                pronoun = IRISH_PRONOUN.get(person)
                if person not in {"2s", "3s", "2p", "3p"} or len(tokens) != 2 or tokens[1] != pronoun:
                    # single-word (synthetic) forms have an analytic alternative; skip them
                    continue
                how = f"Write the verb form followed by the pronoun '{pronoun}'."
            who = PERSON_TEXT[person]
            if person == "3s":
                who = "3rd person singular (sé)"
            builder.add(
                id_parts=[f"verb_{tense}", verb["id"], person],
                task=[
                    f"Task: Give the {TENSE_TEXT[tense]} tense form of the verb for the person given. {how}",
                    *verb_header(lemma, gloss),
                    f"Tense: {TENSE_TEXT[tense]}",
                    f"Person: {who}" if person != "autonomous" else "Person: autonomous (impersonal)",
                ],
                gold=[form],
                phenomenon=f"verb_{tense}",
                source_file="conjugations.json",
                source_id=f"{verb['id']}:{tense}:{person}",
                record=verb,
                diff_key=verb_difficulty_key(verb, tense),
                lemma=lemma,
                extra={"tense": tense, "person": person},
            )


def build_verbs_single_token(
    builder: Builder,
    verb: dict[str, Any],
    gloss: str,
    tenses_allowed: set[str],
    persons_for: dict[str, set[str]] | None,
    how_by_tense: dict[str, str],
    variant_key: str,
) -> None:
    """Welsh, Breton, Cornish: one word per cell, no pronoun, variants listed by the record."""
    lemma = verb["lemma"]
    for tense, persons in (verb.get("tenses") or {}).items():
        if tense not in tenses_allowed or not isinstance(persons, dict):
            continue
        for person, cell in persons.items():
            if person not in PERSON_TEXT:
                continue
            if persons_for and tense in persons_for and person not in persons_for[tense]:
                continue
            form = cell.get("analytic") if isinstance(cell, dict) else None
            if not usable_verb_form(form) or " " in form.strip():
                continue
            gold = [form]
            if isinstance(cell, dict):
                gold += [v for v in cell.get(variant_key) or [] if usable_verb_form(v)]
            builder.add(
                id_parts=[f"verb_{tense}", verb["id"], person],
                task=[
                    f"Task: Give the {how_by_tense.get(tense, TENSE_TEXT.get(tense, tense))} form of the verb "
                    "for the person given. Write one word: the inflected verb form, with no pronoun, "
                    "particle or auxiliary." + (
                        " Use the literary written form, not a spoken periphrastic construction."
                        if builder.language == "welsh"
                        else ""
                    ),
                    *verb_header(lemma, gloss),
                    f"Tense: {how_by_tense.get(tense, TENSE_TEXT.get(tense, tense))}",
                    f"Person: {PERSON_TEXT[person]}",
                ],
                gold=gold,
                phenomenon=f"verb_{tense}",
                source_file="conjugations.json",
                source_id=f"{verb['id']}:{tense}:{person}",
                record=verb,
                diff_key=verb_difficulty_key(verb, tense),
                lemma=lemma,
                extra={"tense": tense, "person": person},
            )


def build_verbs_gd(builder: Builder, verb: dict[str, Any], gloss: str) -> None:
    lemma = verb["lemma"]
    verdict = (verb.get("ai_voice") or {}).get("verdict")
    if verdict in {"major", "wrong"}:
        builder.skipped["verb audit verdict"] += 1
        return
    for tense, value in (verb.get("tenses") or {}).items():
        if not isinstance(value, dict):
            continue
        header = verb_header(lemma, gloss)
        key = verb_difficulty_key(verb, tense)
        if tense == "imperative":
            for person in ("2s", "2p"):
                cell = value.get(person)
                if not isinstance(cell, dict) or not usable_verb_form(cell.get("analytic")):
                    continue
                gold = [cell["analytic"]] + [v for v in [cell.get("variant")] if usable_verb_form(v)]
                builder.add(
                    id_parts=["verb_imperative", verb["id"], person],
                    task=[
                        "Task: Give the imperative form of the verb for the person given, as one word "
                        "with no pronoun.",
                        *header,
                        "Tense: imperative",
                        f"Person: {PERSON_TEXT[person]}",
                    ],
                    gold=gold,
                    phenomenon="verb_imperative",
                    source_file="conjugations.json",
                    source_id=f"{verb['id']}:imperative:{person}",
                    record=verb,
                    diff_key=key,
                    lemma=lemma,
                    extra={"tense": tense, "person": person},
                )
            continue
        if tense == "pastParticiple":
            form = value.get("analytic")
            if usable_verb_form(form):
                builder.add(
                    id_parts=["verb_pastParticiple", verb["id"]],
                    task=[
                        "Task: Give the past participle of the verb, as one word.",
                        *header,
                    ],
                    gold=[form],
                    phenomenon="verb_pastParticiple",
                    source_file="conjugations.json",
                    source_id=f"{verb['id']}:pastParticiple",
                    record=verb,
                    diff_key=key,
                    lemma=lemma,
                    extra={"tense": tense},
                )
            continue
        if tense not in {"past", "future", "conditional"}:
            continue
        if "analytic" in value:
            # regular verb: one stored form for the whole tense
            form = value["analytic"]
            if not usable_verb_form(form) or " " in form.strip():
                continue
            if tense == "conditional":
                if not form.endswith("inn"):
                    continue
                person_line = "Person: 1st person singular (I would ...)"
                how = "the 1st person singular form, as one word with no pronoun"
                person = "1s"
            else:
                person_line = "Person: any (the independent form is the same for every person)"
                how = (
                    "the independent form, the verb form used in plain positive statements, "
                    "as one word with no pronoun"
                )
                person = "all"
            builder.add(
                id_parts=[f"verb_{tense}", verb["id"], "independent", person],
                task=[
                    f"Task: Give the {tense} tense form of the verb: {how}.",
                    *header,
                    f"Tense: {tense}",
                    person_line,
                ],
                gold=[form],
                phenomenon=f"verb_{tense}",
                source_file="conjugations.json",
                source_id=f"{verb['id']}:{tense}:analytic",
                record=verb,
                diff_key=key,
                lemma=lemma,
                extra={"tense": tense, "person": person, "mood": "independent"},
            )
            continue
        # irregular verb: per-person cells with independent/dependent forms
        modes = ["independent"] + (["dependent"] if verdict == "ok" else [])
        for mode in modes:
            by_person = {
                person: cell[mode]
                for person, cell in value.items()
                if isinstance(cell, dict) and usable_verb_form(cell.get(mode)) and " " not in cell[mode].strip()
            }
            if not by_person:
                continue
            if tense in {"past", "future"} and len(set(by_person.values())) == 1:
                chosen = [("all", next(iter(by_person.values())))]
            else:
                chosen = [(p, by_person[p]) for p in ("1s", "3sm") if p in by_person]
            for person, form in chosen:
                if mode == "independent":
                    how = (
                        "the independent form, the verb form used in plain positive statements, "
                        "as one word with no pronoun"
                    )
                else:
                    how = (
                        "the dependent form, the verb form used after negative cha/chan and after the "
                        "question particles an/am and nach, as one word with no pronoun"
                    )
                person_line = (
                    "Person: any (the form is the same for every person)"
                    if person == "all"
                    else f"Person: {PERSON_TEXT[person]}"
                )
                builder.add(
                    id_parts=[f"verb_{tense}", verb["id"], mode, person],
                    task=[
                        f"Task: Give the {tense} tense form of the verb: {how}.",
                        *header,
                        f"Tense: {tense}",
                        person_line,
                    ],
                    gold=[form],
                    phenomenon=f"verb_{tense}",
                    source_file="conjugations.json",
                    source_id=f"{verb['id']}:{tense}:{person}:{mode}",
                    record=verb,
                    diff_key=key,
                    lemma=lemma,
                    extra={"tense": tense, "person": person, "mood": mode},
                )


def build_verbs_gv(builder: Builder, verb: dict[str, Any], gloss: str) -> None:
    lemma = verb["lemma"]
    verdict = (verb.get("ai_voice") or {}).get("verdict")
    if verdict not in {"ok", "minor"}:
        builder.skipped["manx verb without audit"] += 1
        return
    header = verb_header(lemma, gloss)
    tenses = verb.get("tenses") or {}
    for tense, value in tenses.items():
        if value is None:
            continue
        key = verb_difficulty_key(verb, tense)
        if tense == "imperative":
            for person in ("2s",):
                cell = value.get(person)
                form = cell.get("analytic") if isinstance(cell, dict) else cell
                if usable_verb_form(form) and norm(form) != norm(lemma):
                    builder.add(
                        id_parts=["verb_imperative", verb["id"], person],
                        task=[
                            "Task: Give the imperative form of the verb for the person given, as one word "
                            "with no pronoun.",
                            *header,
                            "Tense: imperative",
                            f"Person: {PERSON_TEXT[person]}",
                        ],
                        gold=[form],
                        phenomenon="verb_imperative",
                        source_file="conjugations.json",
                        source_id=f"{verb['id']}:imperative:{person}",
                        record=verb,
                        diff_key=key,
                        lemma=lemma,
                        extra={"tense": tense, "person": person},
                    )
            continue
        if tense == "pastParticiple":
            cell = value.get("sg")
            form = cell.get("analytic") if isinstance(cell, dict) else cell
            if usable_verb_form(form) and verb.get("irregular"):
                builder.add(
                    id_parts=["verb_pastParticiple", verb["id"]],
                    task=["Task: Give the past participle of the verb, as one word.", *header],
                    gold=[form],
                    phenomenon="verb_pastParticiple",
                    source_file="conjugations.json",
                    source_id=f"{verb['id']}:pastParticiple",
                    record=verb,
                    diff_key=key,
                    lemma=lemma,
                    extra={"tense": tense},
                )
            continue
        if "independent" in value or "dependent" in value:
            # irregular verb: independent / dependent forms with the pronoun already attached
            for mode in ("independent", "dependent"):
                cells = value.get(mode)
                if not isinstance(cells, dict):
                    continue
                for person, pronoun in MANX_PRONOUN.items():
                    form = cells.get(person)
                    if not usable_verb_form(form):
                        continue
                    tokens = form.split()
                    if len(tokens) != 2 or tokens[1] != pronoun:
                        continue
                    if mode == "independent":
                        how = "the independent form (plain positive statement)"
                    else:
                        how = "the dependent form (used after cha, nagh and the question particle)"
                    who = PERSON_TEXT[person] + f" ({pronoun})"
                    builder.add(
                        id_parts=[f"verb_{tense}", verb["id"], mode, person],
                        task=[
                            f"Task: Give the {tense} tense form of the verb: {how}. Write the verb form "
                            f"followed by the pronoun '{pronoun}'.",
                            *header,
                            f"Tense: {tense}",
                            f"Person: {who}",
                        ],
                        gold=[form],
                        phenomenon=f"verb_{tense}",
                        source_file="conjugations.json",
                        source_id=f"{verb['id']}:{tense}:{mode}:{person}",
                        record=verb,
                        diff_key=key,
                        lemma=lemma,
                        extra={"tense": tense, "person": person, "mood": mode},
                    )
            continue
        # regular verb: only forms that are plainly person-marked and one word
        wanted = {"futureIndicative": ("1s", "ym"), "conditional": ("1s", "in")}.get(tense)
        if wanted and not verb.get("irregular"):
            person, suffix = wanted
            cell = value.get(person)
            form = cell.get("analytic") if isinstance(cell, dict) else cell
            if usable_verb_form(form) and form.endswith(suffix) and " " not in form:
                text = TENSE_TEXT[tense]
                builder.add(
                    id_parts=[f"verb_{tense}", verb["id"], person],
                    task=[
                        f"Task: Give the {text} tense form of the verb for the person given, as one "
                        "word with no pronoun.",
                        *header,
                        f"Tense: {text}",
                        f"Person: {PERSON_TEXT[person]}",
                    ],
                    gold=[form],
                    phenomenon=f"verb_{tense}",
                    source_file="conjugations.json",
                    source_id=f"{verb['id']}:{tense}:{person}",
                    record=verb,
                    diff_key=key,
                    lemma=lemma,
                    extra={"tense": tense, "person": person},
                )


def build_verbs(builder: Builder) -> None:
    language = builder.language
    data = load_json(content_path(language, "conjugations"))
    for verb in data["verbs"]:
        if blocked(verb):
            builder.skipped["verb blocked"] += 1
            continue
        lemma = verb.get("lemma", "")
        gloss = clean_gloss((verb.get("glosses") or {}).get("en") or verb.get("english"))
        if not lemma or " " in lemma or not gloss:
            builder.skipped["verb lemma/gloss unusable"] += 1
            continue
        if language == "irish":
            build_verbs_irish(builder, verb, gloss)
        elif language == "welsh":
            build_verbs_single_token(
                builder,
                verb,
                gloss,
                {"present", "conditional", "imperfect", "preterite", "pluperfect", "imperative"},
                {"imperative": {"2s", "1p", "2p"}},
                {
                    "present": "present",
                    "conditional": "conditional",
                    "imperfect": "imperfect",
                    "preterite": "preterite",
                    "pluperfect": "pluperfect",
                    "imperative": "imperative",
                },
                "variants",
            )
        elif language == "breton":
            build_verbs_single_token(
                builder,
                verb,
                gloss,
                {"present", "imperfect", "past", "future", "conditional", "pastConditional", "imperative"},
                {"imperative": {"2s", "1p", "2p"}},
                {},
                "variants",
            )
        elif language == "cornish":
            build_verbs_single_token(
                builder,
                verb,
                gloss,
                {"present", "past", "imperfect", "imperative", "future"},
                {"imperative": {"2s", "2p"}},
                {"present": "present-future (inflected)", "past": "past (preterite)"},
                "_variants",
            )
        elif language == "scots-gaelic":
            build_verbs_gd(builder, verb, gloss)
        elif language == "manx":
            build_verbs_gv(builder, verb, gloss)


# ---------------------------------------------------------------------------
# prepositional pronouns
# ---------------------------------------------------------------------------

CORNISH_CONFIDENCE = re.compile(r"Confidence:\s*(HIGH|MEDIUM-HIGH|MEDIUM|LOW-MEDIUM|LOW)")


def build_prepositional(builder: Builder) -> None:
    language = builder.language
    data = load_json(content_path(language, "prepositional-pronouns"))
    for prep in data["prepositions"]:
        if blocked(prep) or prep.get("doesNotInflect") or not isinstance(prep.get("forms"), dict):
            builder.skipped["preposition blocked/no paradigm"] += 1
            continue
        ai = prep.get("ai_voice")
        verdict = ai.get("verdict") if isinstance(ai, dict) else None
        if verdict in {"wrong", "major"}:
            builder.skipped["preposition audit verdict"] += 1
            continue
        if language == "cornish":
            match = CORNISH_CONFIDENCE.search(ai if isinstance(ai, str) else "")
            if not match or match.group(1) not in {"HIGH", "MEDIUM-HIGH"}:
                builder.skipped["preposition confidence below MEDIUM-HIGH"] += 1
                continue
        base = prep["baseForm"]
        for person, cell in prep["forms"].items():
            if person not in PERSON_TEXT_PP or not isinstance(cell, dict):
                continue
            standard = cell.get("standard")
            if not usable_verb_form(standard) or " " in standard.strip() or norm(standard) == norm(base):
                builder.skipped["preposition form unusable"] += 1
                continue
            meaning = cell.get("english") or ""
            builder.add(
                id_parts=["prepositional_pronoun", prep["id"], person],
                task=[
                    "Task: Give the prepositional pronoun (the preposition fused with a personal "
                    "pronoun) for the slot below. Write the standard simple form, not an emphatic form.",
                    f"Preposition: {base} ({prep['english']})",
                    f"Slot: {PERSON_TEXT_PP[person]}, meaning '{meaning}'" if meaning else f"Slot: {PERSON_TEXT_PP[person]}",
                ],
                gold=[standard],
                phenomenon="prepositional_pronoun",
                source_file="prepositional-pronouns.json",
                source_id=f"{prep['id']}:{person}",
                record=prep,
                diff_key=f"prepPronoun:{prep['id']}",
                lemma=base,
                extra={"person": person},
            )


# ---------------------------------------------------------------------------
# numbers
# ---------------------------------------------------------------------------

CARDINAL_HOW = {
    "irish": "the basic numeral as it stands in a table of cardinal numbers, without the counting "
    "particle 'a'",
    "welsh": "the traditional (non-decimal) numeral, standing on its own",
    "scots-gaelic": "the form used directly before a counted noun, with the number treated as an "
    "abstract count (no noun given)",
    "manx": "the standalone numeral, the form used to name the number (not the form used before a noun)",
    "breton": "the standalone numeral, the form used to name the number",
    "cornish": "the standalone numeral, the form used to name the number (SWF Main)",
}


def split_alternatives(value: str) -> list[str]:
    return [part.strip() for part in value.split("/") if part.strip()]


def irish_cardinal_consistent(number: dict[str, Any]) -> bool:
    """Keep the Irish cardinal only when it is the counting form without 'a' (and its h-prefix)."""
    counting = number.get("counting")
    cardinal = number.get("cardinal")
    if not counting or not cardinal:
        return False
    if counting == cardinal:
        return True
    if not counting.startswith("a "):
        return False
    rest = counting[2:]
    return norm(rest) == norm(cardinal) or (rest.startswith("h") and norm(rest[1:]) == norm(cardinal))


def build_numbers(builder: Builder) -> None:
    language = builder.language
    data = load_json(content_path(language, "numbers"))
    for number in data["numbers"]:
        if blocked(number):
            builder.skipped["number blocked"] += 1
            continue
        value = number.get("value", number.get("numeral"))
        english = number.get("english")
        label = f"{value}" + (f" ({english})" if english else "")
        verdict = (number.get("ai_voice") or {}).get("verdict")
        if verdict in {"wrong", "major"} and (language, number["id"], "cardinal") not in NUMBER_EXCLUDE:
            # whole-record verdicts: only drop kinds the exclusion table lists, others are checked below
            pass
        kinds: list[tuple[str, str, list[str], str]] = []

        def push(kind: str, how: str, gold: list[str], tag: str = "") -> None:
            if (language, number["id"], kind) in NUMBER_EXCLUDE:
                builder.skipped["number excluded: " + NUMBER_EXCLUDE[(language, number["id"], kind)]] += 1
                return
            gold = [g for g in gold if usable_number(g)]
            if gold:
                kinds.append((kind, how, gold, tag))

        def usable_number(text: str) -> bool:
            return bool(text) and "..." not in text and "laa" not in text.split() and text not in {"-"}

        # cardinal
        how = CARDINAL_HOW[language]
        gender_pairs = []
        masculine = number.get("cardinalMasculine") or (number.get("cardinal") if number.get("cardinalFeminine") else None)
        feminine = number.get("cardinalFeminine")
        if masculine and feminine and norm(masculine) != norm(feminine):
            gender_pairs = [("masculine", masculine), ("feminine", feminine)]
        cardinal = number.get("cardinal")
        if gender_pairs:
            for gender, form in gender_pairs:
                push("cardinal", f"{how}; give the {gender} form (for use with {gender} nouns)", [form], gender)
        elif cardinal:
            if language == "irish" and not irish_cardinal_consistent(number):
                builder.skipped["irish cardinal not the plain counting base"] += 1
            else:
                push("cardinal", how, [cardinal])
        # counting
        if number.get("counting") and language == "irish":
            push("counting", "the form used when counting aloud or reciting numbers (with the counting particle)", [number["counting"]])
        if number.get("counting") and language == "scots-gaelic":
            push("counting", "the form used when counting aloud (not before a noun)", [number["counting"]])
        # personal
        if number.get("personal"):
            push("personal", "the numeral used for counting people, as a stand-alone word or phrase", [number["personal"]])
        # ordinal
        ordinal_form = number.get("ordinal")
        if ordinal_form:
            gold = split_alternatives(ordinal_form)
            if language == "manx":
                how_o = "the ordinal ('first', 'second', ...), including the definite article yn as it stands before the ordinal"
            elif language == "welsh" and len(gold) > 1:
                how_o = "the ordinal ('first', 'second', ...); masculine and feminine forms are both accepted"
            else:
                how_o = "the ordinal ('first', 'second', ...), in its basic form"
            if language == "cornish":
                gold = gold + [g.replace("-", " ") for g in gold if "-ugens" in g]
            if "'" in ordinal_form and ordinal_form.startswith("a'") and language == "scots-gaelic":
                builder.skipped["number excluded: ordinal stored with article"] += 1
            else:
                push("ordinal", how_o, gold)
        for kind, how_text, gold, tag in kinds:
            builder.add(
                id_parts=[f"number_{kind}", number["id"], tag] if tag else [f"number_{kind}", number["id"]],
                task=[
                    f"Task: Give the {kind} numeral for the number below: {how_text}.",
                    f"Number: {label}",
                ],
                gold=gold,
                phenomenon=f"number_{kind}",
                source_file="numbers.json",
                source_id=f"{number['id']}:{kind}" + (f":{tag}" if tag else ""),
                record=number,
                diff_key=f"number:{number['id']}",
                lemma=number.get("cardinal") or "",
                evidence_check=language != "welsh",
                extra={"value": value, "number_kind": kind},
            )


# ---------------------------------------------------------------------------
# gender practice: bare noun + gloss -> noun with article
# ---------------------------------------------------------------------------


def noun_lemmas(language: str) -> dict[str, str]:
    """wordId -> bare noun. vocabulary.json ``native`` first, declension lemma as the fallback."""
    data = load_json(content_path(language, "declensions"))
    lemmas = {n["wordId"]: n["lemma"] for n in data["nouns"] if n.get("wordId") and n.get("lemma")}
    vocabulary = load_json(content_path(language, "vocabulary"))
    for word in vocabulary.get("words") or []:
        if word.get("id") and word.get("native") and word.get("partOfSpeech") == "noun":
            lemmas[word["id"]] = word["native"]
    return lemmas


def build_gender(builder: Builder) -> None:
    language = builder.language
    data = load_json(content_path(language, "gender-practice"))
    lemmas = noun_lemmas(language)
    for item in data["items"]:
        if blocked(item) or item.get("eligible") is False or item.get("supersededByItemId"):
            builder.skipped["gender item blocked/ineligible"] += 1
            continue
        if not re.search(r"-article(-v\d+)?$", item["id"]):
            continue  # adjective, genitive and number phrases are not article-only
        word_id = item["wordId"]
        lemma = lemmas.get(word_id)
        if not lemma:
            quoted = re.findall(r"'([^']+)'", item["explanation"].get("en", ""))
            lemma = quoted[0] if quoted and " " not in quoted[0] and quoted[0] != "an" else None
        if not lemma:
            lemma = word_id.split("-", 1)[1]
        gloss_en = (item.get("glosses") or {}).get("en", "")
        gloss = re.sub(r"\bthe\s+", "", gloss_en).strip()
        phrase = item["phrase"]
        if not gloss or not lemma or norm(phrase).split(" ")[-1] == "":
            builder.skipped["gender item unusable"] += 1
            continue
        accept = [phrase]
        for alternative in item.get("alternatives") or []:
            if isinstance(alternative, dict) and alternative.get("text") and alternative.get("approved"):
                accept.append(alternative["text"])
        article_note = ""
        if language == "manx":
            article_note = " Use the article yn."
        builder.add(
            id_parts=["article_gender_mutation", item["id"]],
            task=[
                "Task: Give the noun below with the definite article ('the ...') in the nominative "
                "singular, applying the article form and any mutation or prefix that the noun's "
                f"gender and first sound require.{article_note}",
                f"Noun: {lemma}",
                f"Meaning: {gloss}",
                f"Gender: {item['gender']}",
            ],
            gold=accept,
            phenomenon="article_gender_mutation",
            source_file="gender-practice.json",
            source_id=item["id"],
            record=item,
            diff_key=f"mutation:{item['id']}",
            fallback_level=item.get("cefrLevel"),
            lemma=lemma,
            evidence_check=False,
            extra={"gender": item["gender"]},
        )


# ---------------------------------------------------------------------------
# copula drills (cloze of the copula word)
# ---------------------------------------------------------------------------

IRISH_COPULA_LEAD = {"Is", "Ní", "An", "Ba", "Níor", "Níorbh"}
COPULA_BAD_ENGLISH = re.compile(r"^(Is it true that:|Not:|\(Past\)|\(Past,)")
IRISH_BAD_LENITION = re.compile(r"\bsh[cptm]", re.IGNORECASE)


def copula_cloze(language: str, drill: dict[str, Any]) -> tuple[str, list[str]] | None:
    """Return (sentence with ___, accepted blank fillers) or None when no single clean blank exists."""
    sentence = drill["native"].strip()
    tokens = sentence.split(" ")
    english = drill["english"]
    if COPULA_BAD_ENGLISH.search(english) or not drill.get("usesCopula"):
        return None
    if language == "irish":
        if tokens[0] not in IRISH_COPULA_LEAD or IRISH_BAD_LENITION.search(sentence):
            return None
        return "___ " + " ".join(tokens[1:]), [tokens[0]]
    if language == "welsh":
        if tokens[0] not in {"Nid", "Ai"}:
            return None
        return "___ " + " ".join(tokens[1:]), [tokens[0]]
    if language == "scots-gaelic":
        if tokens[0] == "An":
            return "___ " + " ".join(tokens[1:]), [tokens[0]]
        if tokens[0] == "'S" and len(tokens) > 1 and tokens[1] == "ann":
            return "___ " + " ".join(tokens[2:]), ["'S ann"]
        return None
    if language == "manx":
        if tokens[0] != "She":
            return None
        return "___ " + " ".join(tokens[1:]), [tokens[0]]
    if language == "breton":
        if tokens.count("eo") != 1 or "bet" in tokens:
            return None
        at = tokens.index("eo")
        return " ".join(tokens[:at] + ["___"] + tokens[at + 1 :]), ["eo"]
    if language == "cornish":
        if tokens.count("yw") != 1:
            return None
        at = tokens.index("yw")
        return " ".join(tokens[:at] + ["___"] + tokens[at + 1 :]), ["yw"]
    return None


def build_copula(builder: Builder) -> None:
    language = builder.language
    data = load_json(content_path(language, "copula-drills"))
    for drill in data["items"]:
        if blocked(drill):
            builder.skipped["copula blocked"] += 1
            continue
        cloze = copula_cloze(language, drill)
        if not cloze:
            builder.skipped["copula drill without a single clean blank"] += 1
            continue
        sentence, gold = cloze
        builder.add(
            id_parts=["copula", drill["id"]],
            task=[
                "Task: Fill in the blank with the copula word (or copula particle) that the sentence "
                "needs. Write only the missing word(s).",
                f"Sentence: {sentence}",
                f"English: {drill['english']}",
            ],
            gold=gold,
            phenomenon="copula",
            source_file="copula-drills.json",
            source_id=drill["id"],
            record=drill,
            diff_key=f"copula:{drill['id']}",
            lemma=gold[0],
            evidence_check=False,
            extra={"category": drill.get("category"), "cloze_sentence": drill["native"]},
        )


# ---------------------------------------------------------------------------
# sampling
# ---------------------------------------------------------------------------


def choose(language_items: list[dict[str, Any]], total: int) -> list[dict[str, Any]]:
    """Counts per phenomenon from stratified_sample; picks inside a phenomenon span the CEFR range."""
    by_phenomenon: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in language_items:
        by_phenomenon[item["metadata"]["phenomenon"]].append(item)
    pools: dict[str, list[dict[str, Any]]] = {}
    for phenomenon, entries in by_phenomenon.items():
        preferred = [entry for entry in entries if entry["metadata"]["_preferred"]]
        pools[phenomenon] = preferred if len(preferred) >= max(12, 3 * total // max(len(by_phenomenon), 1)) else entries
    flat = [entry for entries in pools.values() for entry in entries]
    counts = Counter(
        entry["metadata"]["phenomenon"] for entry in stratified_sample(flat, total, keys=("phenomenon",))
    )
    chosen: list[dict[str, Any]] = []
    for phenomenon in sorted(counts):
        chosen.extend(stratified_sample(pools[phenomenon], counts[phenomenon], keys=("cefr",)))
    return sorted(chosen, key=lambda entry: entry["id"])


def main() -> None:
    all_items: list[dict[str, Any]] = []
    candidates: dict[str, dict[str, int]] = {}
    skipped: dict[str, dict[str, int]] = {}
    shortfalls: dict[str, Any] = {}
    cefr_by_language: dict[str, dict[str, int]] = {}
    for language in LANGUAGES:
        builder = Builder(language)
        build_nouns(builder)
        build_verbs(builder)
        build_prepositional(builder)
        build_numbers(builder)
        build_gender(builder)
        build_copula(builder)
        # de-duplicate by normalized prompt + answer
        seen: set[tuple[str, str]] = set()
        deduped = []
        for item in sorted(builder.items, key=lambda entry: entry["id"]):
            key = (norm(item["input"]), norm(item["target"]))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        candidates[language] = dict(sorted(Counter(i["metadata"]["phenomenon"] for i in deduped).items()))
        skipped[language] = dict(sorted(builder.skipped.items()))
        picked = choose(deduped, PER_LANGUAGE)
        counts = Counter(i["metadata"]["phenomenon"] for i in picked)
        cefr_by_language[language] = dict(sorted(Counter(str(i["metadata"]["cefr"]) for i in picked).items()))
        phenomena = sorted(candidates[language])
        even = PER_LANGUAGE // max(len(phenomena), 1)
        short = {p: {"wanted_even_share": even, "got": counts.get(p, 0), "candidates": candidates[language][p]}
                 for p in phenomena if counts.get(p, 0) < even}
        shortfalls[language] = {"items": len(picked), "target": PER_LANGUAGE, "phenomena_below_even_share": short}
        all_items.extend(picked)
    report: dict[str, Any] = {
        "per_language_target": PER_LANGUAGE,
        "candidates_by_language_phenomenon": candidates,
        "selected_by_language_phenomenon": {
            language: dict(sorted(Counter(i["metadata"]["phenomenon"] for i in all_items if i["metadata"]["language"] == language).items()))
            for language in LANGUAGES
        },
        "skipped_records": skipped,
        "shortfalls": shortfalls,
        "cefr_by_language": cefr_by_language,
        "evidence_by_language": {
            language: dict(sorted(Counter(i["metadata"]["evidence"] for i in all_items if i["metadata"]["language"] == language).items()))
            for language in LANGUAGES
        },
        "human_checked_rule": "metadata.human_checked is true only if the record has reviewStatus == 'approved' "
        "or humanReviewed == true; no source record carries either field, so all items are false.",
        "fields_used": {
            "declensions": "nouns[].{id,lemma,english|glosses.en,gender,declensionClass,forms.*,pluralForms,wordId,sources,_blocked}",
            "conjugations": "verbs[].{id,lemma,english|glosses.en,irregular,tenses.<tense>.<person>.{analytic,independent,dependent,variant(s)},ai_voice.verdict,_blocked}",
            "prepositional_pronouns": "prepositions[].{id,baseForm,english,forms.<person>.{standard,english},ai_voice,_blocked,doesNotInflect}",
            "numbers": "numbers[].{id,value|numeral,english,cardinal(Masculine|Feminine),counting,personal,ordinal,ai_voice,_blocked}",
            "gender_practice": "items[].{id,wordId,phrase,gender,glosses.en,alternatives[].text,eligible,supersededByItemId,_blocked}",
            "copula_drills": "items[].{id,native,english,usesCopula,_blocked}",
            "cefr": "item-difficulty.json items[<key>] mapped through bands; keys declension:<id>:<form>, conjugation:<id>:<tense>, prepPronoun:<id>, number:<id>, copula:<id>; null when no key",
        },
        "copula": "Copula drills are sentence translations, not closed forms. Used only as cloze of the "
        "leading copula particle (Irish Is/Ní/An/Ba/Níor/Níorbh, Welsh Nid/Ai, Scottish Gaelic An and 'S ann, "
        "Manx She) or the copula verb (Breton eo, Cornish yw) when the English translation fixes the "
        "polarity and tense. Affirmative Welsh ydw/ydy/yw drills are skipped (ydw/wyf and ydy/yw are all valid). "
        "Drills with English such as 'Is it true that:' or an sc-/sp- lenition error in the sentence are skipped.",
        "welsh_future_skipped": "Welsh future cells are pronoun-bearing colloquial forms (cana i) and the "
        "synthetic future has no listing, so the future is not asked; subjunctive covers five verbs and is skipped.",
        "sampling": "Per language: counts per phenomenon from stratified_sample(keys=('phenomenon',)); "
        "picks inside a phenomenon from stratified_sample(keys=('cefr',)). Candidates prefer evidence "
        "confirmed forms and vocabulary-linked nouns when at least 12 such candidates exist.",
        "seed": SEED,
        "items_with_multiple_accepted_answers": {
            language: sum(
                1
                for i in all_items
                if i["metadata"]["language"] == language and len(i["metadata"]["accept"]) > 1
            )
            for language in LANGUAGES
        },
        "accept_sources": "Extra accepted answers come only from the app records: Welsh pluralForms, "
        "Welsh ordinals written a/b, Breton variants, Cornish _variants, Scottish Gaelic imperative variant, "
        "Manx gender-practice alternatives, and the spaced spelling of Cornish -ugens numerals "
        "(the record's AI audit says both spellings are attested). No external dialect list is used.",
        "cefr_note": "item-difficulty.json scores for declension, conjugation, prepPronoun, number and copula "
        "keys only reach A1-B2 (Welsh conjugation has 5 C1 keys), so the sample cannot reach C1/C2; "
        "gender-practice items have no key and no cefrLevel, so their cefr is null.",
    }
    for item in all_items:
        item["metadata"].pop("_preferred", None)
    write_outputs(SUITE, TEST, all_items, report)
    print(f"wrote {len(all_items)} items")


if __name__ == "__main__":
    main()
