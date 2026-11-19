#!/usr/bin/env python3
"""Export public Teanga Bench bundles for Hugging Face Datasets and Static Spaces.

Reads ONLY public `samples/` (20 items per test + attribution notices) and
`results/` (`leaderboard.json` + `runs/*.json`). Never touches `data/private/`.
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = REPO_ROOT / "samples"
RESULTS_DIR = REPO_ROOT / "results"


def _assert_public_path(path: Path) -> None:
    if "private" in path.parts:
        raise RuntimeError(f"Refusing to read private path: {path}")


def _copy_public_samples(dataset_dir: Path) -> list[str]:
    copied: list[str] = []
    licence_note = SAMPLES_DIR / "LICENCE.md"
    if licence_note.is_file():
        dst_samples = dataset_dir / "samples"
        dst_samples.mkdir(parents=True, exist_ok=True)
        shutil.copy2(licence_note, dst_samples / "LICENCE.md")
        copied.append("samples/LICENCE.md")
    for suite in ("blas", "tonada"):
        src_suite = SAMPLES_DIR / suite
        _assert_public_path(src_suite)
        dst_suite = dataset_dir / "samples" / suite
        dst_suite.mkdir(parents=True, exist_ok=True)
        for src_file in sorted(src_suite.iterdir()):
            _assert_public_path(src_file)
            if src_file.is_file() and (
                src_file.suffix == ".jsonl" or src_file.name.endswith(".ATTRIBUTION.md")
            ):
                shutil.copy2(src_file, dst_suite / src_file.name)
                copied.append(f"samples/{suite}/{src_file.name}")
    return copied


def _copy_public_results(dataset_dir: Path) -> None:
    dst_results = dataset_dir / "results"
    dst_runs = dst_results / "runs"
    dst_runs.mkdir(parents=True, exist_ok=True)

    lb_src = RESULTS_DIR / "leaderboard.json"
    _assert_public_path(lb_src)
    shutil.copy2(lb_src, dst_results / "leaderboard.json")

    runs_src = RESULTS_DIR / "runs"
    _assert_public_path(runs_src)
    for run_file in sorted(runs_src.glob("*.json")):
        _assert_public_path(run_file)
        shutil.copy2(run_file, dst_runs / run_file.name)


def _write_dataset_readme(dataset_dir: Path, leaderboard: dict) -> None:
    models = leaderboard.get("models", [])
    rows = []
    for m in models:
        ov = m["overall"]
        bl = m["suites"]["blas"]
        to = m["suites"]["tonada"]
        rows.append(
            f"| {m['rank']} | `{m['model']}` | {ov['score']*100:.1f}% "
            f"({ov['ci95'][0]*100:.1f}%–{ov['ci95'][1]*100:.1f}%) | "
            f"{bl['score']*100:.1f}% | {to['score']*100:.1f}% | ${m['cost_usd']:.2f} |"
        )
    table_md = "\n".join(rows)

    readme = f"""---
license: other
license_name: apache-2.0-code-mixed-sample-licences
language:
  - ga
  - cy
  - gd
  - gv
  - br
  - kw
  - en
  - pt
  - es
  - vi
  - ja
task_categories:
  - translation
  - text-generation
  - question-answering
pretty_name: Teanga Bench
size_categories:
  - n<1K
---

# Teanga Bench (Public Sample & Results Bundle)

**Teanga Bench** measures how well large language models perform the work of a language tutor across two suites:

