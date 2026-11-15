"""Static research site: pages, navigation, escaping, determinism, guards. Offline."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from site_fakes import fake_document, nine_models

from teanga_bench.markdown_lite import markdown_to_html
from teanga_bench.site import SUITES, SiteError, build_site, display_name

LINK = re.compile(r'(?:href|src|data-local)="([^"]+)"')
NAV = re.compile(r'<nav class="site-nav" aria-label="Main">(.*?)</nav>', re.S)
SUITE_PAGES = ("index.html", "tests.html", "models.html", "methodology.html")


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

    labels = {}
    for suite in ("blas", "tonada"):
        for page in sorted((out / suite).rglob("*.html")):
            text = _read(page)
            nav = NAV.search(text).group(1)
            labels[suite] = re.findall(r">([A-Za-z]+)<", nav)
            current = re.findall(r'href="([^"]+)" aria-current="page"', nav)
            if page.parent.name == "models":
                assert current == [] and 'href="../models.html" aria-current="true"' in nav
                assert 'href="../models.html">Models</a>' in text  # breadcrumb back to the index
            else:
                expected = "./" if page.name == "index.html" else f"./{page.name}"
                assert current == [expected], f"{page.relative_to(out)} marks {current}"
            for other in SUITES.values():
                assert other.short in text  # the suite switcher names both suites
            other = SUITES["tonada" if suite == "blas" else "blas"]
            assert f'href="{other.url}"' in text
    assert labels["blas"] == ["Leaderboard", "Tests", "Languages", "Models", "Methodology", "GitHub"]
    assert labels["tonada"] == ["Leaderboard", "Tests", "Learners", "Models", "Methodology", "GitHub"]


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
    out = tmp_path / "site"
    build_site(_two_runs(tmp_path), out, repo_root=_repo(tmp_path))
    for page in out.rglob("*.html"):
        text = _read(page)
        assert not re.search(r'<(?:script|link|img)[^>]+(?:src|href)="https?://', text), page
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


def test_public_sample_runs_are_labelled(tmp_path):
    results = _results(tmp_path, {"s__sample": fake_document("s/sample", 0.6, dataset="public_sample")})
    out = tmp_path / "site"
    build_site(results, out, repo_root=_repo(tmp_path))
    assert "public sample" in _read(out / "blas" / "index.html")
    assert "public sample" in _read(out / "blas" / "models.html")
    model = _read(out / "blas" / "models" / "s-sample.html")
    assert "not comparable with full-set runs" in model


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
