"""Technical SEO, OpenGraph/Twitter cards, sitemaps, robots.txt, and Schema.org Dataset JSON-LD tests."""

from __future__ import annotations

import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

from bs4 import BeautifulSoup
from site_fakes import fake_document

from teanga_bench.og_cards import (
    CARD_HEIGHT,
    CARD_WIDTH,
    PNG_SIGNATURE,
    CardRow,
    CardSpec,
    _fallback_png,
    build_card_svg,
    render_card_png,
)
from teanga_bench.site import SUITES, _json_ld_script, build_site

EXPECTED_CLEAN_PATHS = {
    "blas": {
        "index.html": "https://research.blasapp.com/",
        "tests.html": "https://research.blasapp.com/tests",
        "findings.html": "https://research.blasapp.com/findings",
        "languages.html": "https://research.blasapp.com/languages",
        "models.html": "https://research.blasapp.com/models",
        "methodology.html": "https://research.blasapp.com/methodology",
    },
    "tonada": {
        "index.html": "https://research.tonadaapp.com/",
        "tests.html": "https://research.tonadaapp.com/tests",
        "findings.html": "https://research.tonadaapp.com/findings",
        "learners.html": "https://research.tonadaapp.com/learners",
        "models.html": "https://research.tonadaapp.com/models",
        "methodology.html": "https://research.tonadaapp.com/methodology",
    },
}


