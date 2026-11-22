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
| `--max-cost` | 5.00, or with `--resume` the earlier cap | Hard cap in USD on the run's total candidate plus judge spend, earlier attempts included |
| `--epochs` | 1 | Times each item is asked (v1 used 3; pass `--epochs 3` to measure multi-epoch consistency) |
| `--limit` | all | Items per test, for smoke runs (never ranked or published) |
| `--tests` | v2 core (4 tests) | Test names, or `suite/test`. Defaults to `default_tests` in `config/models.yaml` (`blas/morphology`, `blas/translation`, `blas/tutor_accuracy`, `tonada/tutor_accuracy`) |
| `--all-tests` | off | Run every discovered test, including retired v1 tests (`blas/lesson_exercises`, `blas/round_trip`, `tonada/exercises`) |
| `--reasoning-effort` | `low` | Reasoning effort (`minimal`, `low`, `medium`, `high`, `none`, or `default` for provider default). Falls back to a token cap (`512` for `low`) on models exposing `reasoning` without `reasoning_effort` |
| `--batch` | off | Route `openai/`, `anthropic/`, or `google/` candidates through their direct 50%-off Batch API (requires provider key and SDK via `uv pip install -e '.[batch]'`) |
| `--direct-model` | inferred | With `--batch`: override the direct provider Inspect model id |
| `--max-tokens` | 16000 (4096 in low-reasoning `--batch`) | Override candidate `max_tokens` |
| `--output` | `results/runs/<id>.json` (full) or `results/samples/<id>.json` (samples) | Where the results JSON goes |
| `--data-root` | repo root | Folder holding `data/private/` and `samples/` |
| `--log-dir` | `logs/<id with / as __>-<UTC time>/` | Inspect logs. The folder is recorded in the results as `config.log_dir` |
| `--resume` | off | Finish the incomplete run in `--output`. See [Resuming a run](#resuming-a-run) |
| `--rerun-truncated` | off | With `--resume`: also ask again every answer that stopped at a lower token limit than the current one. Works on a complete run. See [Answers cut off by the token limit](#answers-cut-off-by-the-token-limit) |
| `--publish` | off | After a complete live run, run `publish` for it. Refused up front for mock models and for `--output` outside `results/runs/`. Works with `--resume` |

`run` writes the results JSON, a Markdown report next to it (`.md`), and then
rebuilds the leaderboard. Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | Every test finished (and, with `--publish`, the publish worked) |
| 1 | Some test did not finish, the leaderboard failed, or the publish was refused or failed |
| 2 | The run could not start, or `--resume` was refused |
| 3 | The cost cap stopped the run |
| 4 | OpenRouter ran out of credit and the run stopped (`incomplete_reason: "insufficient_credit"`) |

For every run that did not finish, `run` prints the exact command that resumes
it, such as `teanga-bench run --model openai/gpt-6-luna --resume`. After the
cost cap it adds a doubled `--max-cost`; raise it as you see fit.

`teanga-bench resume-plan --model <id>` is read-only. It shows what `--resume`
would do: per test, the sample-epochs it would reuse, rescore and run, and an
estimated remaining cost. Options: `--results-dir` (folder holding `runs/`,
default `results/`), `--log-dir` (folder holding the run's log folders, or the
log folder itself, default `logs/`), `--data-root`, and `--rerun-truncated`
(plan for `run --resume --rerun-truncated`). Exit code 0 means the run can be
resumed, 1 that it cannot (complete with nothing to re-run, or a dataset
changed), 2 that the files could not be read.

`teanga-bench reexport --model <id>` rebuilds a **complete** results JSON from
the saved Inspect sample scores, without model calls, judge calls, pricing
requests, or API credentials. It uses resume's log selection and sample merge.
Options: `--results-dir`, `--log-dir`, and `--data-root` have the same meanings
as in `resume-plan`; `--output PATH` writes elsewhere instead of replacing the
original file. It does not rebuild reports, the leaderboard, or the site.

Every sample-epoch must already have a final score, and the resume dataset
check must pass. Before writing, it compares each original test's `score`,
`ci95`, `n_items`, and `cost_usd`, and every suite/run `overall` value against
the rebuilt values (absolute tolerance `1e-9`). Any mismatch prints the
differences and writes nothing. Exit codes: 0 on success, 1 on refusal or error.
Costs and the original `config`, `resumed`, `corrections`, and `truncation`
blocks stay unchanged, including their absence in older files. Run timestamps
stay unchanged; `reexported: {at, from_schema, to_schema}` records the export.
This is suitable for adding new derived breakdowns to existing results:

```bash
teanga-bench reexport --model openai/gpt-6-luna --output /tmp/luna-reexport.json
```

`teanga-bench leaderboard` reads every `results/runs/*.json` and writes the v2
`results/leaderboard.json`, `results/leaderboard.md`, and SVG charts in
`results/charts/`. When `results/v1-archive/runs/` is present it also rebuilds
that board beside the archive. `run` rebuilds the v2 board only. A directory
that contains both protocols writes two boards, and one version's charts do
not replace the other's.

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
evidence. Each test also crosses phenomenon with language (Blas) or learner L1
(Tonada), omitting cells with fewer than five fully scored items. Older files
may lack this cross-breakdown. The overall score is the mean of per-test means,
every test weighted equally, with its own interval.

## Key and pricing

The OpenRouter key is `OPENROUTER_API_KEY` (required on Linux and CI), or on
macOS only the keychain item `omp-openrouter`
(`security find-generic-password -s omp-openrouter -w`). Direct `--batch` runs
additionally require `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or
`GOOGLE_API_KEY`/`GEMINI_API_KEY` and the matching SDK (`uv pip install -e '.[batch]'`).
Keys are held in memory and in the process environment only, and are never
printed, logged, or written to disk.

At the start of each run the harness fetches `https://openrouter.ai/api/v1/models`.
If the model id is not in the list, the run stops with a clear error. The
prompt, completion and cache prices (USD per token) and the retrieval time are
recorded in the results. Under `--batch`, candidate list prices are scaled by
`0.5` (`pricing.batch_discount: 0.5`). A model with no fixed price, such as a
router, is refused because it cannot be capped.

## Cost cap

Every call, candidate or judge, goes through one guard in `teanga_bench/cost.py`.
Before a call it reserves the worst case: the prompt bytes counted as tokens, plus
`max_tokens` at the completion price. If spend so far, plus all reserved calls in
flight, plus that worst case would pass `--max-cost`, the call waits until a call
in flight settles, then checks again. When no call is in flight and the worst
case still does not fit, the call is not made and the run stops. After a call
the reservation is replaced by the cost of the usage the provider reported.
`max_tokens` is set on every call: 16000 for the candidate and 1024 for judges.

The wait matters because the candidate limit is large. For the most expensive
model so far (completion $50 per million tokens), one call's worst case is
about $0.80, so eight calls in flight would reserve $6.40, more than the
default $5 cap. Without the wait, the run would stop after six calls. With it,
fewer calls run at once as the cap gets close, and the run stops at most one
worst case short of the cap. A smaller, guessed reservation was not used: it
would let spend pass the cap when several long answers arrive together.

When the cap is reached, the run writes its results with
`status: "cost_cap_reached"`. Tests that did not finish are marked
`incomplete`, with only fully scored items in their statistics. Tests not yet
started are marked `incomplete` too. In a resumed run the cap covers the spend
of the earlier attempts as well, so `cost.total_usd` never passes it.

Known gaps:

- The cap relies on the live per-token prices. A provider that bills more than
  the listed prices, or tiered prices for very long prompts, is not modelled.
- Output tokens are billed at the higher of the completion and reasoning price.
- The worst-case reservation means a run can stop a little before it reaches
  the cap, by up to one call's worst case. Near the cap, calls run one at a time.
- If a provider returns no usage, the call is billed at its worst case.

Inspect's own `cost_limit` is per sample, not per run, so it is not used.

Spend is booked per `suite/test`. Results files without `config.dataset_hashes`
(written before resume support) booked it per bare test name, so their
`tonada/tutor_accuracy` cost also counted the spend of `blas/tutor_accuracy`.
`cost.total_usd` and `cost.by_model` were always right. A resume undoes the
double count when it carries those per-test costs forward, but only when the
per-test costs add up to more than the total. The `openai/gpt-6-luna` file was
corrected by hand, so its costs are carried as they are. A resume keeps the
file's `corrections` notes.

## Out of credit and rate limits

A 402 from OpenRouter (not enough credit, including "would exceed your
available credits given your current in-flight requests") and a 429 (rate
limit) do not fail the sample. The cost guard holds one backoff for the whole
run: the first refusal starts a pause, calls refused while it lasts do not
lengthen it, and every new call waits for it to end, so the run pauses instead
of hammering the provider. Pauses start at 15 s and double up to 2 minutes; a
successful call resets the next pause to 15 s. The pauses of one run add up to
at most 20 minutes. A refusal after that stops the run cleanly: no further
request is sent, unfinished and unstarted tests are marked `incomplete` with
`incomplete_reason: "insufficient_credit"`, the run gets `status:
"incomplete"` and top-level `incomplete_reason: "insufficient_credit"`, and
`run` prints that you should add credit and finish with `--resume` (exit code 4).

Retries happen in one layer per failure kind, so they do not multiply. Inspect
retries transient errors (5xx, timeouts) and 429 inside each call, up to
`max_retries` (3) in the call config; it never retries 402. The guard handles
402, and a 429 that Inspect gave up on. Inspect's sample-level `retry_on_error`
is set to 0, because rerunning a whole sample would repeat calls that already
succeeded. A judge refused for credit is not counted as a judge failure: the
sample stops with an error, keeps its candidate output, and is judged on resume.

## Answers cut off by the token limit

A model that reasons before it answers spends output tokens on hidden
reasoning. If it reaches `max_tokens` first, the reply stops there and is often
empty. That answer is scored by the normal rules, so an empty answer scores 0.
The solver records in each sample's store whether any candidate call stopped
at the limit (`stop_reason` `max_tokens`, or `length` from some providers) and
the limit used. Results count these per test as `n_truncated_item_epochs`, and
in total in the top-level `truncation` block.

The first runs used a 2048-token limit. The limit is now 16000. To ask the cut
off answers again under the new limit:

```bash
teanga-bench resume-plan --model qwen/qwen3.8-flash --rerun-truncated   # read-only
teanga-bench run --model qwen/qwen3.8-flash --resume --rerun-truncated [--max-cost 10]
```

`--rerun-truncated` treats every sample-epoch whose candidate call stopped at a
lower limit than the current one as missing. It runs exactly those again,
scores them again (tutor items are judged again), and keeps everything else.
Other epochs of the same items are restored, not asked. Logs written before the
solver recorded truncation are read from the candidate's model events, which
carry the stop reason and the limit. Spend is carried forward as in any resume.
The `resumed` block records `truncation_rerun` (`old_limit`, `new_limit`,
`n_rerun`), and each attempt records its `candidate_max_tokens`.
`config.max_tokens.candidate` is the current limit, so a run with a
`truncation_rerun` block mixes answers given under two limits: those that did
not reach the old limit, and the rest under the new one.

Without the flag, a complete run is refused as before. With the flag and
nothing to re-run, `run` refuses too. `resume-plan --rerun-truncated` shows the
count per test in a `trunc.` column. Its estimate assumes a re-run sample-epoch
costs 3 times the average completed sample-epoch of that test, because these
are the long answers; it says so in its output.

Known gaps: results files written before truncation was recorded have no
`truncation` block, so their leaderboard `truncated_share` is null until they
are resumed with `--rerun-truncated`. A run with nothing to re-run is refused,
so it keeps a null share. In old logs, a sample-epoch an older resume restored
without calling the model takes its truncation from the attempt it came from;
if that log is missing, only the final reply's stop reason is read, which can
miss a cut-off first call of a round trip.

## Resuming a run

```bash
teanga-bench resume-plan --model anthropic/claude-haiku-5.5   # read-only
teanga-bench run --model anthropic/claude-haiku-5.5 --resume [--max-cost 10] [--publish]
```

`--resume` reads the results file (`--output`, or the default path) and the
Inspect logs of every earlier attempt: the folders recorded in `config.log_dir`
and `resumed.attempts[].log_dir`, or, for results written before folders were
recorded, the `logs/<id with / as __>-<UTC time>/` folders whose time falls
inside the run. Only logs of the same model and tests created during the run
are read. Each sample-epoch of the current dataset is then:

- reused, when an earlier attempt scored it, and for tutor items the judges
  gave their verdicts. Nothing is called again. A judge that failed for a
  reason other than credit (an unusable reply after 3 retries) is final, as in
  a normal run;
- rescored, when the candidate output is complete but the scoring is not: a
  judge was refused for credit, or the scorer stopped. The saved candidate
  output is reused and the item is judged again;
- run, otherwise.

Only items with a sample-epoch to rescore or run go to Inspect, selected by
sample id. Their other epochs are restored from the saved output and score,
not asked again. The new results are built from the merged samples, so the
file has the same schema and the same statistics as an uninterrupted run with
the same outputs, plus a `resumed` block. Inspect's `eval_retry` is not used:
it rebuilds tasks from Inspect's registry, which these data-driven tasks are
not in, it would keep a sample whose judge was refused for credit, and it
knows nothing of the spend already made.

A resume keeps the first attempt's `--epochs`, `--limit`, `--tests` and judge
pair, and refuses if you pass different ones. It refuses when a dataset file
changed since the first attempt: results record a sha256 of each dataset file
in `config.dataset_hashes`. Results written before the hash existed are checked
by item ids (from the first attempt's logs) and item counts instead, and the
resume records `dataset_check: "item_ids_and_count"`. Prices are read live
again. The spend of the earlier attempts is carried forward from the results
file, so `cost.total_usd` is the true total and `--max-cost` (default: the
earlier cap) caps that total. A complete run cannot be resumed, except with
`--rerun-truncated`.

Known gaps: a run killed before it writes its results (Ctrl-C, a crash) leaves
no results file, so it cannot be resumed. A resumed run is ranked like any
other complete run, even though its sample-epochs were asked at different
times. `resume-plan` estimates cost from the tokens of the completed
sample-epochs of each test; with fewer than 10 in a test it uses the average
over the whole run, which can be far off for tests with long outputs.

## Running several models

Run models one or two at a time unless the account has credit for all of them
at once. Parallel runs share one OpenRouter balance, and OpenRouter refuses a
request that would exceed the credit left after the requests already in flight,
so many parallel runs are refused for credit together. The 402 pause holds a
run for at most 20 minutes; after that it stops with `insufficient_credit` and
must be resumed.

## Layout

```
config/models.yaml        Fixed judge pair and provider-to-family map
data/private/             Full item sets (git-ignored)
samples/                  Public samples, 20 items per test
scripts/build_*.py        Dataset builders
teanga_bench/             Harness
tests/                    Offline tests; tiny fixtures in tests/fixtures/
results/runs/             One v2 results JSON and report per model
results/leaderboard.*     v2 leaderboard and charts/
results/v1-archive/       Nine archived v1 runs, plus that board and its charts
site/                     Static research site, built by teanga-bench site
vercel.json               Serves site/ on the two research domains
docs/results-schema.md    Contract for the research pages
docs/operating-policy.md  Release cadence, v2 cost decision, and v1-to-v2 cutover
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
`site_charts.py`, `site_css.py`, `site_findings.py` (the computed takeaway
sentence that opens every chart) and `markdown_lite.py`.

```
site/suites.html                       Index of both suites (preview hosts only)
site/assets/site.css
site/<suite>/index.html                Leaderboard, model x test table, cards that link onward
site/<suite>/tests.html                Every test, one tab each: the task, a public sample item, marking, results
site/<suite>/findings.html             Ties, CEFR levels, topics, directions, tutor steps, evidence, cost, consistency
site/<suite>/languages.html            Blas: scores by language
site/<suite>/learners.html             Tonada: scores by the learner's first language
site/<suite>/models.html               Every ranked model as a card, score against cost
site/<suite>/models/<model-slug>.html  One page per ranked v2 model, or a redirect to the v1 archive when that model has no v2 run
site/<suite>/methodology.html          docs/methodology.md plus a table from data/build-reports/
site/<suite>/data/leaderboard.json     The suite's slice of the v2 leaderboard
site/<suite>/v1/                       v1 (archived) leaderboard, model pages, charts and data JSON
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
   `results/leaderboard.md`, `results/charts`, `results/v1-archive`, `site`
   and `vercel.json` (the legacy model-page redirects). It rebuilds the v2
   leaderboard from `results/runs` and does not modify archived run files.
   If `git diff --cached --name-only` then shows any other path, or anything
   under `data/private/`, it unstages everything and stops.
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
