"""Static research site built from the results files.

``build_site(results_dir, out_dir)`` reads ``<results_dir>/runs/*.json`` and
writes plain HTML, one stylesheet and inline SVG charts:

    site/suites.html                     index of both suites (preview host only)
    site/assets/site.css
    site/<suite>/index.html              leaderboard
    site/<suite>/methodology.html
    site/<suite>/models/<model-slug>.html
    site/<suite>/data/leaderboard.json   the suite's slice of the leaderboard

Every link is relative, so pages work under ``/blas/`` and under a host that
rewrites ``/`` to ``/blas/``. The build is deterministic: the only date on the
pages is the newest run's ``generated_at``. Model output is untrusted and is
always escaped as text.
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
from teanga_bench.export import SCHEMA_VERSION
from teanga_bench.leaderboard import BLAS_LANGUAGES, load_runs
from teanga_bench.markdown_lite import markdown_to_html
from teanga_bench.paths import REPO_ROOT
from teanga_bench.site_charts import (
    BarRow,
    ScatterPoint,
    heat_style,
    interval_bar,
    interval_short,
    interval_words,
    money,
    pct,
    ranked_bars,
    scatter,
)
from teanga_bench.site_css import ACCENTS, SITE_CSS

SITE = REPO_ROOT / "site"
REPO_URL = "https://github.com/johnway114/teanga-bench"
DOCS_BASE_URL = f"{REPO_URL}/blob/main"
PUBLIC_SAMPLE_SIZE = 20
MIN_TOPIC_ITEMS = 5
TOPIC_COUNT = 5
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
    name: str
    description: str
    url: str
    statement: str
    group_field: str
    group_label: str
    group_order: tuple[str, ...]


SUITES: dict[str, SuiteInfo] = {
    "blas": SuiteInfo(
        key="blas",
        name="Blas suite",
        description="Irish, Welsh, Scottish Gaelic, Manx, Breton and Cornish",
        url="https://research.blasapp.com/",
        statement=(
            "Teanga Bench measures how well large language models handle six Celtic languages: "
            "Irish, Welsh, Scottish Gaelic, Manx, Breton and Cornish. Every model answers the same "
            "few hundred items per test, taken from the Blas course, dictionaries and parallel "
            "corpora: lesson exercises, word forms, translation, round-trip translation, and finding "
            "and fixing errors as a tutor would. Each item is asked several times. The score is the "
            "share of items answered correctly; translation tests give partial credit for closeness "
            "to reference translations."
        ),
        group_field="by_language",
        group_label="Language",
        group_order=BLAS_LANGUAGES,
    ),
    "tonada": SuiteInfo(
        key="tonada",
        name="Tonada suite",
        description="English tutoring for Portuguese, Spanish, Vietnamese and Japanese speakers",
        url="https://research.tonadaapp.com/",
        statement=(
            "Teanga Bench measures how well large language models tutor English for people whose "
            "first language is Portuguese, Spanish, Vietnamese or Japanese. Every model answers the "
            "same few hundred items per test, taken from the Tonada course and a public corpus of "
            "sentence edits: closed exercises with the instruction in the learner's language, and "
            "finding and fixing errors in English sentences as a tutor would. Each item is asked "
            "several times. The score is the share of items answered correctly."
        ),
        group_field="by_l1",
        group_label="First language",
        group_order=("portuguese", "spanish", "vietnamese", "japanese"),
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


# ---------------------------------------------------------------------------
# Data


@dataclass
class Entry:
    """One run seen from one suite."""

    model: str
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
        entries.append(
            Entry(
                model=run["model"]["id"],
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


# ---------------------------------------------------------------------------
# HTML helpers


def e(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


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
        ("methodology", "Methodology", f"{home}methodology.html"),
        ("github", "GitHub", REPO_URL),
    ):
        current_attr = ' aria-current="page"' if key == current else ""
        nav.append(f'<a href="{e(href)}"{current_attr}>{label}</a>')
    other = SUITES["tonada" if suite.key == "blas" else "blas"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="stylesheet" href="{root}assets/site.css">
</head>
<body class="suite-{suite.key}">
<a class="skip" href="#main">Skip to content</a>
<header class="site-head"><div class="wrap">
<a class="brand" href="{home}">{BENCHMARK_NAME} <span class="brand-suite">{e(suite.name)}</span></a>
<nav class="site-nav" aria-label="Site">{"".join(nav)}</nav>
</div></header>
<main id="main" class="wrap">
{body}
</main>
<footer class="site-foot"><div class="wrap">
<p>{BENCHMARK_NAME} is open source under Apache-2.0. Code, the public samples and every results file are on <a href="{REPO_URL}">GitHub</a>.</p>
<p>Gold answers come from the sources named in the <a href="{home}methodology.html">methodology</a>; they have not been reviewed by native speakers.</p>
<p>{f"Results as of {e(_date(updated))}. " if updated else ""}Also see the <a href="{e(other.url)}">{e(other.name)}: {e(other.description)}</a>.</p>
</div></footer>
</body>
</html>
"""