def _results(tmp_path: Path, documents: dict[str, dict]) -> Path:
    runs = tmp_path / "results" / "runs"
    runs.mkdir(parents=True)
    for name, doc in documents.items():
        (runs / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")
    return tmp_path / "results"


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    reports = root / "data" / "build-reports"
    reports.mkdir(parents=True)
    report = {
        "suite": "blas",
        "test": "morphology",
        "n_items": 360,
        "n_public_sample": 20,
        "by_language": {"irish": 60, "welsh": 60},
        "by_cefr": {"A1": 100, "None": 260},
        "by_licence": {"private-blas": 360},
        "by_evidence": {"blas-app+bunamo": 11, "blas-app-only": 349},
        "human_checked": 0,
    }
    (reports / "blas_morphology.json").write_text(json.dumps(report), encoding="utf-8")
    return root


def _two_runs(tmp_path: Path) -> Path:
    return _results(
        tmp_path,
        {
            "a__strong": fake_document("a/strong", 0.85, generated_at="2026-11-12T08:00:00+00:00"),
            "b__weak": fake_document("b/weak", 0.45, generated_at="2026-11-13T09:30:00+00:00"),
            "c__capped": fake_document(
                "c/capped",
                0.95,
                status="cost_cap_reached",
                generated_at="2026-11-12T09:00:00+00:00",
            ),
        },
    )


def _png_size(data: bytes) -> tuple[int, int]:
    assert data.startswith(PNG_SIGNATURE)
    assert data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


def _meta_map(soup: BeautifulSoup) -> dict[str, str]:
    tags: dict[str, str] = {}
    for meta in soup.find_all("meta"):
        key = meta.get("property") or meta.get("name")
        if key and meta.get("content") is not None:
            tags[key] = meta["content"]
    return tags


def test_every_html_page_has_canonical_og_and_twitter_tags(tmp_path):
    out = tmp_path / "site"
    build_site(_two_runs(tmp_path), out, repo_root=_repo(tmp_path))

    all_pages = sorted(out.rglob("*.html"))
    assert len(all_pages) == 17  # suites.html + 2 * (6 suite pages + 2 model pages)

    for page in all_pages:
        soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
        canonical = soup.find("link", rel="canonical")
        assert canonical is not None and canonical.get("href"), page
        metas = _meta_map(soup)

        for key in (
            "description",
            "og:type",
            "og:site_name",
            "og:title",
            "og:description",
            "og:url",
            "og:image",
            "og:image:width",
            "og:image:height",
            "og:image:alt",
            "twitter:card",
            "twitter:title",
            "twitter:description",
            "twitter:image",
            "twitter:image:alt",
        ):
            assert metas.get(key), f"{page.relative_to(out)} missing {key}"

        assert metas["og:type"] == "website"
        assert metas["og:site_name"] == "Teanga Bench"
        assert metas["og:url"] == canonical["href"]
        assert metas["og:image:width"] == "1200"
        assert metas["og:image:height"] == "630"
        assert metas["twitter:card"] == "summary_large_image"
        assert metas["twitter:image"] == metas["og:image"]
        assert metas["twitter:title"] == metas["og:title"]
        assert metas["twitter:description"] == metas["og:description"]
        assert metas["twitter:image:alt"] == metas["og:image:alt"]

    for suite_key, pages in EXPECTED_CLEAN_PATHS.items():
        base = SUITES[suite_key].url.rstrip("/")
        for rel, expected_url in pages.items():
            soup = BeautifulSoup((out / suite_key / rel).read_text(encoding="utf-8"), "html.parser")
            assert soup.find("link", rel="canonical")["href"] == expected_url
            metas = _meta_map(soup)
            assert metas["og:image"] == f"{base}/og-image.png"
        for slug in ("a-strong", "b-weak"):
            soup = BeautifulSoup((out / suite_key / "models" / f"{slug}.html").read_text(encoding="utf-8"), "html.parser")
            assert soup.find("link", rel="canonical")["href"] == f"{base}/models/{slug}"


def test_dataset_json_ld_on_key_pages_and_safely_escaped(tmp_path):
    out = tmp_path / "site"
    build_site(_two_runs(tmp_path), out, repo_root=_repo(tmp_path))

    expected_keywords = {
        "blas": {"ga", "gle", "cy", "cym", "gd", "gla", "gv", "glv", "br", "bre", "kw", "cor", "Irish", "Welsh"},
        "tonada": {"en", "eng", "pt", "por", "es", "spa", "vi", "vie", "ja", "jpn", "Portuguese", "Japanese"},
    }

    for suite_key in ("blas", "tonada"):
        base = SUITES[suite_key].url.rstrip("/")
        dataset_files = ("index.html", "tests.html", f"{SUITES[suite_key].group_page}.html", "methodology.html")
        for rel in dataset_files:
            soup = BeautifulSoup((out / suite_key / rel).read_text(encoding="utf-8"), "html.parser")
            scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
            assert len(scripts) == 1, f"{suite_key}/{rel}"
            payload = json.loads(scripts[0].string)
            assert payload["@context"] == "https://schema.org"
            assert payload["@type"] == "Dataset"
            assert payload["name"]
            assert len(payload["description"]) >= 80
            assert payload["url"] == EXPECTED_CLEAN_PATHS[suite_key][rel]
            assert payload["license"] == "https://www.apache.org/licenses/LICENSE-2.0"
            assert payload["isAccessibleForFree"] is True
            assert payload["creator"]["name"] == "John Conway"
            assert expected_keywords[suite_key].issubset(set(payload["keywords"]))
            urls = {d["contentUrl"] for d in payload["distribution"] if d.get("@type") == "DataDownload"}
            assert urls == {f"{base}/data/leaderboard.json", "https://github.com/johnway114/teanga-bench"}
            assert payload["dateModified"] == "2026-11-13T09:30:00+00:00"

    script = _json_ld_script({"name": "</script><script>alert(1)</script><!--&>"})
    assert "</script>" not in script[len('<script type="application/ld+json">') : -len("</script>")]
    inner = script[len('<script type="application/ld+json">') : -len("</script>")]
    assert json.loads(inner)["name"] == "</script><script>alert(1)</script><!--&>"


def test_og_images_are_valid_1200x630_png_and_deterministic(tmp_path):
    out1 = tmp_path / "one"
    out2 = tmp_path / "two"
    results = _two_runs(tmp_path)
    repo = _repo(tmp_path)
    build_site(results, out1, repo_root=repo)
    build_site(results, out2, repo_root=repo)

    for suite_key in ("blas", "tonada"):
        png1 = (out1 / suite_key / "og-image.png").read_bytes()
        png2 = (out2 / suite_key / "og-image.png").read_bytes()
        assert png1 == png2
        assert _png_size(png1) == (CARD_WIDTH, CARD_HEIGHT)

    spec = CardSpec(
        suite_key="blas",
        suite_name="Blas suite",
        headline="How well do AI models handle the Celtic languages?",
        description="Irish, Welsh, Scottish Gaelic, Manx, Breton and Cornish",
        domain="research.blasapp.com",
        n_tests=5,
        total_ranked=1,
        rows=(CardRow(rank=1, display="Model <One> & Co", provider="Maker", score=0.85),),
        updated_label="13 November 2026",
    )
    svg = build_card_svg(spec)
    assert "&lt;One&gt; &amp; Co" in svg
    assert render_card_png(spec) == render_card_png(spec)
    fallback = _fallback_png(spec)
    assert _png_size(fallback) == (CARD_WIDTH, CARD_HEIGHT)


def test_sitemaps_and_robots_txt_have_clean_canonical_urls(tmp_path):
    out = tmp_path / "site"
    build_site(_two_runs(tmp_path), out, repo_root=_repo(tmp_path))

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    for suite_key, pages in EXPECTED_CLEAN_PATHS.items():
        base = SUITES[suite_key].url.rstrip("/")
        robots = (out / suite_key / "robots.txt").read_text(encoding="utf-8")
        assert "User-agent: *" in robots
        assert "Allow: /" in robots
        assert f"Sitemap: {base}/sitemap.xml" in robots

        sitemap_text = (out / suite_key / "sitemap.xml").read_text(encoding="utf-8")
        root = ET.fromstring(sitemap_text)
        locs = [el.text for el in root.findall("sm:url/sm:loc", ns)]
        expected = list(pages.values()) + [f"{base}/models/a-strong", f"{base}/models/b-weak"]
        assert locs == expected
        assert all(not loc.endswith(".html") for loc in locs)
        assert f"{base}/models/c-capped" not in locs
        lastmods = [el.text for el in root.findall("sm:url/sm:lastmod", ns)]
        assert len(lastmods) == len(locs)


def test_empty_results_still_generate_seo_files(tmp_path):
    results = tmp_path / "results"
    (results / "runs").mkdir(parents=True)
    out = tmp_path / "site"
    build_site(results, out, repo_root=_repo(tmp_path))

    for suite_key in ("blas", "tonada"):
        assert _png_size((out / suite_key / "og-image.png").read_bytes()) == (CARD_WIDTH, CARD_HEIGHT)
        assert (out / suite_key / "robots.txt").is_file()
        root = ET.fromstring((out / suite_key / "sitemap.xml").read_text(encoding="utf-8"))
        assert root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url")
        assert not root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod")
