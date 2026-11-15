# Teanga Bench harness

Teanga Bench (`teanga-bench`) is an Inspect AI benchmark. One command runs every
test on one model and writes the results. The brief is in the top-level README.

```bash
teanga-bench run --model openai/gpt-6-luna
```

The harness never calls a model unless you run `teanga-bench run` with a real
model id. Tests and the mock path make no paid call.

## Commands

`teanga-bench run --model <openrouter-id>` runs every test on that model.

| Option | Default | Meaning |
| --- | --- | --- |
| `--model` | required | OpenRouter id, such as `anthropic/claude-haiku-5.5`. `mockllm/model` runs the offline mock path |
| `--max-cost` | 5.00 | Hard cap in USD for candidate plus judge spend |
| `--epochs` | 3 | Times each item is asked |
| `--limit` | all | Items per test, for smoke runs |
| `--tests` | all | Test names, or `suite/test` |
| `--output` | `results/runs/<id with / as __>.json` | Where the results JSON goes |
| `--data-root` | repo root | Folder holding `data/private/` and `samples/` |
| `--log-dir` | `logs/` | Inspect logs |
| `--publish` | off | After a complete live run, run `publish` for it. Refused up front for mock models and for `--output` outside `results/runs/` |

`run` writes the results JSON, a Markdown report next to it (`.md`), and then
rebuilds the leaderboard. Exit code 0 means every test finished (and, with
`--publish`, the publish worked). Exit code 3 means the cost cap stopped the run.
Exit code 1 means some test did not finish, the leaderboard failed, or the
publish was refused or failed. Exit code 2 means the run could not start.

`teanga-bench leaderboard` reads every `results/runs/*.json` and writes
`results/leaderboard.json`, `results/leaderboard.md`, and SVG charts in
`results/charts/`. `run` calls it for you.

`teanga-bench validate` checks every dataset file: unique ids, required
metadata, non-empty `accept` and `references`, tutor edits that rebuild the gold
sentence. There is no limit on item count.

`teanga-bench site` builds the research site into `site/` from
`results/runs/*.json`. `teanga-bench publish --model <id>` (or `--results
<file>`) publishes one run. Both are described below.

## Datasets

Tasks are data-driven. Every file `data/private/<suite>/<test>.jsonl` is one
test. When a test has no private file, the harness uses
`samples/<suite>/<test>.jsonl` instead. Each test records `dataset: "full"` or
`"public_sample"` in the results. Runs on samples are not comparable with runs on
full sets. The build scripts are in `scripts/`, and `scripts/_common.py` lists the required
metadata.

Each item has `metadata.scoring`, which picks the scorer.

| `scoring` | What is asked | Score |
| --- | --- | --- |
| `accept_list` | An answer on an `ANSWER:` line | 1 if it matches any string in `accept` after light normalisation, else 0 |
| `tutor` | Find, fix and explain an error, or leave a clean sentence alone | Rule-only headline, 0 or 1. See below |
| `translation` | Translate `source_text` | chrF++ against `references`, 0 to 1 |
| `round_trip` | Translate `source_text` into `pivot_lang`, then, in a fresh conversation, back into `source_lang` | chrF++ of the back-translation against `source_text`, 0 to 1. The pivot text is stored |

### Tutor items

The headline is rule-only. It is 1 when the model found the error, gave an
accepted fix, and did not over-correct. A clean item scores 1 when the model
reports no error and leaves the sentence unchanged.

The explanation is a separate, secondary score. Two judges mark it, and it is
labelled judge-marked and not human-validated. No human review exists.

## Judges

A judge marks only the explanation of tutor items. Every run uses the same fixed
pair, set under `judges` in `config/models.yaml`: `deepseek/deepseek-v4.1-flash-1017`
and `qwen/qwen3.8-flash`. A fixed pair makes explanation scores comparable across
models.

When the candidate is in the family of either judge (the provider prefix, mapped
in `config/models.yaml`), no judge is called. The explanation score is null with
`explanation_status: "not_scored_same_family_as_judge"`. If a judge id is missing
from the live model list at the start of the run, the explanation score is null with
`explanation_status: "not_scored_judge_unavailable"`. In both cases the run still
completes, because the headline scores never need a judge.

An explanation passes only when both judges pass it. A failed judge call is retried
up to 3 times. If it still fails, the explanation is unscored and leaves the
explanation denominator. It is never scored 0. The results report `judge_agreement`
and `judge_failures`.

The leaderboard shows explanation scores only for runs whose judge pair equals the
pair in the current config. Other runs show a null score and a reason. If you change
the pair, older runs stop being comparable.

## Statistics

Each item is asked `--epochs` times, with the provider's default temperature, so
repeats show real variation. The item score is the mean over epochs. Per test the
results give the mean score, a 95% interval, `n_items`, `epochs`, and
`consistency` (the share of items with the same result in every epoch).

The interval resamples items with replacement: 2000 resamples, fixed seed
`20261115`, 2.5th and 97.5th percentiles. The same inputs give the same interval.
The same statistics are given by language, l1, phenomenon, CEFR level and
evidence. The overall score is the mean of per-test means, every test weighted
equally, with its own interval.

