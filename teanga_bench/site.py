"""Static research site built from the results files.

``build_site(results_dir, out_dir)`` reads ``<results_dir>/runs/*.json`` and
writes plain HTML, one stylesheet and inline SVG charts:

    site/suites.html                       index of both suites (preview host only)
    site/assets/site.css
    site/<suite>/index.html                leaderboard, model x test table, cards that link onward
    site/<suite>/tests.html                every test, one tab each: the task, a real item, marking, results
    site/<suite>/findings.html             charts of what the results show, each with a computed takeaway
    site/<suite>/languages.html            Blas: scores by language
    site/<suite>/learners.html             Tonada: scores by the learner's first language
    site/<suite>/models.html               every ranked model as a card, score against cost
    site/<suite>/models/<model-slug>.html  one model: summary, then collapsible detail
    site/<suite>/methodology.html          one-minute summary, docs/methodology.md, test sets
    site/<suite>/data/leaderboard.json     the suite's slice of the leaderboard

Both suites share one layout; only the accent colour differs. Links between
pages are relative, so pages work under ``/blas/`` and under a host that
rewrites ``/`` to ``/blas/``. The suite switcher links to the other domain and
a small script points it at the local copy on any other host. The build is
deterministic: the only date on the pages is the newest run's
``generated_at``. Model output is untrusted and is always escaped as text.
Every page reads fully with JavaScript off: the script only adds sorting,
'Show all', tabs and copy-link. Every chart opens with a takeaway sentence
computed in ``site_findings`` and keeps its exact numbers in a 'View as
table' disclosure.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import statistics
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Callable, Iterable

from teanga_bench import BENCHMARK, BENCHMARK_NAME, __version__
from teanga_bench.export import EXPLANATION_SCORED, SCHEMA_VERSION
from teanga_bench.leaderboard import BLAS_LANGUAGES, load_runs
from teanga_bench.markdown_lite import markdown_to_html
from teanga_bench.models_config import configured_judges
from teanga_bench.paths import REPO_ROOT
from teanga_bench.site_charts import (
    PERCENT_TICKS,
    BarRow,
    DotRow,
    Mark,
    ScatterPoint,
    Series,
    dot_rows,
    heat_style,
    interval_bar,
    interval_short,
    interval_words,
    line_chart,
    mini_bar,
    money,
    money_axis,
    nice_domain,
    pct,
    radar,
    ranked_bars,
    scatter,
    score_ticks,
    swatch,
)
from teanga_bench.site_css import SITE_CSS
from teanga_bench.site_findings import (
    MIN_ITEMS,
    Est,
    compare_sentence,
    correlation_sentence,
    direction_sentence,
    group_sentence,
    leader_sentence,
    level_sentence,
    matrix_sentence,
    ordinal,
    overlaps,
    profile_sentence,
    spread_sentence,
    tie_groups,
    tied_with,
    tutor_sentence,
    topic_language_sentence,
    value_sentence,
)

SITE = REPO_ROOT / "site"
REPO_URL = "https://github.com/johnway114/teanga-bench"
DOCS_BASE_URL = f"{REPO_URL}/blob/main"
PUBLIC_SAMPLE_SIZE = 20
MIN_TOPIC_ITEMS = 5
TOPIC_COUNT = 5
LEADERBOARD_TOP = 5
GENERATED_DIRS = ("assets", "blas", "tonada")
GENERATED_FILES = ("suites.html",)
CEFR_ORDER = ("A1", "A2", "B1", "B2", "C1", "C2")
MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


class SiteError(RuntimeError):
    """The site cannot be built safely from these results."""


@dataclass(frozen=True)
class SuiteInfo:
    key: str
    short: str
    name: str
    topic: str
    description: str
    url: str
    headline: str
    intro: str
    statement: str
    measured: str
    group_field: str
    group_label: str
    group_order: tuple[str, ...]
    group_page: str
    group_nav: str
    group_title: str


SUITES: dict[str, SuiteInfo] = {
    "blas": SuiteInfo(
        key="blas",
        short="Blas",
        name="Blas suite",
        topic="Celtic languages",
        description="Irish, Welsh, Scottish Gaelic, Manx, Breton and Cornish",
        url="https://research.blasapp.com/",
        headline="How well do AI models handle the Celtic languages?",
        intro=(
            "Teanga Bench tests large language models on Irish, Welsh, Scottish Gaelic, Manx, Breton "
            "and Cornish, with items taken from the Blas course, dictionaries and parallel corpora."
        ),
        statement=(
            "Teanga Bench measures how well large language models handle six Celtic languages: "
            "Irish, Welsh, Scottish Gaelic, Manx, Breton and Cornish. Every model answers the same "
            "few hundred items per test, taken from the Blas course, dictionaries and parallel "
            "corpora: lesson exercises, word forms, translation, round-trip translation, and finding "
            "and fixing errors as a tutor would. Each item is asked several times. The score is the "
            "share of items answered correctly; translation tests give partial credit for closeness "
            "to reference translations."
        ),
        measured=(
            "How well language models do a tutor's work in Irish, Welsh, Scottish Gaelic, Manx, Breton "
            "and Cornish: lesson exercises, word forms, translation, round-trip translation, and finding "
            "and fixing errors."
        ),
        group_field="by_language",
        group_label="Language",
        group_order=BLAS_LANGUAGES,
        group_page="languages",
        group_nav="Languages",
        group_title="Results by language",
    ),
    "tonada": SuiteInfo(
        key="tonada",
        short="Tonada",
        name="Tonada suite",
        topic="English tutoring",
        description="English tutoring for Portuguese, Spanish, Vietnamese and Japanese speakers",
        url="https://research.tonadaapp.com/",
        headline="How well do AI models tutor English?",
        intro=(
            "Teanga Bench tests large language models on English tutoring for speakers of Portuguese, "
            "Spanish, Vietnamese and Japanese, with items taken from the Tonada course and real English edits."
        ),
        statement=(
            "Teanga Bench measures how well large language models tutor English for people whose "
            "first language is Portuguese, Spanish, Vietnamese or Japanese. Every model answers the "
            "same few hundred items per test, taken from the Tonada course and a public corpus of "
            "sentence edits: closed exercises with the instruction in the learner's language, and "
            "finding and fixing errors in English sentences as a tutor would. Each item is asked "
            "several times. The score is the share of items answered correctly."
        ),
        measured=(
            "How well language models tutor English for speakers of Portuguese, Spanish, Vietnamese and "
            "Japanese: lesson exercises with the instruction in the learner's language, and finding and "
            "fixing errors in English sentences."
        ),
        group_field="by_l1",
        group_label="First language",
        group_order=("portuguese", "spanish", "vietnamese", "japanese"),
        group_page="learners",
        group_nav="Learners",
        group_title="Results by first language",
    ),
}

TEST_INFO: dict[tuple[str, str], tuple[str, str]] = {
    ("blas", "lesson_exercises"): (
        "Lesson exercises",
        "Multiple-choice, word-order and fill-the-gap questions from the Blas course, marked against the course's accepted answers.",
    ),
    ("blas", "morphology"): (
        "Word forms",
        "Give one inflected form, such as a verb tense, a plural or a prepositional pronoun, marked against a list of accepted forms.",
    ),
    ("blas", "translation"): (
        "Translation",
        "Translate a sentence into or out of the language, scored by chrF++ similarity to one or more reference translations.",
    ),
    ("blas", "round_trip"): (
        "Round trip",
        "Translate a sentence into another language, then back again in a fresh conversation, scored by chrF++ similarity to the original.",
    ),
    ("blas", "tutor_accuracy"): (
        "Tutor accuracy",
        "Find and fix the error in a sentence, or leave a correct sentence alone; an item counts only when the error is found and fixed and nothing else is changed.",
    ),
    ("tonada", "exercises"): (
        "Lesson exercises",
        "Closed English exercises from the Tonada course, with the instruction in the learner's first language, marked against the accepted answers.",
    ),
    ("tonada", "tutor_accuracy"): (
        "Tutor accuracy",
        "Find and fix the error in an English sentence, or leave a correct sentence alone; an item counts only when the error is found and fixed and nothing else is changed.",
    ),
}

SCORING_INFO = {
    "accept_list": "Short answers marked against a list of accepted answers.",
    "tutor": "Find and fix an error, or leave a correct sentence alone.",
    "translation": "Translation scored by chrF++ similarity to reference translations.",
    "round_trip": "Translation there and back, scored by chrF++ similarity to the original.",
}

# For the Tests page: what the model is asked to do, how the answer is marked,
# and what the item's topic label means. Consistent with docs/methodology.md.
TEST_EXPLAIN: dict[tuple[str, str], tuple[str, str, str]] = {
    ("blas", "lesson_exercises"): (
        "Answer one exercise from the Blas course: pick the right option, put words in order or fill a gap.",
        "By rule: the answer must match one of the course's accepted answers; case, apostrophe style and outer "
        "spaces do not matter.",
        "course category",
    ),
    ("blas", "morphology"): (
        "Give one word form, such as a verb in a given tense, a plural, a number or a preposition fused with a pronoun.",
        "By rule: the form must match one of the accepted forms from the course tables.",
        "grammar topic",
    ),
    ("blas", "translation"): (
        "Translate one sentence into English or out of English, or a sentence of legal or administrative text "
        "(paired with French for Breton).",
        "By rule: chrF++, the overlap of characters and words with a reference translation, from 0 to 100%, so "
        "close translations get partial credit.",
        "direction",
    ),
    ("blas", "round_trip"): (
        "Translate a sentence into English, then, in a new conversation, translate that English back.",
        "By rule: chrF++ overlap between the sentence that comes back and the original.",
        "topic",
    ),
    ("blas", "tutor_accuracy"): (
        "Check a learner's sentence: say whether it has an error, give the wrong words and the correction, and explain.",
        "By rule: an item counts only when the error is found and fixed and nothing else changes, or a correct "
        "sentence is left alone. Two judge models mark the explanation separately.",
        "course category",
    ),
    ("tonada", "exercises"): (
        "Answer one closed exercise from the Tonada English course, with the instruction in the learner's first language.",
        "By rule: the answer must match one of the course's accepted answers.",
        "lesson topic",
    ),
    ("tonada", "tutor_accuracy"): (
        "Check an English sentence written by a learner: say whether it has an error, give the wrong words and the "
        "correction, and explain in the learner's language.",
        "By rule: an item counts only when the error is found and fixed and nothing else changes, or a correct "
        "sentence is left alone. Two judge models mark the explanation separately.",
        "error type",
    ),
}
DEFAULT_EXPLAIN = ("", "", "topic")

# Plain names for the evidence labels in docs/methodology.md.
EVIDENCE_NAMES = {
    "blas-app+bunamo": "Course, form listed in BÚNaMo",
    "blas-app+kaikki": "Course, form listed in Kaikki",
    "blas-app-only": "Course only",
    "blas-app-unverified": "Course, marked unverified",
    "corpus-reference": "Parallel corpus",
    "distractor-derived-unverified": "Built from exercise options",
    "planted-typo": "Planted typo",
    "tonada-app-machine-reviewed": "Course, machine-reviewed",
    "tonada-app-distractor-machine-reviewed": "Built from exercise options",
    "tonada-app-answer-machine-reviewed": "Correct course sentence",
    "wikipedia-revision-silver-unreviewed": "Wikipedia edit, unreviewed",
}

GROUP_NAMES = {
    "irish": "Irish",
    "welsh": "Welsh",
    "scots-gaelic": "Scottish Gaelic",
    "manx": "Manx",
    "breton": "Breton",
    "cornish": "Cornish",
    "english": "English",
    "portuguese": "Portuguese",
    "spanish": "Spanish",
    "vietnamese": "Vietnamese",
    "japanese": "Japanese",
    "none": "None",
    "unspecified": "Unspecified",
    "None": "Unspecified",
}

# OpenRouter provider prefixes as their makers write them. An unknown prefix is
# shown as it is.
PROVIDER_NAMES = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "deepseek": "DeepSeek",
    "qwen": "Qwen",
    "mistralai": "Mistral AI",
    "meta": "Meta",
    "meta-llama": "Meta",
    "x-ai": "xAI",
    "z-ai": "Z.ai",
    "moonshotai": "Moonshot AI",
    "nvidia": "NVIDIA",
    "amazon": "Amazon",
    "cohere": "Cohere",
    "minimax": "MiniMax",
    "perplexity": "Perplexity",
    "tencent": "Tencent",
    "xiaomi": "Xiaomi",
    "baidu": "Baidu",
    "bytedance-seed": "ByteDance Seed",
}
# Words in model ids that are not simply capitalised.
NAME_WORDS = {"gpt": "GPT", "glm": "GLM", "oss": "OSS", "deepseek": "DeepSeek", "minimax": "MiniMax", "vl": "VL", "ai": "AI"}

HOWTO_POINTS = (
    "<strong>Score</strong> is the share of items answered correctly, averaged over repeat asks. "
    "Translation tests give partial credit. Every test counts equally.",
    "<strong>The thin line</strong> on each bar is the 95% range. When two models' ranges overlap, "
    "the gap between them may be chance.",
    "<strong>Sources, not reviewers.</strong> Items and answers come from the named sources and were not "
    "reviewed by people. Tutor explanations are marked by judge models and shown separately.",
)

RANGE_HINT = "95% range: the score would fall in this range in 95% of resamples of the items."


def _one_minute(suite: SuiteInfo) -> tuple[str, ...]:
    """The methodology summary. Plain text, consistent with docs/methodology.md."""
    return (
        f"<strong>What is measured.</strong> {e(suite.measured)}",
        "<strong>Where items come from.</strong> Every item and answer is copied from a named source, or "
        "derived from one by a documented rule: the Blas and Tonada app content, parallel corpora, "
        "Wikipedia edits and reference dictionaries. No language model wrote an answer for the benchmark.",
        "<strong>No human review.</strong> No person has reviewed the items. A score measures agreement "
        "with the sources, and a few gold answers will be wrong.",
        "<strong>Private sets, public samples.</strong> The full item sets stay private so that they do "
        f"not end up in training data. {PUBLIC_SAMPLE_SIZE} items per test are public, and only those "
        "appear as failure examples.",
        "<strong>Marking.</strong> Answers are marked by fixed rules: a list of accepted answers, or "
        "chrF++ overlap for translation. Two judge models mark only tutor explanations, which are a "
        "separate, secondary score.",
        "<strong>Reading the 95% range.</strong> Each item is asked three times, and every score has a "
        "95% range from resampling the items. When two models' ranges overlap, treat the gap as "
        "possibly chance.",
        "<strong>Known limits.</strong> Error sentences are built from exercise options, planted typos "
        "and Wikipedia edits, not real learner errors. Valid variant forms missing from the sources are "
        "marked wrong. Small groups have wide ranges.",
    )


# ---------------------------------------------------------------------------
# Data


@dataclass
class Entry:
    """One run seen from one suite."""

    model: str
    display: str
    provider: str
    family: str
    slug: str
    run_file: str
    run_kind: str
    status: str
    generated_at: str
    epochs: int | None
    data: str
    ranked: bool
    rank: int | None
    overall: dict[str, Any] | None
    tests: dict[str, dict[str, Any]]
    cost_usd: float
    cost_per_correct_usd: float | None
    run: dict[str, Any]

    @property
    def score(self) -> float | None:
        return (self.overall or {}).get("score")

    @property
    def ci95(self) -> list[float] | None:
        return (self.overall or {}).get("ci95")


def check_public_examples(runs: Iterable[dict[str, Any]]) -> None:
    """Raise when any failure example is not marked ``public: true``."""
    for run in runs:
        name = run.get("_file") or run.get("model", {}).get("id", "results file")
        for suite_name, suite in sorted((run.get("suites") or {}).items()):
            for test_name, block in sorted((suite.get("tests") or {}).items()):
                for example in block.get("failure_examples") or []:
                    if example.get("public") is not True:
                        raise SiteError(
                            f"{name}: failure example {example.get('id')!r} in {suite_name}/{test_name} "
                            "is not marked public: true. Private items must never be published."
                        )


def slugify(model: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-") or "model"


def display_name(model_id: str) -> tuple[str, str]:
    """A readable name and maker for an OpenRouter id:
    ``openai/gpt-6-luna`` gives ``("GPT-6 Luna", "OpenAI")``."""
    provider, _, name = model_id.lstrip("~").partition("/")
    if not name:
        provider, name = "", provider
    name, _, variant = name.partition(":")
    words: list[str] = []
    for token in re.split(r"[-_\s]+", name):
        if not token:
            continue
        low = token.lower()
        if low in NAME_WORDS:
            word = NAME_WORDS[low]
        elif re.fullmatch(r"o\d+", low):
            word = low  # o3, o4: lower case by the maker's own style
        elif re.fullmatch(r"\d+(\.\d+)?[bm]", low):
            word = low.upper()  # parameter counts: 120B
        else:
            word = token[0].upper() + token[1:]
        if words and words[-1] == "GPT":
            words[-1] = f"GPT-{word}"
        else:
            words.append(word)
    label = " ".join(words) or model_id
    if variant:
        label += f" ({variant})"
    return label, PROVIDER_NAMES.get(provider, provider)


def _entries(runs: list[dict[str, Any]], suite: str) -> list[Entry]:
    entries: list[Entry] = []
    used: set[str] = set()
    for run in sorted(runs, key=lambda r: (r["model"]["id"], r.get("_file", ""))):
        block = (run.get("suites") or {}).get(suite)
        if not block:
            continue
        slug = base = slugify(run["model"]["id"])
        n = 2
        while slug in used:
            slug, n = f"{base}-{n}", n + 1
        used.add(slug)
        tests = dict(sorted((block.get("tests") or {}).items()))
        cost = sum(float(t.get("cost_usd") or 0.0) for t in tests.values())
        correct = sum(
            (t.get("score") or 0.0) * (t.get("n_items") or 0) * (t.get("epochs") or 0)
            for t in tests.values()
            if t.get("status") == "complete"
        )
        kinds = {t.get("dataset", "full") for t in tests.values()}
        overall = block.get("overall")
        display, provider = display_name(run["model"]["id"])
        entries.append(
            Entry(
                model=run["model"]["id"],
                display=display,
                provider=provider,
                family=run["model"].get("family") or "",
                slug=slug,
                run_file=run.get("_file", ""),
                run_kind=run.get("run_kind", ""),
                status=run.get("status", ""),
                generated_at=run.get("generated_at", ""),
                epochs=(run.get("config") or {}).get("epochs"),
                data=kinds.pop() if len(kinds) == 1 else "mixed",
                ranked=(
                    run.get("run_kind") == "live"
                    and run.get("status") == "complete"
                    and bool(overall)
                    and overall.get("score") is not None
                ),
                rank=None,
                overall=overall,
                tests=tests,
                cost_usd=cost,
                cost_per_correct_usd=(cost / correct) if correct > 0 else None,
                run=run,
            )
        )
    entries.sort(key=lambda e: (not e.ranked, -(e.score or 0.0), e.cost_usd, e.model))
    rank = 0
    for entry in entries:
        if entry.ranked:
            rank += 1
            entry.rank = rank
    return entries


def _reports(repo_root: Path, suite: str) -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    for path in sorted((repo_root / "data" / "build-reports").glob(f"{suite}_*.json")):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if report.get("suite") == suite and report.get("test"):
            reports[str(report["test"])] = report
    return reports


def _sample_sources(repo_root: Path, suite: str, test: str) -> list[str]:
    path = repo_root / "samples" / suite / f"{test}.jsonl"
    if not path.exists():
        return []
    sources = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            source = (json.loads(line).get("metadata") or {}).get("source")
            if source:
                sources.add(str(source))
    return sorted(sources)


def _test_order(suite: str, names: Iterable[str]) -> list[str]:
    known = [test for (s, test) in TEST_INFO if s == suite]
    names = set(names)
    return [t for t in known if t in names] + sorted(names - set(known))


def _test_title(suite: str, test: str) -> str:
    return TEST_INFO.get((suite, test), (test.replace("_", " ").capitalize(), ""))[0]


def _test_description(suite: str, test: str, scoring: str | None) -> str:
    info = TEST_INFO.get((suite, test))
    if info:
        return info[1]
    return SCORING_INFO.get(scoring or "", "")


def _test_anchor(test: str) -> str:
    return f"test-{test.replace('_', '-')}"


def _group_name(value: str) -> str:
    return GROUP_NAMES.get(value, value.replace("_", " ").replace("-", " ").capitalize())


def _topic_name(value: str) -> str:
    """Topic labels as recorded on items; the two labels for sentences with no error read the same."""
    if value in ("clean", "no_error"):
        return "no error"
    return value.replace("_", " ")


def _date(iso: str | None) -> str:
    if not iso:
        return "no results yet"
    try:
        moment = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso[:10]
    return f"{moment.day} {MONTHS[moment.month - 1]} {moment.year}"


def _ordered_groups(values: Iterable[str], order: tuple[str, ...]) -> list[str]:
    values = set(values)
    return [v for v in order if v in values] + sorted(values - set(order))


def _group_means(entry: Entry, field: str) -> dict[str, float]:
    """Mean of per-test scores for each group value, every test weighted equally."""
    sums: dict[str, list[float]] = {}
    for block in entry.tests.values():
        if block.get("status") != "complete":
            continue
        for value, stat in (block.get(field) or {}).items():
            if value in ("unspecified", "none") or not stat or stat.get("score") is None:
                continue
            sums.setdefault(value, []).append(float(stat["score"]))
    return {value: sum(scores) / len(scores) for value, scores in sums.items()}


def _complete_score(entry: Entry, test: str) -> float | None:
    block = entry.tests.get(test)
    if not block or block.get("status") != "complete" or block.get("score") is None:
        return None
    return float(block["score"])


def _explanation_comparable(block: dict[str, Any], run: dict[str, Any], current_pair: set[str]) -> bool:
    """True when the run's explanation score was judged by the current fixed pair,
    the same rule as the leaderboard file."""
    tutor = block.get("tutor") or {}
    explanation = tutor.get("explanation") or {}
    judges = set(tutor.get("judges") or run.get("judges") or [])
    return (
        explanation.get("status") == EXPLANATION_SCORED
        and explanation.get("score") is not None
        and judges == current_pair
    )


# ---------------------------------------------------------------------------
# HTML helpers


def e(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


def _usd(value: float | None) -> str:
    return e(money(value))


def _per_thousand(value: float | None) -> str:
    """Cost per correct answer, shown per 1,000 answers so it reads as money."""
    return _usd(None if value is None else value * 1000)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _data_tag(data: str) -> str:
    if data == "full":
        return ""
    label = "public sample" if data == "public_sample" else "mixed data"
    return f' <span class="tag">{label}</span>'


def _test_tags(block: dict[str, Any]) -> str:
    tags = ""
    if block.get("dataset") == "public_sample":
        tags += ' <span class="tag">public sample</span>'
    if block.get("status") != "complete":
        tags += ' <span class="tag tag-warn">incomplete</span>'
    return tags


def _model_label(entry: Entry, prefix: str = "models/") -> str:
    return (
        f'<a class="m-name" href="{prefix}{entry.slug}.html">{e(entry.display)}</a>'
        f'<span class="m-sub">{e(entry.provider)}</span>{_data_tag(entry.data)}'
    )


def _table(
    head: list[str], rows: list[str], *, caption: str = "", css: str = "", label: str = "", compact: bool = False
) -> str:
    """A table in its own horizontal scroll box. The caption sits above the
    box as a note, so it stays readable when the table scrolls on a phone."""
    note = f'<p class="table-note">{caption}</p>' if caption else ""
    head_html = "".join(head)
    name = label or re.sub(r"<[^>]+>", "", caption)
    aria = f' role="region" aria-label="{e(name)}" tabindex="0"' if name else ""
    css_attr = f' class="{css}"' if css else ""
    block = "table-block compact" if compact else "table-block"
    return (
        f'<div class="{block}">{note}<div class="table-scroll"{aria}><table{css_attr}>'
        f"<thead><tr>{head_html}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>"
    )


def _th(text: str, right: bool = False) -> str:
    css = ' class="r"' if right else ""
    return f'<th scope="col"{css}>{text}</th>'


def _heading(anchor: str, text_html: str, level: int = 2) -> str:
    """A section heading with a link to itself; the script turns the link into copy-link."""
    return (
        f'<div class="h-row"><h{level} id="{anchor}">{text_html}</h{level}>'
        f'<a class="copy-link" href="#{anchor}" aria-label="Link to this section">#</a></div>'
    )


def _drill(anchor: str, title: str, body: str, *, count: str = "", note: str = "") -> str:
    """A collapsed section: the title is always visible, the detail opens on demand."""
    count_html = f'<span class="drill-count">{count}</span>' if count else ""
    note_html = f'<span class="drill-note">{note}</span>' if note else ""
    return (
        f'<details class="drill" id="{anchor}"><summary><span class="drill-title"><h2>{title}</h2>{note_html}</span>'
        f'{count_html}</summary><div class="drill-body">{body}</div></details>'
    )


# Optional plain-text notice from ``<results_dir>/notice.txt``, shown with every honesty note.
# ``build_site`` sets it. It is for a temporary warning, such as scores that are being re-run.
_SITE_NOTICE = ""


def _honesty(home: str) -> str:
    notice = f'<p class="notice">{e(_SITE_NOTICE)}</p>' if _SITE_NOTICE else ""
    return notice + (
        '<p class="honesty"><span class="honesty-mark" aria-hidden="true">i</span><span>'
        "Items and answers come from the named sources and have not been reviewed by people, so a few "
        f'gold answers may be wrong. <a href="{home}methodology.html#no-human-review">How the items are built</a></span></p>'
    )


def _page_head(title: str, lede: str = "", meta: str = "", eyebrow: str = "") -> str:
    parts = ['<div class="page-head">']
    if eyebrow:
        parts.append(f'<p class="eyebrow">{eyebrow}</p>')
    parts.append(f"<h1>{title}</h1>")
    if lede:
        parts.append(f'<p class="lede">{lede}</p>')
    if meta:
        parts.append(f'<p class="meta">{meta}</p>')
    parts.append("</div>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Page shell and script

# Progressive enhancement only: every page reads fully without it.
SITE_JS = """\
(function () {
  var d = document;
  function each(sel, fn, root) { Array.prototype.forEach.call((root || d).querySelectorAll(sel), fn); }
  if (!/^research\\.(blasapp|tonadaapp)\\.com$/.test(location.hostname)) {
    each("a[data-local]", function (a) { a.setAttribute("href", a.getAttribute("data-local")); });
  }
  var nav = d.querySelector(".site-nav"), here = nav && nav.querySelector("[aria-current]");
  if (here && nav.scrollWidth > nav.clientWidth) nav.scrollLeft = here.offsetLeft - 16;
  function target() {
    var id = decodeURIComponent(location.hash.slice(1));
    var el = id ? d.getElementById(id) : null;
    for (var p = el; p; p = p.parentElement) { if (p.tagName === "DETAILS") p.open = true; }
    return el;
  }
  each("[data-collapsible]", function (box) {
    var btn = box.querySelector("[data-show-all]");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var open = box.classList.toggle("expanded");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.textContent = btn.getAttribute(open ? "data-less" : "data-more");
    });
  });
  each("table[data-sortable]", function (table) {
    var body = table.tBodies[0], top = parseInt(table.getAttribute("data-top") || "0", 10);
    each("th[data-sort]", function (th) {
      var col = th.cellIndex, first = th.getAttribute("data-sort");
      var b = d.createElement("button");
      b.type = "button";
      b.className = "sort";
      while (th.firstChild) b.appendChild(th.firstChild);
      th.appendChild(b);
      b.addEventListener("click", function () {
        var now = th.getAttribute("aria-sort");
        var asc = now ? now !== "ascending" : first === "asc";
        var rows = Array.prototype.slice.call(body.rows);
        rows.sort(function (x, y) {
          var a = x.cells[col].getAttribute("data-v"), c = y.cells[col].getAttribute("data-v");
          var na = parseFloat(a), nc = parseFloat(c);
          var r = isNaN(na) || isNaN(nc) ? a.localeCompare(c) : na - nc;
          return asc ? r : -r;
        });
        rows.forEach(function (r, i) { body.appendChild(r); if (top) r.classList.toggle("more", i >= top); });
        each("th[aria-sort]", function (h) { h.removeAttribute("aria-sort"); }, table);
        th.setAttribute("aria-sort", asc ? "ascending" : "descending");
      });
    }, table);
  });
  var tabSets = [];
  each("[data-tabs]", function (box) {
    var links = box.querySelectorAll("[data-tablist] a"), panels = [];
    box.querySelector("[data-tablist]").setAttribute("role", "tablist");
    function show(i) {
      panels.forEach(function (p, j) {
        p.hidden = j !== i;
        links[j].setAttribute("aria-selected", j === i ? "true" : "false");
        links[j].tabIndex = j === i ? 0 : -1;
      });
    }
    Array.prototype.forEach.call(links, function (a, i) {
      var panel = d.getElementById(a.getAttribute("href").slice(1));
      panels.push(panel);
      a.id = "tab-" + panel.id;
      a.setAttribute("role", "tab");
      a.setAttribute("aria-controls", panel.id);
      panel.setAttribute("role", "tabpanel");
      panel.setAttribute("aria-labelledby", a.id);
      a.addEventListener("click", function (ev) {
        ev.preventDefault();
        show(i);
        history.replaceState(null, "", "#" + panel.id);
      });
      a.addEventListener("keydown", function (ev) {
        var k = ev.key === "ArrowRight" ? 1 : ev.key === "ArrowLeft" ? -1 : 0;
        if (!k) return;
        ev.preventDefault();
        var j = (i + k + links.length) % links.length;
        show(j);
        links[j].focus();
        history.replaceState(null, "", "#" + panels[j].id);
      });
    });
    function sync() {
      var el = target(), at = 0;
      panels.forEach(function (p, j) { if (el && p.contains(el)) at = j; });
      show(at);
    }
    sync();
    box.classList.add("tabs-ready");
    tabSets.push(sync);
  });
  target();
  window.addEventListener("hashchange", function () { target(); tabSets.forEach(function (f) { f(); }); });
  each("a.copy-link", function (a) {
    a.addEventListener("click", function (ev) {
      if (!navigator.clipboard) return;
      ev.preventDefault();
      navigator.clipboard.writeText(location.href.split("#")[0] + a.getAttribute("href")).then(function () {
        a.classList.add("copied");
        a.setAttribute("aria-label", "Link copied");
        setTimeout(function () { a.classList.remove("copied"); a.setAttribute("aria-label", "Link to this section"); }, 1600);
      });
    });
  });
})();
"""


def _page(
    *,
    title: str,
    description: str,
    body: str,
    suite: SuiteInfo,
    depth: int,
    current: str,
    updated: str | None,
) -> str:
    root = "../" * depth
    home = "./" if depth == 1 else "../" * (depth - 1)
    nav = []
    for key, label, href in (
        ("home", "Leaderboard", home),
        ("tests", "Tests", f"{home}tests.html"),
        ("findings", "Findings", f"{home}findings.html"),
        ("groups", suite.group_nav, f"{home}{suite.group_page}.html"),
        ("models", "Models", f"{home}models.html"),
        ("methodology", "Methodology", f"{home}methodology.html"),
    ):
        if key == current:
            attr = ' aria-current="page"'
        elif key == "models" and current == "model":
            attr = ' aria-current="true"'
        else:
            attr = ""
        nav.append(f'<li><a href="{href}"{attr}>{label}</a></li>')
    nav.append(f'<li><a class="ext" href="{REPO_URL}">GitHub<span class="sr-only"> (code and data)</span></a></li>')
    switch = []
    for other in SUITES.values():
        attrs = f'class="sw sw-{other.key}" title="{e(other.name)}: {e(other.description)}"'
        if other.key == suite.key:
            switch.append(f'<a {attrs} href="{home}" aria-current="true">{e(other.short)}</a>')
        else:
            switch.append(f'<a {attrs} href="{e(other.url)}" data-local="{root}{other.key}/">{e(other.short)}</a>')
    other = SUITES["tonada" if suite.key == "blas" else "blas"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="stylesheet" href="{root}assets/site.css">
<script>document.documentElement.className += " js";</script>
</head>
<body class="suite-{suite.key}">
<a class="skip" href="#main">Skip to content</a>
<header class="site-head"><div class="wrap head-row">
<a class="brand" href="{home}"><span class="brand-mark" aria-hidden="true"></span>{BENCHMARK_NAME}</a>
<nav class="site-nav" aria-label="Main"><ul>{"".join(nav)}</ul></nav>
<nav class="switcher" aria-label="Suite">{"".join(switch)}</nav>
</div></header>
<main id="main" class="wrap">
{body}
</main>
<footer class="site-foot"><div class="wrap">
<p>{BENCHMARK_NAME} is open source under Apache-2.0. Code, the public samples and every results file are on <a href="{REPO_URL}">GitHub</a>.</p>
<p>Gold answers come from the sources named in the <a href="{home}methodology.html">methodology</a>; they have not been reviewed by native speakers.</p>
<p>{f"Results as of {e(_date(updated))}. " if updated else ""}Also see the <a href="{e(other.url)}" data-local="{root}{other.key}/">{e(other.name)}: {e(other.description)}</a>.</p>
</div></footer>
<script>
{SITE_JS}</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Suite home


def _leaderboard(entries: list[Entry]) -> str:
    rows = []
    for entry in entries:
        more = ' class="more"' if (entry.rank or 0) > LEADERBOARD_TOP else ""
        rows.append(
            f"<tr{more}>"
            f'<td class="c-rank num" data-v="{entry.rank}">{entry.rank}</td>'
            f'<th scope="row" class="c-model" data-v="{e(entry.display.lower())}">{_model_label(entry)}</th>'
            f'<td class="c-score" data-v="{(entry.score or 0.0):.6f}"><div class="score-cell"><span class="big num">{pct(entry.score)}</span>'
            f'<span class="c-bar">{interval_bar(entry.score, entry.ci95, entry.display)}</span>'
            f'<span class="range num">{e(interval_short(entry.ci95))}</span></div></td>'
            f'<td class="c-cost r num" data-v="{entry.cost_usd:.6f}">{_usd(entry.cost_usd)}</td>'
            "</tr>"
        )
    head = (
        '<th scope="col" class="c-rank" data-sort="asc" aria-sort="ascending"><span aria-hidden="true">#</span><span class="sr-only">Rank</span></th>'
        '<th scope="col" class="c-model" data-sort="asc">Model</th>'
        f'<th scope="col" class="c-score" data-sort="desc">Score <span class="hint" title="{e(RANGE_HINT)}">and 95% range</span></th>'
        '<th scope="col" class="c-cost r" data-sort="asc">Cost<span class="wide-only"> per run</span></th>'
    )
    button = ""
    if len(entries) > LEADERBOARD_TOP:
        more = f"Show all {len(entries)} models"
        less = f"Show the top {LEADERBOARD_TOP}"
        button = (
            f'<button type="button" class="show-all" data-show-all aria-expanded="false" '
            f'data-more="{more}" data-less="{less}">{more}</button>'
        )
    return (
        '<div class="lb" data-collapsible>'
        '<div class="table-scroll lb-scroll" role="region" aria-label="Leaderboard" tabindex="0">'
        f'<table class="lb-table" data-sortable data-top="{LEADERBOARD_TOP}">'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
        f"{button}"
        '<p class="table-note">Every test counts equally. The bar is the score and the thin line is the '
        "95% range. Cost is one run of this suite on OpenRouter at that day's prices, judges included.</p>"
        "</div>"
    )


def _test_means(ranked: list[Entry], tests: list[str]) -> dict[str, float]:
    means = {}
    for test in tests:
        scores = [s for s in (_complete_score(entry, test) for entry in ranked) if s is not None]
        if scores:
            means[test] = sum(scores) / len(scores)
    return means


def _group_averages(suite: SuiteInfo, ranked: list[Entry]) -> dict[str, float]:
    """Mean over models of each model's group mean."""
    per_model = [_group_means(entry, suite.group_field) for entry in ranked]
    groups = _ordered_groups({g for m in per_model for g in m}, suite.group_order)
    out = {}
    for group in groups:
        scores = [m[group] for m in per_model if group in m]
        out[group] = sum(scores) / len(scores)
    return out