def _howto(suite: SuiteInfo, home: str) -> str:
    return f"""<aside class="howto" aria-labelledby="howto-title">
<h2 id="howto-title">How to read this</h2>
<ul>
<li><strong>Score.</strong> The share of items the model got right, averaged over repeats. Translation tests give partial credit by chrF++ similarity to reference translations. The overall score weights every test equally.</li>
<li><strong>Interval.</strong> The bar is the score; the thin line across it is the 95% interval, found by resampling the test items 2,000 times. When two models' intervals overlap, the gap between them may be chance.</li>
<li><strong>Sources, not reviewers.</strong> Items and answers are taken from the sources named in the methodology. No one has reviewed them by hand, so a few gold answers may be wrong. Tutor explanations are marked by two judge models, not by people.</li>
<li><strong>Private items.</strong> The full item sets are private so that models cannot be trained on them. {PUBLIC_SAMPLE_SIZE} items per test are public, and the failure examples on the model pages come only from those.</li>
<li><strong>Cost.</strong> What one run of this suite cost on OpenRouter at the prices listed on the day it ran, judge models included.</li>
</ul>
<p><a href="{home}methodology.html">Read the methodology</a> · <a href="{REPO_URL}">Code and public samples on GitHub</a></p>
</aside>"""


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


def _data_tag(data: str) -> str:
    if data == "full":
        return ""
    label = "public sample" if data == "public_sample" else "mixed data"
    return f' <span class="tag">{label}</span>'


def _usd(value: float | None) -> str:
    return e(money(value))


# ---------------------------------------------------------------------------
# Suite home


def _leaderboard_table(entries: list[Entry]) -> str:
    rows = []
    for entry in entries:
        overall = entry.overall or {}
        rows.append(
            "<tr>"
            f'<td class="rank">{entry.rank}</td>'
            f'<th scope="row" class="model"><a href="models/{entry.slug}.html">{e(entry.model)}</a>{_data_tag(entry.data)}</th>'
            f'<td class="score">{pct(entry.score)}</td>'
            f'<td class="ci-cell">{interval_bar(entry.score, overall.get("ci95"), entry.model)}'
            f'<span class="ci-text">{e(interval_words(overall.get("ci95")))}</span></td>'
            f'<td class="r num">{e(overall.get("n_items"))}</td>'
            f'<td class="r num">{_usd(entry.cost_usd)}</td>'
            f'<td class="r num">{_usd(entry.cost_per_correct_usd)}</td>'
            "</tr>"
        )
    head = [
        _th("Rank"), _th("Model"), _th("Score"), _th("95% interval"),
        _th("Items", True), _th("Cost per run", True), _th("Cost per correct answer", True),
    ]
    return _table(
        head,
        rows,
        caption="Ranked by overall score, every test weighted equally. Cost is one run of this suite, judges included.",
        css="board",
        label="Leaderboard",
    )


