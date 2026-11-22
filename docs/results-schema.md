# Teanga Bench results JSON

Version `2.2.0`. One file per v2 run, written by `teanga-bench run` to
`results/runs/<model id with / as __>.json`. The nine v1 runs live in
`results/v1-archive/runs/`. `teanga-bench leaderboard` reads `results/runs/`
and writes the v2 board to `results/leaderboard.json`. The v1 board is
`results/v1-archive/leaderboard.json`.

The benchmark name is **Teanga Bench** (`benchmark: "teanga-bench"`). Suite keys
are `blas` and `tonada` because those sites read the file.

UTF-8 JSON. Unknown fields may be added in `2.x` and must be ignored. A new major
version is a breaking change. Version 2 replaces version 1: there is one model per
file, and scores carry intervals.

Do not present a run as a model score when `run_kind` is `"mock"`, or rank it
when `status` is not `"complete"`.

## Top level

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | string | `"2.2.0"`. `2.2.0` adds language/L1-by-phenomenon cells and optional `reexported` provenance. `2.1.0` added truncation fields; older files are `"2.0.0"` |
| `methodology` | string | `"v1"` or `"v2"`. The evaluation protocol, not a schema version. New runs write `"v2"`. The nine archived runs are stamped `"v1"`. Absent on older files: readers treat a file as v1 only when it has the historical shape (7 tests, including `blas/lesson_exercises`, `blas/round_trip` and `tonada/exercises`, `epochs` 3, and no `reasoning_effort`). Anything else without the field is v2. v1 and v2 scores are not comparable and are not ranked on one board |
| `benchmark`, `benchmark_name`, `benchmark_version` | string | Name and the package version that wrote the file |
| `started_at`, `generated_at` | string | UTC ISO-8601 |
| `run_kind` | string | `"live"`, `"mock"`, or `"smoke"` (a run with `--limit`, never ranked or published) |
| `status` | string | `"complete"`, `"cost_cap_reached"`, or `"incomplete"` (some test did not finish) |
| `incomplete_reason` | string or null | Null when complete. Else `"cost_cap_reached"`, `"insufficient_credit"` (OpenRouter kept refusing calls with 402 or 429 through the run's 20-minute backoff budget), or `"errors"`. Absent in files written before it existed |
| `model` | object | The candidate. See below |
| `config` | object | Run settings. See below |
| `judges` | array of 2 strings | The fixed judge pair, always recorded, even when no judge was called |
| `explanation_status` | string | `"scored"`, `"not_scored_same_family_as_judge"`, or `"not_scored_judge_unavailable"` |
| `judge_info` | object | Judge details. See below |
| `gold.note` | string | Warning that gold is sourced, not native-speaker reviewed |
| `cost` | object | Spend. See below |
| `overall` | object or null | Score over completed tests. See below. Null when no test completed |
| `truncation` | object | Answers cut off by the token limit. See below. Absent before `2.1.0` |
| `suites` | object | Map of suite name to `{overall, tests}` |
| `tool_versions.inspect_ai` | string | Inspect version |
| `resumed` | object | Only in a run finished with `--resume`. See below |
| `corrections` | array of strings | Only in a file edited by hand after it was written: one note per edit. A resume keeps it |
| `reexported` | object | Only after offline `reexport`: `at` (UTC ISO-8601), `from_schema`, `to_schema`. Records the latest export, not a model attempt; original run timestamps and protected blocks remain unchanged |

### `model`

| Field | Meaning |
| --- | --- |
| `id` | OpenRouter id, such as `openai/gpt-6-luna` |
| `family` | Family from the provider prefix, via `config/models.yaml` |
| `inspect_id` | Inspect model string |
| `pricing` | Null for mock runs. Else `prompt_usd_per_token`, `completion_usd_per_token`, `cache_read_usd_per_token`, `cache_write_usd_per_token` (null when not listed), `source` (the models URL), and `retrieved_at` |

The completion price is the higher of the completion price and the reasoning
price, so the cap errs towards stopping early.

### `config`

`epochs`, `limit`, `max_cost_usd`, `max_tokens` (`candidate`, `judge`),
`reasoning_effort` (`"minimal"`, `"low"`, `"medium"`, `"high"`, `"none"`,
`"default"`, `"tokens:<N>"`, or `"unsupported"`), `batch` (boolean),
`temperature` (`"provider default"`), `bootstrap` (`seed`, `resamples`,
`confidence`), `tests` (names run), `pricing_source`, `dataset_hashes` (map of
`suite/test` to `"sha256:<hex>"` of the dataset file, so a resume can refuse a
changed dataset), and `log_dir` (the first attempt's Inspect log folder,
relative to the repo when inside it). Files written before resume support have
neither `dataset_hashes` nor `log_dir`, and v1 files omit `reasoning_effort`
and `batch`.

### `judge_info`

| Field | Meaning |
| --- | --- |
| `called` | True when judges were called in this run |
| `families` | Judge id to family |
| `pricing` | Judge id to prices and `retrieved_at`. Empty when no judge was called |
| `rule` | Plain-language rule for the pair |
| `retries_per_call` | Retries for a failed judge call (3) |

### `cost`

| Field | Meaning |
| --- | --- |
| `cap_usd` | The `--max-cost` value |
| `total_usd` | Candidate plus judge spend, from live prices times reported tokens. In a resumed run, the total over every attempt |
| `candidate_usd`, `judge_usd` | The two parts |
| `cap_reached` | True when the cap stopped the run |
| `by_model` | Per model id: `calls`, token counts (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`), `cost_usd` |

### `overall`

`score` (0 to 1), `ci95` (`[low, high]`), `n_tests`, `n_items`, and `by_language`:
a map from language to the same four fields. Each completed test is weighted
equally. The interval resamples items inside each test. Incomplete tests are left out.

### `truncation`

A scored item-epoch is truncated when any candidate call for it stopped at the
answer limit (`stop_reason` `max_tokens`, or `length`). Reasoning models can
spend the whole limit on hidden reasoning and return an empty answer. A
truncated answer is scored by the normal rules, so an empty answer scores 0.

| Field | Meaning |
| --- | --- |
| `max_tokens` | The current candidate limit, equal to `config.max_tokens.candidate` |
| `n_item_epochs` | Scored item-epochs over all tests |
| `n_truncated_item_epochs` | Of those, the truncated ones. In a run with `resumed.truncation_rerun`, answers kept from before the re-run did not reach the old limit |
| `rule` | The definition above, in one sentence |

### `resumed`

Present only when the run was finished with `teanga-bench run --resume`. The
rest of the file has the same fields and meaning as for a run that was never
interrupted. `started_at` is the first attempt's start.

| Field | Meaning |
| --- | --- |
| `count` | Number of resumes |
| `attempts` | One object per attempt, the first attempt first |
| `attempts[].started_at`, `generated_at` | When the attempt started and wrote its results |
| `attempts[].status`, `incomplete_reason` | The run's status after that attempt |
| `attempts[].cost_usd` | Spend in that attempt |
| `attempts[].log_dir` | That attempt's Inspect log folder |
| `attempts[].prices_retrieved_at` | When that attempt read live prices (null for mock runs) |
| `attempts[].candidate_max_tokens` | The candidate answer limit of that attempt. Attempts written before it was recorded used 2048 and get that value on the next resume |
| `attempts[].dataset_check` | Resumes only: `"dataset_hash"`, or `"item_ids_and_count"` when the first attempt predates `dataset_hashes` |
| `attempts[].sample_epochs` | Resumes only: `reused` (scored earlier, not called again), `rescored` (candidate output reused, judges or scorer run again), `run` (asked again), and `rerun_truncated` (the part of `run` asked again because the answer stopped at a lower token limit, with `--rerun-truncated`) |
| `attempts[].tests` | Resumes only: the same four counts per `suite/test` |
| `attempts[].truncation_rerun` | Only on an attempt run with `--rerun-truncated` that re-ran something: `old_limit`, `new_limit`, `n_rerun` for that attempt |
| `truncation_rerun` | Present once any attempt re-ran truncated answers: `old_limit` (the limit those answers were first given under; the lowest if they differ), `new_limit` (the limit they were asked again under), and `n_rerun` (item-epochs asked again, over all attempts). Such a run mixes two limits: `config.max_tokens.candidate` is the new one |

## Statistics

An item's score is its mean over epochs. A 95% interval is the 2.5th and 97.5th
percentiles of 2000 item resamples with seed `20261115`. Scores are 0 to 1.
Wherever a block has `score` it also has `ci95`, `n_items`, `epochs`, and
`consistency`. `consistency` is the share of items whose score is the same in
every epoch (compared at 4 decimals). It is null when `epochs` is 1.

## `suites.<suite>.tests.<test>`

| Field | Meaning |
| --- | --- |
| `suite`, `test`, `scoring` | Names, and the scorer kind: `accept_list`, `tutor`, `translation`, or `round_trip` |
| `dataset` | `"full"` or `"public_sample"` |
| `status` | `"complete"` or `"incomplete"` |
| `incomplete_reason` | Null, `"cost_cap_reached"`, `"insufficient_credit"`, `"errors"`, `"missing_samples"`, or `"eval_<status>: ..."` |
| `n_items_dataset` | Items asked for (after `--limit`) |
| `n_truncated_item_epochs` | Scored item-epochs where a candidate call stopped at the answer limit. See `truncation`. Absent before `2.1.0` |
| `n_items` | Items with a score in every epoch. Only these are in the statistics |
| `n_errors` | Item-epochs that errored |
| `score`, `ci95`, `epochs`, `consistency` | As above |
| `cost_usd` | Candidate plus judge spend on this test |
| `cost_per_correct_usd` | `cost_usd / (score * n_items * epochs)`, the cost of one full-score answer. Null when the score is 0 |
| `cost` | `candidate` and `judge` usage objects |
| `n_human_checked` | Scored items whose metadata says `human_checked: true` |
| `by_language`, `by_l1`, `by_phenomenon`, `by_cefr`, `by_evidence` | Map of value to the statistics above. A missing value is `"unspecified"` |
| `by_language_phenomenon` | Blas tests: language -> phenomenon -> statistics (`score`, `ci95`, `n_items`, `epochs`, `consistency`). Only cells with at least 5 fully scored items. Empty languages are omitted |
| `by_l1_phenomenon` | Tonada tests: the same cross-breakdown, with learner first language (`l1`) as the outer key instead of language |
| `tutor` | Only for tutor tests. See below |
| `failure_examples` | Up to 3 lowest-scoring public items |

A test that did not start has `status: "incomplete"`, `incomplete_reason`,
`n_items_dataset`, and null scores.

The cross-breakdowns are optional in older files; readers must not assume they
exist. New exports include the appropriate field on every test, with `{}` when
no cell qualifies (including unstarted tests). Missing metadata uses
`"unspecified"`, as in the one-dimensional breakdowns. The five-item threshold
counts items, not item-epochs. Cell intervals use the same fixed bootstrap
settings, with a stream keyed by test, language/L1, and phenomenon.

### `tutor`

| Field | Meaning |
| --- | --- |
| `headline` | Plain-language definition: rule-only, found and fixed and no over-correction |
| `components` | Mean of `found`, `fixed`, `no_overcorrection` |
| `judges` | The judge pair, as in the top-level `judges` |
| `explanation.label` | `"judge-marked, not human-validated"` |
| `explanation.status` | Same values as the top-level `explanation_status` |
| `explanation.score`, `ci95`, `n_items`, `epochs` | Secondary score. Counts only item-epochs the judges scored. Null when `status` is not `"scored"` |
| `explanation.judged_item_epochs` | Item-epochs where both judges gave a verdict |
| `explanation.unscored_item_epochs` | Item-epochs where a judge failed. Excluded from the score |
| `explanation.judge_agreement` | Share of judged item-epochs where both judges agree. Null when none |
| `explanation.judge_failures` | Judge calls that still failed after 3 retries |

The test `score` is the headline and does not use the judges.

### `failure_examples[]`

Only items whose id is in the public `samples/` file for that test appear here.

| Field | Meaning |
| --- | --- |
| `id`, `public` | Item id, and `true` |
| `language`, `l1`, `phenomenon` | From the item |
| `input`, `expected`, `output` | Prompt, first gold answer or reference, and the model's reply, each clipped to 500 characters |
| `score` | Score of the worst epoch |
| `pivot_text` | Round-trip items only |

## Leaderboard file

There are two boards. `results/leaderboard.json` is the **v2** board, built only
from `results/runs/*.json`. `results/v1-archive/leaderboard.json` is the **v1
(archived)** board, built only from `results/v1-archive/runs/*.json`. Neither
file ranks the other protocol. When `methodology` is present it is `"v1"` or
`"v2"`, and `note` says the two are not comparable.

Each board has `schema_version`, `generated_at`, `note`,
`current_judges` (the pair in the current config), `skipped` (files not read), and
`models`. Each entry has `model`, `family`, `run_file`, `run_kind`, `status`,
`ranked`, `rank`, `generated_at`, `data` (`full`, `public_sample`, or `mixed`),
`epochs`, `methodology`, `overall`, `cost_usd`, `suites`, `languages`, `tests`, `judges` (the pair
the run used), `explanation_status`, `explanation`, `truncated_share`, and
`truncation_rerun`.

`truncated_share` is `truncation.n_truncated_item_epochs / truncation.n_item_epochs`
of the run, or null for files without a `truncation` block. `truncation_rerun`
copies `resumed.truncation_rerun`, or is null when the run was never re-run for
truncation.

`explanation` maps each tutor test to `score`, `ci95`, `comparable`, `reason`, and
`judges`. `comparable` is true only when the run was scored and its judge pair equals
`current_judges`. Otherwise `score` and `ci95` are null and `reason` is
`"judge_pair_differs_from_current_config"`, `"not_scored_same_family_as_judge"`,
`"not_scored_judge_unavailable"`, or `"no_judged_items"`.

Only runs with status `complete` are ranked. Mock runs and smoke runs are skipped. The Markdown and
the `explanation.svg` chart show explanation scores only for comparable runs.

## What the sites should show

For each model: overall score with its interval, then each test with score,
interval, `n_items` and cost. Show the tutor explanation only as a secondary,
judge-marked number, and only where `comparable` is true. Say when `data` is `public_sample`. Skip runs whose
`run_kind` is not `"live"` and whose `status` is not `"complete"`.