def _headlines(suite: SuiteInfo, ranked: list[Entry], tests: list[str]) -> str:
    best = ranked[0]
    across = "the one ranked model" if len(ranked) == 1 else f"mean across {len(ranked)} models"
    facts = [("Best overall", _model_link(best), f"{pct(best.score)} overall")]
    if len(ranked) > 1:
        floor = (best.ci95 or [best.score or 0.0])[0]
        level = [en for en in ranked if ((en.ci95 or [0.0, en.score or 0.0])[1]) >= floor]
        value = min(level, key=lambda en: (en.cost_usd, en.rank or 0))
        facts.append(
            ("Best value", _model_link(value), f"{pct(value.score)} for {_usd(value.cost_usd)}: the cheapest model that may be tied with the leader")
        )
    means = _test_means(ranked, tests)
    if means:
        hardest = min(means, key=lambda t: (means[t], t))
        facts.append(
            ("Hardest test", f'<a href="tests.html#{_test_anchor(hardest)}">{e(_test_title(suite.key, hardest))}</a>', f"{pct(means[hardest])}, {across}")
        )
    groups = _group_averages(suite, ranked)
    if groups:
        hardest_group = min(groups, key=lambda g: (groups[g], g))
        facts.append(
            (f"Hardest {suite.group_label.lower()}", f'<a href="{suite.group_page}.html">{e(_group_name(hardest_group))}</a>', f"{pct(groups[hardest_group])}, {across}")
        )
    items = "".join(
        f'<li><span class="hl-k">{label}</span><span class="hl-v">{value}</span><span class="hl-d">{detail}</span></li>'
        for label, value, detail in facts
    )
    return f'<section class="headlines" aria-label="Headline facts"><ul>{items}</ul></section>'