def _test_section(suite: SuiteInfo, test: str, entries: list[Entry], report: dict[str, Any] | None) -> str:
    scoring = next((en.tests[test].get("scoring") for en in entries if test in en.tests), None)
    rows = []
    epochs = set()
    n_items = set()
    for entry in entries:
        block = entry.tests.get(test)
        if not block or block.get("status") != "complete" or block.get("score") is None:
            continue
        epochs.add(block.get("epochs"))
        n_items.add(block.get("n_items"))
        rows.append(
            BarRow(
                label_html=f'<a href="models/{entry.slug}.html">{e(entry.model)}</a>',
                label_text=entry.model,
                score=float(block["score"]),
                ci95=block.get("ci95"),
            )
        )
    facts = []
    if len(n_items) == 1:
        facts.append(f"{n_items.pop()} items")
    elif report:
        facts.append(f"{report.get('n_items')} items in the full set")
    if len(epochs) == 1:
        facts.append(f"each asked {epochs.pop()} times")
    caption = "Score with 95% interval" + (f"; {', '.join(facts)}." if facts else ".")
    if scoring == "tutor":
        caption += " Rule-only headline; the judge-marked explanation score is on each model page."
    anchor = f"test-{test.replace('_', '-')}"
    return (
        f'<section class="test-block" aria-labelledby="{anchor}">'
        f'<h3 id="{anchor}">{e(_test_title(suite.key, test))}</h3>'
        f"<p>{e(_test_description(suite.key, test, scoring or (report or {}).get('scoring')))}</p>"
        f"{ranked_bars(rows, e(caption))}"
        "</section>"
    )


def _heat_table(suite: SuiteInfo, entries: list[Entry]) -> str:
    means = {entry.model: _group_means(entry, suite.group_field) for entry in entries}
    groups = _ordered_groups({g for m in means.values() for g in m}, suite.group_order)
    if not groups:
        return '<p class="empty-note">No breakdown available yet.</p>'
    rgb = ACCENTS[suite.key]["rgb"]
    rows = []
    for entry in entries:
        cells = []
        for group in groups:
            score = means[entry.model].get(group)
            if score is None:
                cells.append('<td class="empty">n/a</td>')
            else:
                cells.append(f"<td{heat_style(score, rgb)}>{score * 100:.0f}%</td>")
        rows.append(
            f'<tr><th scope="row"><a href="models/{entry.slug}.html">{e(entry.model)}</a></th>{"".join(cells)}</tr>'
        )
    head = [_th("Model")] + [_th(e(_group_name(g))) for g in groups]
    caption = (
        f"Score by {suite.group_label.lower()}: the mean of the per-test scores, every test weighted "
        "equally. Darker cells are higher. Intervals are on the model pages."
    )
    return _table(head, rows, caption=e(caption), css="heat", label=f"Score by {suite.group_label.lower()}")


