"""Shared helpers for the dataset build scripts.

Build scripts copy gold strings from source files. They never contain gold
strings themselves. Each script writes three files:

- ``data/private/<suite>/<test>.jsonl``: the full set (git-ignored).
- ``samples/<suite>/<test>.jsonl``: 20 public sample items.
- ``data/build-reports/<suite>_<test>.json``: counts, shortfalls and sources.
"""

from __future__ import annotations

import gzip
import json
import random
import re
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

SEED = 20261115
SAMPLE_SIZE = 20

REPO = Path(__file__).resolve().parents[1]
HOME = Path.home()
BLAS = HOME / "Documents" / "blas"
BLAS_CONTENT = BLAS / "data" / "content"
BLAS_SOURCES = BLAS / "data" / "sources"
BLAS_ENGLISH = HOME / "Documents" / "blas-english"
LANGUAGE_DATA = HOME / "Documents" / "language-data"
GEC_ARTIFACTS = BLAS / "blas-gec-artifacts"

LANGUAGES = ["irish", "welsh", "scots-gaelic", "manx", "breton", "cornish"]
LANGUAGE_NAMES = {
    "irish": "Irish",
    "welsh": "Welsh",
    "scots-gaelic": "Scottish Gaelic",
    "manx": "Manx",
    "breton": "Breton",
    "cornish": "Cornish",
    "english": "English",
}
KAIKKI_LOCAL = {
    "irish": BLAS_SOURCES / "irish" / "kaikki-irish.jsonl",
    "manx": BLAS_SOURCES / "manx" / "kaikki-manx.jsonl",
    "cornish": BLAS_SOURCES / "cornish" / "kaikki-cornish.jsonl",
    "scots-gaelic": BLAS_SOURCES / "scots-gaelic" / "kaikki-scottish-gaelic.jsonl",
}

ANSWER_FORMAT = "Reply with the answer on one line, in this exact form:\nANSWER: <answer>"

REQUIRED_METADATA = (
    "suite", "test", "scoring", "language", "l1", "phenomenon", "cefr",
    "source", "source_id", "source_path", "licence", "evidence", "human_checked",
)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def home_relative(path: Path) -> str:
    """Path as recorded in ``source_path``: relative to the home directory."""
    return str(Path(path).resolve().relative_to(HOME))


def norm(text: str) -> str:
    """Comparison key: NFC, straight apostrophes, single spaces, casefold."""
    text = unicodedata.normalize("NFC", text or "")
    text = text.translate({0x2019: "'", 0x2018: "'", 0x02BC: "'"})
    return re.sub(r"\s+", " ", text).strip().rstrip(" .").casefold()


def unique(values: Iterable[str]) -> list[str]:
    """Drop empty strings and duplicates (by ``norm``), keep first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        key = norm(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value.strip())
    return out


def make_item(
    *,
    id: str,
    prompt: str,
    target: str,
    suite: str,
    test: str,
    scoring: str,
    language: str,
    phenomenon: str,
    source: str,
    source_id: str,
    source_path: Path | str,
    licence: str,
    evidence: str,
    cefr: str | None = None,
    l1: str = "none",
    human_checked: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    """Build one item in the contract format. ``extra`` holds scoring fields."""
    if scoring == "accept_list":
        accept = unique(extra.get("accept") or [])
        if not accept:
            raise ValueError(f"{id}: accept_list item has no accepted answer")
        extra["accept"] = accept
        target = accept[0]
        prompt = prompt.rstrip() + "\n" + ANSWER_FORMAT + "\n"
    metadata = {
        "suite": suite,
        "test": test,
        "scoring": scoring,
        "language": language,
        "l1": l1,
        "phenomenon": phenomenon,
        "cefr": cefr,
        "source": source,
        "source_id": source_id,
        "source_path": source_path if isinstance(source_path, str) else home_relative(source_path),
        "licence": licence,
        "evidence": evidence,
        "human_checked": bool(human_checked),
        **extra,
    }
    return {"id": id, "input": prompt, "target": target, "metadata": metadata}


def stratified_sample(
    items: list[dict[str, Any]],
    total: int,
    keys: tuple[str, ...] = ("language", "phenomenon"),
    seed: int = SEED,
) -> list[dict[str, Any]]:
    """Take up to ``total`` items, spread evenly over the strata.

    Strata are filled round-robin, so a small stratum gives all it has and the
    rest of the quota moves to the larger strata. Items are de-duplicated by
    id and by normalized prompt first. The result is the same for the same
    input and seed.
    """
    seen_ids: set[str] = set()
    seen_prompts: set[str] = set()
    pools: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for item in sorted(items, key=lambda entry: entry["id"]):
        prompt_key = norm(item["input"])
        if item["id"] in seen_ids or prompt_key in seen_prompts:
            continue
        seen_ids.add(item["id"])
        seen_prompts.add(prompt_key)
        pools[tuple(str(item["metadata"].get(key)) for key in keys)].append(item)
    rng = random.Random(seed)
    for stratum in sorted(pools):
        rng.shuffle(pools[stratum])
    chosen: list[dict[str, Any]] = []
    depth = 0
    while len(chosen) < total:
        added = False
        for stratum in sorted(pools):
            if depth < len(pools[stratum]) and len(chosen) < total:
                chosen.append(pools[stratum][depth])
                added = True
        if not added:
            break
        depth += 1
    return sorted(chosen, key=lambda entry: entry["id"])


def write_outputs(
    suite: str,
    test: str,
    items: list[dict[str, Any]],
    report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write the private full set, the public sample and the build report."""
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{suite}/{test}: duplicate item ids")
    for item in items:
        missing = [field for field in REQUIRED_METADATA if field not in item["metadata"]]
        if missing:
            raise ValueError(f"{item['id']}: missing metadata {missing}")
    items = sorted(items, key=lambda entry: entry["id"])
    sample = list(items)
    random.Random(SEED).shuffle(sample)
    sample = sorted(sample[:SAMPLE_SIZE], key=lambda entry: entry["id"])
    _write_jsonl(REPO / "data" / "private" / suite / f"{test}.jsonl", items)
    _write_jsonl(REPO / "samples" / suite / f"{test}.jsonl", sample)
    _write_attribution(REPO / "samples" / suite / f"{test}.ATTRIBUTION.md", suite, test, sample)

    def count(field: str) -> dict[str, int]:
        return dict(sorted(Counter(str(item["metadata"].get(field)) for item in items).items()))

    full_report = {
        "suite": suite,
        "test": test,
        "seed": SEED,
        "n_items": len(items),
        "n_public_sample": len(sample),
        "by_language": count("language"),
        "by_l1": count("l1"),
        "by_phenomenon": count("phenomenon"),
        "by_cefr": count("cefr"),
        "by_evidence": count("evidence"),
        "by_licence": count("licence"),
        "human_checked": sum(1 for item in items if item["metadata"]["human_checked"]),
        **(report or {}),
    }
    path = REPO / "data" / "build-reports" / f"{suite}_{test}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(full_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return full_report