def _model_link(entry: Entry, prefix: str = "models/") -> str:
    return f'<a href="{prefix}{entry.slug}.html">{e(entry.display)}</a>'


MATRIX_TOP = 10  # rows of the model x test table shown on the home page before 'Show all'


def _home_cards(suite: SuiteInfo, ranked: list[Entry], tests: list[str]) -> str:
    cards = [
        '<section class="card card-wide" aria-labelledby="card-matrix"><h2 id="card-matrix">Every model on every test</h2>'
        f"{_matrix_viz(suite, ranked, tests, top=MATRIX_TOP)}"
        '<p class="card-foot"><a href="tests.html">What each test asks, with a real example</a></p></section>'
    ]
    groups = _group_averages(suite, ranked)
    if groups:
        noun = suite.group_label.lower()
        group_rows = "".join(
            f'<li><span class="g-name">{e(_group_name(g))}</span>{mini_bar(s)}<span class="g-score num">{pct(s)}</span></li>'
            for g, s in groups.items()
        )
        table_rows = [f'<tr><th scope="row">{e(_group_name(g))}</th><td class="r num">{pct(s)}</td></tr>' for g, s in groups.items()]
        cards.append(
            f'<section class="card" aria-labelledby="card-groups"><h2 id="card-groups">By {e(noun)}</h2>'
            + _viz(
                f'<ul class="group-bars">{group_rows}</ul>',
                takeaway=group_sentence([(_group_name(g), s) for g, s in groups.items()], len(ranked), noun),
                caption=f"Average score across {_plural(len(ranked), 'model')}, every test counted equally.",
                table=_table([_th(e(suite.group_label)), _th("Average", True)], table_rows, label=f"Average by {noun}"),
                css="viz-plain",
            )
            + f'<p class="card-foot"><a href="{suite.group_page}.html">Every model, {e(noun)} by {e(noun)}</a></p></section>'
        )
    present = set(_findings_present(ranked, tests))
    links = "".join(
        f'<li><a href="findings.html#{key}">{e(title)}</a> <span class="muted">{e(FINDINGS_TEASERS.get(key, ""))}</span></li>'
        for key, title, _ in FINDINGS
        if key in present and key != "profile"
    )
    cards.append(
        '<section class="card" aria-labelledby="card-findings"><h2 id="card-findings">More findings</h2>'
        f'<ul class="finding-links">{links}</ul>'
        '<p class="card-foot"><a href="findings.html">All findings</a></p></section>'
    )
    cards.append(
        '<section class="card card-wide" aria-labelledby="card-cost"><h2 id="card-cost">Score against cost</h2>'
        f"{_scatter_viz(suite, ranked)}"
        '<p class="card-foot"><a href="models.html">Compare every model</a></p></section>'
    )
    return f'<div class="cards">{"".join(cards)}</div>'


def _has_tutor_steps(ranked: list[Entry], test: str) -> bool:
    return any((en.tests[test].get("tutor") or {}).get("components") for en, _ in _test_ests(ranked, test))


def _findings_present(ranked: list[Entry], tests: list[str]) -> list[str]:
    """Keys of the Findings sections that have something to show, in page order."""
    with_tests = [t for t in tests if _test_ests(ranked, t)]
    has = {
        "profile": bool(with_tests),
        "ties": bool(ranked),
        "levels": any(_level_plan(ranked, t) for t in with_tests),
        "topics": any(_topic_plan(ranked, t) for t in with_tests),
        "topic-language": bool(with_tests),
        "directions": any(_direction_plan(ranked, t) for t in with_tests),
        "tutor": any(_has_tutor_steps(ranked, t) for t in with_tests),
        "evidence": any(_evidence_plan(ranked, t) for t in with_tests),
        "cost": any(en.cost_per_correct_usd for en in ranked),
        "consistency": any(en.tests[t].get("consistency") is not None for t in with_tests for en, _ in _test_ests(ranked, t)),
    }
    return [key for key, _, _ in FINDINGS if has[key]]


def _howto(home: str) -> str:
    points = "".join(f"<li>{point}</li>" for point in HOWTO_POINTS)
    return (
        '<aside class="note-box" aria-labelledby="howto-title"><h2 id="howto-title">How to read this</h2>'
        f'<ul>{points}</ul><p><a href="{home}methodology.html">Read the full methodology</a></p></aside>'
    )


def _tests_summary(suite: SuiteInfo, tests: list[str], reports: dict[str, dict[str, Any]]) -> str:
    items = []
    for test in tests:
        report = reports.get(test, {})
        size = f" {report['n_items']} items." if report.get("n_items") else ""
        items.append(
            f"<li><strong>{e(_test_title(suite.key, test))}.</strong> "
            f"{e(_test_description(suite.key, test, report.get('scoring')))}{e(size)}</li>"
        )
    if not items:
        return '<p class="empty-note">No test sets are built yet.</p>'
    return f'<ul class="test-list">{"".join(items)}</ul>'


def _unranked_notice(unranked: list[Entry]) -> str:
    if not unranked:
        return ""
    n = len(unranked)
    return (
        f'<p class="notice">{n} other run{"s" if n != 1 else ""} did not finish every test and '
        f'{"are" if n != 1 else "is"} not ranked.</p>'
    )


def _home(suite: SuiteInfo, entries: list[Entry], tests: list[str], reports: dict[str, dict[str, Any]], updated: str | None) -> str:
    ranked = [entry for entry in entries if entry.ranked]
    unranked = [entry for entry in entries if not entry.ranked]
    meta = [f"Results as of <strong>{e(_date(updated))}</strong>" if updated else "No results yet"]
    if ranked:
        meta.append(_plural(len(ranked), "model") + " ranked")
    meta.append(_plural(len(tests), "test"))
    parts = [
        _page_head(
            e(suite.headline),
            e(suite.intro),
            " · ".join(meta),
            eyebrow=f"{BENCHMARK_NAME} · {e(suite.name)}",
        )
    ]
    if not ranked:
        parts.append(
            '<div class="notice"><strong>First results will appear here after the first run.</strong> '
            "Each run asks one model every item in every test and publishes its scores, ranges and cost.</div>"
        )
        parts.append('<h2 id="what">What is measured</h2>')
        parts.append(
            '<p class="section-intro">Each test has a few hundred items. Answers are marked by fixed rules '
            "(an accepted-answer list, or chrF++ for translation), so no model grades another model's "
            "headline score. Every item is asked several times, and every score comes with a 95% range.</p>"
        )
        parts.append(_tests_summary(suite, tests, reports))
        parts.append(_howto("./"))
        return "\n".join(parts)

    parts.append('<h2 id="leaderboard" class="sr-only">Leaderboard</h2>')
    parts.append(_leaderboard(ranked))
    parts.append(_unranked_notice(unranked))
    parts.append(_headlines(suite, ranked, tests))
    parts.append(_home_cards(suite, ranked, tests))
    parts.append(_howto("./"))
    parts.append(
        '<p class="data-links">Data: <a href="data/leaderboard.json">this leaderboard as JSON</a> · '
        f'<a href="{REPO_URL}/tree/main/results/runs">every results file on GitHub</a></p>'
    )
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Tests page


def _explanation_table(suite: SuiteInfo, test: str, ranked: list[Entry], current_pair: set[str]) -> str:
    rows = []
    excluded = []
    for entry in ranked:
        block = entry.tests.get(test) or {}
        explanation = (block.get("tutor") or {}).get("explanation")
        if not explanation:
            continue
        if not _explanation_comparable(block, entry.run, current_pair):
            excluded.append(entry.display)
            continue
        rows.append(
            "<tr>"
            f'<th scope="row">{_model_link(entry)}</th>'
            f'<td class="r num">{pct(explanation.get("score"))}</td>'
            f'<td class="r num">{e(interval_short(explanation.get("ci95")))}</td>'
            f'<td class="r num">{pct(explanation.get("judge_agreement"))}</td>'
            "</tr>"
        )
    if not rows and not excluded:
        return ""
    body = (
        '<p class="section-intro">Tutor items also ask for a short explanation. Two judge models from other '
        "model families mark it. This is a secondary number: judge-marked, not human-validated, and not part "
        "of the score above.</p>"
    )
    if rows:
        body += _table(
            [_th("Model"), _th("Explanation", True), _th("95% range", True), _th("Judges agree", True)],
            rows,
            css="board",
            label=f"Tutor explanation scores, {_test_title(suite.key, test)}",
        )
    if excluded:
        body += (
            f'<p class="muted">Not shown, because the run used a different judge pair or was not judged: '
            f"{e(', '.join(excluded))}. Their own pages list what happened.</p>"
        )
    return _drill(f"{_test_anchor(test)}-explanations", "Tutor explanations", body, note="judge-marked, secondary")


# How each scorer marks, as chips on the structure diagram: (kind, text).
MARKING_CHIPS = {
    "accept_list": (("rule", "Rule: accepted answers"),),
    "translation": (("rule", "Rule: chrF++ overlap with a reference"),),
    "round_trip": (("rule", "Rule: chrF++ overlap with the original"),),
    "tutor": (("rule", "Rule: found, fixed, nothing else changed"), ("judge", "Judges: the explanation, secondary")),
}


def _structure(suite: SuiteInfo, tests: list[str], reports: dict[str, dict[str, Any]], ranked: list[Entry]) -> str:
    """The suite, its tests, and what in each is marked by rule or by judge."""
    items, total = [], 0
    for test in tests:
        report = reports.get(test) or {}
        n = report.get("n_items")
        total += n or 0
        chips = "".join(
            f'<span class="chip chip-{kind}">{e(text)}</span>' for kind, text in MARKING_CHIPS.get(_scoring(ranked, test, reports) or "", ())
        )
        size = f'<span class="st-n">{n} items</span>' if n else ""
        items.append(f'<li><a class="st-test" href="#{_test_anchor(test)}">{e(_test_title(suite.key, test))}</a>{size}<span class="chips">{chips}</span></li>')
    epochs = sorted({en.epochs for en in ranked if en.epochs})
    facts = [_plural(len(tests), "test")]
    if total:
        facts.append(f"{total:,} items")
    if len(epochs) == 1:
        facts.append(f"each item asked {epochs[0]} times")
    return (
        '<figure class="structure"><figcaption class="st-suite">'
        f'<strong>{e(suite.name)}</strong> <span class="muted">{e(" · ".join(facts))}</span></figcaption>'
        f'<ol class="st-tests">{"".join(items)}</ol>'
        '<p class="st-key"><span class="chip chip-rule">Rule</span> marked by a fixed rule; no model is involved. '
        '<span class="chip chip-judge">Judges</span> marked by two judge models; reported apart and not part of the score.</p>'
        "</figure>"
    )


@dataclass(frozen=True)
class Example:
    id: str
    prompt: str
    answer_label: str
    answer: str


def _example_answer(meta: dict[str, Any], target: Any) -> tuple[str, str]:
    scoring = meta.get("scoring")
    accept = [str(a) for a in meta.get("accept") or [] if str(a).strip()]
    if scoring == "accept_list" and accept:
        return ("Accepted answer" if len(accept) == 1 else "Accepted answers"), " · ".join(accept)
    references = [str(r) for r in meta.get("references") or [] if str(r).strip()]
    if scoring == "translation" and references:
        return "Reference translation", references[0]
    if scoring == "round_trip" and meta.get("source_text"):
        return "Marked against the original sentence", str(meta["source_text"])
    if scoring == "tutor" and isinstance(target, str):
        if meta.get("has_error"):
            return "Expected correction", f"{meta.get('error_span', '')} → {meta.get('correction', '')}\nCorrected sentence: {target}"
        return "Expected answer", f"No error: the sentence stays as it is.\n{target}"
    return "Expected answer", str(target) if isinstance(target, str) else ""


def _example_item(repo_root: Path, suite: str, test: str) -> Example | None:
    """One short, clear item from the public sample, chosen the same way on
    every build: tutor items with an error first, then the shortest."""
    path = repo_root / "samples" / suite / f"{test}.jsonl"
    if not path.exists():
        return None
    candidates = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        meta = item.get("metadata") or {}
        prompt = item.get("input")
        if not isinstance(prompt, str) or not prompt.strip():
            continue
        label, answer = _example_answer(meta, item.get("target"))
        if not answer.strip():
            continue
        plain = 1 if meta.get("scoring") == "tutor" and not meta.get("has_error") else 0
        candidates.append(((plain, len(prompt) + len(answer), str(item.get("id"))), Example(str(item.get("id")), prompt.strip(), label, answer)))
    return min(candidates, key=lambda c: c[0])[1] if candidates else None


def _example_html(example: Example | None) -> str:
    if example is None:
        return ""
    return (
        '<div class="example example-item">'
        f'<p class="ex-title">Example item from the public sample <code>{e(example.id)}</code></p>'
        f'<p class="label">Prompt</p><pre>{e(example.prompt)}</pre>'
        f'<p class="label">{e(example.answer_label)}</p><pre>{e(example.answer)}</pre>'
        "</div>"
    )


def _tests_page(
    suite: SuiteInfo,
    ranked: list[Entry],
    tests: list[str],
    reports: dict[str, dict[str, Any]],
    current_pair: set[str],
    repo_root: Path,
) -> str:
    lede = (
        f"{_plural(len(tests), 'test')}, each a few hundred items. Each test says what the model is asked to do, "
        "shows a real item and how it is marked, then compares every model."
        if tests
        else ""
    )
    parts = [_page_head("Tests", lede), _honesty("./")]
    if not tests:
        parts.append(_drill("about", "What the tests measure", f'<p class="section-intro">{e(suite.statement)}</p>'))
        parts.append('<p class="empty-note">No test sets are built yet.</p>')
        return "\n".join(parts)
    parts.append(_structure(suite, tests, reports, ranked))
    tabs = "".join(f'<a href="#{_test_anchor(test)}">{e(_test_title(suite.key, test))}</a>' for test in tests)
    panels = []
    for test in tests:
        report = reports.get(test) or {}
        scoring = _scoring(ranked, test, reports)
        pairs = _test_ests(ranked, test)
        ask, marking, _ = TEST_EXPLAIN.get((suite.key, test), (_test_description(suite.key, test, scoring), "", ""))
        n_items = {est.n for _, est in pairs}
        epochs = {entry.tests[test].get("epochs") for entry, _ in pairs}
        groups = [g for g in (report.get(suite.group_field) or {}) if g not in ("none", "None", "unspecified")]
        facts = []
        if report.get("n_items"):
            facts.append(f"{report['n_items']} items")
        elif len(n_items) == 1:
            facts.append(f"{n_items.pop()} items")
        if groups:
            facts.append(_plural(len(groups), suite.group_label.lower()))
        if len(epochs) == 1 and None not in epochs:
            facts.append(f"each asked {epochs.pop()} times")
        facts.append(f"{_plural(len(pairs), 'model')} with a complete result")
        links = _findings_links(ranked, test)
        findings = (
            '<p class="more-link">On the Findings page: '
            + ", ".join(f'<a href="findings.html#{anchor}">{e(label)}</a>' for anchor, label in links)
            + "</p>"
            if links
            else ""
        )
        anchor = _test_anchor(test)
        explain = f'<p class="panel-desc"><strong>The task.</strong> {e(ask)}</p>'
        if marking:
            explain += f'<p class="panel-desc"><strong>Marking.</strong> {e(marking)}</p>'
        results = _results_viz(suite, ranked, test, scoring) if pairs else '<p class="empty-note">No complete runs yet.</p>'
        panels.append(
            f'<section class="panel" id="{anchor}" aria-labelledby="{anchor}-title">'
            + _heading(f"{anchor}-title", e(_test_title(suite.key, test)))
            + explain
            + f'<p class="meta">{e(" · ".join(facts))}</p>'
            + _example_html(_example_item(repo_root, suite.key, test))
            + f'<h3 class="results-h">Results</h3>{results}'
            + _explanation_table(suite, test, ranked, current_pair)
            + findings
            + f'<p class="more-link"><a href="methodology.html#set-{test.replace("_", "-")}">How this test set is built</a></p>'
            "</section>"
        )
    parts.append(
        '<div class="tabs" data-tabs>'
        f'<nav class="tab-list" aria-label="Tests" data-tablist>{tabs}</nav>'
        f'{"".join(panels)}</div>'
    )
    parts.append(_drill("about", "What the tests measure", f'<p class="section-intro">{e(suite.statement)}</p>' + _tests_summary(suite, tests, reports)))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Languages / learners page


