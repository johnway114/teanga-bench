# Teanga Bench

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24305705.svg)](https://doi.org/10.5281/zenodo.24305705)

Teanga Bench measures how well a large language model does the work of a
language tutor. It has two suites:

- **Blas suite**: Irish, Welsh, Scottish Gaelic, Manx, Breton and Cornish.
  Published at [research.blasapp.com](https://research.blasapp.com).
- **Tonada suite**: English tutoring for learners whose first language is
  Portuguese, Spanish, Vietnamese or Japanese.
  Published at [research.tonadaapp.com](https://research.tonadaapp.com).

Public samples and run files are also mirrored on Hugging Face at
[datasets/johnconway114/teanga-bench](https://huggingface.co/datasets/johnconway114/teanga-bench)
and [spaces/johnconway114/teanga-bench-leaderboard](https://huggingface.co/spaces/johnconway114/teanga-bench-leaderboard).
The name is always "Teanga Bench".

## Run it

    uv venv .venv && uv pip install -e '.[dev]'
    teanga-bench run --model <openrouter-id> --publish

This one command:

1. reads the OpenRouter key from the environment variable
   `OPENROUTER_API_KEY` (required on Linux and CI), or on macOS falls back to
   the keychain service `omp-openrouter`;
2. reads the live price and supported parameters of the model from OpenRouter;
3. runs the v2 core suite (4 high-signal tests: `blas/morphology`,
   `blas/translation`, `blas/tutor_accuracy`, `tonada/tutor_accuracy`), 1 epoch
   per item, with `--reasoning-effort low` (or a 512-token reasoning cap where
   `reasoning_effort` is unavailable), stopping if spend reaches `--max-cost`
   (default 5 US dollars). Pass `--all-tests` to include retired v1 tests
   (`blas/lesson_exercises`, `blas/round_trip`, `tonada/exercises`), or
   `--batch` to route `openai/`, `anthropic/`, or `google/` models through their
   50%-off direct Batch API (`uv pip install -e '.[batch]'`);
4. writes `results/runs/<model>.json` and a Markdown report beside it for full
   sets, or `results/samples/<model>.json` when `data/private/` is missing;
5. rebuilds the leaderboard and the research site in `site/`;
6. with `--publish`, commits the results and the site and pushes them. The
   hosting service then puts the new pages live. `--publish` refuses mock,
   smoke (`--limit`), and `public_sample` runs.

**Checkout without `data/private/`:** A fresh clone only has the 20-item files
in `samples/`. Running `teanga-bench run` without `data/private/` scores those
20-item samples, writes to `results/samples/`, and is never ranked on or
comparable with the published full-set leaderboard.

Other commands: `teanga-bench validate` checks the dataset files,
`teanga-bench leaderboard` rebuilds the leaderboard, `teanga-bench site`
rebuilds the site, and `teanga-bench publish` publishes existing results.

## What is public and what is private

Public, in this repository: the code, the scoring rules, the dataset build
scripts, the methodology, 20 sample items for each test (`samples/`), and all
results. Because `samples/` is public (including sample excerpts tagged
`private-blas` and `private-tonada`), those 20-item files are exposed to model
training data.

Private, never in this repository: the full item sets (`data/private/`). The
benchmark runs on the full sets when they are present, and falls back to
`samples/` (written to `results/samples/`, never ranked or published) when they
are not. Each results file says which was used.

To rebuild the full sets you need the source content on the build machine. See
`scripts/_common.py` for the paths.

## Licences

The harness code, build scripts, and documentation are licensed under
Apache-2.0 (`LICENSE`). Sample text under `samples/` is **not** covered by
Apache-2.0: every item keeps the licence recorded in its `metadata.licence`
field and adjacent `*.ATTRIBUTION.md` file (see [`samples/LICENCE.md`](samples/LICENCE.md)),
including **GPL-3.0** for Gaelg Manx sentences.

## Documents

- [Methodology](docs/methodology.md): sources, marking rules and known limits.
- [Harness guide](docs/HARNESS.md): how a run works, the cost cap, the judges.
- [Results schema](docs/results-schema.md): the format of the results files.

## Tests

| Suite | Test | What the model does | How it is marked |
|---|---|---|---|
| Blas | `morphology` | Gives one grammatical form | Accepted-answer list |
| Blas | `lesson_exercises` | Answers an app exercise | Accepted-answer list |
| Blas | `translation` | Translates a sentence | chrF++ against a reference |
| Blas | `round_trip` | Translates out and back | chrF++ against the original |
| Blas | `tutor_accuracy` | Finds and fixes a learner error | Rules, plus two judges for the explanation |
| Tonada | `exercises` | Answers an English exercise set in the learner's language | Accepted-answer list |
| Tonada | `tutor_accuracy` | Finds and fixes a learner error | Rules, plus two judges for the explanation |

No person reviewed the items. Read the methodology before you cite a score.
