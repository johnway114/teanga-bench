"""Static research site built from the results files.

``build_site(results_dir, out_dir)`` reads ``<results_dir>/runs/*.json`` and
writes plain HTML, one stylesheet and inline SVG charts:

    site/suites.html                       index of both suites (preview host only)
    site/assets/site.css
    site/<suite>/index.html                leaderboard, headline facts, cards that link onward
    site/<suite>/tests.html                every test, one tab each
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
'Show all', tabs and copy-link.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Iterable

from teanga_bench import BENCHMARK, BENCHMARK_NAME, __version__
from teanga_bench.export import EXPLANATION_SCORED, SCHEMA_VERSION
from teanga_bench.leaderboard import BLAS_LANGUAGES, load_runs
from teanga_bench.markdown_lite import markdown_to_html
from teanga_bench.models_config import configured_judges
from teanga_bench.paths import REPO_ROOT
from teanga_bench.site_charts import (
    BarRow,
    ScatterPoint,
    heat_style,
    interval_bar,
    interval_short,
    mini_bar,
    money,
    pct,
    ranked_bars,
    scatter,
)
from teanga_bench.site_css import SITE_CSS

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


def _honesty(home: str) -> str:
    return (
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


def _home_cards(suite: SuiteInfo, ranked: list[Entry], tests: list[str]) -> str:
    winners = []
    for test in tests:
        scored = [(s, en) for en in ranked if (s := _complete_score(en, test)) is not None]
        if not scored:
            continue
        score, winner = max(scored, key=lambda pair: (pair[0], -(pair[1].rank or 0)))
        winners.append(
            f'<li><a class="w-test" href="tests.html#{_test_anchor(test)}">{e(_test_title(suite.key, test))}</a>'
            f'<span class="w-model">{e(winner.display)}</span><span class="w-score num">{pct(score)}</span></li>'
        )
    groups = _group_averages(suite, ranked)
    group_rows = "".join(
        f'<li><span class="g-name">{e(_group_name(g))}</span>{mini_bar(s)}<span class="g-score num">{pct(s)}</span></li>'
        for g, s in groups.items()
    )
    cards = [
        '<section class="card" aria-labelledby="card-tests"><h2 id="card-tests">Best model per test</h2>'
        f'<ul class="winners">{"".join(winners)}</ul>'
        '<p class="card-foot"><a href="tests.html">All test results</a></p></section>'
    ]
    if group_rows:
        cards.append(
            f'<section class="card" aria-labelledby="card-groups"><h2 id="card-groups">By {e(suite.group_label.lower())}</h2>'
            f'<p class="card-note">Average score across {_plural(len(ranked), "model")}.</p>'
            f'<ul class="group-bars">{group_rows}</ul>'
            f'<p class="card-foot"><a href="{suite.group_page}.html">Every model, {e(suite.group_label.lower())} by {e(suite.group_label.lower())}</a></p></section>'
        )
    cards.append(
        '<section class="card card-wide" aria-labelledby="card-cost"><h2 id="card-cost">Score against cost</h2>'
        f'<div class="cost-split">{_scatter_figure(suite, ranked)}</div>'
        '<p class="card-foot"><a href="models.html">Compare every model</a></p></section>'
    )
    return f'<div class="cards">{"".join(cards)}</div>'


def _scatter_figure(suite: SuiteInfo, entries: list[Entry], prefix: str = "models/") -> str:
    points = [ScatterPoint(entry.rank or 0, entry.display, entry.cost_usd, entry.score or 0.0, entry.ci95) for entry in entries]
    chart = scatter(points, f"scatter-{suite.key}", f"Overall score against cost, {suite.name}")
    legend = "".join(
        f'<li value="{entry.rank}"><a href="{prefix}{entry.slug}.html">{e(entry.display)}</a> '
        f'<span class="num">{pct(entry.score)} · {_usd(entry.cost_usd)}</span></li>'
        for entry in entries
    )
    return (
        f'<figure class="scatter-fig">{chart}<figcaption>'
        "<p>Each circle is a model, numbered by rank. Higher is better; further left is cheaper. "
        "The vertical line is the 95% range.</p>"
        f'<ol class="legend">{legend}</ol></figcaption></figure>'
    )


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


def _tests_page(suite: SuiteInfo, ranked: list[Entry], tests: list[str], reports: dict[str, dict[str, Any]], current_pair: set[str]) -> str:
    lede = f"{_plural(len(tests), 'test')}, each a few hundred items. Pick a test to compare every model." if tests else ""
    parts = [
        _page_head("Tests", lede),
        _honesty("./"),
        _drill("about", "What the tests measure", f'<p class="section-intro">{e(suite.statement)}</p>' + _tests_summary(suite, tests, reports)),
    ]
    if not tests:
        parts.append('<p class="empty-note">No test sets are built yet.</p>')
        return "\n".join(parts)
    tabs = "".join(
        f'<a href="#{_test_anchor(test)}">{e(_test_title(suite.key, test))}</a>' for test in tests
    )
    panels = []
    for test in tests:
        report = reports.get(test) or {}
        scoring = next((en.tests[test].get("scoring") for en in ranked if test in en.tests), None) or report.get("scoring")
        rows, epochs, n_items = [], set(), set()
        for entry in ranked:
            block = entry.tests.get(test)
            score = _complete_score(entry, test)
            if score is None:
                continue
            epochs.add(block.get("epochs"))
            n_items.add(block.get("n_items"))
            rows.append(
                BarRow(
                    label_html=_model_label(entry),
                    label_text=entry.display,
                    score=score,
                    ci95=block.get("ci95"),
                )
            )
        facts = []
        if len(n_items) == 1:
            facts.append(f"{n_items.pop()} items")
        elif report.get("n_items"):
            facts.append(f"{report.get('n_items')} items in the full set")
        if len(epochs) == 1:
            facts.append(f"each asked {epochs.pop()} times")
        facts.append(f"{_plural(len(rows), 'model')} with a complete result")
        caption = "Score with 95% range."
        if scoring == "tutor":
            caption += " Marked by rule only; the judge-marked explanation score is separate, below."
        anchor = _test_anchor(test)
        panels.append(
            f'<section class="panel" id="{anchor}" aria-labelledby="{anchor}-title">'
            + _heading(f"{anchor}-title", e(_test_title(suite.key, test)))
            + f'<p class="panel-desc">{e(_test_description(suite.key, test, scoring))}</p>'
            f'<p class="meta">{e(" · ".join(facts))}</p>'
            f"{ranked_bars(rows, e(caption))}"
            f"{_explanation_table(suite, test, ranked, current_pair)}"
            f'<p class="more-link"><a href="methodology.html#set-{test.replace("_", "-")}">How this test set is built</a></p>'
            "</section>"
        )
    parts.append(
        '<div class="tabs" data-tabs>'
        f'<nav class="tab-list" aria-label="Tests" data-tablist>{tabs}</nav>'
        f'{"".join(panels)}</div>'
    )
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
    parts.append(ranked_bars(rows, "Highest first. Ranges per model are on each model page."))
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
# Models index


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
    parts.append(_unranked_notice(unranked))
    if ranked:
        parts.append(_heading("cost", "Score against cost"))
        parts.append(f'<div class="card cost-split">{_scatter_figure(suite, ranked)}</div>')
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


def _model_page(suite: SuiteInfo, entry: Entry, tests: list[str], n_ranked: int, current_pair: set[str]) -> str:
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
    rows = []
    for test in tests:
        block = entry.tests[test]
        if block.get("score") is None:
            continue
        rows.append(
            BarRow(
                label_html=f'<a href="../tests.html#{_test_anchor(test)}">{e(_test_title(suite.key, test))}</a>',
                label_text=_test_title(suite.key, test),
                score=float(block["score"]),
                ci95=block.get("ci95"),
                note_html=_test_tags(block),
            )
        )
    parts = [
        '<nav class="crumbs" aria-label="Breadcrumb"><ol><li><a href="../">Leaderboard</a></li>'
        f'<li><a href="../models.html">Models</a></li><li aria-current="page">{e(entry.display)}</li></ol></nav>',
        _page_head(e(entry.display) + _data_tag(entry.data), meta=" · ".join(m for m in meta if m)),
        notices,
        f'<dl class="facts">{"".join(facts)}</dl>',
        _honesty("../"),
        _heading("tests", "Scores by test"),
        ranked_bars(rows, "Score with 95% range. Select a test to compare every model.", sort=False),
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
    results_dir, out_dir, repo_root = Path(results_dir), Path(out_dir), Path(repo_root)
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
            _tests_page(suite, ranked, tests, reports, current_pair),
            "tests",
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
                _model_page(suite, entry, tests, len(ranked), current_pair),
                "model",
                depth=2,
            )
        put(
            f"{suite.key}/data/leaderboard.json",
            json.dumps(_slice(suite, entries, updated), indent=2, ensure_ascii=False) + "\n",
        )
        summary["suites"][suite.key] = {"ranked": len(ranked), "runs": len(entries)}
    return summary