def _heat_grid(suite: SuiteInfo, entries: list[Entry], scores: dict[str, dict[str, float]], label: str) -> str:
    groups = _ordered_groups({g for m in scores.values() for g in m}, suite.group_order)
    if not groups:
        return '<p class="empty-note">No breakdown available yet.</p>'
    rows = []
    for entry in entries:
        cells = []
        for group in groups:
            score = scores[entry.model].get(group)
            if score is None:
                cells.append('<td class="empty">n/a</td>')
            else:
                cells.append(f"<td{heat_style(score)}>{score * 100:.1f}%</td>")
        rows.append(f'<tr><th scope="row">{_model_link(entry)}</th>{"".join(cells)}</tr>')
    head = [_th("Model")] + [_th(e(_group_name(g))) for g in groups]
    return _table(head, rows, css="heat", label=label)


def _groups_page(suite: SuiteInfo, ranked: list[Entry], tests: list[str]) -> str:
    noun = suite.group_label.lower()
    parts = [
        _page_head(
            e(suite.group_title),
            f"How each model scores for each {e(noun)}: the mean of its per-test scores, every test counted equally.",
        ),
        _honesty("./"),
    ]
    if not ranked:
        parts.append('<p class="empty-note">No complete runs yet.</p>')
        return "\n".join(parts)
    averages = _group_averages(suite, ranked)
    rows = [BarRow(label_html=e(_group_name(g)), label_text=_group_name(g), score=s, ci95=None) for g, s in averages.items()]
    parts.append(_heading("average", f"Average across {_plural(len(ranked), 'model')}"))
    per_model = {entry.slug: _group_means(entry, suite.group_field) for entry in ranked}
    names = _labels(ranked)
    table_rows = []
    for group, average in sorted(averages.items(), key=lambda item: (-item[1], item[0])):
        scores = sorted((means[group], names[slug]) for slug, means in per_model.items() if group in means)
        table_rows.append(
            f'<tr><th scope="row">{e(_group_name(group))}</th><td class="r num">{pct(average)}</td>'
            f"<td>{e(scores[0][1])} ({pct(scores[0][0])})</td><td>{e(scores[-1][1])} ({pct(scores[-1][0])})</td></tr>"
        )
    parts.append(
        _viz(
            ranked_bars(rows),
            takeaway=group_sentence([(_group_name(g), s) for g, s in averages.items()], len(ranked), noun),
            caption=f"Mean of each model's per-test scores for each {e(noun)}, averaged over models; highest first. "
            "Ranges per model are on each model page.",
            table=_table(
                [_th(e(suite.group_label)), _th("Average", True), _th("Lowest model"), _th("Highest model")],
                table_rows,
                label=f"Average score by {noun}",
            ),
        )
    )
    parts.append(_heading("grid", "Every model"))
    means = {entry.model: _group_means(entry, suite.group_field) for entry in ranked}
    parts.append(
        '<p class="section-intro">Darker cells are higher. Select a model for its ranges and item counts.</p>'
        + _heat_grid(suite, ranked, means, f"Score by {noun}")
    )
    parts.append(_heading("by-test", "Test by test"))
    for test in tests:
        per_test = {
            entry.model: {
                g: float(stat["score"])
                for g, stat in ((entry.tests.get(test) or {}).get(suite.group_field) or {}).items()
                if g not in ("none", "unspecified") and stat and stat.get("score") is not None
                and _complete_score(entry, test) is not None
            }
            for entry in ranked
        }
        if not any(per_test.values()):
            continue
        parts.append(
            _drill(
                f"by-test-{test.replace('_', '-')}",
                e(_test_title(suite.key, test)),
                _heat_grid(suite, ranked, per_test, f"{_test_title(suite.key, test)} by {noun}"),
            )
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Charts with takeaways, shared by the Findings page and the other pages


def _fold(content: str, count: int, top: int, noun: str) -> str:
    """Use the site's existing progressive-enhancement Show all control."""
    if count <= top:
        return content
    more, less = f"Show all {count} {noun}", f"Show the first {top}"
    return (
        f'<div class="collapsible" data-collapsible>{content}<button type="button" class="show-all" '
        f'aria-expanded="false" data-show-all data-more="{more}" data-less="{less}">{more}</button></div>'
    )


def _viz(chart: str, *, takeaway: str, caption: str, table: str, css: str = "") -> str:
    """A chart as a figure: the computed takeaway and what is plotted first,
    then the graphic, then the exact numbers behind 'View as table'."""
    return (
        f'<figure class="viz{" " + css if css else ""}"><figcaption>'
        f'<p class="takeaway">{e(takeaway)}</p><p class="viz-cap">{caption}</p></figcaption>'
        f'<div class="viz-body">{chart}</div>'
        f'<details class="as-table"><summary>View as table</summary>{table}</details></figure>'
    )


def _labels(ranked: list[Entry]) -> dict[str, str]:
    """A unique display name per entry slug, for sentences and tables."""
    seen: dict[str, int] = {}
    out = {}
    for entry in ranked:
        seen[entry.display] = seen.get(entry.display, 0) + 1
        out[entry.slug] = entry.display if seen[entry.display] == 1 else f"{entry.display} ({seen[entry.display]})"
    return out


def _est(stat: dict[str, Any] | None) -> Est | None:
    if not stat or stat.get("score") is None:
        return None
    ci = stat.get("ci95")
    return Est(float(stat["score"]), (float(ci[0]), float(ci[1])) if ci else None, stat.get("n_items"))


def _overall_est(entry: Entry) -> Est:
    ci = entry.ci95
    return Est(float(entry.score or 0.0), (float(ci[0]), float(ci[1])) if ci else None)


def _ci(est: Est | None) -> list[float] | None:
    return list(est.ci) if est and est.ci else None


def _test_ests(ranked: list[Entry], test: str) -> list[tuple[Entry, Est]]:
    """Every ranked model with a complete result on this test."""
    out = []
    for entry in ranked:
        if _complete_score(entry, test) is not None:
            est = _est(entry.tests[test])
            if est:
                out.append((entry, est))
    return out


def _breakdown(ranked: list[Entry], test: str, field: str) -> dict[str, list[tuple[Entry, Est]]]:
    """Value of a breakdown field to each model's estimate, complete tests only."""
    out: dict[str, list[tuple[Entry, Est]]] = {}
    for entry, _ in _test_ests(ranked, test):
        for key, stat in (entry.tests[test].get(field) or {}).items():
            if key in ("none", "unspecified", "None"):
                continue
            est = _est(stat)
            if est:
                out.setdefault(key, []).append((entry, est))
    return out


def _n_items(pairs: list[tuple[Entry, Est]]) -> int:
    """Items behind a breakdown value: the smallest count any model reports."""
    return min((est.n or 0) for _, est in pairs) if pairs else 0


def _scoring(ranked: list[Entry], test: str, reports: dict[str, dict[str, Any]] | None = None) -> str | None:
    found = next((entry.tests[test].get("scoring") for entry in ranked if test in entry.tests), None)
    return found or ((reports or {}).get(test) or {}).get("scoring")


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _score_cell(est: Est | None) -> str:
    if est is None:
        return '<td class="muted">n/a</td>'
    return f'<td class="num"><strong>{pct(est.score)}</strong> <span class="ci-text">{e(interval_short(_ci(est)))}</span></td>'


def _key(items: list[tuple[str, str, str]]) -> str:
    """A legend row of (shape, tone, label): the marker drawn next to its name."""
    return '<ul class="key">' + "".join(f"<li>{swatch(shape, tone)}{label}</li>" for shape, tone, label in items) + "</ul>"


def _ranking_rows(ranked: list[Entry], test: str) -> list[tuple[str, Est]]:
    names = _labels(ranked)
    return [(names[entry.slug], est) for entry, est in _test_ests(ranked, test)]


def _results_viz(suite: SuiteInfo, ranked: list[Entry], test: str, scoring: str | None) -> str:
    """One test's scores, every model, highest first (Tests page)."""
    pairs = _test_ests(ranked, test)
    rows = [BarRow(label_html=_model_label(entry), label_text=entry.display, score=est.score, ci95=_ci(est)) for entry, est in pairs]
    caption = "Score of each model with its 95% range (the thin line)."
    if scoring == "tutor":
        caption += " Marked by rule only; the judge-marked explanation score is separate, below."
    table_rows = [
        f'<tr><th scope="row">{_model_link(entry)}</th><td class="r num">{pct(est.score)}</td>'
        f'<td class="r num">{e(interval_short(_ci(est)))}</td><td class="r num">{e(est.n)}</td>'
        f'<td class="r num">{pct(entry.tests[test].get("consistency"))}</td></tr>'
        for entry, est in sorted(pairs, key=lambda p: (-p[1].score, p[0].display))
    ]
    return _viz(
        ranked_bars(rows),
        takeaway=leader_sentence(_ranking_rows(ranked, test)),
        caption=e(caption),
        table=_table(
            [_th("Model"), _th("Score", True), _th("95% range", True), _th("Items", True), _th("Consistency", True)],
            table_rows,
            label=f"{_test_title(suite.key, test)}: every model",
        ),
    )


def _matrix_viz(suite: SuiteInfo, ranked: list[Entry], tests: list[str], *, top: int = 0) -> str:
    """Models as rows, tests as columns: the profile of every model."""
    names = _labels(ranked)
    columns: list[tuple[str, str, list[tuple[Entry, Est]]]] = [("overall", "Overall", [(en, _overall_est(en)) for en in ranked])]
    for test in tests:
        pairs = _test_ests(ranked, test)
        if pairs:
            columns.append((test, _test_title(suite.key, test), pairs))
    if not ranked or len(columns) == 1:
        return '<p class="empty-note">No complete runs yet.</p>'
    low = max(0.0, math.floor(min(est.score for _, _, pairs in columns for _, est in pairs) * 10) / 10)
    lookup = {key: {en.slug: est for en, est in pairs} for key, _, pairs in columns}
    leaders = {key: min(pairs, key=lambda p: (-p[1].score, p[0].rank or 0)) for key, _, pairs in columns}
    head = ['<th scope="col" class="c-model" data-sort="asc">Model</th>']
    for key, title, _ in columns:
        initial = ' aria-sort="descending"' if key == "overall" else ""
        css = "r c-overall" if key == "overall" else "r"
        head.append(f'<th scope="col" class="{css}" data-sort="desc"{initial}>{e(title)}</th>')
    rows, plain = [], []
    for i, entry in enumerate(ranked):
        more = ' class="more"' if top and i >= top else ""
        cells = [f'<th scope="row" class="c-model" data-v="{e(names[entry.slug].lower())}">{_model_link(entry)}</th>']
        plain_cells = [f'<th scope="row">{e(names[entry.slug])}</th>']
        for key, title, _ in columns:
            est = lookup[key].get(entry.slug)
            plain_cells.append(_score_cell(est))
            if est is None:
                cells.append('<td class="empty" data-v="-1">n/a</td>')
                continue
            lead_entry, lead_est = leaders[key]
            tip = f"{names[entry.slug]}, {title}: {pct(est.score)}, 95% range {interval_short(_ci(est))}"
            mark = ""
            if lead_entry.slug == entry.slug:
                mark = '<span class="mk mk-best" aria-hidden="true">▲</span><span class="sr-only"> (highest)</span>'
                tip += ". Highest in this column"
            elif overlaps(est, lead_est):
                mark = '<span class="mk mk-tie" aria-hidden="true">≈</span><span class="sr-only"> (tied with the highest)</span>'
                tip += ". Tied with the highest: the 95% ranges overlap"
            css = ' class="r c-overall"' if key == "overall" else ' class="r"'
            cells.append(f'<td{css} data-v="{est.score:.6f}" title="{e(tip)}"{heat_style(est.score, low)}>{pct(est.score)}{mark}</td>')
        rows.append(f"<tr{more}>{''.join(cells)}</tr>")
        plain.append(f"<tr>{''.join(plain_cells)}</tr>")
    top_attr = f' data-top="{top}"' if top else ""
    table = (
        f'<div class="table-scroll" role="region" aria-label="Score of every model on every test, {e(suite.name)}" tabindex="0">'
        f'<table class="heat matrix" data-sortable{top_attr}><thead><tr>{"".join(head)}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )
    if top and len(ranked) > top:
        more_text, less_text = f"Show all {len(ranked)} models", f"Show the top {top}"
        table = (
            f'<div class="collapsible" data-collapsible>{table}<button type="button" class="show-all" data-show-all '
            f'aria-expanded="false" data-more="{more_text}" data-less="{less_text}">{more_text}</button></div>'
        )
    sentence = matrix_sentence(
        [(title, [(names[en.slug], est) for en, est in pairs]) for key, title, pairs in columns if key != "overall"]
    )
    caption = (
        f"Score of each model on each test; Overall counts every test equally. Darker cells are higher, shaded from "
        f"{low * 100:.0f}% to 100%. <span class=\"mk mk-best\" aria-hidden=\"true\">▲</span> highest in the column; "
        "<span class=\"mk mk-tie\" aria-hidden=\"true\">≈</span> tied with the highest (the 95% ranges overlap). "
        '<span class="js-only">Select a column heading to sort.</span>'
    )
    plain_head = [_th("Model")] + [_th(e(title)) for _, title, _ in columns]
    return _viz(
        table,
        takeaway=sentence,
        caption=caption,
        table=_table(plain_head, plain, label="Scores with 95% ranges", css="board"),
        css="viz-matrix",
    )


def _scatter_viz(suite: SuiteInfo, ranked: list[Entry], prefix: str = "models/") -> str:
    points = [ScatterPoint(entry.rank or 0, entry.display, entry.cost_usd, entry.score or 0.0, entry.ci95) for entry in ranked]
    chart = scatter(points, f"scatter-{suite.key}", f"Overall score against cost, {suite.name}")
    legend = "".join(
        f'<li value="{entry.rank}"><a href="{prefix}{entry.slug}.html">{e(entry.display)}</a> '
        f'<span class="num">{pct(entry.score)} · {_usd(entry.cost_usd)}</span></li>'
        for entry in ranked
    )
    names = _labels(ranked)
    rows = [
        f'<tr><th scope="row">{e(names[en.slug])}</th><td class="r num">{en.rank}</td><td class="r num">{pct(en.score)}</td>'
        f'<td class="r num">{e(interval_short(en.ci95))}</td><td class="r num">{_usd(en.cost_usd)}</td></tr>'
        for en in ranked
    ]
    return _viz(
        f'<div class="scatter-split">{chart}<ol class="legend">{legend}</ol></div>',
        takeaway=value_sentence([(names[en.slug], _overall_est(en), en.cost_usd) for en in ranked]),
        caption="Each circle is a model, numbered by rank. Higher is better; further left is cheaper. "
        "The vertical line is the 95% range. Cost is one run of this suite, judges included.",
        table=_table(
            [_th("Model"), _th("Rank", True), _th("Score", True), _th("95% range", True), _th("Cost per run", True)],
            rows,
            label="Score and cost",
        ),
        css="viz-scatter",
    )


# ---------------------------------------------------------------------------
# Findings page

MODEL_ROWS_TOP = 12  # longer model lists fold behind 'Show all'
LINE_LIMIT = 12  # more models than this and a line chart shows only the median and the band
TOPIC_SHOW = 5  # easiest and hardest shown when a test has many topics

# Section key, title and what the view shows.
FINDINGS: tuple[tuple[str, str, str], ...] = (
    ("profile", "Every model on every test", "The quickest way to see each model's strengths and weaknesses."),
    (
        "ties",
        "Who is tied with whom",
        "Scores come from a sample of items, so small gaps can be chance. Models whose 95% ranges overlap "
        "are not clearly different.",
    ),
    (
        "levels",
        "Scores by CEFR level",
        "Items carry the CEFR level of the course content they come from, from A1 (beginner) up. Do models "
        "drop as items get harder?",
    ),
    (
        "topics",
        "Hardest and easiest topics",
        "Each item records its grammar topic, error type or course category. Which are hardest across models?",
    ),
    (
        "topic-language",
        "Grammar topic by language",
        "Where each topic is hardest, averaged over the models with a recorded topic–language breakdown.",
    ),
    (
        "directions",
        "Translation directions",
        "Translation items go into English or out of English, or come from legal and administrative parallel text.",
    ),
    (
        "tutor",
        "Tutor accuracy step by step",
        "A tutor item counts only when three rule-marked checks all pass on the same item. Which check fails most?",
    ),
    (
        "evidence",
        "Evidence check",
        "Each gold answer has an evidence label: cross-checked against a dictionary, from the course alone, or "
        "marked unverified. Does weaker gold change the picture?",
    ),
    ("cost", "Cost per correct answer", "What a correct answer costs at OpenRouter prices on the day of the run."),
    (
        "consistency",
        "Consistency",
        "Each item is asked several times. How often does a model get the same score every time?",
    ),
)

# One line per section for the home page's 'More findings' card.
FINDINGS_TEASERS = {
    "ties": "which gaps may be chance",
    "levels": "do models drop as items get harder?",
    "topics": "the hardest grammar points and error types",
    "topic-language": "which topics are hardest in each language?",
    "directions": "into English against out of English",
    "tutor": "which check fails most",
    "evidence": "does weaker gold change the picture?",
    "cost": "what a correct answer costs",
    "consistency": "the same score on every ask?",
}

DIRECTIONS = (
    ("to_english", "Into English", "dot", "a"),
    ("from_english", "Out of English", "square", "b"),
    ("legal_or_administrative", "Legal and administrative corpus", "ring", "c"),
)


def _finding_anchor(section: str, test: str) -> str:
    return f"{section}-{test.replace('_', '-')}"


def _subsection(anchor: str, title: str, body: str, *, open_: bool = True) -> str:
    """One test's chart in a findings section. Secondary charts fold away."""
    if open_:
        return f'<section class="multiple" id="{anchor}" aria-labelledby="{anchor}-h"><h3 id="{anchor}-h">{e(title)}</h3>{body}</section>'
    return (
        f'<details class="drill drill-sm" id="{anchor}"><summary><span class="drill-title"><h3>{e(title)}</h3></span>'
        f'</summary><div class="drill-body">{body}</div></details>'
    )


def _ties_viz(ranked: list[Entry]) -> str:
    names = _labels(ranked)
    items = [(names[en.slug], _overall_est(en)) for en in ranked]
    by_name = {names[en.slug]: en for en in ranked}
    ends = [v for _, est in items for v in (est.ci or (est.score, est.score))]
    lo, hi, step = nice_domain(ends, max_ticks=8)

    def pos(v: float) -> float:
        return (v - lo) / (hi - lo)

    lead_name, lead = min(items, key=lambda item: (-item[1].score, item[0]))
    band = (pos(lead.ci[0]), pos(lead.ci[1])) if lead.ci else None
    rows: list[DotRow | str] = []
    for gi, group in enumerate(tie_groups(items)):
        top_name = group[0]
        if gi == 0:
            heading = (
                f"Tied at the top: {len(group)} models whose 95% range overlaps {e(top_name)}’s"
                if len(group) > 1
                else f"Clear leader: no other model’s range overlaps {e(top_name)}’s"
            )
        elif len(group) > 1:
            heading = f"Group {gi + 1}: {len(group)} models whose range overlaps {e(top_name)}’s"
        else:
            heading = f"Group {gi + 1}: {e(top_name)}, overlapping no lower model"
        rows.append(heading)
        for name in group:
            est, entry = dict(items)[name], by_name[name]
            words = f"{name}: {pct(est.score)}, 95% range {interval_words(_ci(est))}"
            rows.append(
                DotRow(
                    label_html=f'<a href="models/{entry.slug}.html">{e(name)}</a>',
                    aria=words,
                    marks=(
                        Mark(pos(est.score), "dot", "hl", pos(est.ci[0]) if est.ci else None, pos(est.ci[1]) if est.ci else None, words),
                    ),
                    value_html=f'<strong>{pct(est.score)}</strong> <span class="ci">{e(interval_short(_ci(est)))}</span>',
                    band=band,
                )
            )
    table_rows = [
        f'<tr><th scope="row">{e(name)}</th><td class="r num">{pct(est.score)}</td><td class="r num">{e(interval_short(_ci(est)))}</td>'
        f"<td>{e(', '.join(tied_with(name, items)) or 'none')}</td></tr>"
        for name, est in sorted(items, key=lambda item: (-item[1].score, item[0]))
    ]
    return _viz(
        dot_rows(rows, score_ticks(lo, hi, step)),
        takeaway=leader_sentence(items),
        caption=(
            "Dot: overall score; line: its 95% range; the axis is zoomed in. The shaded column is the leader’s range: "
            "a model whose line reaches it may be tied with the leader. Groups run from the top: each is its highest "
            "model plus every model left whose range overlaps that model’s."
        ),
        table=_table(
            [_th("Model"), _th("Score", True), _th("95% range", True), _th("Range overlaps")],
            table_rows,
            label="Overall scores and overlapping ranges",
        ),
    )


def _level_plan(ranked: list[Entry], test: str) -> tuple[list[str], dict[str, int], dict[str, dict[str, Est]]] | None:
    """Levels with enough items to plot, item counts for every level, and
    each model's estimates by level. None when fewer than two levels qualify."""
    by = _breakdown(ranked, test, "by_cefr")
    present = [level for level in CEFR_ORDER if level in by]
    counts = {level: _n_items(by[level]) for level in present}
    plotted = [level for level in present if counts[level] >= MIN_ITEMS]
    if len(plotted) < 2:
        return None
    lookup = {level: {en.slug: est for en, est in by[level]} for level in present}
    return plotted, counts, lookup


def _levels_viz(suite: SuiteInfo, ranked: list[Entry], test: str) -> str:
    plotted, counts, lookup = _level_plan(ranked, test)  # type: ignore[misc]
    names = _labels(ranked)
    models = [en for en, _ in _test_ests(ranked, test)]
    series = [
        Series(names[en.slug], tuple((lookup[lv][en.slug].score if en.slug in lookup[lv] else None) for lv in plotted))
        for en in models
    ]
    columns = [[lookup[lv][en.slug].score for en in models if en.slug in lookup[lv]] for lv in plotted]
    if len(models) == 1:
        series = [Series(series[0].label, series[0].values, "median")]
        band: list[tuple[float, float] | None] = []
    else:
        if len(models) > LINE_LIMIT:
            series = []  # too many to tell apart: the band and the median carry the chart, the table every model
        series.append(Series("Median", tuple(statistics.median(c) if c else None for c in columns), "median"))
        band = [(min(c), max(c)) if c else None for c in columns]
    title = _test_title(suite.key, test)
    median_words = ", ".join(f"{lv} {pct(v)}" for lv, v in zip(plotted, series[-1].values) if v is not None)
    chart = line_chart(
        plotted,
        [f"n={counts[lv]}" for lv in plotted],
        series,
        band=band,
        chart_id=f"levels-{suite.key}-{test.replace('_', '-')}",
        title=f"{title}: score by CEFR level",
        desc=f"{series[-1].label}: {median_words}.",
    )
    per_model = [(names[en.slug], {lv: lookup[lv][en.slug] for lv in plotted if en.slug in lookup[lv]}) for en in models]
    head = [_th("Model")] + [_th(f"{lv} <span class=\"ci-text\">n={counts[lv]}</span>") for lv in counts]
    rows = []
    for en in models:
        cells = []
        for lv in counts:
            if lv not in plotted:
                cells.append('<td class="muted">too few items</td>')
            else:
                cells.append(_score_cell(lookup[lv].get(en.slug)))
        rows.append(f'<tr><th scope="row">{e(names[en.slug])}</th>{"".join(cells)}</tr>')
    left_out = f" With more than {LINE_LIMIT} models, single lines are left out; the table has every model." if len(models) > LINE_LIMIT else ""
    caption = (
        f"{'Thin lines: one per model (point at a line to name it). ' if len(models) <= LINE_LIMIT else ''}"
        "Bold line: the median model. Band: lowest to highest model. n: items at that level; levels with fewer than "
        f"{MIN_ITEMS} items are left out.{left_out}"
        if len(models) > 1
        else f"Score at each level. n: items at that level; levels with fewer than {MIN_ITEMS} items are left out."
    )
    return _viz(
        chart,
        takeaway=level_sentence(plotted, per_model),
        caption=caption,
        table=_table(head, rows, label=f"{title} by CEFR level"),
    )


def _levels_section(suite: SuiteInfo, ranked: list[Entry], tests: list[str]) -> str:
    charts, skipped = [], []
    for test in tests:
        if not _test_ests(ranked, test):
            continue
        if _level_plan(ranked, test) is None:
            skipped.append(_test_title(suite.key, test))
            continue
        charts.append(_subsection(_finding_anchor("levels", test), _test_title(suite.key, test), _levels_viz(suite, ranked, test)))
    if not charts:
        return ""
    note = (
        f'<p class="muted">Not shown: {e(", ".join(skipped))}, with fewer than two levels of {MIN_ITEMS} or more items.</p>'
        if skipped
        else ""
    )
    return f'<div class="multiples">{"".join(charts)}</div>{note}'


def _topic_plan(ranked: list[Entry], test: str) -> tuple[list[str], dict[str, int], dict[str, list[tuple[Entry, Est]]], int] | None:
    """Topics with enough items, highest average first. None when fewer than three."""
    if _scoring(ranked, test) not in ("accept_list", "tutor"):
        return None
    by = _breakdown(ranked, test, "by_phenomenon")
    counts = {key: _n_items(pairs) for key, pairs in by.items()}
    keep = [key for key in by if counts[key] >= MIN_ITEMS]
    if len(keep) < 3:
        return None
    keep.sort(key=lambda k: (-_mean([est.score for _, est in by[k]]), k))
    return keep, counts, by, len(by)


def _spread_rows(
    keys: list[str],
    by: dict[str, list[tuple[Entry, Est]]],
    counts: dict[str, int],
    label: Callable[[str], str],
    names: dict[str, str],
    *,
    code: bool = False,
) -> list[DotRow]:
    """One row per category: the average over models as a bar, every model as a tick."""
    rows = []
    for key in keys:
        pairs = by[key]
        mean = _mean([est.score for _, est in pairs])
        scores = sorted(est.score for _, est in pairs)
        marks = [Mark(est.score, "tick", "muted", title=f"{names[en.slug]}: {pct(est.score)}") for en, est in pairs]
        marks.append(Mark(mean, "bar", "hl", title=f"Average over {_plural(len(pairs), 'model')}: {pct(mean)}"))
        note = f"{counts[key]} items" + (f" · <code>{e(key)}</code>" if code else "")
        rows.append(
            DotRow(
                label_html=e(label(key)),
                aria=f"{label(key)}: average {pct(mean)} over {_plural(len(pairs), 'model')}, models from {pct(scores[0])} to {pct(scores[-1])}; {counts[key]} items",
                marks=tuple(marks),
                value_html=f"<strong>{pct(mean)}</strong>",
                note_html=note,
            )
        )
    return rows


def _spread_table(keys: list[str], by: dict[str, list[tuple[Entry, Est]]], counts: dict[str, int], label: Callable[[str], str], names: dict[str, str], head: str) -> str:
    rows = []
    for key in keys:
        pairs = sorted(by[key], key=lambda p: (p[1].score, names[p[0].slug]))
        mean = _mean([est.score for _, est in pairs])
        rows.append(
            f'<tr><th scope="row">{e(label(key))}</th><td class="r num">{counts[key]}</td><td class="r num">{pct(mean)}</td>'
            f"<td>{e(names[pairs[0][0].slug])} ({pct(pairs[0][1].score)})</td><td>{e(names[pairs[-1][0].slug])} ({pct(pairs[-1][1].score)})</td></tr>"
        )
    return _table(
        [_th(e(head)), _th("Items", True), _th("Average", True), _th("Lowest model"), _th("Highest model")],
        rows,
        label=head,
    )


def _topics_viz(suite: SuiteInfo, ranked: list[Entry], test: str) -> str:
    keep, counts, by, total = _topic_plan(ranked, test)  # type: ignore[misc]
    names = _labels(ranked)
    noun = TEST_EXPLAIN.get((suite.key, test), DEFAULT_EXPLAIN)[2]
    if len(keep) > 2 * TOPIC_SHOW:
        shown: list[DotRow | str] = [f"Easiest {TOPIC_SHOW}"]
        shown += _spread_rows(keep[:TOPIC_SHOW], by, counts, _topic_name, names)
        shown.append(f"Hardest {TOPIC_SHOW}")
        shown += _spread_rows(keep[-TOPIC_SHOW:], by, counts, _topic_name, names)
        scope = f"the {TOPIC_SHOW} easiest and {TOPIC_SHOW} hardest of {len(keep)} {noun}s with {MIN_ITEMS} or more items"
    else:
        shown = list(_spread_rows(keep, by, counts, _topic_name, names))
        scope = f"every {noun} with {MIN_ITEMS} or more items"
    left_out = total - len(keep)
    per_model = [
        (names[en.slug], {k: est for k in (keep[0], keep[-1]) for x, est in by[k] if x.slug == en.slug})
        for en, _ in _test_ests(ranked, test)
    ]
    caption = (
        f"Bar: average over models; ticks: single models. Shows {scope}"
        + (f"; {left_out} smaller ones are left out." if left_out else ".")
    )
    return _viz(
        dot_rows(shown, PERCENT_TICKS),
        takeaway=compare_sentence(per_model, _topic_name, noun, high_word="easiest", low_word="hardest"),
        caption=e(caption),
        table=_spread_table(keep, by, counts, _topic_name, names, noun.capitalize()),
    )


def _spread_gap(by: dict[str, list[tuple[Entry, Est]]], keys: list[str]) -> float:
    means = [_mean([est.score for _, est in by[k]]) for k in keys]
    return max(means) - min(means)


def _lead_first(suite: SuiteInfo, plans: list[tuple[str, float, str]], section: str) -> str:
    """Charts in one section: the one with the widest gap open, the rest folded."""
    if not plans:
        return ""
    lead = max(plans, key=lambda p: (p[1], -[t for t, _, _ in plans].index(p[0])))[0]
    ordered = [p for p in plans if p[0] == lead] + [p for p in plans if p[0] != lead]
    return "".join(
        _subsection(_finding_anchor(section, test), _test_title(suite.key, test), body, open_=test == lead)
        for test, _, body in ordered
    )


def _topics_section(suite: SuiteInfo, ranked: list[Entry], tests: list[str]) -> str:
    plans = []
    for test in tests:
        plan = _topic_plan(ranked, test)
        if plan:
            keep, _, by, _ = plan
            plans.append((test, _spread_gap(by, keep), _topics_viz(suite, ranked, test)))
    if not plans:
        return ""
    note = (
        '<p class="muted">Topic labels come from the item sources. Where results include a joint breakdown, '
        '<a href="#topic-language">grammar topic by language</a> shows how these averages differ by language.</p>'
    )
    return _lead_first(suite, plans, "topics") + note


def _topic_language_section(suite: SuiteInfo, ranked: list[Entry], tests: list[str]) -> str:
    field = "by_l1_phenomenon" if suite.key == "tonada" else "by_language_phenomenon"
    present = [test for test in tests if any(field in en.tests[test] for en, _ in _test_ests(ranked, test))]
    if not present:
        return '<p class="empty-note">This view needs results files written by a newer version.</p>'
    return "".join(_subsection(_finding_anchor("topic-language", test), _test_title(suite.key, test),
                              _topic_language_viz(suite, ranked, test, field)) for test in present)


def _topic_language_viz(suite: SuiteInfo, ranked: list[Entry], test: str, field: str) -> str:
    by: dict[tuple[str, str], list[Est]] = {}
    groups, topics = set(), set()
    for en, _ in _test_ests(ranked, test):
        for group, values in (en.tests[test].get(field) or {}).items():
            groups.add(group)
            for topic, stat in values.items():
                topics.add(topic)
                est = _est(stat)
                if est and (est.n or 0) >= MIN_TOPIC_ITEMS:
                    by.setdefault((topic, group), []).append(est)
    columns = _ordered_groups(groups, suite.group_order)
    means = {key: _mean([est.score for est in values]) for key, values in by.items()}
    ordered = sorted(topics, key=lambda topic: (
        _mean([value for (t, _), value in means.items() if t == topic])
        if any(t == topic for t, _ in means) else 2, topic))
    lows = {group: min(value for (t, g), value in means.items() if g == group)
            for group in columns if any(g == group for _, g in means)}
    rows, plain = [], []
    for i, topic in enumerate(ordered):
        cells, text = [], []
        for group in columns:
            key = (topic, group)
            if key not in means:
                cells.append('<td class="empty">—</td>')
                text.append('<td>—</td>')
                continue
            score, values = means[key], by[key]
            count = min(est.n or 0 for est in values)
            high_count = max(est.n or 0 for est in values)
            count_text = str(count) if count == high_count else f"{count}–{high_count}"
            tip = f"{_topic_name(topic)}, {_group_name(group)}: {pct(score)}; {count_text} dataset items per model; {len(values)} models"
            mark = '<span class="mk" aria-hidden="true">▼</span><span class="sr-only"> (hardest in this column)</span>' if score == lows[group] else ""
            cells.append(f'<td title="{e(tip)}"{heat_style(score)}>{pct(score)}{mark}</td>')
            text.append(f'<td class="num">{pct(score)}; {count_text} items per model; {len(values)} models</td>')
        more = ' class="more"' if i >= 12 else ""
        heading = f'<th scope="row">{e(_topic_name(topic))}</th>'
        rows.append(f'<tr{more}>{heading}{"".join(cells)}</tr>')
        plain.append(f'<tr>{heading}{"".join(text)}</tr>')
    head = [_th("Topic")] + [_th(e(_group_name(group))) for group in columns]
    chart = _table(head, rows, css="heat topic-language", label="Topic scores by first language" if suite.key == "tonada" else "Topic scores by language")
    chart = _fold(chart, len(ordered), 12, "topics")
    note = (
        "Minimum: 5 dataset items per topic–language pair in each contributing model result. "
        "A dash means no qualifying result. Counts are dataset items, not repeated asks or sums across models."
    )
    chart += f'<p class="table-note">{note}</p>'
    return _viz(
        chart,
        takeaway=topic_language_sentence([(_topic_name(t), _group_name(g), value) for (t, g), value in means.items()]),
        caption=("Mean score across available models, each model weighted equally; topics sorted by mean, hardest first. "
                 "Darker cells mean higher scores (0–100%). ▼ marks every tied hardest cell in each column. "
                 + ("Columns are learners’ first languages. " if suite.key == "tonada" else "")
                 + "Model coverage can differ between cells; averages have no pooled confidence interval."),
        table=_table(head, plain, label="Topic scores, dataset item counts and contributing models"),
        css="viz-topic-language",
    )


def _direction_plan(ranked: list[Entry], test: str) -> list[tuple[str, str, str, str]] | None:
    by = _breakdown(ranked, test, "by_phenomenon")
    kept = [d for d in DIRECTIONS if d[0] in by and _n_items(by[d[0]]) >= MIN_ITEMS]
    if not {"to_english", "from_english"} <= {d[0] for d in kept}:
        return None
    return kept


def _directions_viz(suite: SuiteInfo, ranked: list[Entry], test: str) -> str:
    kept = _direction_plan(ranked, test) or []
    by = _breakdown(ranked, test, "by_phenomenon")
    names = _labels(ranked)
    lookup = {key: {en.slug: est for en, est in by[key]} for key, *_ in kept}
    counts = {key: _n_items(by[key]) for key, *_ in kept}
    models = [en for en, _ in _test_ests(ranked, test)]
    values = [est.score for key in lookup for est in lookup[key].values()]
    lo, hi, step = nice_domain(values)

    def pos(v: float) -> float:
        return (v - lo) / (hi - lo)

    rows, pairs, table_rows = [], [], []
    for en in models:
        name = names[en.slug]
        marks, words = [], []
        for key, label, shape, tone in kept:
            est = lookup[key].get(en.slug)
            if est is None:
                continue
            marks.append(Mark(pos(est.score), shape, tone, title=f"{name}, {label.lower()}: {pct(est.score)}"))
            words.append(f"{label.lower()} {pct(est.score)}")
        into, out = lookup["to_english"].get(en.slug), lookup["from_english"].get(en.slug)
        gap = f"{(into.score - out.score) * 100:+.1f} pts" if into and out else "n/a"
        if into and out:
            pairs.append((name, into, out))
        rows.append(
            DotRow(
                label_html=f'<a href="models/{en.slug}.html">{e(name)}</a>',
                aria=f"{name}: {'; '.join(words)}",
                marks=tuple(marks),
                value_html=f'<span class="num">{e(gap)}</span>',
            )
        )
        table_rows.append(
            f'<tr><th scope="row">{e(name)}</th>{"".join(_score_cell(lookup[key].get(en.slug)) for key, *_ in kept)}</tr>'
        )
    key_html = _key([(shape, tone, f"{e(label)} <span class=\"ci-text\">{counts[key]} items</span>") for key, label, shape, tone in kept])
    legal = (
        " The legal and administrative items are published parallel text, in either direction; Breton is paired with French there."
        if any(k == "legal_or_administrative" for k, *_ in kept)
        else ""
    )
    return _viz(
        key_html + dot_rows(rows, score_ticks(lo, hi, step), top=MODEL_ROWS_TOP, more_label="models"),
        takeaway=direction_sentence(pairs),
        caption=e(
            "chrF++ score by direction for each model; the axis is zoomed in. Right: into English minus out of "
            f"English, in percentage points.{legal}"
        ),
        table=_table(
            [_th("Model")] + [_th(f"{e(label)} <span class=\"ci-text\">n={counts[key]}</span>") for key, label, *_ in kept],
            table_rows,
            label="Translation score by direction",
        ),
    )


def _directions_section(suite: SuiteInfo, ranked: list[Entry], tests: list[str]) -> str:
    charts = [
        _subsection(_finding_anchor("directions", test), _test_title(suite.key, test), _directions_viz(suite, ranked, test))
        for test in tests
        if _test_ests(ranked, test) and _direction_plan(ranked, test)
    ]
    return "".join(charts)


TUTOR_COLUMNS = (("found", "Found the error"), ("fixed", "Fixed it"), ("no_overcorrection", "Changed nothing else"))


def _step_cell(value: float | None, *, strong: bool = False, judge: bool = False) -> str:
    if value is None:
        return '<td class="muted">n/a</td>'
    css = "step-bar judge" if judge else "step-bar"
    number = f"<strong>{pct(value)}</strong>" if strong else pct(value)
    return (
        f'<td class="step" data-v="{value:.6f}"><span class="{css}" aria-hidden="true"><span style="width:{max(0.0, min(1.0, value)) * 100:.1f}%"></span></span>'
        f'<span class="num">{number}</span></td>'
    )


def _tutor_viz(suite: SuiteInfo, ranked: list[Entry], test: str, current_pair: set[str]) -> str:
    names = _labels(ranked)
    pairs = [(en, est) for en, est in _test_ests(ranked, test) if (en.tests[test].get("tutor") or {}).get("components")]
    pairs.sort(key=lambda p: (-p[1].score, names[p[0].slug]))
    rows, plain, parts, explanations = [], [], [], []
    for en, est in pairs:
        block = en.tests[test]
        tutor = block.get("tutor") or {}
        components = tutor.get("components") or {}
        explanation = tutor.get("explanation") or {}
        comparable = _explanation_comparable(block, en.run, current_pair)
        parts.append((names[en.slug], {key: components.get(key) for key, _ in TUTOR_COLUMNS}))
        if comparable:
            explanations.append(float(explanation["score"]))
            judge_cell = _step_cell(explanation.get("score"), judge=True)
        else:
            reason = {
                "not_scored_same_family_as_judge": "not scored: same family as a judge",
                "not_scored_judge_unavailable": "not scored: judge unavailable",
            }.get(explanation.get("status") or "", "not comparable: other judge pair")
            judge_cell = f'<td class="muted step-none">{e(reason)}</td>'
        cells = "".join(_step_cell(components.get(key)) for key, _ in TUTOR_COLUMNS)
        rows.append(
            f'<tr><th scope="row">{_model_link(en)}</th>{cells}{_step_cell(est.score, strong=True)}{judge_cell}</tr>'
        )
        plain.append(
            f'<tr><th scope="row">{e(names[en.slug])}</th>{_score_cell(est)}'
            + (_score_cell(Est(float(explanation["score"]), tuple(explanation["ci95"]) if explanation.get("ci95") else None)) if comparable else '<td class="muted">n/a</td>')
            + f'<td class="r num">{pct(explanation.get("judge_agreement")) if comparable else "n/a"}</td></tr>'
        )
    head = (
        [_th("Model")]
        + [_th(e(label)) for _, label in TUTOR_COLUMNS]
        + [_th("All three: the score"), '<th scope="col" class="judge-col">Explanation <span class="tag">judge-marked</span></th>']
    )
    chart = _table(head, rows, css="board steps", label=f"{_test_title(suite.key, test)}: step by step")
    return _viz(
        chart,
        takeaway=tutor_sentence(parts, explanations),
        caption=e(
            "Share of items that pass each check, over every ask. The score needs all three rule checks on the same "
            "item. The explanation (hatched) is marked by two judge models from other families: it is secondary, not "
            "human-validated and not part of the score."
        ),
        table=_table(
            [_th("Model"), _th("Score and 95% range"), _th("Explanation and 95% range"), _th("Judges agree", True)],
            plain,
            label="Tutor score and explanation",
        ),
    )


def _tutor_section(suite: SuiteInfo, ranked: list[Entry], tests: list[str], current_pair: set[str]) -> str:
    return "".join(
        _subsection(_finding_anchor("tutor", test), _test_title(suite.key, test), _tutor_viz(suite, ranked, test, current_pair))
        for test in tests
        if _has_tutor_steps(ranked, test)
    )


def _evidence_plan(ranked: list[Entry], test: str) -> tuple[list[str], dict[str, int], dict[str, list[tuple[Entry, Est]]]] | None:
    by = _breakdown(ranked, test, "by_evidence")
    counts = {key: _n_items(pairs) for key, pairs in by.items()}
    keep = [key for key in by if counts[key] >= MIN_ITEMS]
    if len(keep) < 2:
        return None
    keep.sort(key=lambda k: (-_mean([est.score for _, est in by[k]]), k))
    return keep, counts, by


def _evidence_name(key: str) -> str:
    return EVIDENCE_NAMES.get(key, key)


def _evidence_viz(suite: SuiteInfo, ranked: list[Entry], test: str) -> str:
    keep, counts, by = _evidence_plan(ranked, test)  # type: ignore[misc]
    names = _labels(ranked)
    left_out = [k for k in by if k not in keep]
    per_model = [
        (names[en.slug], {k: est for k in keep for x, est in by[k] if x.slug == en.slug}) for en, _ in _test_ests(ranked, test)
    ]
    caption = (
        "Bar: average over models; ticks: single models. The groups also differ in what they contain, so a gap "
        "is not by itself proof that weaker gold is wrong."
    )
    if left_out:
        caption += f" Left out, with fewer than {MIN_ITEMS} items: {', '.join(_evidence_name(k) for k in sorted(left_out))}."
    return _viz(
        dot_rows(_spread_rows(keep, by, counts, _evidence_name, names, code=True), PERCENT_TICKS),
        takeaway=compare_sentence(per_model, lambda k: f"‘{_evidence_name(k)}’", "evidence group"),
        caption=e(caption),
        table=_spread_table(keep, by, counts, _evidence_name, names, "Evidence"),
    )


def _evidence_section(suite: SuiteInfo, ranked: list[Entry], tests: list[str]) -> str:
    plans = []
    for test in tests:
        plan = _evidence_plan(ranked, test)
        if plan:
            plans.append((test, _spread_gap(plan[2], plan[0]), _evidence_viz(suite, ranked, test)))
    if not plans:
        return ""
    return (
        '<p class="section-intro">Labels, from strongest to weakest gold: cross-checked against a dictionary '
        "(BÚNaMo or Kaikki), from a published parallel corpus, from the course alone, or marked unverified or built "
        'by a rule. <a href="methodology.html#no-human-review">What each label means</a>.</p>' + _lead_first(suite, plans, "evidence")
    )


def _cost_viz(ranked: list[Entry]) -> str:
    names = _labels(ranked)
    items = sorted(
        ((en, en.cost_per_correct_usd * 1000) for en in ranked if en.cost_per_correct_usd),
        key=lambda p: (p[1], names[p[0].slug]),
    )
    if not items:
        return ""
    pos, ticks, log = money_axis([v for _, v in items])
    rows = [
        DotRow(
            label_html=f'<a href="models/{en.slug}.html">{e(names[en.slug])}</a>',
            aria=f"{names[en.slug]}: {money(v)} per 1,000 correct answers",
            marks=(Mark(pos(v), "bar", "hl", title=f"{names[en.slug]}: {money(v)} per 1,000 correct"),),
            value_html=f"<strong>{_usd(v)}</strong>",
        )
        for en, v in items
    ]
    table_rows = [
        f'<tr><th scope="row">{e(names[en.slug])}</th><td class="r num">{pct(en.score)}</td>'
        f'<td class="r num">{_usd(en.cost_usd)}</td><td class="r num">{_usd(v)}</td></tr>'
        for en, v in items
    ]
    scale = " Log scale: each grid step multiplies the cost, so equal gaps are equal ratios." if log else ""
    return _viz(
        dot_rows(rows, ticks, top=MODEL_ROWS_TOP, more_label="models"),
        takeaway=spread_sentence([(names[en.slug], v) for en, v in items], "cost per 1,000 correct answers", money, ratio=True),
        caption=e(
            "Suite cost, candidate and judges, divided by the number of full-score answers and shown per 1,000 "
            f"answers; cheapest first.{scale}"
        )
        + ' Score against cost per run is on the <a href="models.html#cost">Models page</a>.',
        table=_table(
            [_th("Model"), _th("Score", True), _th("Cost per run", True), _th("Per 1,000 correct", True)],
            table_rows,
            label="Cost per correct answer",
        ),
    )


def _consistency_viz(suite: SuiteInfo, ranked: list[Entry], tests: list[str]) -> str:
    names = _labels(ranked)
    per_model = []
    for en in ranked:
        values = {
            t: float(en.tests[t]["consistency"])
            for t in tests
            if _complete_score(en, t) is not None and en.tests[t].get("consistency") is not None
        }
        if values:
            per_model.append((en, values, _mean(list(values.values()))))
    if not per_model:
        return ""
    per_model.sort(key=lambda p: (-p[2], names[p[0].slug]))
    shown = [t for t in tests if any(t in values for _, values, _ in per_model)]
    rows = []
    for en, values, mean in per_model:
        marks = [Mark(v, "tick", "muted", title=f"{_test_title(suite.key, t)}: {pct(v)}") for t, v in values.items()]
        marks.append(Mark(mean, "bar", "hl", title=f"Mean over {_plural(len(values), 'test')}: {pct(mean)}"))
        rows.append(
            DotRow(
                label_html=f'<a href="models/{en.slug}.html">{e(names[en.slug])}</a>',
                aria=f"{names[en.slug]}: mean consistency {pct(mean)}; "
                + "; ".join(f"{_test_title(suite.key, t)} {pct(v)}" for t, v in values.items()),
                marks=tuple(marks),
                value_html=f"<strong>{pct(mean)}</strong>",
            )
        )
    table_rows = [
        f'<tr><th scope="row">{e(names[en.slug])}</th>'
        + "".join(f'<td class="r num">{pct(values.get(t))}</td>' for t in shown)
        + f'<td class="r num"><strong>{pct(mean)}</strong></td><td class="r num">{pct(en.score)}</td></tr>'
        for en, values, mean in per_model
    ]
    epochs = sorted({en.epochs for en, _, _ in per_model if en.epochs})
    asks = f"all {epochs[0]} asks" if len(epochs) == 1 else "every ask"
    return _viz(
        dot_rows(rows, PERCENT_TICKS, top=MODEL_ROWS_TOP, more_label="models"),
        takeaway=spread_sentence([(names[en.slug], mean) for en, _, mean in per_model], "mean consistency", pct),
        caption=e(
            f"Consistency is the share of items that got the same score in {asks}: a model that often changes its "
            "answer is less dependable for learners. Bar: mean over the tests; ticks: single tests (point at one to name "
            "it). Translation tests give partial credit, so exact repeats are rarer there."
        ),
        table=_table(
            [_th("Model")] + [_th(e(_test_title(suite.key, t)), True) for t in shown] + [_th("Mean", True), _th("Score", True)],
            table_rows,
            label="Consistency by test",
        ),
    )


def _consistency_scatter(suite: SuiteInfo, ranked: list[Entry], tests: list[str], *, accept_only: bool = False) -> str:
    names = _labels(ranked)
    # Require the same tests for every point; do not silently average whatever
    # happens to be available for an individual model.
    selected = [t for t in tests if not accept_only or _scoring(ranked, t) == "accept_list"]
    points, rows, legend = [], [], []
    for entry in ranked:
        blocks = [entry.tests.get(t, {}) for t in selected]
        if not blocks or entry.score is None or any(
            b.get("status") != "complete" or b.get("consistency") is None or b.get("epochs") != 3 for b in blocks
        ):
            continue
        mean = _mean([float(b["consistency"]) for b in blocks])
        points.append(ScatterPoint(entry.rank or 0, names[entry.slug], mean, entry.score, entry.ci95))
        rows.append(f'<tr><th scope="row">{_model_link(entry)}</th><td>{pct(mean)}</td><td>{pct(entry.score)}</td></tr>')
        legend.append(f'<li value="{entry.rank}">{_model_link(entry)} <span class="num">{pct(mean)} consistency; {pct(entry.score)} score</span></li>')
    if not points:
        return ""
    chart_id = f"{suite.key}-consistency-{'accept' if accept_only else 'all'}"
    caption = (
        "Points are models, labelled by suite rank; whiskers are 95% score ranges. Crowded labels link back to their dots. "
        "x: share of items with the same score on all three asks, averaged equally over tests; "
        "y: overall suite score. Translation tests rarely repeat exactly, so consistency is lower there by construction. "
        + ("Consistency uses accept-list tests only; y still uses the overall suite score. " if accept_only else "Consistency uses all suite tests. ")
        + "Models need three-ask consistency on every included test."
    )
    return _viz(
        '<div class="scatter-split">' + scatter(points, chart_id, "Score against consistency", consistency=True)
        + f'<ol class="legend">{"".join(legend)}</ol></div>',
        takeaway=correlation_sentence([(p.cost, p.score) for p in points]),
        caption=e(caption),
        table=_table(
            [_th("Model"), _th("Mean consistency"), _th("Overall suite score")], rows,
            label="Score against consistency",
            caption="Link strength uses |Spearman rho|: ≥0.7 strong, ≥0.4 moderate, ≥0.2 weak; otherwise no clear link. Descriptive, not a significance test.",
        ),
        css="viz-consistency-scatter",
    )


def _consistency_scatter_section(suite: SuiteInfo, ranked: list[Entry], tests: list[str]) -> str:
    main = _consistency_scatter(suite, ranked, tests)
    if not main:
        return ""
    accept = [t for t in tests if _scoring(ranked, t) == "accept_list"]
    restricted = _consistency_scatter(suite, ranked, tests, accept_only=True) if accept and len(accept) < len(tests) else ""
    return _heading("score-consistency", "Score against consistency", 3) + main + (
        _subsection("consistency-accept-list", "Accept-list tests only", restricted, open_=False) if restricted else ""
    )


def _findings_page(suite: SuiteInfo, ranked: list[Entry], tests: list[str], current_pair: set[str]) -> str:
    parts = [
        _page_head(
            "Findings",
            "What the results show beyond the ranking: profiles, ties, difficulty, topics and cost. Every chart "
            "opens with a sentence computed from the data and has its numbers in a table.",
        ),
        _honesty("./"),
    ]
    if not ranked:
        parts.append(
            '<p class="empty-note">No complete runs yet. This page will show every model on every test, which models '
            "are tied, scores by level, topic and evidence, and cost per correct answer.</p>"
        )
        return "\n".join(parts)
    bodies = {
        "profile": _matrix_viz(suite, ranked, tests),
        "ties": _ties_viz(ranked),
        "levels": _levels_section(suite, ranked, tests),
        "topics": _topics_section(suite, ranked, tests),
        "topic-language": _topic_language_section(suite, ranked, tests),
        "directions": _directions_section(suite, ranked, tests),
        "tutor": _tutor_section(suite, ranked, tests, current_pair),
        "evidence": _evidence_section(suite, ranked, tests),
        "cost": _cost_viz(ranked),
        "consistency": _consistency_viz(suite, ranked, tests) + _consistency_scatter_section(suite, ranked, tests),
    }
    present = [(key, title, intro) for key, title, intro in FINDINGS if bodies.get(key)]
    parts.append(
        '<nav class="toc-inline" aria-label="On this page"><ol>'
        + "".join(f'<li><a href="#{key}">{e(title)}</a></li>' for key, title, _ in present)
        + "</ol></nav>"
    )
    for key, title, intro in present:
        parts.append(
            f'<section class="finding" aria-labelledby="{key}">{_heading(key, e(title))}'
            f'<p class="section-intro">{e(intro)}</p>{bodies[key]}</section>'
        )
    return "\n".join(parts)


def _findings_links(ranked: list[Entry], test: str) -> list[tuple[str, str]]:
    """Findings views that include this test, as (anchor, label)."""
    links = []
    if _level_plan(ranked, test):
        links.append((_finding_anchor("levels", test), "by CEFR level"))
    if _topic_plan(ranked, test):
        links.append((_finding_anchor("topics", test), "hardest topics"))
    if _direction_plan(ranked, test):
        links.append((_finding_anchor("directions", test), "by direction"))
    if _has_tutor_steps(ranked, test):
        links.append((_finding_anchor("tutor", test), "step by step"))
    if _evidence_plan(ranked, test):
        links.append((_finding_anchor("evidence", test), "by evidence"))
    return links


# ---------------------------------------------------------------------------
# Models index


def _radar_data(suite: SuiteInfo, entry: Entry, tests: list[str], ranked: list[Entry]) -> tuple[list[str], list[float], list[float], list[float]]:
    labels, own, medians, best = [], [], [], []
    for test in tests:
        value = _complete_score(entry, test)
        scores = [est.score for _, est in _test_ests(ranked, test)]
        if value is None or not scores:
            continue
        labels.append(_test_title(suite.key, test))
        own.append(value)
        medians.append(statistics.median(scores))
        best.append(max(scores))
    return labels, own, medians, best


RADAR_CAPTION = (
    "One axis per test, with the same scale on every profile: 0% at the centre to 100% at the outer ring. "
    "Solid accent: this model; faint dashed polygon: median model score on each test; faint dotted outer "
    "polygon: best score on each test (not necessarily one model). Vertex labels show this model’s scores. "
    "Compare scores, not polygon area; no confidence intervals are shown."
)


def _radar_viz(suite: SuiteInfo, entry: Entry, tests: list[str], ranked: list[Entry]) -> str:
    labels, own, medians, best = _radar_data(suite, entry, tests, ranked)
    if len(labels) < 3:
        return ""
    names = _labels(ranked)
    sentence = profile_sentence(names[entry.slug], [(_test_title(suite.key, test), _ranking_rows(ranked, test)) for test in tests])
    rows = [f'<tr><th scope="row">{e(label)}</th><td>{pct(value)}</td><td>{pct(median)}</td><td>{pct(high)}</td></tr>'
            for label, value, median, high in zip(labels, own, medians, best)]
    return _viz(
        radar(labels, own, medians, best, f"{names[entry.slug]} test profile"),
        takeaway=sentence, caption=RADAR_CAPTION,
        table=_table([_th("Test"), _th("This model"), _th("Median"), _th("Best")], rows, label="Radar profile scores"),
        css="viz-radar",
    )


def _radar_grid(suite: SuiteInfo, ranked: list[Entry], tests: list[str]) -> str:
    cards, rows = [], []
    names = _labels(ranked)
    for entry in ranked:
        labels, own, medians, best = _radar_data(suite, entry, tests, ranked)
        if len(labels) < 3:
            continue
        more = ' class="more"' if len(cards) >= MODEL_ROWS_TOP else ""
        cards.append(f'<li{more}><a class="radar-card" href="models/{entry.slug}.html"><strong>{e(names[entry.slug])}</strong>'
                     + radar(labels, own, medians, best, f"{names[entry.slug]} test profile") + "</a></li>")
        rows.append(f'<tr><th scope="row">{_model_link(entry)}</th>' + "".join(f'<td>{pct(_complete_score(entry, t))}</td>' for t in tests) + "</tr>")
    return _viz(
        _fold(f'<ol class="radar-grid-cards">{"".join(cards)}</ol>', len(cards), MODEL_ROWS_TOP, "models"),
        takeaway=matrix_sentence([(_test_title(suite.key, test), _ranking_rows(ranked, test)) for test in tests]),
        caption=RADAR_CAPTION + " Select a profile to open the model page; ordered by suite rank.",
        table=_table([_th("Model")] + [_th(e(_test_title(suite.key, t))) for t in tests], rows, label="Model profile scores"),
        css="viz-radar-grid",
    )


def _models_page(suite: SuiteInfo, entries: list[Entry]) -> str:
    ranked = [entry for entry in entries if entry.ranked]
    unranked = [entry for entry in entries if not entry.ranked]
    lede = (
        f"{_plural(len(ranked), 'model')} ranked. Select a model for every score, breakdown and cost."
        if ranked
        else "No model has a complete run yet."
    )
    parts = [_page_head("Models", lede), _honesty("./")]
    if ranked:
        cards = []
        for entry in ranked:
            cards.append(
                f'<li><a class="model-card" href="models/{entry.slug}.html">'
                f'<span class="mc-rank">#{entry.rank}</span>'
                f'<span class="mc-name">{e(entry.display)}{_data_tag(entry.data)}</span>'
                f'<span class="mc-sub">{e(entry.provider)} · <code>{e(entry.model)}</code></span>'
                f'<span class="mc-score num">{pct(entry.score)}</span>'
                f'<span class="mc-bar">{interval_bar(entry.score, entry.ci95, entry.display, decorative=True)}</span>'
                f'<span class="mc-range num">95% range {e(interval_short(entry.ci95))}</span>'
                f'<span class="mc-cost"><span><strong class="num">{_usd(entry.cost_usd)}</strong> per run</span>'
                f'<span><strong class="num">{_per_thousand(entry.cost_per_correct_usd)}</strong> per 1,000 correct</span></span>'
                "</a></li>"
            )
        parts.append(f'<ol class="model-cards">{"".join(cards)}</ol>')
        tests = _test_order(suite.key, {t for en in ranked for t in en.tests})
        if len(tests) >= 3:
            parts.append(_heading("radar-profiles", "Model profiles"))
            parts.append(_radar_grid(suite, ranked, tests))
    parts.append(_unranked_notice(unranked))
    if ranked:
        parts.append(_heading("cost", "Score against cost"))
        parts.append(_scatter_viz(suite, ranked))
        parts.append('<p class="more-link"><a href="findings.html#cost">Cost per correct answer, every model</a></p>')
        parts.append(
            '<p class="data-links">Data: <a href="data/leaderboard.json">this leaderboard as JSON</a> · '
            f'<a href="{REPO_URL}/tree/main/results/runs">every results file on GitHub</a></p>'
        )
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Model page


def _fact(label: str, value: str, small: str = "", lead: bool = False) -> str:
    small_html = f"<small>{small}</small>" if small else ""
    return f'<div class="fact{" lead" if lead else ""}"><dt>{label}</dt><dd>{value}{small_html}</dd></div>'


def _tests_table(suite: SuiteInfo, entry: Entry, tests: list[str]) -> str:
    rows = []
    for test in tests:
        block = entry.tests.get(test)
        if not block:
            continue
        rows.append(
            "<tr>"
            f'<th scope="row">{e(_test_title(suite.key, test))}{_test_tags(block)}</th>'
            f'<td class="r num"><strong>{pct(block.get("score"))}</strong></td>'
            f'<td class="r num">{e(interval_short(block.get("ci95")))}</td>'
            f'<td class="r num">{e(block.get("n_items"))}</td>'
            f'<td class="r num">{pct(block.get("consistency"))}</td>'
            f'<td class="r num">{_usd(block.get("cost_usd"))}</td>'
            f'<td class="r num">{_per_thousand(block.get("cost_per_correct_usd"))}</td>'
            "</tr>"
        )
    head = [
        _th("Test"), _th("Score", True), _th("95% range", True), _th("Items", True),
        _th("Consistency", True), _th("Cost", True), _th("Per 1,000 correct", True),
    ]
    note = "Consistency is the share of items that got the same score in every repeat ask."
    return _table(head, rows, caption=note, css="board", label="Items, consistency and cost by test")


def _breakdown_table(suite: SuiteInfo, entry: Entry, tests: list[str], field: str, label: str, order: tuple[str, ...]) -> str:
    present = [t for t in tests if entry.tests.get(t, {}).get(field)]
    values = _ordered_groups({v for t in present for v in entry.tests[t][field]}, order)
    if not values or (len(values) == 1 and values[0] in ("none", "unspecified")):
        return ""
    rows = []
    for value in values:
        cells = []
        for test in present:
            stat = entry.tests[test][field].get(value)
            if not stat or stat.get("score") is None:
                cells.append('<td class="muted">n/a</td>')
                continue
            cells.append(
                f'<td class="num"><strong>{pct(stat["score"])}</strong> '
                f'<span class="ci-text">{e(interval_short(stat.get("ci95")))} · n={e(stat.get("n_items"))}</span></td>'
            )
        rows.append(f'<tr><th scope="row">{e(_group_name(value))}</th>{"".join(cells)}</tr>')
    head = [_th(e(label))] + [_th(e(_test_title(suite.key, t))) for t in present]
    return _table(
        head,
        rows,
        caption="Score, 95% range and number of items (n) for each test.",
        css="board",
        label=f"Score by {label.lower()}",
    )


def _topics(suite: SuiteInfo, entry: Entry, tests: list[str]) -> str:
    out = []
    for test in tests:
        block = entry.tests.get(test) or {}
        topics = [
            (name, stat)
            for name, stat in (block.get("by_phenomenon") or {}).items()
            if stat and stat.get("score") is not None
        ]
        if len(topics) < 2:
            continue
        enough = [t for t in topics if (t[1].get("n_items") or 0) >= MIN_TOPIC_ITEMS]
        pool = enough if len(enough) >= 2 else topics
        best = sorted(pool, key=lambda t: (-t[1]["score"], t[0]))

        def topic_table(rows: list[tuple[str, dict[str, Any]]], label: str) -> str:
            body = [
                f'<tr><th scope="row">{e(_topic_name(name))}</th><td class="r num">{pct(stat["score"])}</td>'
                f'<td class="r num">{e(stat.get("n_items"))}</td></tr>'
                for name, stat in rows
            ]
            return _table([_th("Topic"), _th("Score", True), _th("Items", True)], body, caption=e(label), compact=True)

        out.append(f"<h3>{e(_test_title(suite.key, test))}</h3>")
        if len(pool) <= 2 * TOPIC_COUNT:
            out.append(topic_table(best, "All topics, highest score first."))
        else:
            worst = sorted(pool, key=lambda t: (t[1]["score"], t[0]))[:TOPIC_COUNT]
            out.append(
                '<div class="split">'
                + topic_table(best[:TOPIC_COUNT], f"Strongest {TOPIC_COUNT} topics.")
                + topic_table(worst, f"Weakest {TOPIC_COUNT} topics.")
                + "</div>"
            )
        if pool is enough and len(enough) < len(topics):
            out.append(f'<p class="muted">Only topics with at least {MIN_TOPIC_ITEMS} items are ranked.</p>')
    if not out:
        return ""
    return _drill(
        "topics",
        "Grammar topics",
        '<p class="section-intro">The topic is the grammar point or error type recorded on each item.</p>' + "".join(out),
    )


def _tutor(suite: SuiteInfo, entry: Entry, tests: list[str], current_pair: set[str]) -> str:
    out = []
    for test in tests:
        block = entry.tests.get(test) or {}
        tutor = block.get("tutor")
        if not tutor:
            continue
        explanation = tutor.get("explanation") or {}
        components = tutor.get("components") or {}
        judges = ", ".join(str(j) for j in tutor.get("judges") or []) or "n/a"
        comparable = "" if _explanation_comparable(block, entry.run, current_pair) else (
            " Not comparable with other models: this run was not judged by the current judge pair."
        )
        out.append(f"<h3>{e(_test_title(suite.key, test))}</h3>")
        out.append(
            '<dl class="plain">'
            f"<dt>Headline score</dt><dd>{pct(block.get('score'))}: found the error, fixed it and changed nothing else (rule-only, no judge).</dd>"
            f"<dt>Parts of the headline</dt><dd>Found {pct(components.get('found'))} · fixed {pct(components.get('fixed'))} · "
            f"no over-correction {pct(components.get('no_overcorrection'))}</dd>"
            f"<dt>Explanation score</dt><dd>{pct(explanation.get('score'))} (95% range {e(interval_short(explanation.get('ci95')))}), "
            f"{e(explanation.get('label') or 'judge-marked, not human-validated')}. An explanation passes only when both judges pass it.{e(comparable)}</dd>"
            f"<dt>Judge agreement</dt><dd>{pct(explanation.get('judge_agreement'))} of {e(explanation.get('judged_item_epochs'))} judged answers</dd>"
            f"<dt>Unscored</dt><dd>{e(explanation.get('unscored_item_epochs'))} answers a judge could not mark, after "
            f"{e(explanation.get('judge_failures'))} failed judge calls; they are left out, not scored 0.</dd>"
            f"<dt>Judges</dt><dd>{e(judges)}</dd>"
            "</dl>"
        )
    if not out:
        return ""
    return _drill(
        "tutor",
        "Tutor explanations",
        '<p class="section-intro">Tutor items also ask for a short explanation. Two judge models from other '
        "model families mark it. This is a secondary number: it is judge-marked and not human-validated.</p>"
        + "".join(out),
        note="judge-marked, secondary",
    )


def _price_rows(pricing: dict[str, Any] | None) -> str:
    if not pricing:
        return "<dd>n/a</dd>"
    parts = []
    for key, label in (
        ("prompt_usd_per_token", "input"),
        ("completion_usd_per_token", "output"),
        ("cache_read_usd_per_token", "cache read"),
        ("cache_write_usd_per_token", "cache write"),
    ):
        value = pricing.get(key)
        if value is not None:
            amount = float(value) * 1_000_000
            parts.append(f"${amount:.4f} {label}" if amount < 0.1 else f"${amount:.2f} {label}")
    prices = ", ".join(parts) + " per million tokens" if parts else "No prices listed"
    source = str(pricing.get("source") or "OpenRouter")
    where = f'<a href="{e(source)}">{e(source)}</a>' if source.startswith("https://") else e(source)
    return f"<dd>{e(prices)}. Retrieved {e(_date(pricing.get('retrieved_at')))} from {where}.</dd>"


def _cost(entry: Entry) -> str:
    run = entry.run
    cost = run.get("cost") or {}
    judge_cost = sum(
        float(((block.get("cost") or {}).get("judge") or {}).get("cost_usd") or 0.0) for block in entry.tests.values()
    )
    judge_pricing = (run.get("judge_info") or {}).get("pricing") or {}
    judge_prices = "".join(
        f"<dt>Judge {e(judge_id)}</dt>{_price_rows(judge_pricing.get(judge_id))}"
        for judge_id in run.get("judges") or []
        if judge_pricing.get(judge_id)
    )
    return _drill(
        "cost",
        "Cost and prices",
        '<dl class="plain">'
        f"<dt>This suite</dt><dd>{_usd(entry.cost_usd)}, of which {_usd(judge_cost)} was judge spend</dd>"
        f"<dt>Whole run</dt><dd>{_usd(cost.get('total_usd'))} for both suites, against a cap of {_usd(cost.get('cap_usd'))}</dd>"
        f"<dt>Cost per correct answer</dt><dd>{_usd(entry.cost_per_correct_usd)} ({_per_thousand(entry.cost_per_correct_usd)} per 1,000): "
        "suite cost divided by the number of full-score answers</dd>"
        f"<dt>Run date</dt><dd>{e(_date(entry.generated_at))}</dd>"
        f"<dt>Prices for {e(entry.model)}</dt>{_price_rows((run.get('model') or {}).get('pricing'))}"
        f"{judge_prices}"
        "</dl>",
    )


def _examples(suite: SuiteInfo, entry: Entry, tests: list[str]) -> str:
    out = []
    total = 0
    for test in tests:
        examples = [ex for ex in (entry.tests.get(test) or {}).get("failure_examples") or [] if ex.get("public") is True]
        if not examples:
            continue
        total += len(examples)
        out.append(f"<h3>{e(_test_title(suite.key, test))}</h3>")
        cards = []
        for ex in examples:
            where = [_group_name(str(ex.get(k))) for k in ("language", "l1") if ex.get(k) not in (None, "none", "english")]
            if ex.get("phenomenon"):
                where.append(_topic_name(str(ex["phenomenon"])))
            pivot = (
                f'<p class="label">Pivot text</p><pre>{e(ex.get("pivot_text"))}</pre>' if ex.get("pivot_text") else ""
            )
            score = ex.get("score")
            score_text = f"score {score:.2f}" if isinstance(score, (int, float)) else ""
            cards.append(
                '<article class="example">'
                f"<h4>{e(ex.get('id'))}</h4>"
                f'<p class="muted">{e(" · ".join(where + ([score_text] if score_text else [])))}</p>'
                f'<p class="label">Prompt</p><pre>{e(ex.get("input"))}</pre>'
                f'<p class="label">Expected</p><pre>{e(ex.get("expected"))}</pre>'
                f'<p class="label">Model output</p><pre>{e(ex.get("output"))}</pre>'
                f"{pivot}"
                "</article>"
            )
        out.append(f'<div class="examples">{"".join(cards)}</div>')
    intro = (
        '<p class="section-intro">The lowest-scoring items from the public samples, with the worst of the '
        "repeats. Private items are never shown. Model output is shown exactly as text.</p>"
    )
    body = intro + ("".join(out) if out else '<p class="empty-note">No public failure examples for this model.</p>')
    return _drill("failures", "Failure examples", body, count=str(total) if total else "")


def _profile_viz(suite: SuiteInfo, entry: Entry, tests: list[str], ranked: list[Entry]) -> str:
    """This model on every test against the range of all ranked models."""
    names = _labels(ranked)
    own_name = names.get(entry.slug, entry.display)
    rows, per_test, table_rows = [], [], []
    for test in tests:
        pairs = _test_ests(ranked, test)
        own = next((est for en, est in pairs if en.slug == entry.slug), None)
        if own is None:
            continue
        title = _test_title(suite.key, test)
        per_test.append((title, [(names[en.slug], est) for en, est in pairs]))
        rank = 1 + sum(1 for _, est in pairs if est.score > own.score)
        others = [(en, est) for en, est in pairs if en.slug != entry.slug]
        words = f"{own_name}: {pct(own.score)}, 95% range {interval_words(_ci(own))}, {ordinal(rank)} of {len(pairs)}"
        marks = [Mark(est.score, "tick", "muted", title=f"{names[en.slug]}: {pct(est.score)}") for en, est in others]
        marks.append(Mark(own.score, "dot", "hl", own.ci[0] if own.ci else None, own.ci[1] if own.ci else None, words))
        scores = [est.score for _, est in pairs]
        aria = words + (f"; other models from {pct(min(s.score for _, s in others))} to {pct(max(s.score for _, s in others))}" if others else "")
        rows.append(
            DotRow(
                label_html=f'<a href="../tests.html#{_test_anchor(test)}">{e(title)}</a>{_test_tags(entry.tests[test])}',
                aria=aria,
                marks=tuple(marks),
                value_html=f'<strong>{pct(own.score)}</strong> <span class="ci">{ordinal(rank)} of {len(pairs)}</span>',
            )
        )
        lead_entry, lead = min(pairs, key=lambda p: (-p[1].score, p[0].rank or 0))
        table_rows.append(
            f'<tr><th scope="row">{e(title)}</th>{_score_cell(own)}<td class="r num">{ordinal(rank)} of {len(pairs)}</td>'
            f"<td>{e(names[lead_entry.slug])} ({pct(lead.score)})</td><td class=\"r num\">{pct(statistics.median(scores))}</td></tr>"
        )
    if not rows:
        return '<p class="empty-note">No complete test results.</p>'
    key = _key([("dot", "hl", "This model, with its 95% range"), ("tick", "muted", "Each other ranked model")])
    return _viz(
        key + dot_rows(rows, PERCENT_TICKS),
        takeaway=profile_sentence(own_name, per_test),
        caption=e(
            "Score on each test. Right: the score and its place among the ranked models. Select a test to compare "
            "every model."
        ),
        table=_table(
            [_th("Test"), _th("Score and 95% range"), _th("Place", True), _th("Highest"), _th("Median model", True)],
            table_rows,
            label="Scores by test",
        ),
    )


def _model_page(suite: SuiteInfo, entry: Entry, tests: list[str], ranked: list[Entry], current_pair: set[str]) -> str:
    n_ranked = len(ranked)
    tests = [t for t in tests if t in entry.tests]
    consistency = [b.get("consistency") for b in entry.tests.values() if b.get("consistency") is not None]
    epochs = entry.epochs
    facts = [
        _fact("Overall score", pct(entry.score), e(f"95% range {interval_short(entry.ci95)}"), lead=True),
        _fact("Rank", f"{entry.rank} of {n_ranked}" if entry.rank else "Not ranked"),
        _fact("Cost per run", _usd(entry.cost_usd), "this suite, judges included"),
        _fact("Per 1,000 correct", _per_thousand(entry.cost_per_correct_usd), "cost of 1,000 full-score answers"),
    ]
    if consistency:
        facts.append(
            _fact("Consistency", pct(sum(consistency) / len(consistency)), f"same score in all {epochs} asks, mean over tests" if epochs else "mean over tests")
        )
    meta = [f"{e(entry.provider)}" if entry.provider else "", f"<code>{e(entry.model)}</code>", f"run {e(_date(entry.generated_at))}"]
    if epochs:
        meta.append(f"each item asked {epochs} times")
    notices = ""
    if entry.data != "full":
        notices = (
            '<p class="notice">This run used the public sample items, not the full sets, so its scores are not '
            "comparable with full-set runs.</p>"
        )
    parts = [
        '<nav class="crumbs" aria-label="Breadcrumb"><ol><li><a href="../">Leaderboard</a></li>'
        f'<li><a href="../models.html">Models</a></li><li aria-current="page">{e(entry.display)}</li></ol></nav>',
        _page_head(e(entry.display) + _data_tag(entry.data), meta=" · ".join(m for m in meta if m)),
        notices,
        f'<dl class="facts">{"".join(facts)}</dl>',
        _honesty("../"),
        _heading("tests", "Scores by test"),
        _profile_viz(suite, entry, tests, ranked),
        _radar_viz(suite, entry, tests, ranked) if len(tests) >= 3 else "",
        _drill("test-details", "Items, consistency and cost by test", _tests_table(suite, entry, tests)),
    ]
    group_table = _breakdown_table(suite, entry, tests, suite.group_field, suite.group_label, suite.group_order)
    if group_table:
        parts.append(_drill("by-group", f"By {e(suite.group_label.lower())}", group_table))
    cefr = _breakdown_table(suite, entry, tests, "by_cefr", "CEFR level", CEFR_ORDER)
    if cefr:
        parts.append(
            _drill(
                "by-cefr",
                "By CEFR level",
                '<p class="section-intro">The CEFR level comes from the course content; items without one are '
                "listed as unspecified.</p>" + cefr,
            )
        )
    parts.append(_topics(suite, entry, tests))
    parts.append(_tutor(suite, entry, tests, current_pair))
    parts.append(_cost(entry))
    parts.append(_examples(suite, entry, tests))
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Methodology


def _counts(mapping: dict[str, Any] | None, name=lambda v: v) -> str:
    if not mapping:
        return "n/a"
    return ", ".join(f"{name(str(k))} {v}" for k, v in mapping.items())


_H2 = re.compile(r'<h2 id="([^"]+)">(.*?)</h2>')


def _methodology(suite: SuiteInfo, tests: list[str], reports: dict[str, dict[str, Any]], repo_root: Path) -> tuple[str, str]:
    path = repo_root / "docs" / "methodology.md"
    title = "Methodology"
    prose = ""
    if path.exists():
        text = path.read_text(encoding="utf-8")
        lines = text.lstrip("\n").split("\n")
        if lines and re.match(r"^#\s+\S", lines[0]):
            title = lines[0].lstrip("#").strip()
            text = "\n".join(lines[1:])
        prose = markdown_to_html(text, base_url=DOCS_BASE_URL, base_dir="docs")
    toc = [("in-one-minute", "In one minute")]
    toc += [(anchor, re.sub(r"<[^>]+>", "", inner)) for anchor, inner in _H2.findall(prose)]
    toc.append(("test-sets", f"Test sets in the {e(suite.name)}"))
    prose = _H2.sub(lambda m: _heading(m.group(1), m.group(2)), prose)

    summary = "".join(f"<li>{point}</li>" for point in _one_minute(suite))
    parts = [
        _page_head(e(title), f"How {BENCHMARK_NAME} builds and scores the {e(suite.name)}, and what the scores can and cannot tell you."),
        f'<section class="summary-box" aria-labelledby="in-one-minute"><h2 id="in-one-minute">In one minute</h2><ul>{summary}</ul></section>',
        '<div class="doc">',
        '<nav class="toc" aria-label="On this page"><p class="toc-title">On this page</p><ol>'
        + "".join(f'<li><a href="#{anchor}">{label}</a></li>' for anchor, label in toc)
        + "</ol></nav>",
        '<div class="doc-body">',
        f'<div class="prose">{prose}</div>' if prose else "",
        _heading("test-sets", f"Test sets in the {e(suite.name)}"),
        '<p class="section-intro">Generated from the build reports in <code>data/build-reports/</code>. '
        f"Items are sampled with a fixed seed. The full sets are private; {PUBLIC_SAMPLE_SIZE} items per test are "
        f'published in <a href="{REPO_URL}/tree/main/samples/{suite.key}">samples/{suite.key}</a>.</p>',
    ]
    group_key = "by_language" if suite.key == "blas" else "by_l1"
    rows = []
    details = []
    for test in tests:
        report = reports.get(test)
        if not report:
            continue
        title_text = e(_test_title(suite.key, test))
        rows.append(
            "<tr>"
            f'<th scope="row">{title_text}<br><code>{e(test)}</code></th>'
            f'<td class="r num">{e(report.get("n_items"))}</td>'
            f'<td class="r num">{e(report.get("n_public_sample", "n/a"))}</td>'
            f"<td>{e(_counts(report.get(group_key), _group_name))}</td>"
            f"<td>{e(_counts(report.get('by_cefr'), _group_name))}</td>"
            f'<td class="r num">{e(report.get("human_checked", 0))}</td>'
            "</tr>"
        )
        sources = sorted(
            {Path(str(s)).name for s in (report.get("sources") or report.get("source_files") or [])}
            | set(_sample_sources(repo_root, suite.key, test))
        )
        shortfalls = {k: v for k, v in (report.get("shortfalls") or {}).items() if v}
        details.append(
            '<details class="drill drill-sm" id="set-' + test.replace("_", "-") + '">'
            f'<summary><span class="drill-title"><h3>{title_text}</h3></span></summary><div class="drill-body">'
            f"<p>{e(_test_description(suite.key, test, None))}</p>"
            '<dl class="plain">'
            f"<dt>Sources</dt><dd>{e(', '.join(sources) or 'n/a')}</dd>"
            f"<dt>Licences</dt><dd>{e(_counts(report.get('by_licence')))}</dd>"
            f"<dt>Evidence</dt><dd>{e(_counts(report.get('by_evidence')))}</dd>"
            + (f"<dt>Shortfalls</dt><dd>{e(', '.join(sorted(shortfalls)))} (see the build report)</dd>" if shortfalls else "")
            + f'<dt>Build report</dt><dd><a href="{REPO_URL}/blob/main/data/build-reports/{suite.key}_{e(test)}.json">'
            f"{suite.key}_{e(test)}.json</a></dd>"
            "</dl></div></details>"
        )
    if rows:
        parts.append(
            _table(
                [_th("Test"), _th("Items", True), _th("Public", True), _th(e(suite.group_label)), _th("CEFR level"), _th("Human-checked", True)],
                rows,
                caption="Items per test, with counts by group. Human-checked counts only items whose source records human review.",
                css="board",
                label="Test sets",
            )
        )
        parts.append(
            '<p class="section-intro">Evidence says how strong the gold answer is: for example whether a course '
            "answer is confirmed by a dictionary, or comes from the course alone. Open a test for its sources.</p>"
        )
        parts.extend(details)
    else:
        parts.append('<p class="empty-note">No build reports found for this suite.</p>')
    parts.append("</div></div>")
    return title, "\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Leaderboard slice and preview index


def _slice(suite: SuiteInfo, entries: list[Entry], updated: str | None) -> dict[str, Any]:
    models = []
    for entry in entries:
        models.append(
            {
                "rank": entry.rank,
                "ranked": entry.ranked,
                "model": entry.model,
                "family": entry.family,
                "page": f"models/{entry.slug}.html" if entry.ranked else None,
                "run_file": entry.run_file,
                "run_kind": entry.run_kind,
                "status": entry.status,
                "generated_at": entry.generated_at,
                "data": entry.data,
                "epochs": entry.epochs,
                "overall": entry.overall,
                "cost_usd": entry.cost_usd,
                "cost_per_correct_usd": entry.cost_per_correct_usd,
                suite.group_field: _group_means(entry, suite.group_field),
                "tests": {
                    name: {
                        key: block.get(key)
                        for key in ("score", "ci95", "n_items", "epochs", "consistency", "status", "dataset", "cost_usd", "cost_per_correct_usd")
                    }
                    for name, block in entry.tests.items()
                },
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "benchmark": BENCHMARK,
        "benchmark_name": BENCHMARK_NAME,
        "benchmark_version": __version__,
        "suite": suite.key,
        "generated_at": updated,
        "note": (
            "Only live runs with status complete are ranked. Scores are means over items with a 95% "
            "bootstrap interval; the suite score weights every test equally. cost_usd is the spend on "
            f"this suite's tests. {suite.group_field} gives the mean of per-test scores."
        ),
        "models": models,
    }


def _preview_index(updated: str | None) -> str:
    cards = "".join(
        f'<a class="suite-card suite-{s.key}" href="{s.key}/"><strong>{e(s.short)} · {e(s.topic)}</strong>{e(s.description)}</a>'
        for s in SUITES.values()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{BENCHMARK_NAME} research pages</title>
<link rel="stylesheet" href="assets/site.css">
</head>
<body>
<header class="site-head"><div class="wrap head-row"><span class="brand"><span class="brand-mark" aria-hidden="true"></span>{BENCHMARK_NAME}</span>
<nav class="site-nav" aria-label="Main"><ul><li><a class="ext" href="{REPO_URL}">GitHub</a></li></ul></nav></div></header>
<main id="main" class="wrap">
<div class="page-head"><h1>{BENCHMARK_NAME}</h1>
<p class="lede">A benchmark of how well large language models handle language learning and tutoring.{f" Results as of {e(_date(updated))}." if updated else ""}</p></div>
<nav class="suites" aria-label="Suites">{cards}</nav>
</main>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Build


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def build_site(results_dir: Path | str, out_dir: Path | str = SITE, *, repo_root: Path | str = REPO_ROOT) -> dict[str, Any]:
    """Build the static site. Returns a summary: ranked models per suite and files written."""
    global _SITE_NOTICE
    results_dir, out_dir, repo_root = Path(results_dir), Path(out_dir), Path(repo_root)
    notice_file = results_dir / "notice.txt"
    _SITE_NOTICE = " ".join(notice_file.read_text(encoding="utf-8").split()) if notice_file.is_file() else ""
    runs_dir = results_dir / "runs"
    runs, _skipped = load_runs(runs_dir) if runs_dir.is_dir() else ([], [])
    runs = [run for run in runs if run.get("run_kind") == "live"]
    check_public_examples(runs)
    updated = max((run.get("generated_at") or "" for run in runs), default="") or None
    current_pair = {judge.id for judge in configured_judges()}

    out_dir.mkdir(parents=True, exist_ok=True)
    for name in GENERATED_DIRS:
        shutil.rmtree(out_dir / name, ignore_errors=True)
    for name in GENERATED_FILES:
        (out_dir / name).unlink(missing_ok=True)

    written: list[str] = []

    def put(relative: str, text: str) -> None:
        _write(out_dir / relative, text)
        written.append(relative)

    put("assets/site.css", SITE_CSS)
    put("suites.html", _preview_index(updated))
    summary: dict[str, Any] = {"updated": updated, "suites": {}, "files": written}
    for suite in SUITES.values():
        entries = _entries(runs, suite.key)
        ranked = [entry for entry in entries if entry.ranked]
        reports = _reports(repo_root, suite.key)
        tests = _test_order(suite.key, set(reports) | {t for entry in ranked for t in entry.tests})

        def page(relative: str, title: str, description: str, body: str, current: str, depth: int = 1) -> None:
            put(
                f"{suite.key}/{relative}",
                _page(
                    title=title,
                    description=description,
                    body=body,
                    suite=suite,
                    depth=depth,
                    current=current,
                    updated=updated,
                ),
            )

        suffix = f"{BENCHMARK_NAME}, {suite.name}"
        page("index.html", f"{BENCHMARK_NAME}: {suite.description}", suite.statement, _home(suite, entries, tests, reports, updated), "home")
        page(
            "tests.html",
            f"Tests: {suffix}",
            f"Every test in the {BENCHMARK_NAME} {suite.name}, with each model's score.",
            _tests_page(suite, ranked, tests, reports, current_pair, repo_root),
            "tests",
        )
        page(
            "findings.html",
            f"Findings: {suffix}",
            f"What the {BENCHMARK_NAME} {suite.name} results show: every model on every test, ties, difficulty by "
            "level, topics, evidence and cost.",
            _findings_page(suite, ranked, tests, current_pair),
            "findings",
        )
        page(
            f"{suite.group_page}.html",
            f"{suite.group_title}: {suffix}",
            f"{suite.group_title} in the {BENCHMARK_NAME} {suite.name}.",
            _groups_page(suite, ranked, tests),
            "groups",
        )
        page(
            "models.html",
            f"Models: {suffix}",
            f"Every model ranked on the {BENCHMARK_NAME} {suite.name}.",
            _models_page(suite, entries),
            "models",
        )
        method_title, method_body = _methodology(suite, tests, reports, repo_root)
        page(
            "methodology.html",
            f"{method_title}: {suffix}",
            f"How {BENCHMARK_NAME} builds and scores the {suite.name}.",
            method_body,
            "methodology",
        )
        for entry in ranked:
            page(
                f"models/{entry.slug}.html",
                f"{entry.display} ({entry.model}): {suffix}",
                f"{entry.model} on the {BENCHMARK_NAME} {suite.name}: {pct(entry.score)} overall.",
                _model_page(suite, entry, tests, ranked, current_pair),
                "model",
                depth=2,
            )
        put(
            f"{suite.key}/data/leaderboard.json",
            json.dumps(_slice(suite, entries, updated), indent=2, ensure_ascii=False) + "\n",
        )
        summary["suites"][suite.key] = {"ranked": len(ranked), "runs": len(entries)}
    return summary