def _scatter_section(suite: SuiteInfo, entries: list[Entry]) -> str:
    points = [
        ScatterPoint(entry.rank or 0, entry.model, entry.cost_usd, entry.score or 0.0, (entry.overall or {}).get("ci95"))
        for entry in entries
    ]
    chart = scatter(points, f"scatter-{suite.key}", f"Overall score against cost, {suite.name}")
    legend = "".join(
        f'<li value="{entry.rank}"><a href="models/{entry.slug}.html">{e(entry.model)}</a>: '
        f'{pct(entry.score)} for {_usd(entry.cost_usd)}</li>'
        for entry in entries
    )
    return (
        '<figure class="chart">'
        "<figcaption>Overall score (with 95% interval) against the cost of one run of this suite. "
        "Up and to the left is better. Numbers are leaderboard ranks.</figcaption>"
        f'{chart}<ol class="legend">{legend}</ol>'
        "</figure>"
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
    return f"<ul>{''.join(items)}</ul>"


def _home(suite: SuiteInfo, entries: list[Entry], tests: list[str], reports: dict[str, dict[str, Any]], updated: str | None) -> str:
    ranked = [entry for entry in entries if entry.ranked]
    unranked = [entry for entry in entries if not entry.ranked]
    parts = [
        f"<h1>{BENCHMARK_NAME}: {e(suite.description)}</h1>",
        f'<p class="lede">{e(suite.statement)}</p>',
    ]
    meta = [f"Last updated <strong>{e(_date(updated))}</strong>" if updated else "No results yet"]
    if ranked:
        meta.append(f"{len(ranked)} model{'s' if len(ranked) != 1 else ''} ranked")
    meta.append(f"{len(tests)} test{'s' if len(tests) != 1 else ''}")
    parts.append(f'<p class="meta">{" · ".join(meta)}</p>')
    if not ranked:
        parts.append(
            '<div class="notice"><strong>First results will appear here after the first run.</strong> '
            "Each run asks one model every item in every test and publishes its scores, intervals and cost.</div>"
        )
        parts.append('<h2 id="what">What is measured</h2>')
        parts.append(
            '<p class="section-intro">Each test has a few hundred items. Answers are marked by fixed rules '
            "(an accepted-answer list, or chrF++ for translation), so no model grades another model's "
            "headline score. Every item is asked several times, and every score comes with a 95% interval.</p>"
        )
        parts.append(_tests_summary(suite, tests, reports))
        parts.append(_howto(suite, "./"))
        return "\n".join(parts)

    parts.append('<h2 id="leaderboard">Leaderboard</h2>')
    parts.append(_leaderboard_table(ranked))
    if unranked:
        n = len(unranked)
        parts.append(
            f'<p class="muted">{n} other run{"s" if n != 1 else ""} did not finish every test and '
            f'{"are" if n != 1 else "is"} not ranked.</p>'
        )
    parts.append(_howto(suite, "./"))
    parts.append('<h2 id="tests">Results by test</h2>')
    for test in tests:
        parts.append(_test_section(suite, test, ranked, reports.get(test)))
    parts.append(f'<h2 id="by-group">By {e(suite.group_label.lower())}</h2>')
    parts.append(_heat_table(suite, ranked))
    parts.append('<h2 id="cost">Score against cost</h2>')
    parts.append(_scatter_section(suite, ranked))
    parts.append(
        '<p class="muted">The numbers on this page are also available as '
        '<a href="data/leaderboard.json">JSON</a>. Full results files for every run are in the '
        f'<a href="{REPO_URL}/tree/main/results/runs">repository</a>.</p>'
    )
    return "\n".join(parts)


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
        title = e(_test_title(suite.key, test))
        if block.get("dataset") == "public_sample":
            title += ' <span class="tag">public sample</span>'
        if block.get("status") != "complete":
            title += f' <span class="tag">incomplete</span>'
        rows.append(
            "<tr>"
            f'<th scope="row">{title}</th>'
            f'<td class="num"><strong>{pct(block.get("score"))}</strong></td>'
            f'<td class="ci-cell">{interval_bar(block.get("score"), block.get("ci95"), _test_title(suite.key, test))}'
            f'<span class="ci-text">{e(interval_words(block.get("ci95")))}</span></td>'
            f'<td class="r num">{e(block.get("n_items"))}</td>'
            f'<td class="r num">{pct(block.get("consistency"), 0)}</td>'
            f'<td class="r num">{_usd(block.get("cost_usd"))}</td>'
            f'<td class="r num">{_usd(block.get("cost_per_correct_usd"))}</td>'
            "</tr>"
        )
    head = [
        _th("Test"), _th("Score"), _th("95% interval"), _th("Items", True),
        _th("Consistency", True), _th("Cost", True), _th("Cost per correct", True),
    ]
    return _table(head, rows, css="board", label="Scores by test")


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
            ci = interval_short(stat.get("ci95"))
            cells.append(
                f'<td class="num"><strong>{pct(stat["score"])}</strong> '
                f'<span class="ci-text">{e(ci)} · n={e(stat.get("n_items"))}</span></td>'
            )
        rows.append(f'<tr><th scope="row">{e(_group_name(value))}</th>{"".join(cells)}</tr>')
    head = [_th(e(label))] + [_th(e(_test_title(suite.key, t))) for t in present]
    return _table(
        head,
        rows,
        caption="Score, 95% interval and number of items (n) for each test.",
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

        title = e(_test_title(suite.key, test))
        out.append(f"<h3>{title}</h3>")
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
    return (
        '<h2 id="topics">Grammar topics</h2>'
        '<p class="section-intro">The topic is the grammar point or error type recorded on each item.</p>'
        + "".join(out)
    )


def _tutor(suite: SuiteInfo, entry: Entry, tests: list[str]) -> str:
    out = []
    for test in tests:
        block = entry.tests.get(test) or {}
        tutor = block.get("tutor")
        if not tutor:
            continue
        explanation = tutor.get("explanation") or {}
        components = tutor.get("components") or {}
        judges = ", ".join(str(j) for j in tutor.get("judges") or []) or "n/a"
        out.append(f"<h3>{e(_test_title(suite.key, test))}</h3>")
        out.append(
            '<dl class="plain">'
            f"<dt>Headline score</dt><dd>{pct(block.get('score'))}: found the error, fixed it and changed nothing else (rule-only, no judge).</dd>"
            f"<dt>Parts of the headline</dt><dd>Found {pct(components.get('found'))} · fixed {pct(components.get('fixed'))} · "
            f"no over-correction {pct(components.get('no_overcorrection'))}</dd>"
            f"<dt>Explanation score</dt><dd>{pct(explanation.get('score'))} (95% interval {e(interval_words(explanation.get('ci95')))}), "
            f"{e(explanation.get('label') or 'judge-marked, not human-validated')}. An explanation passes only when both judges pass it.</dd>"
            f"<dt>Judge agreement</dt><dd>{pct(explanation.get('judge_agreement'))} of {e(explanation.get('judged_item_epochs'))} judged answers</dd>"
            f"<dt>Unscored</dt><dd>{e(explanation.get('unscored_item_epochs'))} answers a judge could not mark, after "
            f"{e(explanation.get('judge_failures'))} failed judge calls; they are left out, not scored 0.</dd>"
            f"<dt>Judges</dt><dd>{e(judges)}</dd>"
            "</dl>"
        )
    if not out:
        return ""
    return (
        '<h2 id="tutor">Tutor explanations</h2>'
        '<p class="section-intro">Tutor items also ask for a short explanation. Two judge models from other '
        "model families mark it. This is a secondary number: it is judge-marked and not human-validated.</p>"
        + "".join(out)
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
    return (
        '<h2 id="cost">Cost and prices</h2>'
        '<dl class="plain">'
        f"<dt>This suite</dt><dd>{_usd(entry.cost_usd)}, of which {_usd(judge_cost)} was judge spend</dd>"
        f"<dt>Whole run</dt><dd>{_usd(cost.get('total_usd'))} for both suites, against a cap of {_usd(cost.get('cap_usd'))}</dd>"
        f"<dt>Cost per correct answer</dt><dd>{_usd(entry.cost_per_correct_usd)}: suite cost divided by the number of full-score answers</dd>"
        f"<dt>Run date</dt><dd>{e(_date(entry.generated_at))}</dd>"
        f"<dt>Prices for {e(entry.model)}</dt>{_price_rows((run.get('model') or {}).get('pricing'))}"
        f"{judge_prices}"
        "</dl>"
    )


def _examples(suite: SuiteInfo, entry: Entry, tests: list[str]) -> str:
    out = []
    for test in tests:
        examples = [ex for ex in (entry.tests.get(test) or {}).get("failure_examples") or [] if ex.get("public") is True]
        if not examples:
            continue
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
        '<h2 id="failures">Failure examples</h2>'
        '<p class="section-intro">The lowest-scoring items from the public samples, with the worst of the '
        "repeats. Private items are never shown. Model output is shown exactly as text.</p>"
    )
    return intro + ("".join(out) if out else '<p class="empty-note">No public failure examples for this model.</p>')


def _model_page(suite: SuiteInfo, entry: Entry, tests: list[str], n_ranked: int) -> str:
    overall = entry.overall or {}
    tests = [t for t in tests if t in entry.tests]
    consistency = [b.get("consistency") for b in entry.tests.values() if b.get("consistency") is not None]
    facts = [
        _fact("Overall score", pct(entry.score), e(f"95% interval {interval_words(overall.get('ci95'))}"), lead=True),
        _fact("Rank", f"{entry.rank} of {n_ranked}" if entry.rank else "Not ranked"),
        _fact("Cost per run", _usd(entry.cost_usd), "this suite, judges included"),
        _fact("Cost per correct", _usd(entry.cost_per_correct_usd)),
    ]
    if consistency:
        facts.append(_fact("Consistency", pct(sum(consistency) / len(consistency), 0), "mean over tests"))
    epochs = entry.epochs
    meta = [f"{e(entry.family)} family" if entry.family else "", f"run {e(_date(entry.generated_at))}"]
    if epochs:
        meta.append(f"each item asked {epochs} times")
    if entry.data != "full":
        meta.append("public sample data, not comparable with full-set runs")
    parts = [
        '<p class="crumbs"><a href="../">Back to the leaderboard</a></p>',
        f"<h1>{e(entry.model)}</h1>",
        f'<p class="meta">{" · ".join(m for m in meta if m)}</p>',
        f'<dl class="facts">{"".join(facts)}</dl>',
        '<h2 id="tests">Scores by test</h2>',
        _tests_table(suite, entry, tests),
    ]
    if epochs and epochs > 1:
        parts.append(
            f'<p class="section-intro">Consistency is the share of items that got the same score in all '
            f"{epochs} repeats. A low number means the model's answers vary from one ask to the next.</p>"
        )
    parts.append(_tutor(suite, entry, tests))
    group_table = _breakdown_table(suite, entry, tests, suite.group_field, suite.group_label, suite.group_order)
    if group_table:
        parts.append(f'<h2 id="by-group">By {e(suite.group_label.lower())}</h2>{group_table}')
    cefr = _breakdown_table(suite, entry, tests, "by_cefr", "CEFR level", CEFR_ORDER)
    if cefr:
        parts.append(
            '<h2 id="by-cefr">By CEFR level</h2><p class="section-intro">The CEFR level comes from the course content; '
            "items without one are listed as unspecified.</p>" + cefr
        )
    parts.append(_topics(suite, entry, tests))
    parts.append(_cost(entry))
    parts.append(_examples(suite, entry, tests))
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Methodology


def _counts(mapping: dict[str, Any] | None, name=lambda v: v) -> str:
    if not mapping:
        return "n/a"
    return ", ".join(f"{name(str(k))} {v}" for k, v in mapping.items())


def _methodology(suite: SuiteInfo, tests: list[str], reports: dict[str, dict[str, Any]], repo_root: Path) -> tuple[str, str]:
    path = repo_root / "docs" / "methodology.md"
    title = "Methodology"
    parts = []
    if path.exists():
        text = path.read_text(encoding="utf-8")
        lines = text.lstrip("\n").split("\n")
        if lines and re.match(r"^#\s+\S", lines[0]):
            title = lines[0].lstrip("#").strip()
            text = "\n".join(lines[1:])
        parts.append(
            '<div class="prose">'
            + markdown_to_html(text, heading_offset=1, base_url=DOCS_BASE_URL, base_dir="docs")
            + "</div>"
        )
    parts.insert(0, f"<h1>{e(title)}</h1>")
    parts.append('<h2 id="test-sets">Test sets in the ' + e(suite.name) + "</h2>")
    parts.append(
        '<p class="section-intro">Generated from the build reports in <code>data/build-reports/</code>. '
        f"Items are sampled with a fixed seed. The full sets are private; {PUBLIC_SAMPLE_SIZE} items per test are "
        f'published in <a href="{REPO_URL}/tree/main/samples/{suite.key}">samples/{suite.key}</a>.</p>'
    )
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
            f"<h3>{title_text}</h3>"
            f"<p>{e(_test_description(suite.key, test, None))}</p>"
            '<dl class="plain">'
            f"<dt>Sources</dt><dd>{e(', '.join(sources) or 'n/a')}</dd>"
            f"<dt>Licences</dt><dd>{e(_counts(report.get('by_licence')))}</dd>"
            f"<dt>Evidence</dt><dd>{e(_counts(report.get('by_evidence')))}</dd>"
            + (f"<dt>Shortfalls</dt><dd>{e(', '.join(sorted(shortfalls)))} (see the build report)</dd>" if shortfalls else "")
            + f'<dt>Build report</dt><dd><a href="{REPO_URL}/blob/main/data/build-reports/{suite.key}_{e(test)}.json">'
            f"{suite.key}_{e(test)}.json</a></dd>"
            "</dl>"
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
            "answer is confirmed by a dictionary, or comes from the course alone.</p>"
        )
        parts.extend(details)
    else:
        parts.append('<p class="empty-note">No build reports found for this suite.</p>')
    return title, "\n".join(parts)


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
        f'<a class="suite-card suite-{s.key}" href="{s.key}/"><strong>{e(s.name)}</strong>{e(s.description)}</a>'
        for s in SUITES.values()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{BENCHMARK_NAME} research pages</title>
<link rel="stylesheet" href="assets/site.css">
</head>
<body>
<header class="site-head"><div class="wrap"><span class="brand">{BENCHMARK_NAME}</span>
<nav class="site-nav" aria-label="Site"><a href="{REPO_URL}">GitHub</a></nav></div></header>
<main id="main" class="wrap">
<h1>{BENCHMARK_NAME}</h1>
<p class="lede">A benchmark of how well large language models handle language learning and tutoring.{f" Results as of {e(_date(updated))}." if updated else ""}</p>
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
        put(
            f"{suite.key}/index.html",
            _page(
                title=f"{BENCHMARK_NAME}: {suite.description}",
                description=suite.statement,
                body=_home(suite, entries, tests, reports, updated),
                suite=suite,
                depth=1,
                current="home",
                updated=updated,
            ),
        )
        method_title, method_body = _methodology(suite, tests, reports, repo_root)
        put(
            f"{suite.key}/methodology.html",
            _page(
                title=f"{method_title}: {BENCHMARK_NAME}, {suite.name}",
                description=f"How {BENCHMARK_NAME} builds and scores the {suite.name}.",
                body=method_body,
                suite=suite,
                depth=1,
                current="methodology",
                updated=updated,
            ),
        )
        for entry in ranked:
            put(
                f"{suite.key}/models/{entry.slug}.html",
                _page(
                    title=f"{entry.model}: {BENCHMARK_NAME}, {suite.name}",
                    description=f"{entry.model} on the {BENCHMARK_NAME} {suite.name}: {pct(entry.score)} overall.",
                    body=_model_page(suite, entry, tests, len(ranked)),
                    suite=suite,
                    depth=2,
                    current="",
                    updated=updated,
                ),
            )
        put(
            f"{suite.key}/data/leaderboard.json",
            json.dumps(_slice(suite, entries, updated), indent=2, ensure_ascii=False) + "\n",
        )
        summary["suites"][suite.key] = {"ranked": len(ranked), "runs": len(entries)}
    return summary
