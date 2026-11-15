# Teanga Bench results JSON

Version `2.0.0`. One file per run, written by `teanga-bench run` to
`results/runs/<model id with / as __>.json`. `teanga-bench leaderboard` reads
these files and writes `results/leaderboard.json`.

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
| `schema_version` | string | `"2.0.0"` |
| `benchmark`, `benchmark_name`, `benchmark_version` | string | Name and the package version that wrote the file |
| `started_at`, `generated_at` | string | UTC ISO-8601 |
| `run_kind` | string | `"live"` or `"mock"` |
| `status` | string | `"complete"`, `"cost_cap_reached"`, or `"incomplete"` (some test hit errors) |
| `model` | object | The candidate. See below |
| `config` | object | Run settings. See below |
| `judges` | array of 2 strings | The fixed judge pair, always recorded, even when no judge was called |
| `explanation_status` | string | `"scored"`, `"not_scored_same_family_as_judge"`, or `"not_scored_judge_unavailable"` |
| `judge_info` | object | Judge details. See below |
| `gold.note` | string | Warning that gold is sourced, not native-speaker reviewed |
| `cost` | object | Spend. See below |
| `overall` | object or null | Score over completed tests. See below. Null when no test completed |
| `suites` | object | Map of suite name to `{overall, tests}` |
| `tool_versions.inspect_ai` | string | Inspect version |

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
`temperature` (`"provider default"`), `bootstrap` (`seed`, `resamples`,
`confidence`), `tests` (names run), `pricing_source`.

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
| `total_usd` | Candidate plus judge spend, from live prices times reported tokens |
| `candidate_usd`, `judge_usd` | The two parts |
| `cap_reached` | True when the cap stopped the run |
| `by_model` | Per model id: `calls`, token counts (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`), `cost_usd` |

### `overall`

`score` (0 to 1), `ci95` (`[low, high]`), `n_tests`, `n_items`, and `by_language`:
a map from language to the same four fields. Each completed test is weighted
equally. The interval resamples items inside each test. Incomplete tests are left out.

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
| `incomplete_reason` | Null, `"cost_cap_reached"`, `"errors"`, `"missing_samples"`, or `"eval_<status>: ..."` |
| `n_items_dataset` | Items asked for (after `--limit`) |
| `n_items` | Items with a score in every epoch. Only these are in the statistics |
| `n_errors` | Item-epochs that errored |
| `score`, `ci95`, `epochs`, `consistency` | As above |
| `cost_usd` | Candidate plus judge spend on this test |
| `cost_per_correct_usd` | `cost_usd / (score * n_items * epochs)`, the cost of one full-score answer. Null when the score is 0 |
| `cost` | `candidate` and `judge` usage objects |
| `n_human_checked` | Scored items whose metadata says `human_checked: true` |
| `by_language`, `by_l1`, `by_phenomenon`, `by_cefr`, `by_evidence` | Map of value to the statistics above. A missing value is `"unspecified"` |
| `tutor` | Only for tutor tests. See below |
| `failure_examples` | Up to 3 lowest-scoring public items |

A test that did not start has `status: "incomplete"`, `incomplete_reason`,
`n_items_dataset`, and null scores.

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

`results/leaderboard.json` has `schema_version`, `generated_at`, `note`,
`current_judges` (the pair in the current config), `skipped` (files not read), and
`models`. Each entry has `model`, `family`, `run_file`, `run_kind`, `status`,
`ranked`, `rank`, `generated_at`, `data` (`full`, `public_sample`, or `mixed`),
`epochs`, `overall`, `cost_usd`, `suites`, `languages`, `tests`, `judges` (the pair
the run used), `explanation_status`, and `explanation`.

`explanation` maps each tutor test to `score`, `ci95`, `comparable`, `reason`, and
`judges`. `comparable` is true only when the run was scored and its judge pair equals
`current_judges`. Otherwise `score` and `ci95` are null and `reason` is
`"judge_pair_differs_from_current_config"`, `"not_scored_same_family_as_judge"`,
`"not_scored_judge_unavailable"`, or `"no_judged_items"`.

Only runs with status `complete` are ranked. Mock runs are skipped. The Markdown and
the `explanation.svg` chart show explanation scores only for comparable runs.

## What the sites should show

For each model: overall score with its interval, then each test with score,
interval, `n_items` and cost. Show the tutor explanation only as a secondary,
judge-marked number, and only where `comparable` is true. Say when `data` is `public_sample`. Skip runs whose
`run_kind` is not `"live"` and whose `status` is not `"complete"`.
