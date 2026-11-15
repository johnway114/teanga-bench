"""Build blas/translation and blas/round_trip.

Run with: ``uv run --with pyarrow python scripts/build_blas_translation.py``
(pyarrow is needed to read the parallel-corpus parquet files; nothing else is
third-party, and there are no network or paid API calls.)

Sources
-------
A. Blas app sentences, ``~/Documents/blas/data/content/<language>/sentences.json``.
B. Test splits of the parallel corpora in
   ``~/Documents/language-data/gold/text/parallel/`` (Irish-English, Welsh-English,
   Breton-French). Only rows with ``split == "test"``.

blas/translation: 60 items per language (360). Half translate into English
(French for the Breton corpus rows), half translate from English. For Irish,
Welsh and Breton, 20 of the 60 are corpus rows (10 per direction).

blas/round_trip: 40 items per language (240) of 6-25 words from (A), never a
sentence used in blas/translation. The first leg translates into English.

Selection is deterministic (seed 20261115, inputs sorted), so a rebuild is
byte-identical.
"""

from __future__ import annotations

import hashlib
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pyarrow.parquet as pq  # noqa: E402

from _common import (  # noqa: E402
    BLAS_CONTENT,
    LANGUAGE_DATA,
    LANGUAGE_NAMES,
    LANGUAGES,
    SEED,
    home_relative,
    in_bunamo,
    kaikki_forms,
    load_json,
    make_item,
    norm,
    unique,
    write_outputs,
)

SUITE = "blas"
TRANSLATION_TARGET = 60
ROUND_TRIP_TARGET = 40
CORPUS_QUOTA = 20  # of the 60, for Irish, Welsh and Breton
TRANSLATION_WORDS = (4, 30)
ROUND_TRIP_WORDS = (6, 25)
CORPUS_WORDS = (6, 40)

PARALLEL_DIR = LANGUAGE_DATA / "gold" / "text" / "parallel"
CORPORA = {
    "irish": {
        "pair": "gle_eng",
        "other": "English",
        "source": "gaois-parallel-irish",
        "attribution": (
            "Irish-English pairs: Gaois (Fiontar & Scoil na Gaeilge, DCU), Irish legislation "
            "and Constitution translation memory, licensed CC BY 4.0 "
            "(https://creativecommons.org/licenses/by/4.0/). Attribution required."
        ),
    },
    "welsh": {
        "pair": "cym_eng",
        "other": "English",
        "source": "senedd-legislation-parallel-cym-eng",
        "attribution": (
            "Welsh-English pairs: Senedd Cymru / Welsh Parliament and Welsh legislation, "
            "'Contains public sector information licensed under the Open Government Licence "
            "v3.0' (https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)."
        ),
    },
    "breton": {
        "pair": "bre_fra",
        "other": "French",
        "source": "ofis-publik-breton-french-corpus",
        "attribution": (
            "Breton-French pairs: Ofis Publik ar Brezhoneg parallel corpus, licensed CC BY 4.0 "
            "(https://creativecommons.org/licenses/by/4.0/). Attribution to Ofis Publik ar "
            "Brezhoneg required; no endorsement claim."
        ),
    },
}
CARD_NOTES = [
    "No DATASET_CARD.md exists inside gold/text/parallel/. Attribution text taken from "
    "derived/master-celtic-v1/sample_pack_10k/RIGHTS.md (provenance statement) and "
    "derived/productisation-v1/releases/run-20260919-v1/blas-bre-fra-translation-v1/RIGHTS.md.",
    "Per-language gold/text/<ga|cy|br>/DATASET_CARD.md cover the monolingual shards, not these "
    "parallel files; the parallel test split is described only by the sample-pack card "
    "(gle_eng 31,092 / cym_eng 73,546 / bre_fra 61,628 master pairs, hash-partitioned 90/5/5).",
]

# Sentence sources that belong to the app itself. Everything else is a public
# corpus that models may have trained on.
PRIVATE_SOURCES = {"sentence-bank", "hand-authored-earclip", "blas-course-attested"}
# Names in ``sources[]`` that annotate a sentence but are not its origin.
NOT_ORIGIN = {"vocabulary-cross-attest"}
NOT_ORIGIN_PREFIX = ("wave",)
PLACEHOLDERS = {"", "-", "n/a", "na", "none", "null", "?", "…"}
TIER_NAMES = ["private+approved", "public+approved", "private+deferred", "public+deferred"]

