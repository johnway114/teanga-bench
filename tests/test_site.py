"""Static research site: build, escaping, determinism, guards. Offline."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from site_fakes import fake_document

from teanga_bench.markdown_lite import markdown_to_html
from teanga_bench.site import SiteError, build_site

HREF = re.compile(r'(?:href|src)="([^"]+)"')


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


def test_site_builds_from_two_complete_runs(tmp_path):
    results = _two_runs(tmp_path)
    out = tmp_path / "site"
    summary = build_site(results, out, repo_root=_repo(tmp_path))

    assert summary["suites"]["blas"]["ranked"] == 2 and summary["suites"]["tonada"]["ranked"] == 2
    for suite in ("blas", "tonada"):
        home = (out / suite / "index.html").read_text(encoding="utf-8")
        assert home.index("a/strong") < home.index("b/weak")  # ranked by score
        assert "95% interval" in home and "How to read this" in home
        assert "https://github.com/johnway114/teanga-bench" in home
        assert "13 November 2026" in home  # newest run's date, not the clock
        assert "Blas" + " Bench" not in home
        for slug in ("a-strong", "b-weak"):
            assert (out / suite / "models" / f"{slug}.html").exists()
        board = json.loads((out / suite / "data" / "leaderboard.json").read_text(encoding="utf-8"))
        assert board["suite"] == suite
        assert [m["rank"] for m in board["models"]] == [1, 2]
        assert set(board["models"][0]["tests"]) == set(fake_document("x/y", 0.5)["suites"][suite]["tests"])
    assert "Irish" in (out / "blas" / "index.html").read_text(encoding="utf-8")
    assert "Portuguese" in (out / "tonada" / "index.html").read_text(encoding="utf-8")
    model = (out / "blas" / "models" / "a-strong.html").read_text(encoding="utf-8")
    for heading in ("Scores by test", "Tutor explanations", "By language", "By CEFR level", "Grammar topics", "Cost and prices", "Failure examples"):
        assert heading in model
    assert "Judge agreement" in model and "87.0%" in model
    method = (out / "blas" / "methodology.html").read_text(encoding="utf-8")
    assert "Word forms" in method and "blas-app+bunamo 11" in method and "counting" not in method
    assert (out / "assets" / "site.css").exists() and (out / "suites.html").exists()


def test_every_relative_link_resolves(tmp_path):
    out = tmp_path / "site"
    build_site(_two_runs(tmp_path), out, repo_root=_repo(tmp_path))
    pages = sorted(out.rglob("*.html"))
    assert pages
    for page in pages:
        for target in HREF.findall(page.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            assert not target.startswith("/"), f"{page}: absolute link {target}"
            resolved = (page.parent / target.split("#")[0]).resolve()
            if target.endswith("/"):
                resolved = resolved / "index.html"
            assert resolved.exists(), f"{page.relative_to(out)} links to missing {target}"


def test_empty_results_dir_builds_empty_state(tmp_path):
    results = tmp_path / "results"
    (results / "runs").mkdir(parents=True)
    out = tmp_path / "site"
    summary = build_site(results, out, repo_root=_repo(tmp_path))
    assert summary["updated"] is None
    for suite in ("blas", "tonada"):
        home = (out / suite / "index.html").read_text(encoding="utf-8")
        assert "First results will appear here after the first run" in home
        assert "What is measured" in home
        assert not (out / suite / "models").exists()
        assert json.loads((out / suite / "data" / "leaderboard.json").read_text(encoding="utf-8"))["models"] == []
    assert "Word forms" in (out / "blas" / "index.html").read_text(encoding="utf-8")
    # A results dir with no runs/ folder at all also builds.
    build_site(tmp_path / "nothing", tmp_path / "site2", repo_root=_repo(tmp_path / "x"))


def test_model_output_is_escaped(tmp_path):
    attack = '<script>alert("x")</script><img src=x onerror=alert(1)>'
    results = _two_runs(tmp_path, output_text=attack)
    out = tmp_path / "site"
    build_site(results, out, repo_root=_repo(tmp_path))
    for page in out.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        assert "<script" not in text.lower()
        assert "onerror=alert" not in text or "&lt;img" in text
    model = (out / "blas" / "models" / "a-strong.html").read_text(encoding="utf-8")
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in model


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
    home = (out / "blas" / "index.html").read_text(encoding="utf-8")
    assert "a/ok" in home and "c/capped" not in home and "mockllm" not in home
    assert "1 other run did not finish" in home
    assert not (out / "blas" / "models" / "c-capped.html").exists()


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
    page = (out / "blas" / "methodology.html").read_text(encoding="utf-8")
    assert "<h1>How it works</h1>" in page
    assert '<h3 id="table">Table</h3>' in page
    assert "<strong>bold</strong>" in page and "<code>code</code>" in page
    assert 'href="https://github.com/johnway114/teanga-bench/blob/main/docs/HARNESS.md"' in page
    assert "javascript:" not in page and "<script" not in page
    assert "<td>1</td>" in page and "<li>one</li>" in page
    assert "&lt;b&gt;raw&lt;/b&gt;" in page
    assert "Word forms" in page  # the generated test table follows


def test_markdown_lists_and_paragraphs():
    html = markdown_to_html("Para one\ncontinues.\n\n1. first\n2. second\n   wrapped\n")
    assert "<p>Para one continues.</p>" in html
    assert "<ol><li>first</li><li>second wrapped</li></ol>" in html
