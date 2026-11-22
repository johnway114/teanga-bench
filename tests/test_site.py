"""Static research site: pages, navigation, escaping, determinism, guards. Offline."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from site_fakes import fake_document, nine_models, twenty_models

from teanga_bench.markdown_lite import markdown_to_html
from teanga_bench.site import SUITES, SiteError, build_site, display_name
from teanga_bench.site_findings import (
    Est,
    compare_sentence,
    correlation_sentence,
    direction_sentence,
    leader_sentence,
    level_sentence,
    matrix_sentence,
    overlaps,
    profile_sentence,
    spread_sentence,
    tie_groups,
    value_sentence,
    topic_language_sentence,
)

LINK = re.compile(r'(?:href|src|data-local)="([^"]+)"')
NAV = re.compile(r'<nav class="site-nav" aria-label="Main">(.*?)</nav>', re.S)
SUITE_PAGES = ("index.html", "tests.html", "findings.html", "models.html", "methodology.html")
VIZ = re.compile(r'<figure class="viz[^"]*">(.*?)</figure>', re.S)
CHART_SVG = re.compile(r'<svg class="(?:dtrack|lines|scatter|radar)"')
LAB_PAGES = ("lab", "speech", "transcribe", "write", "benchmarks", "arena", "developers")
LAB_NAV = re.compile(r'<nav class="lab-nav" aria-label="Open Lab">(.*?)</nav>', re.S)


def _results(tmp_path: Path, documents: dict[str, dict]) -> Path:
    runs = tmp_path / "results" / "runs"
    runs.mkdir(parents=True)
    for name, document in documents.items():
        (runs / f"{name}.json").write_text(json.dumps(document), encoding="utf-8")
    return tmp_path / "results"


def _repo(tmp_path: Path, methodology: str | None = None) -> Path:
    root = tmp_path / "repo"
    reports = root / "data" / "build-reports"
    reports.mkdir(parents=True)
    report = {
        "suite": "blas", "test": "morphology", "n_items": 360, "n_public_sample": 20,
        "by_language": {"irish": 60, "welsh": 60}, "by_cefr": {"A1": 100, "None": 260},
        "by_licence": {"private-blas": 360}, "by_evidence": {"blas-app+bunamo": 11, "blas-app-only": 349},
        "human_checked": 0,
    }
    (reports / "blas_morphology.json").write_text(json.dumps(report), encoding="utf-8")
    (reports / "counting.json").write_text(json.dumps({"test": "blas/counting", "n_items": 3}), encoding="utf-8")
    if methodology is not None:
        (root / "docs").mkdir()
        (root / "docs" / "methodology.md").write_text(methodology, encoding="utf-8")
    return root


def _two_runs(tmp_path: Path, **kwargs) -> Path:
    return _results(
        tmp_path,
        {
            "a__strong": fake_document("a/strong", 0.85, generated_at="2026-11-12T08:00:00+00:00", **kwargs),
            "b__weak": fake_document("b/weak", 0.45, generated_at="2026-11-13T09:30:00+00:00"),
        },
    )


def _all_files(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _pages(suite: str) -> tuple[str, ...]:
    return SUITE_PAGES + (f"{SUITES[suite].group_page}.html",)


def test_site_builds_every_page_from_two_complete_runs(tmp_path):
    out = tmp_path / "site"
    summary = build_site(_two_runs(tmp_path), out, repo_root=_repo(tmp_path))

    assert summary["suites"]["blas"]["ranked"] == 2 and summary["suites"]["tonada"]["ranked"] == 2
    assert (out / "assets" / "site.css").exists() and (out / "suites.html").exists()
    for suite in ("blas", "tonada"):
        for name in _pages(suite):
            assert (out / suite / name).exists(), f"{suite}/{name}"
        for slug in ("a-strong", "b-weak"):
            assert (out / suite / "models" / f"{slug}.html").exists()
        home = _read(out / suite / "index.html")
        assert home.index("models/a-strong.html") < home.index("models/b-weak.html")  # ranked by score
        assert "95% range" in home and "How to read this" in home
        assert "13 November 2026" in home  # newest run's date, not the clock
        assert "Best overall" in home and "Hardest test" in home
        for name in _pages(suite):
            assert "Blas" + " Bench" not in _read(out / suite / name)
        board = json.loads(_read(out / suite / "data" / "leaderboard.json"))
        assert board["suite"] == suite
        assert [m["rank"] for m in board["models"]] == [1, 2]
        assert set(board["models"][0]["tests"]) == set(fake_document("x/y", 0.5)["suites"][suite]["tests"])
    assert "Irish" in _read(out / "blas" / "languages.html")
    assert "Portuguese" in _read(out / "tonada" / "learners.html")
    assert "Word forms" in _read(out / "blas" / "tests.html")
    model = _read(out / "blas" / "models" / "a-strong.html")
    for heading in ("Scores by test", "Tutor explanations", "By language", "By CEFR level", "Grammar topics", "Cost and prices", "Failure examples"):
        assert heading in model
    assert "<code>a/strong</code>" in model  # the exact OpenRouter id stays visible
    assert "Judge agreement" in model and "87.0%" in model and "judge-marked" in model
    method = _read(out / "blas" / "methodology.html")
    assert "Word forms" in method and "blas-app+bunamo 11" in method and "counting" not in method
    assert "In one minute" in method
    for slug in LAB_PAGES:
        assert (out / "blas" / f"{slug}.html").is_file()
        assert not (out / "tonada" / f"{slug}.html").exists()
    arena = _read(out / "blas" / "arena.html")
    assert "There is no public listening round." in arena
    assert "<audio" not in arena and "arena.js" not in arena
    speech = _read(out / "blas" / "speech.html")
    assert "No clips or synthesis are cleared" in speech and "<audio" not in speech
    developers = _read(out / "blas" / "developers.html")
    assert 'id="developer-lookup"' in developers and "assets/developers.js" in developers


def test_every_link_resolves_and_nav_is_shared(tmp_path):
    out = tmp_path / "site"
    build_site(_two_runs(tmp_path), out, repo_root=_repo(tmp_path))
    pages = sorted(out.rglob("*.html"))
    assert pages
    for page in pages:
        for target in LINK.findall(_read(page)):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            assert not target.startswith("/"), f"{page}: absolute link {target}"
            resolved = (page.parent / target.split("#")[0]).resolve()
            if target.endswith("/") or target.split("#")[0] in ("", "."):
                resolved = resolved / "index.html"
            assert resolved.exists(), f"{page.relative_to(out)} links to missing {target}"

    assert 'href="lab.html"' in _read(out / "blas" / "index.html")
    assert 'href="lab.html"' not in _read(out / "tonada" / "index.html")
    assert '<a href="./">Explore the Teanga leaderboard</a>' in _read(out / "blas" / "benchmarks.html")
    for suite in ("blas", "tonada"):
        for page in sorted((out / suite).rglob("*.html")):
            text = _read(page)
            nav = NAV.search(text).group(1)
            labels = re.findall(r">([A-Za-z]+)<", nav)
            current = re.findall(r'href="([^"]+)" aria-current="page"', nav)
            lab = LAB_NAV.search(text)
            if suite == "blas" and page.parent == out / suite and page.stem in LAB_PAGES:
                assert labels == ["Leaderboard", "GitHub"]
                assert current == ["lab.html"] and 'href="lab.html" aria-current="page">Open Lab</a>' in nav
                assert 'href="./">Leaderboard</a>' in nav
                assert lab is not None
                assert LINK.findall(lab.group(1)) == [f"{slug}.html" for slug in LAB_PAGES]
                assert re.findall(r'href="([^"]+)" aria-current="page"', lab.group(1)) == [page.name]
            elif page.parent.name == "models":
                assert current == [] and 'href="../models.html" aria-current="true"' in nav
                assert 'href="../models.html">Models</a>' in text  # breadcrumb back to the index
            else:
                expected = "./" if page.name == "index.html" else f"./{page.name}"
                assert current == [expected], f"{page.relative_to(out)} marks {current}"
            if lab is None:
                assert labels == [
                    "Leaderboard", "Tests", "Findings", SUITES[suite].group_nav, "Models", "Methodology", "GitHub",
                ]
            for other in SUITES.values():
                assert other.short in text  # the suite switcher names both suites
            other = SUITES["tonada" if suite == "blas" else "blas"]
            assert f'href="{other.url}"' in text
            assert bool(lab) == (suite == "blas" and page.parent == out / suite and page.stem in LAB_PAGES)


def test_honesty_note_on_every_page_with_scores(tmp_path):
    out = tmp_path / "site"
    build_site(_two_runs(tmp_path), out, repo_root=_repo(tmp_path))
    for suite in ("blas", "tonada"):
        pages = [out / suite / name for name in _pages(suite) if name != "methodology.html"]
        pages += sorted((out / suite / "models").glob("*.html"))
        for page in pages:
            text = _read(page)
            assert "not been reviewed by people" in text or "were not reviewed by people" in text, page
            assert "methodology.html" in text


def test_leaderboard_shows_top_five_then_show_all(tmp_path):
    out = tmp_path / "site"
    build_site(_results(tmp_path, nine_models()), out, repo_root=_repo(tmp_path))
    home = _read(out / "blas" / "index.html")
    rows = re.findall(r"<tr( class=\"more\")?><td class=\"c-rank", home)
    assert len(rows) == 9 and sum(1 for r in rows if r) == 4  # every row is in the HTML
    assert "Show all 9 models" in home and "data-sortable" in home
    assert "1 other run did not finish every test and is not ranked." in home
    models = _read(out / "blas" / "models.html")
    assert models.count('class="model-card"') == 9
    assert "1 other run did not finish" in models


def test_empty_results_dir_builds_empty_state(tmp_path):
    results = tmp_path / "results"
    (results / "runs").mkdir(parents=True)
    out = tmp_path / "site"
    summary = build_site(results, out, repo_root=_repo(tmp_path))
    assert summary["updated"] is None
    for suite in ("blas", "tonada"):
        home = _read(out / suite / "index.html")
        assert "First results will appear here after the first run" in home
        assert "What is measured" in home
        for name in _pages(suite):
            assert (out / suite / name).exists()
        assert not (out / suite / "models").exists()
        assert json.loads(_read(out / suite / "data" / "leaderboard.json"))["models"] == []
    assert "Word forms" in _read(out / "blas" / "index.html")
    # A results dir with no runs/ folder at all also builds.
    build_site(tmp_path / "nothing", tmp_path / "site2", repo_root=_repo(tmp_path / "x"))


def test_model_output_is_escaped(tmp_path):
    attack = '<script>alert("x")</script><img src=x onerror=alert(1)>'
    results = _two_runs(tmp_path, output_text=attack)
    out = tmp_path / "site"
    build_site(results, out, repo_root=_repo(tmp_path))
    for page in out.rglob("*.html"):
        text = _read(page)
        assert "<script>alert" not in text and "<img src=x" not in text
    model = _read(out / "blas" / "models" / "a-strong.html")
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in model


def test_pages_hold_no_external_requests(tmp_path):
    from bs4 import BeautifulSoup

    out = tmp_path / "site"
    build_site(_two_runs(tmp_path), out, repo_root=_repo(tmp_path))
    for page in out.rglob("*.html"):
        text = _read(page)
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup.find_all(["script", "img"]):
            for attr in ("src", "href"):
                val = tag.get(attr, "")
                assert not re.match(r"https?://", val), (page, tag)
        for tag in soup.find_all("link"):
            rels = set(tag.get("rel") or [])
            if rels and rels <= {"canonical", "alternate"}:
                continue
            for attr in ("src", "href"):
                val = tag.get(attr, "")
                assert not re.match(r"https?://", val), (page, tag)
        assert "@import" not in text
    assert "url(" not in _read(out / "assets" / "site.css")


def test_build_is_deterministic(tmp_path):
    results = _two_runs(tmp_path)
    repo = _repo(tmp_path, methodology="# Method\n\nText.\n")
    first, second = tmp_path / "one", tmp_path / "two"
    build_site(results, first, repo_root=repo)
    build_site(results, second, repo_root=repo)
    assert _all_files(first) == _all_files(second)
    (first / "blas" / "models" / "stale.html").write_text("old", encoding="utf-8")
    build_site(results, first, repo_root=repo)  # rebuild in place removes stale pages
    assert _all_files(first) == _all_files(second)


def test_unranked_and_mock_runs_are_not_shown(tmp_path):
    results = _results(
        tmp_path,
        {
            "a__ok": fake_document("a/ok", 0.7),
            "c__capped": fake_document("c/capped", 0.95, status="cost_cap_reached"),
            "mock": fake_document("mockllm/model", 0.99, run_kind="mock"),
        },
    )
    out = tmp_path / "site"
    build_site(results, out, repo_root=_repo(tmp_path))
    for name in _pages("blas"):
        text = _read(out / "blas" / name)
        assert "c/capped" not in text and "capped" not in text.lower() and "mockllm" not in text
    assert "1 other run did not finish" in _read(out / "blas" / "index.html")
    assert not (out / "blas" / "models" / "c-capped.html").exists()


def test_public_sample_runs_are_not_ranked(tmp_path):
    results = _results(tmp_path, {"s__sample": fake_document("s/sample", 0.6, dataset="public_sample")})
    out = tmp_path / "site"
    summary = build_site(results, out, repo_root=_repo(tmp_path))
    assert summary["suites"]["blas"]["ranked"] == 0
    assert summary["suites"]["tonada"]["ranked"] == 0
    assert not (out / "blas" / "models" / "s-sample.html").exists()
    assert "s/sample" not in _read(out / "blas" / "index.html")


def test_explanations_from_another_judge_pair_are_not_compared(tmp_path):
    document = fake_document("o/other", 0.6)
    document["suites"]["blas"]["tests"]["tutor_accuracy"]["tutor"]["judges"] = ["x/judge-one", "y/judge-two"]
    out = tmp_path / "site"
    build_site(_results(tmp_path, {"o__other": document}), out, repo_root=_repo(tmp_path))
    tests = _read(out / "blas" / "tests.html")
    assert "Not shown, because the run used a different judge pair" in tests
    assert "Not comparable with other models" in _read(out / "blas" / "models" / "o-other.html")


def test_non_public_failure_example_is_refused(tmp_path):
    document = fake_document("a/leaky", 0.6)
    document["suites"]["blas"]["tests"]["morphology"]["failure_examples"][0]["public"] = False
    results = _results(tmp_path, {"a__leaky": document})
    repo = _repo(tmp_path)
    with pytest.raises(SiteError, match="not marked public"):
        build_site(results, tmp_path / "site", repo_root=repo)
    del document["suites"]["blas"]["tests"]["morphology"]["failure_examples"][0]["public"]
    (results / "runs" / "a__leaky.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SiteError):
        build_site(results, tmp_path / "site", repo_root=repo)


def test_methodology_markdown_is_rendered_and_escaped(tmp_path):
    markdown = (
        "# How it works\n\nPlain **bold** and `code` and a [link](HARNESS.md) and "
        "[bad](javascript:alert(1)).\n\n<script>x</script>\n\n## Table\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n"
        "- one\n- two\n\n```\n<b>raw</b>\n```\n"
    )
    out = tmp_path / "site"
    build_site(tmp_path / "none", out, repo_root=_repo(tmp_path, methodology=markdown))
    page = _read(out / "blas" / "methodology.html")
    assert "<h1>How it works</h1>" in page
    assert '<h2 id="table">Table</h2>' in page
    assert '<li><a href="#table">Table</a></li>' in page  # listed in the table of contents
    assert "<strong>bold</strong>" in page and "<code>code</code>" in page
    assert 'href="https://github.com/johnway114/teanga-bench/blob/main/docs/HARNESS.md"' in page
    assert "javascript:" not in page and "<script>x" not in page
    assert "<td>1</td>" in page and "<li>one</li>" in page
    assert "&lt;b&gt;raw&lt;/b&gt;" in page
    assert "Word forms" in page  # the generated test table follows


def test_markdown_lists_and_paragraphs():
    html = markdown_to_html("Para one\ncontinues.\n\n1. first\n2. second\n   wrapped\n")
    assert "<p>Para one continues.</p>" in html
    assert "<ol><li>first</li><li>second wrapped</li></ol>" in html


@pytest.mark.parametrize(
    "model_id, name, maker",
    [
        ("openai/gpt-6-luna", "GPT-6 Luna", "OpenAI"),
        ("openai/gpt-oss-120b", "GPT-OSS 120B", "OpenAI"),
        ("anthropic/claude-opus-5", "Claude Opus 5", "Anthropic"),
        ("deepseek/deepseek-v4.1-flash-1017", "DeepSeek V4.1 Flash 1017", "DeepSeek"),
        ("qwen/qwen3.8-flash", "Qwen3.8 Flash", "Qwen"),
        ("openai/o4-mini", "o4 Mini", "OpenAI"),
        ("~newco/thing:free", "Thing (free)", "newco"),
    ],
)
def test_display_names(model_id, name, maker):
    assert display_name(model_id) == (name, maker)


def _vizzes(text: str) -> list[str]:
    return VIZ.findall(text)


def test_findings_page_shows_every_view(tmp_path):
    out = tmp_path / "site"
    build_site(_results(tmp_path, nine_models()), out, repo_root=_repo(tmp_path))
    blas = _read(out / "blas" / "findings.html")
    for anchor in ("profile", "ties", "levels", "topics", "directions", "tutor", "evidence", "cost", "consistency"):
        assert f'<h2 id="{anchor}">' in blas, anchor
        assert f'<a href="#{anchor}">' in blas  # listed in the table of contents
    tonada = _read(out / "tonada" / "findings.html")
    assert 'id="directions"' not in tonada  # no translation test in the Tonada suite
    assert 'id="tutor"' in tonada and 'id="levels"' in tonada
    # C1 has 12 items in the fakes: in the table, never plotted.
    assert "too few items" in blas and "C1 <span" in blas and ">C1</text>" not in blas
    assert "judge-marked" in blas and "step-bar judge" in blas
    home = _read(out / "blas" / "index.html")
    assert 'class="heat matrix" data-sortable data-top="10"' in home
    assert home.count("(highest)</span>") == 6  # one best cell per column: overall and five tests
    assert 'href="findings.html#ties"' in home
    model = _read(out / "blas" / "models" / "anthropic-claude-opus-5.html")
    assert "places best in" in model or "in every test" in model
    assert model.count('class="dtrack"') == 5  # one profile row per test
    tests = _read(out / "blas" / "tests.html")
    assert 'class="structure"' in tests and "Judges: the explanation, secondary" in tests
    assert 'href="findings.html#levels-morphology"' in tests


def test_every_chart_has_a_takeaway_caption_and_table(tmp_path):
    out = tmp_path / "site"
    build_site(_results(tmp_path, nine_models()), out, repo_root=_repo(tmp_path))
    seen = 0
    for page in sorted(out.rglob("*.html")):
        text = _read(page)
        figures = _vizzes(text)
        inside = sum(len(CHART_SVG.findall(fig)) for fig in figures)
        assert inside == len(CHART_SVG.findall(text)), f"{page.relative_to(out)}: a chart outside a takeaway figure"
        for fig in figures:
            takeaway = re.search(r'<p class="takeaway">([^<]+)</p>', fig)
            assert takeaway and takeaway.group(1).strip().endswith("."), page
            assert '<p class="viz-cap">' in fig, page
            assert "<summary>View as table</summary>" in fig and "<table" in fig.split("View as table")[1], page
        seen += len(figures)
    assert seen > 50
    findings = _read(out / "blas" / "findings.html")
    assert len(_vizzes(findings)) >= 9


def test_example_items_come_from_public_samples_and_are_escaped(tmp_path):
    repo = _repo(tmp_path)
    samples = repo / "samples" / "blas"
    samples.mkdir(parents=True)
    items = [
        {"id": "s-long", "input": "Give the plural of 'teach'. " + "Think it over. " * 20, "target": "tithe",
         "metadata": {"scoring": "accept_list", "accept": ["tithe"]}},
        {"id": "s-short", "input": "Plural of <b>cat</b>?", "target": "cait",
         "metadata": {"scoring": "accept_list", "accept": ["cait", "<i>cait</i>"]}},
    ]
    (samples / "morphology.jsonl").write_text("\n".join(json.dumps(item) for item in items) + "\n", encoding="utf-8")
    tutor = [
        {"id": "t-clean", "input": "Check: Tá sé.", "target": "Tá sé.", "metadata": {"scoring": "tutor", "has_error": False}},
        {"id": "t-error", "input": "Check this longer sentence: Tá sé mór go leor.", "target": "Tá sé mór go leor.",
         "metadata": {"scoring": "tutor", "has_error": True, "error_span": "mór", "correction": "mhór"}},
    ]
    (samples / "tutor_accuracy.jsonl").write_text("\n".join(json.dumps(item) for item in tutor) + "\n", encoding="utf-8")
    out = tmp_path / "site"
    build_site(_two_runs(tmp_path), out, repo_root=repo)
    tests = _read(out / "blas" / "tests.html")
    assert tests.count('class="example example-item"') == 2  # only tests with a public sample file
    assert "s-short" in tests and "s-long" not in tests  # the shortest item, chosen on every build
    assert "Plural of &lt;b&gt;cat&lt;/b&gt;?" in tests and "<b>cat</b>" not in tests
    assert "cait · &lt;i&gt;cait&lt;/i&gt;" in tests
    assert "t-error" in tests and "t-clean" not in tests  # a tutor item with an error explains more
    assert "mór → mhór" in tests


def test_one_model_and_twenty_two_models_build(tmp_path):
    one = tmp_path / "one"
    build_site(_results(tmp_path / "a", {"a__solo": fake_document("a/solo", 0.7)}), one, repo_root=_repo(tmp_path / "a"))
    findings = _read(one / "blas" / "findings.html")
    assert "Solo is the only model with a complete result" in findings
    assert "Solo is the only ranked model" in _read(one / "blas" / "index.html")
    assert "nothing to compare yet" in _read(one / "blas" / "models" / "a-solo.html")
    for fig in _vizzes(findings):
        assert '<p class="takeaway">' in fig

    many = tmp_path / "many"
    build_site(_results(tmp_path / "b", twenty_models()), many, repo_root=_repo(tmp_path / "b"))
    home = _read(many / "blas" / "index.html")
    assert "Show all 22 models" in home and home.count('<tr class="more">') >= 12
    findings = _read(many / "blas" / "findings.html")
    assert 'class="ln-model"' not in findings and "single lines are left out" in findings
    assert findings.count("Show all 22 models") >= 3  # directions, cost and consistency fold
    assert len(list((many / "blas" / "models").glob("*.html"))) == 22


def test_empty_results_dir_has_an_empty_findings_page(tmp_path):
    results = tmp_path / "results"
    (results / "runs").mkdir(parents=True)
    out = tmp_path / "site"
    build_site(results, out, repo_root=_repo(tmp_path))
    findings = _read(out / "blas" / "findings.html")
    assert "No complete runs yet" in findings and 'class="viz' not in findings


A = Est(0.80, (0.76, 0.84), 200)
B = Est(0.78, (0.74, 0.82), 200)
C = Est(0.60, (0.57, 0.63), 200)


def test_overlap_and_groups():
    assert overlaps(A, B) and not overlaps(A, C)
    assert overlaps(A, Est(0.1))  # no range: a gap cannot be called clear
    assert tie_groups([("C", C), ("A", A), ("B", B)]) == [["A", "B"], ["C"]]


def test_leader_sentence_says_tied_when_ranges_overlap():
    tied = leader_sentence([("A", A), ("B", B), ("C", C)])
    assert "tied with B" in tied and "95% ranges overlap" in tied and "C" not in tied.split("tied with")[1]
    assert "clearly ahead" in leader_sentence([("A", A), ("C", C)])
    assert "none is clearly ahead" in leader_sentence([("A", A), ("B", B), ("D", Est(0.79, (0.75, 0.83)))])
    assert "only model" in leader_sentence([("A", A)])


def test_matrix_and_profile_sentences_say_tied():
    tests = [("T1", [("A", A), ("B", B)]), ("T2", [("A", C), ("B", A)])]
    sentence = matrix_sentence(tests)
    assert sentence.startswith("A and B each have the highest score in 1 of 2 tests")
    assert "in 1 of the 2 tests the top score is tied" in sentence
    profile = profile_sentence("B", tests)
    assert "places best in T2 (1st of 2)" in profile
    assert "worst in T1 (2nd of 2, 2.0 points below the top but tied with it)" in profile
    assert "tied means the 95% ranges overlap" in profile
    assert profile_sentence("A", [("T1", [("A", A), ("B", B)]), ("T2", [("A", A), ("C", C)])]) == (
        "A ranks 1st in every test, but in 1 of them another model is tied with it (95% ranges overlap)."
    )


def test_level_direction_and_compare_sentences_say_not_clear_when_ranges_overlap():
    overlapping = [("A", {"A1": A, "B2": B}), ("B", {"A1": A, "B2": B})]
    assert level_sentence(["A1", "B2"], overlapping) == (
        "2 of 2 models score lower at B2 than at A1, but none of these drops is clear: the 95% ranges overlap."
    )
    clear = overlapping + [("C", {"A1": A, "B2": C})]
    assert "All 3 models score lower at B2 than at A1; the drop is clear (95% ranges do not overlap) for 1 of them." == level_sentence(["A1", "B2"], clear)
    assert "Fewer than two levels" in level_sentence(["A1"], overlapping)
    assert "but no gap is clear" in direction_sentence([("A", A, B), ("B", A, B)])
    assert "for 1 of them" in direction_sentence([("A", A, C), ("B", A, B)])
    compared = compare_sentence([("A", {"x": A, "y": B}), ("B", {"x": A, "y": B})], str, "topic")
    assert "highest-scoring topic is x (80.0%, 200 items)" in compared and "the gap is not clear" in compared
    assert "clear (95% ranges do not overlap) for 1 of 1" not in compare_sentence([("A", {"x": A, "y": C})], str, "topic")


def test_cost_and_value_sentences():
    assert spread_sentence([("A", 0.2), ("B", 8.0)], "cost per 1,000 correct answers", lambda v: f"${v:.2f}", ratio=True) == (
        "Cost per 1,000 correct answers runs from $0.20 (A) to $8.00 (B), 40 times as much."
    )
    assert value_sentence([("A", A, 30.0), ("B", B, 3.0), ("C", C, 0.5)]).startswith(
        "B is the cheapest model tied with the leader (95% ranges overlap)"
    )
    assert "also the cheapest" in value_sentence([("A", A, 1.0), ("C", C, 0.5)])


def test_topic_language_view_and_legacy_note(tmp_path):
    from bs4 import BeautifulSoup

    documents = nine_models()
    assert any("by_language_phenomenon" not in d["suites"]["blas"]["tests"]["morphology"] for d in documents.values())
    out = tmp_path / "new"
    build_site(_results(tmp_path / "new", documents), out, repo_root=_repo(tmp_path / "new"))
    page = BeautifulSoup(_read(out / "blas" / "findings.html"), "html.parser")
    figure = page.select_one(".viz-topic-language")
    assert figure.select_one(".takeaway") and figure.select_one(".viz-cap") and figure.select_one(".as-table table")
    assert "5 dataset items" in figure.get_text()
    assert "Show all 15 topics" in figure.get_text()
    rows = figure.select(".viz-body table tbody tr")
    assert len(rows) == 15 and len(figure.select(".viz-body tr.more")) == 3
    assert "dataset items per model; 6 models" in figure.select_one("td[title]")["title"]
    assert figure.select_one("td.empty").get_text() == "—"
    assert "items per model; 6 models" in figure.select_one(".as-table").get_text()
    assert "first languages" in _read(out / "tonada" / "findings.html")
    legacy = tmp_path / "legacy"
    build_site(_results(tmp_path / "old", {"old": fake_document("a/old", .7, topic_language=False)}),
               legacy, repo_root=_repo(tmp_path / "old"))
    for suite in ("blas", "tonada"):
        text = _read(legacy / suite / "findings.html")
        assert "This view needs results files written by a newer version." in text
        assert "viz-topic-language" not in text


def test_joint_cells_use_dataset_threshold_not_pooled_results(tmp_path):
    from bs4 import BeautifulSoup

    docs = {str(i): fake_document(f"a/model-{i}", .7) for i in range(5)}
    for i, document in enumerate(docs.values()):
        stat = {"score": .2 + i * .1, "n_items": 5, "ci95": [.1, .9], "epochs": 3, "consistency": .8}
        document["suites"]["blas"]["tests"]["morphology"]["by_language_phenomenon"] = {
            "irish": {"five": stat, "four": {**stat, "score": .01, "n_items": 4}},
            "welsh": {"five": {**stat, "score": .8}},
        }
    out = tmp_path / "site"
    build_site(_results(tmp_path, docs), out, repo_root=_repo(tmp_path))
    soup = BeautifulSoup(_read(out / "blas" / "findings.html"), "html.parser")
    chart = soup.select_one("#topic-language-morphology").parent
    assert "40.0%" in chart.get_text()  # equal-model mean, five dataset items suffice
    assert "1.0%" not in chart.get_text()  # 4 * 5 pooled results do not qualify
    assert chart.select_one("td.empty")
    assert "hardest in this column" in chart.get_text()


def test_radars_match_suite_size_and_grid_folds_at_twelve(tmp_path):
    from bs4 import BeautifulSoup

    out = tmp_path / "site"
    build_site(_results(tmp_path, twenty_models()), out, repo_root=_repo(tmp_path))
    blas = BeautifulSoup(_read(out / "blas" / "models.html"), "html.parser")
    grid = blas.select_one(".viz-radar-grid")
    assert len(grid.select(".radar-card")) == 22
    assert len(grid.select("li.more")) == 10
    assert grid.select_one("button")["data-more"] == "Show all 22 models"
    assert all(link["href"].startswith("models/") for link in grid.select(".radar-card"))
    for path in (out / "blas" / "models").glob("*.html"):
        soup = BeautifulSoup(_read(path), "html.parser")
        radar = soup.select_one(".viz-radar")
        assert radar and len(radar.select(".radar-label")) == 5
        assert len(radar.select(".radar-value")) == 5
        assert "0% at the centre to 100%" in radar.get_text()
        assert radar.select_one(".as-table table")
    assert 'class="radar"' not in _read(out / "tonada" / "models.html")
    for path in (out / "tonada" / "models").glob("*.html"):
        text = _read(path)
        assert 'class="radar"' not in text and 'class="dtrack"' in text


@pytest.mark.parametrize(("ys", "word"), [
    ([0, 1, 2, 3, 4], "strong"),
    ([4, 3, 2, 1, 0], "less consistent: a strong"),
    ([0, 1, 4, 3, 2], "moderate"),
    ([0, 3, 4, 1, 2], "weak"),
    ([0, 4, 3, 2, 1], "no clear link"),
    ([1, 1, 1, 1, 1], "undefined"),
])
def test_correlation_wording(ys, word):
    text = correlation_sentence(list(zip(range(5), ys)))
    assert word in text and "5 models" in text


def test_correlation_ties_and_too_few_models():
    assert "too few models (4" in correlation_sentence([(1, 1)] * 4)
    assert "too few models (0" in correlation_sentence([])
    assert "rank correlation 1.00" in correlation_sentence([(0, 0), (1, 1), (1, 1), (3, 3), (4, 4)])


def test_topic_language_takeaway_is_descriptive():
    text = topic_language_sentence([("past", "Irish", .2), ("past", "Welsh", .5), ("plural", "Irish", .3), ("plural", "Welsh", .7)])
    assert "past for Irish (20.0%)" in text and "Irish is lowest on 2 of 2" in text
    assert "not clear differences" in text
    assert "no single language" in topic_language_sentence([("past", "Irish", .2), ("past", "Welsh", .2)])


def test_consistency_scatter_has_both_scopes_and_excludes_non_three_ask_runs(tmp_path):
    from bs4 import BeautifulSoup

    documents = nine_models()
    documents["one_ask"] = fake_document("a/one-ask", .5, epochs=1)
    out = tmp_path / "site"
    build_site(_results(tmp_path, documents), out, repo_root=_repo(tmp_path))
    soup = BeautifulSoup(_read(out / "blas" / "findings.html"), "html.parser")
    figures = soup.select(".viz-consistency-scatter")
    assert len(figures) == 2
    for figure in figures:
        assert "9 models" in figure.select_one(".takeaway").get_text()
        assert "lower there by construction" in figure.select_one(".viz-cap").get_text()
        assert len(figure.select(".as-table tbody tr")) == 9
        assert "One Ask" not in figure.get_text()
        assert "Mean consistency" in figure.select_one("svg").get_text()
    assert "Consistency uses accept-list tests only" in figures[1].get_text()