WORD_RE = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")


# --------------------------------------------------------------------------
# text helpers
# --------------------------------------------------------------------------

def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


def n_words(text: str) -> int:
    return len(text.split())


def balanced(text: str) -> bool:
    for open_, close in ("()", "[]", "{}"):
        if text.count(open_) != text.count(close):
            return False
    return text.count('"') % 2 == 0


SENTENCE_END = re.compile(r"[.?!]['\"”’»)]*$")
TRAILING_INITIAL = re.compile(r"\b[^\W\d_]\.$")


def sentence_like(text: str) -> bool:
    """Ends like a full sentence and not on an initial or abbreviation ("Andrew R.T.")."""
    return bool(SENTENCE_END.search(text)) and not TRAILING_INITIAL.search(text)


SENTENCE_MARK = re.compile(r"[.?!](?=\s|$|['\"”’»)])")


def aligned(native: str, english: str) -> bool:
    """Same number of sentences, and word counts within a factor of two (3+ English words)."""
    ratio = n_words(english) / max(n_words(native), 1)
    return (
        n_words(english) >= 3
        and 0.5 <= ratio <= 2.0
        and len(SENTENCE_MARK.findall(native)) == len(SENTENCE_MARK.findall(english))
    )


ACRONYM = re.compile(r"\b[A-ZÁÉÍÓÚŴŶ]{2,}\b")
TRAILING_NUMBER = re.compile(r"\s\d+\.?$")
QUOTES = re.compile(r"[“”\"«»„]")
# Pre-1958 Irish spelling and syntax that a modern translator will not reproduce.
OLD_IRISH = re.compile(r"\bnách\b|\bfé\b|\bi gcóir\b|\bdo (?:thabhairt|dhéanamh|chur|ghlaoch|léiriú|chros-cheistiú|ghabháil|bheith|dhul)\b|\w+adh lá\b|\bdo [bcdfgmpst]h\w+(?:ú|adh|amh|iú|áil|eamh)\b|\ba bheas\b|\bno\b|\bdhin\b|\bdintar\b|\bseirbheáil|\bla\b")


GARBLED = re.compile(r"[a-zà-ÿ][A-ZÀ-Ý]|[A-Za-z]\d{3,}[A-Za-z]|\S{25,}|\s[.,;:]($|\s)")


def title_case_heavy(text: str) -> bool:
    words = [w for w in text.split() if len(w) > 3 and w[0].isalpha()]
    return len(words) >= 4 and sum(1 for w in words[1:] if w[0].isupper()) / len(words) > 0.5


def corpus_pair_problem(source: str, target: str, pair: str) -> str | None:
    """Reason a corpus pair is unsafe as a one-reference translation test, or None."""
    if ACRONYM.search(source) or ACRONYM.search(target):
        return "acronym_or_all_caps"
    if TRAILING_NUMBER.search(source) or TRAILING_NUMBER.search(target):
        return "trailing_section_number"
    if QUOTES.search(source) or QUOTES.search(target):
        return "quoted_material"
    if GARBLED.search(source) or GARBLED.search(target):
        return "garbled_extraction"
    if title_case_heavy(source) or title_case_heavy(target):
        return "title_case_heading"
    if sorted(re.findall(r"\d+", source)) != sorted(re.findall(r"\d+", target)):
        return "numbers_differ"
    if len(SENTENCE_MARK.findall(source)) != len(SENTENCE_MARK.findall(target)):
        return "sentence_count_differs"
    if pair == "gle_eng" and OLD_IRISH.search(source):
        return "pre_standard_irish"
    return None


def stable_rng(*parts: object) -> random.Random:
    return random.Random(":".join(str(part) for part in (SEED, *parts)))


def digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


# --------------------------------------------------------------------------
# app sentences (source A)
# --------------------------------------------------------------------------

def difficulty_band(bands: dict[str, list[float]], score: float | None) -> str | None:
    if score is None:
        return None
    ordered = sorted(bands.items(), key=lambda pair: pair[1][0])
    band = ordered[0][0]
    for level, (low, _high) in ordered:
        if score >= low:
            band = level
    return band