ATTRIBUTION_NOTICES = {
    "private-blas": "Blas app content. Copyright Blas. Published here as benchmark samples.",
    "private-tonada": "Tonada app content. Copyright Tonada. Published here as benchmark samples.",
    "Tatoeba": "Sentences from Tatoeba (https://tatoeba.org), licensed CC BY 2.0 FR.",
    "Gaelg": "Sentences from the Gaelg Manx corpus, licensed GPL-3.0.",
    "CC BY-SA 4.0": (
        "Text from Wikipedia (https://www.wikipedia.org) or from Wiktionary via Kaikki (https://kaikki.org), "
        "licensed CC BY-SA 4.0. Items derived from that text are shared under the same licence."
    ),
    "WikiEdits": (
        "Edit pairs from WikiEdits-MultiGEC "
        "(https://huggingface.co/datasets/lang-uk/WikiEdits-MultiGEC), dataset licensed MIT."
    ),
    "OGL": "Contains public sector information licensed under the Open Government Licence v3.0.",
    "CC BY 4.0": (
        "Irish and English legislation text from Gaois (Fiontar & Scoil na Gaeilge, DCU), and Breton and "
        "French text from Ofis Publik ar Brezhoneg, licensed CC BY 4.0. No endorsement is implied."
    ),
}


def _write_attribution(path: Path, suite: str, test: str, sample: list[dict[str, Any]]) -> None:
    """Write the sources, licences and notices for one public sample file."""
    pairs = Counter((item["metadata"]["source"], item["metadata"]["licence"]) for item in sample)
    lines = [
        f"# Attribution for samples/{suite}/{test}.jsonl",
        "",
        "Each item also records its own `source` and `licence`.",
        "",
        "| Source | Licence | Items |",
        "|---|---|---|",
    ]
    lines += [f"| {source} | {licence} | {count} |" for (source, licence), count in sorted(pairs.items())]
    licences = " ".join(licence for _, licence in pairs)
    notices = [text for key, text in ATTRIBUTION_NOTICES.items() if key in licences]
    lines += ["", "## Notices", ""] + [f"- {text}" for text in notices]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in items]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@lru_cache(maxsize=1)
def bunamo_surfaces() -> dict[str, list[str]]:
    """Irish surface form -> BÚNaMo lemmas (ODbL). Used to cross-check gold."""
    with gzip.open(REPO / "data" / "bunamo-surfaces.json.gz", "rt", encoding="utf-8") as handle:
        return json.load(handle)


def in_bunamo(form: str) -> bool:
    """True when every word of an Irish form is a BÚNaMo surface form."""
    surfaces = bunamo_surfaces()
    words = re.findall(r"[^\W\d_]+(?:['-][^\W\d_]+)*", norm(form))
    return bool(words) and all(word in surfaces for word in words)


@lru_cache(maxsize=None)
def kaikki_forms(language: str) -> dict[str, set[str]]:
    """Headword -> every inflected form Kaikki lists (CC BY-SA 4.0).

    Covers Irish, Manx, Cornish and Scottish Gaelic, from the local extracts.
    Returns an empty dict for a language with no local extract.
    """
    path = KAIKKI_LOCAL.get(language)
    index: dict[str, set[str]] = defaultdict(set)
    if path is None or not path.is_file():
        return index
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            entry = json.loads(line)
            word = norm(entry.get("word", ""))
            if not word:
                continue
            index[word].add(word)
            for form in entry.get("forms") or []:
                tags = form.get("tags") or []
                text = form.get("form")
                if text and "error-unrecognized-form" not in tags and text != "-":
                    index[word].add(norm(text))
    return index