## Key and pricing

The key is `OPENROUTER_API_KEY`, or else the macOS keychain item `omp-openrouter`
(`security find-generic-password -s omp-openrouter -w`). It is held in memory and
in the process environment. It is never printed, logged, or written to disk.

At the start of each run the harness fetches `https://openrouter.ai/api/v1/models`.
If the model id is not in the list, the run stops with a clear error. The
prompt, completion and cache prices (USD per token) and the retrieval time are
recorded in the results. A model with no fixed price, such as a router, is
refused because it cannot be capped.

## Cost cap

Every call, candidate or judge, goes through one guard in `teanga_bench/cost.py`.
Before a call it reserves the worst case: the prompt bytes counted as tokens, plus
`max_tokens` at the completion price. If spend so far, plus all reserved calls in
flight, plus that worst case would pass `--max-cost`, the call is not made and
the run stops. After a call the reservation is replaced by the cost of the usage
the provider reported. `max_tokens` is set on every call: 2048 for the candidate
and 1024 for judges.

When the cap is reached, the run writes its results with
`status: "cost_cap_reached"`. Tests that did not finish are marked
`incomplete`, with only fully scored items in their statistics. Tests not yet
started are marked `incomplete` too.

Known gaps:

- The cap relies on the live per-token prices. A provider that bills more than
  the listed prices, or tiered prices for very long prompts, is not modelled.
- Output tokens are billed at the higher of the completion and reasoning price.
- The worst-case reservation means a run can stop a little before it reaches
  the cap, by up to about eight calls' worst case.
- If a provider returns no usage, the call is billed at its worst case.

Inspect's own `cost_limit` is per sample, not per run, so it is not used.

## Layout

```
config/models.yaml        Fixed judge pair and provider-to-family map
data/private/             Full item sets (git-ignored)
samples/                  Public samples, 20 items per test
scripts/build_*.py        Dataset builders
teanga_bench/             Harness
tests/                    Offline tests; tiny fixtures in tests/fixtures/
results/runs/             One results JSON and report per model
results/leaderboard.*     Leaderboard and charts/
site/                     Static research site, built by teanga-bench site
vercel.json               Serves site/ on the two research domains
docs/results-schema.md    Contract for the research pages
```

## Local development

Python 3.11+.

```bash
uv venv .venv && uv pip install -e '.[dev]'
pytest                     # offline, no key
teanga-bench validate
teanga-bench run --model mockllm/model --limit 5 --output /tmp/mock.json
```

A mock run uses two mock judges and no pricing. Without `--output`, a mock run
writes to `results/mock/`, which is git-ignored, and builds its own leaderboard
there, so it never reaches the real leaderboard.

## Research site and publishing

`teanga-bench site` writes static HTML, one stylesheet and inline SVG charts to
`site/`, which is committed. Code: `teanga_bench/site.py`, with
`site_charts.py`, `site_css.py` and `markdown_lite.py`.

```
site/suites.html                       Index of both suites (preview hosts only)
site/assets/site.css
site/<suite>/index.html                Leaderboard, per-test charts, grid, score against cost
site/<suite>/models/<model-slug>.html  One page per ranked model
site/<suite>/methodology.html          docs/methodology.md plus a table from data/build-reports/
site/<suite>/data/leaderboard.json     The suite's slice of the leaderboard
```

Only live runs with status `complete` are ranked and get a model page. The build
is deterministic: the only date on the pages is the newest run's
`generated_at`. It stops with an error if any failure example is not marked
`public: true`. Model output is escaped as text. Every link is relative, so the
pages work under `/blas/` and under a host whose root is rewritten to `/blas/`.

`vercel.json` serves `site/` with no build step. On `research.blasapp.com` every
path is rewritten to `/blas/...` and on `research.tonadaapp.com` to
`/tonada/...`. Vercel serves real files before rewrites, so `/assets/...` works
on both hosts, and `site/` has no root `index.html` on purpose: one would
shadow the host rewrites. On any other host, such as a `*.vercel.app` preview,
`/` is rewritten to `suites.html`.

`teanga-bench publish --model <id>` publishes `results/runs/<id>.json`:

1. It refuses a mock run, a run whose status is not `complete`, and a file
   outside `results/runs/`.
2. It rebuilds the leaderboard and the site.
3. It stages only `results/runs`, `results/leaderboard.json`,
   `results/leaderboard.md`, `results/charts` and `site`. If
   `git diff --cached --name-only` then shows any other path, or anything under
   `data/private/`, it unstages everything and stops.
4. It commits `Publish results: <model id>`, runs `git pull --rebase
   --autostash` from the branch's upstream, and pushes to it. It never force
   pushes. When nothing changed it says so and exits 0.
5. It prints `https://research.blasapp.com/` and
   `https://research.tonadaapp.com/`.

## Public output

Failure examples in the results JSON, the report and the leaderboard come only from
items whose id is in the public sample file of that test. Each is marked
`public: true`. Items that are only in `data/private/` never appear.

## CI

`.github/workflows/tests.yml` runs the offline tests on pull requests and on pushes
to main. There is no scheduled or live job.

## License

Apache-2.0. Copyright 2026 John Conway.