def origin_of(sentence: dict[str, Any]) -> str | None:
    if sentence.get("source"):
        return sentence["source"]
    for entry in sentence.get("sources") or []:
        name = (entry or {}).get("name")
        if name and name not in NOT_ORIGIN and not name.startswith(NOT_ORIGIN_PREFIX):
            return name
    return None


def distinct_values(sentences: list[dict[str, Any]]) -> dict[str, Any]:
    def count(values) -> dict[str, int]:
        return dict(sorted(Counter(values).items(), key=lambda pair: (-pair[1], pair[0])))

    return {
        "source": count(s.get("source") for s in sentences),
        "sources[].name": count(
            (e or {}).get("name") for s in sentences for e in (s.get("sources") or [])
        ),
        "verificationStatus": count(s.get("verificationStatus") for s in sentences),
        "usageRestrictions": count(
            "+".join(sorted(s.get("usageRestrictions") or [])) or "(none)" for s in sentences
        ),
    }


def load_app_sentences(language: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Clean candidate sentences for one language, plus filter statistics."""
    path = BLAS_CONTENT / language / "sentences.json"
    data = load_json(path)
    difficulty = load_json(BLAS_CONTENT / language / "item-difficulty.json")
    bands, scores = difficulty["bands"], difficulty["items"]
    sentences = data["sentences"]
    stats: dict[str, Any] = {"raw": len(sentences), "distinct_values": distinct_values(sentences)}
    drops: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []
    for sentence in sentences:
        native = clean(sentence.get("native"))
        english = clean(sentence.get("english"))
        if sentence.get("_blocked"):
            drops["blocked"] += 1
        elif sentence.get("qualityFlags"):
            drops["quality_flags"] += 1
        elif sentence.get("verificationStatus") == "rejected":
            drops["rejected"] += 1
        elif "do-not-display" in (sentence.get("usageRestrictions") or []):
            drops["do_not_display"] += 1
        elif sentence.get("meaningAmbiguity") not in ("clear", "unknown", None):
            drops["ambiguous_meaning"] += 1
        elif norm(native) in PLACEHOLDERS or norm(english) in PLACEHOLDERS:
            drops["empty_or_placeholder"] += 1
        elif norm(native) == norm(english):
            drops["untranslated"] += 1
        elif not balanced(native) or not balanced(english):
            drops["unbalanced_brackets"] += 1
        elif not (sentence_like(native) and sentence_like(english)):
            drops["not_sentence_like"] += 1
        elif not aligned(native, english):
            drops["misaligned_length_or_sentence_count"] += 1
        elif "\n" in (sentence.get("native") or "") or "\n" in (sentence.get("english") or ""):
            drops["multi_line"] += 1
        elif n_words(native) < TRANSLATION_WORDS[0] or n_words(native) > TRANSLATION_WORDS[1]:
            drops["word_count_outside_4_30"] += 1
        else:
            origin = origin_of(sentence)
            approved = str(sentence.get("verificationStatus", "")).startswith("approved")
            private = origin in PRIVATE_SOURCES
            tier = (0 if approved else 2) + (0 if private else 1)
            score = scores.get(f"sentence:{sentence['id']}")
            cefr = difficulty_band(bands, score) or sentence.get("cefrLevel") or None
            references = unique([english, *[clean(t) for t in sentence.get("acceptedTranslations") or []]])
            reviewed = (
                sentence.get("reviewStatus") == "approved" or sentence.get("humanReviewed") is True
            )
            candidates.append(
                {
                    "id": sentence["id"],
                    "native": native,
                    "english": english,
                    "references": references,
                    "words": n_words(native),
                    "origin": origin or "unknown",
                    "contamination_risk": "private" if private else "public-source",
                    "verification_status": sentence.get("verificationStatus"),
                    "tier": tier,
                    "cefr": cefr,
                    "human_checked": bool(reviewed),
                }
            )
    # One sentence per native text and per English text, best tier first.
    candidates.sort(key=lambda c: (c["tier"], c["id"]))
    seen_native: set[str] = set()
    seen_english: set[str] = set()
    deduped = []
    for candidate in candidates:
        native_key, english_key = norm(candidate["native"]), norm(candidate["english"])
        if native_key in seen_native or english_key in seen_english:
            drops["duplicate_text"] += 1
            continue
        seen_native.add(native_key)
        seen_english.add(english_key)
        deduped.append(candidate)
    stats["dropped"] = dict(sorted(drops.items()))
    stats["candidates"] = len(deduped)
    stats["candidates_by_tier"] = {
        name: sum(1 for c in deduped if c["tier"] == index) for index, name in enumerate(TIER_NAMES)
    }
    stats["candidates_by_origin"] = dict(sorted(Counter(c["origin"] for c in deduped).items()))
    return deduped, stats


def pick(pool: list[dict[str, Any]], need: int, rng: random.Random) -> list[dict[str, Any]]:
    """Fill ``need`` items tier by tier (private first), spreading over CEFR levels."""
    chosen: list[dict[str, Any]] = []
    for tier in range(len(TIER_NAMES)):
        if len(chosen) >= need:
            break
        by_cefr: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for candidate in sorted(pool, key=lambda c: c["id"]):
            if candidate["tier"] == tier:
                by_cefr[str(candidate["cefr"])].append(candidate)
        for level in sorted(by_cefr):
            rng.shuffle(by_cefr[level])
        depth = 0
        while len(chosen) < need and any(depth < len(group) for group in by_cefr.values()):
            for level in sorted(by_cefr):
                if depth < len(by_cefr[level]) and len(chosen) < need:
                    chosen.append(by_cefr[level][depth])
            depth += 1
    return chosen


def split_directions(chosen: list[dict[str, Any]], rng: random.Random) -> dict[str, str]:
    """Alternate directions down the CEFR-sorted list so both are level-balanced."""
    ordered = sorted(chosen, key=lambda c: (str(c["cefr"]), rng.random()))
    first = rng.choice(["to_english", "from_english"])
    second = "from_english" if first == "to_english" else "to_english"
    return {c["id"]: (first if index % 2 == 0 else second) for index, c in enumerate(ordered)}


# --------------------------------------------------------------------------
# parallel corpus (source B)
# --------------------------------------------------------------------------

def corpus_candidates(language: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    info = CORPORA[language]
    pair = info["pair"]
    base = PARALLEL_DIR / pair
    test_path = base / f"parallel_{pair}_test.parquet"
    test_rows = pq.read_table(test_path).to_pylist()
    held_back_sources: set[str] = set()
    held_back_targets: set[str] = set()
    for split in ("train", "dev"):
        for row in pq.read_table(base / f"parallel_{pair}_{split}.parquet", columns=["source_text", "target_text"]).to_pylist():
            held_back_sources.add(norm(row["source_text"]))
            held_back_targets.add(norm(row["target_text"]))
    source_counts = Counter(norm(r["source_text"]) for r in test_rows)
    target_counts = Counter(norm(r["target_text"]) for r in test_rows)
    drops: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []
    strict_end = pair != "bre_fra"  # Breton pairs are mostly unpunctuated notices
    for index, row in enumerate(test_rows):
        if row["split"] != "test":
            drops["not_test_split"] += 1
            continue
        source, target = clean(row["source_text"]), clean(row["target_text"])
        words, target_words = n_words(source), n_words(target)
        if not CORPUS_WORDS[0] <= words <= CORPUS_WORDS[1]:
            drops["word_count_outside_6_40"] += 1
        elif not (0.7 <= target_words / words <= 1.7):
            drops["length_ratio"] += 1
        elif norm(source) in PLACEHOLDERS or norm(target) in PLACEHOLDERS or norm(source) == norm(target):
            drops["empty_or_untranslated"] += 1
        elif not (source[0].isalpha() and target[0].isalpha()):
            drops["starts_with_non_letter"] += 1
        elif strict_end and not (source[-1] in ".?!" and target[-1] in ".?!"):
            drops["no_sentence_end"] += 1
        elif strict_end and not (source[0].isupper() and target[0].isupper()):
            drops["starts_lowercase_clause"] += 1
        elif re.search(r"[;:,—–-]\s*[.?!]$", source) or re.search(r"[;:,—–-]\s*[.?!]$", target):
            drops["clause_fragment_ending"] += 1
        elif not (balanced(source) and balanced(target)):
            drops["unbalanced_brackets"] += 1
        elif re.search(r"https?://|@|www\.", source + " " + target):
            drops["url_or_email"] += 1
        elif (problem := corpus_pair_problem(source, target, pair)) is not None:
            drops[problem] += 1
        elif source_counts[norm(source)] > 1 or target_counts[norm(target)] > 1:
            drops["repeated_inside_test"] += 1
        elif norm(source) in held_back_sources or norm(target) in held_back_targets:
            drops["also_in_train_or_dev"] += 1
        else:
            candidates.append(
                {
                    "row": index,
                    "source": source,
                    "target": target,
                    "words": words,
                    "licence": row["license"],
                    "domain": row["domain"],
                    "pair": pair,
                }
            )
    stats = {
        "pair": pair,
        "test_rows": len(test_rows),
        "candidates": len(candidates),
        "dropped": dict(sorted(drops.items())),
        "licence": sorted({r["license"] for r in test_rows}),
        "domain": sorted({r["domain"] for r in test_rows}),
    }
    return candidates, stats


def pick_corpus(pool: list[dict[str, Any]], need: int, rng: random.Random) -> list[dict[str, Any]]:
    """Spread across three length bands, round-robin."""
    bands: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for candidate in sorted(pool, key=lambda c: c["row"]):
        bands[0 if candidate["words"] <= 12 else 1 if candidate["words"] <= 22 else 2].append(candidate)
    for band in bands.values():
        rng.shuffle(band)
    chosen: list[dict[str, Any]] = []
    depth = 0
    while len(chosen) < need and any(depth < len(group) for group in bands.values()):
        for key in sorted(bands):
            if depth < len(bands[key]) and len(chosen) < need:
                chosen.append(bands[key][depth])
        depth += 1
    return chosen


# --------------------------------------------------------------------------
# prompts and items
# --------------------------------------------------------------------------

def translation_prompt(source_lang: str, target_lang: str, text: str) -> str:
    return (
        f"Translate this {source_lang} sentence into {target_lang}.\n"
        f"Reply with the {target_lang} translation only, on one line, with no notes "
        f"or explanation.\n\n"
        f"{source_lang}: {text}\n"
    )


@lru_cache(maxsize=None)
def known_forms(language: str) -> frozenset[str]:
    forms: set[str] = set()
    for values in kaikki_forms(language).values():
        forms.update(values)
    return frozenset(forms)


def evidence_for_native_gold(language: str, text: str) -> str:
    """Evidence label when ``text`` (in the Celtic language) is the gold answer."""
    if language == "irish" and in_bunamo(text):
        return "blas-app+bunamo"
    forms = known_forms(language)
    if forms:
        words = [w for w in WORD_RE.findall(norm(text))]
        if words and all(word in forms for word in words):
            return "blas-app+kaikki"
    return "blas-app-only"


def app_evidence(candidate: dict[str, Any], language: str, native_is_gold: bool) -> str:
    """Evidence label for an app sentence; unverified sentences override everything."""
    if candidate["verification_status"] == "evidence-deferred":
        return "blas-app-unverified"
    return evidence_for_native_gold(language, candidate["native"]) if native_is_gold else "blas-app-only"


# Licence of the third-party source an app sentence came from. Evidence for each:
#   gaelg-parallel-usage: ~/Documents/blas/data/content/manx/grammar-lessons.json:226680 ("A-tier
#     gaelg-parallel-usage, GPL-3.0-or-later"); data/content/manx/LICENCE-lexicon.md:46 and
#     data/sources/manx/gaelg/LICENSE (GPL-3.0).
#   ud-*: data/scripts/build-celtic-corpus-sentences.py:60 ("ud-arcosg": "CC BY-SA 4.0").
# Everything else follows the rule given for the build; unknown names are "unstated".
SOURCE_LICENCES = {
    "sentence-bank": "private-blas",
    "tatoeba": "CC BY 2.0 FR (Tatoeba)",
    "tatoeba-cor-eng": "CC BY 2.0 FR (Tatoeba)",
    "tatoeba-glv-eng": "CC BY 2.0 FR (Tatoeba)",
    "gaelg-parallel-usage": "GPL-3.0 (Gaelg corpus)",
    "senedd-hansard": "OGL-v3 (Senedd Cymru)",
}


def source_licence(origin: str) -> str:
    if origin in SOURCE_LICENCES:
        return SOURCE_LICENCES[origin]
    if origin.startswith("kaikki-"):
        return "CC BY-SA 4.0 (Wiktionary via Kaikki)"
    if origin.startswith("wikipedia"):
        return "CC BY-SA 4.0 (Wikipedia)"
    if origin.startswith("ud-"):
        return "CC BY-SA 4.0 (UD ARCOSG)"
    return f"unstated (source: {origin})"


def app_source_fields(language: str, candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": f"blas-app:{candidate['origin']}",
        "source_id": f"sentences.json#{candidate['id']}",
        "source_path": home_relative(BLAS_CONTENT / language / "sentences.json"),
        "licence": source_licence(candidate["origin"]),
        "human_checked": candidate["human_checked"],
    }


def translation_item(language: str, candidate: dict[str, Any], direction: str) -> dict[str, Any]:
    name = LANGUAGE_NAMES[language]
    if direction == "to_english":
        src_lang, tgt_lang = name, "English"
        text, references = candidate["native"], candidate["references"]
        evidence = app_evidence(candidate, language, native_is_gold=False)
    else:
        src_lang, tgt_lang = "English", name
        text, references = candidate["english"], [candidate["native"]]
        evidence = app_evidence(candidate, language, native_is_gold=True)
    return make_item(
        id=f"blas-translation-{language}-{candidate['id']}-{direction}",
        prompt=translation_prompt(src_lang, tgt_lang, text),
        target=references[0],
        suite=SUITE,
        test="translation",
        scoring="translation",
        language=language,
        phenomenon=direction,
        cefr=candidate["cefr"],
        evidence=evidence,
        source_text=text,
        source_lang=src_lang,
        target_lang=tgt_lang,
        references=references,
        direction=direction,
        contamination_risk=candidate["contamination_risk"],
        verification_status=candidate["verification_status"],
        **app_source_fields(language, candidate),
    )


def corpus_item(language: str, row: dict[str, Any], direction: str) -> dict[str, Any]:
    info = CORPORA[language]
    name, other = LANGUAGE_NAMES[language], info["other"]
    if direction == "to_other":
        src_lang, tgt_lang, text, reference = name, other, row["source"], row["target"]
    else:
        src_lang, tgt_lang, text, reference = other, name, row["target"], row["source"]
    return make_item(
        id=f"blas-translation-{language}-{row['pair']}-test-{row['row']:05d}-{direction}",
        prompt=translation_prompt(src_lang, tgt_lang, text),
        target=reference,
        suite=SUITE,
        test="translation",
        scoring="translation",
        language=language,
        phenomenon="legal_or_administrative",
        cefr=None,
        source=info["source"],
        source_id=f"{row['pair']}:test:row-{row['row']}:{digest(row['source'])}",
        source_path=home_relative(PARALLEL_DIR / row["pair"] / f"parallel_{row['pair']}_test.parquet"),
        licence=row["licence"],
        evidence="corpus-reference",
        human_checked=False,
        source_text=text,
        source_lang=src_lang,
        target_lang=tgt_lang,
        references=[reference],
        direction=f"{'to' if direction == 'to_other' else 'from'}_{other.lower()}",
        contamination_risk="public-source",
        domain=row["domain"],
    )


def round_trip_item(language: str, candidate: dict[str, Any]) -> dict[str, Any]:
    name = LANGUAGE_NAMES[language]
    return make_item(
        id=f"blas-round_trip-{language}-{candidate['id']}",
        prompt=translation_prompt(name, "English", candidate["native"]),
        target=candidate["native"],
        suite=SUITE,
        test="round_trip",
        scoring="round_trip",
        language=language,
        phenomenon="round_trip",
        cefr=candidate["cefr"],
        evidence=app_evidence(candidate, language, native_is_gold=True),
        source_text=candidate["native"],
        source_lang=name,
        pivot_lang="English",
        direction="to_english_and_back",
        contamination_risk=candidate["contamination_risk"],
        verification_status=candidate["verification_status"],
        **app_source_fields(language, candidate),
    )


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def cross_tab(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, int]]:
    table: dict[str, Counter[str]] = defaultdict(Counter)
    for item in items:
        meta = item["metadata"]
        table[meta["language"]][str(meta[key])] += 1
    return {lang: dict(sorted(table[lang].items())) for lang in sorted(table)}


def main() -> None:
    translation: list[dict[str, Any]] = []
    round_trip: list[dict[str, Any]] = []
    per_language: dict[str, Any] = {}
    shortfalls: dict[str, dict[str, str]] = {"translation": {}, "round_trip": {}}

    for language in LANGUAGES:
        pool, stats = load_app_sentences(language)

        # Round trip first: its 6-25 word window is the scarcer pool.
        rt_pool = [c for c in pool if ROUND_TRIP_WORDS[0] <= c["words"] <= ROUND_TRIP_WORDS[1]]
        rt_chosen = pick(rt_pool, ROUND_TRIP_TARGET, stable_rng(language, "round_trip"))
        rt_ids = {c["id"] for c in rt_chosen}

        corpus_stats = None
        corpus_chosen: list[dict[str, Any]] = []
        if language in CORPORA:
            corpus_pool, corpus_stats = corpus_candidates(language)
            corpus_chosen = pick_corpus(corpus_pool, CORPUS_QUOTA, stable_rng(language, "corpus"))
            if len(corpus_chosen) < CORPUS_QUOTA:
                shortfalls["translation"][f"{language}:corpus"] = (
                    f"{len(corpus_chosen)} of {CORPUS_QUOTA} corpus rows"
                )
        app_need = TRANSLATION_TARGET - len(corpus_chosen)
        tr_pool = [c for c in pool if c["id"] not in rt_ids]
        tr_chosen = pick(tr_pool, app_need, stable_rng(language, "translation"))
        if len(rt_chosen) < ROUND_TRIP_TARGET:
            shortfalls["round_trip"][language] = f"{len(rt_chosen)} of {ROUND_TRIP_TARGET}"
        if len(tr_chosen) < app_need:
            shortfalls["translation"][f"{language}:app"] = f"{len(tr_chosen)} of {app_need}"

        directions = split_directions(tr_chosen, stable_rng(language, "directions"))
        for candidate in tr_chosen:
            translation.append(translation_item(language, candidate, directions[candidate["id"]]))
        # Corpus rows alternate direction down the row order for an even split.
        for position, row in enumerate(sorted(corpus_chosen, key=lambda r: r["row"])):
            translation.append(corpus_item(language, row, "to_other" if position % 2 == 0 else "from_other"))
        for candidate in rt_chosen:
            round_trip.append(round_trip_item(language, candidate))

        per_language[language] = {
            "app": stats,
            "corpus": corpus_stats,
            "translation_app_selected": len(tr_chosen),
            "translation_corpus_selected": len(corpus_chosen),
            "round_trip_selected": len(rt_chosen),
            "translation_by_tier": {
                name: sum(1 for c in tr_chosen if c["tier"] == index) for index, name in enumerate(TIER_NAMES)
            },
            "round_trip_by_tier": {
                name: sum(1 for c in rt_chosen if c["tier"] == index) for index, name in enumerate(TIER_NAMES)
            },
        }

    # The two tests must not share a sentence.
    translation_keys = {
        norm(item["metadata"]["source_text"]) for item in translation
    } | {norm(ref) for item in translation for ref in item["metadata"]["references"]}
    for item in round_trip:
        if norm(item["metadata"]["source_text"]) in translation_keys:
            raise ValueError(f"{item['id']} also appears in blas/translation")
    translation_source_ids = {item["metadata"]["source_id"] for item in translation}
    overlap = translation_source_ids & {item["metadata"]["source_id"] for item in round_trip}
    if overlap:
        raise ValueError(f"source ids in both tests: {sorted(overlap)[:5]}")

    common = {
        "human_checked_field": (
            "metadata.human_checked is true only when a sentence has reviewStatus == 'approved' "
            "or humanReviewed == true. No sentence in any of the six languages carries either "
            "field, so every item is human_checked=false. verificationStatus values such as "
            "'approved-blind-artifact-audit' are NOT treated as human review; they are copied "
            "into metadata.verification_status."
        ),
        "fields_used": {
            "sentences": [
                "native", "english", "acceptedTranslations", "cefrLevel", "source",
                "sources[].name", "verificationStatus", "usageRestrictions", "qualityFlags",
                "_blocked", "meaningAmbiguity", "reviewStatus", "humanReviewed",
            ],
            "item-difficulty.json": "items['sentence:<id>'] score mapped through bands; cefrLevel when no key",
        },
        "filters": {
            "app": [
                "skip _blocked, non-empty qualityFlags, verificationStatus 'rejected', "
                "usageRestrictions containing 'do-not-display'",
                "skip empty/placeholder text, native == english, unbalanced brackets",
                "both sides must end in . ? or ! (optionally followed by a quote or bracket) and not on a "
                "single-letter initial, which removes truncated Hansard sentences and fragments",
                "English side has 3+ words, English/native word ratio 0.5-2.0, and both sides have the same "
                "number of sentence-final marks (drops glosses such as 'Was it this morning you came? Yes.')",
                "4-30 words for translation, 6-25 words for round_trip (whitespace split of the native text)",
                "one sentence per normalized native text and per normalized English text",
            ],
            "corpus": [
                "split == 'test' only, 6-40 source words, target/source word ratio 0.7-1.7",
                "both sides start with a letter; Irish and Welsh rows must start with a capital and end in . ? or !",
                "no side may end in a clause mark followed by a full stop (';.', '—.')",
                "no garbled PDF extraction (glued words, lower-to-upper case jumps, 25+ character tokens, space before punctuation)",
                "no all-caps acronyms (they differ by language), no trailing section numbers, no quoted "
                "material, no title-case heading runs, identical digit sets, equal sentence-mark counts, "
                "and for Irish no pre-1958 spelling or syntax (nách, fé, i gcóir, unaccented 'no', 'a bheas', dhin/dintar, 'do' + verbal noun, -adh lá)",
                "balanced brackets, no URLs or e-mail addresses",
                "drop rows whose source or target text repeats inside the test split or "
                "also occurs in the train or dev split (leakage guard)",
            ],
        },
        "selection_order": (
            "Candidates are ranked: private+approved, public+approved, private+deferred, "
            "public+deferred (verificationStatus starting 'approved' = approved; 'evidence-deferred' = "
            "deferred). Each tier is filled before the next, spread round-robin over CEFR levels. "
            "Private = the app's own bank (sentence-bank, hand-authored-earclip, blas-course-attested); "
            "all others (tatoeba, wikipedia, senedd-hansard, common-voice-cy, gaelg-parallel-usage, "
            "kaikki, ofis-publik, ...) are public-source."
        ),
        "corpus_attribution": {language: info["attribution"] for language, info in CORPORA.items()},
        "corpus_card_notes": CARD_NOTES,
        "breton_pivot_note": (
            "Breton corpus rows are Breton<->French pairs; their prompts use French as the other "
            "language and metadata.target_lang/source_lang say French."
        ),
        "per_language": per_language,
        "shortfalls": shortfalls,
    }

    t_report = {
        **common,
        "by_contamination_risk": cross_tab(translation, "contamination_risk"),
        "by_direction": cross_tab(translation, "direction"),
        "by_language_phenomenon": cross_tab(translation, "phenomenon"),
        "target": {"per_language": TRANSLATION_TARGET, "total": TRANSLATION_TARGET * len(LANGUAGES)},
    }
    r_report = {
        **common,
        "by_contamination_risk": cross_tab(round_trip, "contamination_risk"),
        "by_direction": cross_tab(round_trip, "direction"),
        "target": {"per_language": ROUND_TRIP_TARGET, "total": ROUND_TRIP_TARGET * len(LANGUAGES)},
    }
    t_full = write_outputs(SUITE, "translation", translation, t_report)
    r_full = write_outputs(SUITE, "round_trip", round_trip, r_report)
    print(f"translation: {t_full['n_items']} items; round_trip: {r_full['n_items']} items")


if __name__ == "__main__":
    main()