- **Blas suite** ([research.blasapp.com](https://research.blasapp.com)): Irish (`ga`), Welsh (`cy`), Scottish Gaelic (`gd`), Manx (`gv`), Breton (`br`), and Cornish (`kw`) across five tests (`morphology`, `lesson_exercises`, `translation`, `round_trip`, `tutor_accuracy`).
- **Tonada suite** ([research.tonadaapp.com](https://research.tonadaapp.com)): English (`en`) tutoring for learners whose first language is Portuguese (`pt`), Spanish (`es`), Vietnamese (`vi`), or Japanese (`ja`) across two tests (`exercises`, `tutor_accuracy`).

Code, scoring rules, and build scripts live at [github.com/johnway114/teanga-bench](https://github.com/johnway114/teanga-bench).

## What is in this dataset (and what is held out)

- **Included here (`samples/`)**: 20 public sample items per test with per-file `*.ATTRIBUTION.md` licence notices and `samples/LICENCE.md`, plus `results/leaderboard.json` and `results/runs/*.json`. Because `samples/` is public, those sample rows (including excerpts tagged `private-blas` and `private-tonada`) are exposed to training data.
- **Licences**: The code and metadata are Apache-2.0. Sample text in `samples/` is **not** covered by Apache-2.0 and retains each item's `metadata.licence` (including **GPL-3.0** for Gaelg Manx sentences, CC BY 2.0 FR, CC BY 4.0, OGL-v3, CC BY-SA 4.0, and Blas/Tonada sample excerpts).
- **Held out (`data/private/`)**: The full evaluation sets remain private and are **not** included in this repository or dataset bundle to prevent training-data contamination.
- **Human review status**: Every item in Teanga Bench has `human_checked: false`. No human expert signed off on the benchmark items; scores on app-derived tests measure agreement with the source app content, and tutor explanation scores are judge-marked (`deepseek/deepseek-v4.1-flash-1017` and `qwen/qwen3.8-flash`), not human-validated. Read the full [methodology](https://github.com/johnway114/teanga-bench/blob/main/docs/methodology.md) before citing a score.

## Leaderboard Summary (Full 2,260-item Held-Out Sets, 3 Epochs)

| Rank | Model | Overall (95% CI) | Blas Suite | Tonada Suite | Run Cost (USD) |
| --- | --- | --- | --- | --- | --- |
{table_md}

## Citation

If you use Teanga Bench or its results, please cite it using [`CITATION.cff`](https://github.com/johnway114/teanga-bench/blob/main/CITATION.cff):

```bibtex
@software{{conway_2026_teanga_bench,
  author       = {{Conway, John}},
  title        = {{Teanga Bench}},
  year         = 2026,
  version      = {{0.2.0}},
  url          = {{https://research.blasapp.com}},
  code         = {{https://github.com/johnway114/teanga-bench}},
  license      = {{Apache-2.0}}
}}
```
"""
    (dataset_dir / "README.md").write_text(readme, encoding="utf-8")


def _write_space_bundle(space_dir: Path, leaderboard: dict) -> None:
    space_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RESULTS_DIR / "leaderboard.json", space_dir / "leaderboard.json")

    space_readme = """---
title: Teanga Bench
emoji: "\U0001f310"
colorFrom: emerald
colorTo: slate
sdk: static
pinned: true
license: apache-2.0
short_description: Language tutor benchmark for Celtic languages (Blas) & English L1 tutoring (Tonada)
---

# Teanga Bench Leaderboard

Static Hugging Face Space for **Teanga Bench** — evaluating LLMs as language tutors across:
- **Blas suite**: Irish, Welsh, Scottish Gaelic, Manx, Breton, and Cornish ([research.blasapp.com](https://research.blasapp.com))
- **Tonada suite**: English tutoring for Portuguese, Spanish, Vietnamese, and Japanese learners ([research.tonadaapp.com](https://research.tonadaapp.com))

Source code & methodology: [github.com/johnway114/teanga-bench](https://github.com/johnway114/teanga-bench).
"""
    (space_dir / "README.md").write_text(space_readme, encoding="utf-8")

    models = leaderboard.get("models", [])
    rows_html = []
    for m in models:
        ov = m["overall"]
        bl = m["suites"]["blas"]
        to = m["suites"]["tonada"]
        ga = m["languages"]["irish"]
        cy = m["languages"]["welsh"]
        gd = m["languages"]["scots-gaelic"]
        gv = m["languages"]["manx"]
        br = m["languages"]["breton"]
        kw = m["languages"]["cornish"]
        rows_html.append(
            f"<tr>"
            f"<td>{m['rank']}</td>"
            f"<td><code>{html.escape(m['model'])}</code></td>"
            f"<td><strong>{ov['score']*100:.1f}%</strong> "
            f"<span class='ci'>({ov['ci95'][0]*100:.1f}–{ov['ci95'][1]*100:.1f}%)</span></td>"
            f"<td>{bl['score']*100:.1f}%</td>"
            f"<td>{to['score']*100:.1f}%</td>"
            f"<td>{ga['score']*100:.1f}%</td>"
            f"<td>{cy['score']*100:.1f}%</td>"
            f"<td>{gd['score']*100:.1f}%</td>"
            f"<td>{gv['score']*100:.1f}%</td>"
            f"<td>{br['score']*100:.1f}%</td>"
            f"<td>{kw['score']*100:.1f}%</td>"
            f"<td>${m['cost_usd']:.2f}</td>"
            f"</tr>"
        )

    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Teanga Bench — Language Tutor LLM Leaderboard</title>
  <style>
    :root {{
      --bg: #0f172a;
      --card: #1e293b;
      --text: #f1f5f9;
      --muted: #94a3b8;
      --accent: #34d399;
      --border: #334155;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.55;
      padding: 2rem 1rem;
    }}
    .wrap {{ max-width: 1120px; margin: 0 auto; }}
    header {{ margin-bottom: 1.75rem; }}
    h1 {{ margin: 0 0 0.4rem; font-size: 1.9rem; }}
    .sub {{ color: var(--muted); margin: 0 0 1rem; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 0.75rem; }}
    .links a {{
      color: var(--accent);
      text-decoration: none;
      border: 1px solid var(--border);
      background: var(--card);
      padding: 0.4rem 0.75rem;
      border-radius: 6px;
      font-size: 0.9rem;
    }}
    .links a:hover {{ border-color: var(--accent); }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1.25rem;
      margin-bottom: 1.5rem;
      overflow-x: auto;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
    th, td {{ padding: 0.55rem 0.65rem; text-align: left; border-bottom: 1px solid var(--border); white-space: nowrap; }}
    th {{ color: var(--muted); font-weight: 600; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.03em; }}
    .ci {{ color: var(--muted); font-size: 0.82rem; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.86rem; }}
    h2 {{ margin-top: 0; font-size: 1.2rem; }}
    p {{ margin: 0.5rem 0; color: var(--muted); }}
    strong.hi {{ color: var(--text); }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Teanga Bench</h1>
      <p class="sub">Measuring how well large language models do the work of a language tutor across 2,260 held-out items (3 epochs each).</p>
      <div class="links">
        <a href="https://research.blasapp.com" target="_blank" rel="noopener">Blas Suite (Celtic)</a>
        <a href="https://research.tonadaapp.com" target="_blank" rel="noopener">Tonada Suite (English L1)</a>
        <a href="https://github.com/johnway114/teanga-bench" target="_blank" rel="noopener">GitHub Harness &amp; Methodology</a>
        <a href="./leaderboard.json" target="_blank" rel="noopener">leaderboard.json</a>
      </div>
    </header>

    <section class="card">
      <h2>Overall Leaderboard (Full Held-Out Sets, n=2,260)</h2>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Model</th>
            <th>Overall (95% CI)</th>
            <th>Blas</th>
            <th>Tonada</th>
            <th>Irish</th>
            <th>Welsh</th>
            <th>Sc. Gaelic</th>
            <th>Manx</th>
            <th>Breton</th>
            <th>Cornish</th>
            <th>Cost</th>
          </tr>
        </thead>
        <tbody>
          {"".join(rows_html)}
        </tbody>
      </table>
    </section>

    <section class="card">
      <h2>Methodology &amp; Caveats</h2>
      <p><strong class="hi">Two suites:</strong> Blas (1,500 items) tests Irish, Welsh, Scottish Gaelic, Manx, Breton, and Cornish across morphology, lesson exercises, translation (chrF++), round-trip translation, and tutor error correction. Tonada (760 items) tests English exercises and tutor error correction for Portuguese, Spanish, Vietnamese, and Japanese learners.</p>
      <p><strong class="hi">Held-out data &amp; review status:</strong> The full 2,260-item test sets stay private to prevent training contamination; 20 public sample items per test are released in the repository and Hugging Face Dataset. Every item has <code>human_checked: false</code>. Tutor explanation scores are judge-marked and reported separately from the rule-marked headline score.</p>
      <p><strong class="hi">Token-limit finding:</strong> Initial runs used a 2,048-token cap, which truncated reasoning models mid-thought and scored empty outputs as 0 (notably <code>qwen/qwen3.8-flash</code> on 1,978 item-epochs). Raising the cap to 16,000 tokens and re-running truncated item-epochs is documented in the methodology.</p>
    </section>
  </div>
</body>
</html>
"""
    (space_dir / "index.html").write_text(index_html, encoding="utf-8")


def export_bundles(output_dir: Path) -> dict[str, int]:
    lb_path = RESULTS_DIR / "leaderboard.json"
    _assert_public_path(lb_path)
    leaderboard = json.loads(lb_path.read_text(encoding="utf-8"))

    dataset_dir = output_dir / "hf-dataset"
    space_dir = output_dir / "hf-space"

    if dataset_dir.exists():
        shutil.rmtree(dataset_dir)
    if space_dir.exists():
        shutil.rmtree(space_dir)

    dataset_dir.mkdir(parents=True, exist_ok=True)
    copied_samples = _copy_public_samples(dataset_dir)
    _copy_public_results(dataset_dir)
    _write_dataset_readme(dataset_dir, leaderboard)
    _write_space_bundle(space_dir, leaderboard)

    return {
        "sample_files": len(copied_samples),
        "models": len(leaderboard.get("models", [])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Teanga Bench HF Dataset and Space bundles.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "dist" / "hf-bundle",
        help="Directory where hf-dataset/ and hf-space/ will be written.",
    )
    args = parser.parse_args()
    stats = export_bundles(args.output_dir.resolve())
    print(f"Exported hf-dataset/ and hf-space/ to {args.output_dir.resolve()} ({stats['sample_files']} sample/attribution files, {stats['models']} models).")


if __name__ == "__main__":
    main()
