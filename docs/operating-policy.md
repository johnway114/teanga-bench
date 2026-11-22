# Operating Policy and v2 Cost Decision

Recorded 2026-11-19 after the initial nine v1 runs and the [PR #1](https://github.com/johnway114/teanga-bench/pull/1) review.

## 1. Which models we benchmark (cadence policy)

New models now appear every few days. Teanga Bench does **not** track every release automatically.

- **Daily OpenRouter monitoring is alert-only.** Checking OpenRouter's public model list is free and never triggers a paid run automatically.
- **Run only big releases and real production candidates:**
  - **Major flagship generation releases** (new Claude, GPT, or Gemini flagship generations — roughly 4–6 per year). These are the launches worth publishing and sharing.
  - **Cheap production candidates** (<$1 per million output tokens) that Blas or Tonada might actually deploy in production (~$0.20–$1.00 per v2 run).
- **Skip** minor snapshots, point updates, niche labs, and models we would neither deploy nor publish an update about.

Target ongoing spend is roughly **$3–$8 per month** (~$1.90–$3.15 per flagship via `--batch`, or ~$3.60–$6.00 on OpenRouter).

## 2. Why we kept 1,260 items and cut cost via v2 defaults (`2b78ee1`)

The first nine v1 runs (7 tests, 2,260 items, 3 epochs, provider-default reasoning) cost **$36.70–$51.05** per flagship (`anthropic/claude-fable-5.2`, `openai/gpt-6-astra`, `google/gemini-4-hydrogen`, `moonshotai/kimi-k3.1-pro`). Raw logs showed that:

- Judges cost only **$0.59–$0.84** per full 3-epoch run (<2% of spend).
- Always-on and default-on reasoning burned **80–99%** of candidate output tokens on short morphology and translation items (`gemini-4-hydrogen` averaged 795 output tokens/call; `claude-fable-5.2` and `gpt-6-astra` spent 80–89% of morphology/translation output tokens on reasoning).
- Re-scoring all nine v1 runs on **Epoch 1 alone** moved overall scores by at most **0.43pp** and widened overall 95% intervals by only **0.01–0.18pp**, while cutting cost **3×**.
- Three v1 tests added cost without signal: `tonada/exercises` was saturated at **98.0–99.6%**, `blas/lesson_exercises` clustered at **95.6–98.5%** across top models (`r = 0.95` with translation), and `blas/round_trip` took 2 calls per item at `r = 0.96` with `blas/translation`.

Instead of halving item counts (which would push per-language/L1 CIs past ±10pp), v2 keeps **1,260 items across 4 non-saturated core tests** (`blas/morphology`, `blas/translation`, `blas/tutor_accuracy`, `tonada/tutor_accuracy`; overall 95% CI ~±1.6pp) and cuts spend via:

1. **`--epochs 1`** by default (3× cheaper).
2. **4 core tests** by default in `config/models.yaml` (`--all-tests` keeps retired v1 tests runnable).
3. **`--reasoning-effort low`** by default (with automatic `reasoning_tokens: 512` fallback for models exposing `reasoning` without `reasoning_effort`, and clean skip for non-reasoning models).
4. **Optional `--batch`** for 50%-off direct provider Batch APIs (`openai/`, `anthropic/`, `google/` via `uv pip install -e '.[batch]'`).
5. **Trimmed prompt boilerplate** and terse `ANSWER:` instructions.

## 3. API and privacy rules

- **Always use paid, zero-retention API endpoints** (`OPENROUTER_API_KEY`, or direct `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` with `--batch`).
- **Never run `data/private/` items through consumer subscriptions or free tiers** (OpenCode Go/free Zen, Gemini consumer/OAuth plans, `:free` OpenRouter slugs). Consumer plans inject hidden system prompts that break comparability, enforce rolling caps, and can log or train on prompts.
- **Probe new reasoning flagships first** with a `<$0.30` smoke test before committing to a full run:
  ```bash
  teanga-bench run --model <openrouter-id> --limit 5 --max-cost 0.50 --output /tmp/probe.json
  ```

## 4. Transition from v1 to v2 results

v1 runs (7 tests, 3 epochs, default reasoning, 2,260 items) and v2 runs (4 core tests, 1 epoch, low reasoning, cleaned Tonada tutor, 1,260 items) are **not directly comparable**. Neither set voids the other.

- The nine published v1 runs live in `results/v1-archive/runs/` (JSON and the Markdown report beside each file). They are stamped `methodology: "v1"`. Their scores are unchanged; the field is a label, not a rescore. `results/v1-archive/leaderboard.json`, `leaderboard.md` and `charts/` are that board.
- `results/runs/` is the v2 board only. `teanga-bench leaderboard` and `teanga-bench publish` rebuild `results/leaderboard.json` from that directory and do not rewrite the archive. A new run refuses to overwrite a v1 file or to write into the archive.
- The research sites serve v2 at the existing board URLs (`/`, `/models`, `/findings`, `/tests`, `/methodology`). v1 is the **v1 (archived)** board under `/v1/` on both hosts, including model pages and `v1/data/leaderboard.json`. Every page names its protocol, says the two are not comparable, and links to the other board.
- A model that exists only in v1 keeps `https://research.blasapp.com/models/<slug>` and the Tonada counterpart as a redirect to `/v1/models/<slug>`, so a cited v1 score is not silently replaced. Once that model also has a v2 run, `/models/<slug>` is the v2 page and links to the archive page, which stays the v1 score.
- The Zenodo deposit [10.5281/zenodo.24305705](https://doi.org/10.5281/zenodo.24305705) remains the citation for Teanga Bench and records the v1 result set. Do not retarget that DOI at v2 scores.
- Re-run the models worth publishing on v2 (~$10–$12 for the top 5–6 plus a new flagship, with `--batch`). Publish those into `results/runs/`. The archive stays put.

## 5. PR #1 review triage (`2b78ee1`)

PR #1 (`docs/review-recommendations.md`) was closed after landing its actionable fixes directly on `main`:

- Isolated `public_sample` runs into git-ignored `results/samples/` and blocked them from `leaderboard`, `site`, and `publish`.
- Clarified Linux/CI `OPENROUTER_API_KEY` vs macOS keychain fallback.
- Removed the 44 unreviewed Wikipedia revision items from `tonada/tutor_accuracy` (v1 logs showed grammatical style edits scored 32.6–43.9% and inverted model rankings) and rebuilt to 360 machine-reviewed app items.
- Added `samples/LICENCE.md` and updated `README.md`, `CITATION.cff`, and `scripts/export_hf_bundle.py` to carve `samples/` (including GPL-3.0 Gaelg Manx text) out of Apache-2.0 and disclose training-data exposure of public samples.
