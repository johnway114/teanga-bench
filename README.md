# Teanga Bench

Teanga Bench measures how well a large language model does the work of a
language tutor. It has two suites:

- **Blas suite**: Irish, Welsh, Scottish Gaelic, Manx, Breton and Cornish.
  Results will be published at `research.blasapp.com`.
- **Tonada suite**: English tutoring for learners whose first language is
  Portuguese, Spanish, Vietnamese or Japanese.
  Results will be published at `research.tonadaapp.com`.

The name is always "Teanga Bench".

## Run it

    uv venv .venv && uv pip install -e '.[dev]'
    teanga-bench run --model <openrouter-id> --publish

This one command:

1. reads the OpenRouter key from the environment variable
   `OPENROUTER_API_KEY`, or from the macOS keychain service `omp-openrouter`;
2. reads the live price of the model from OpenRouter;
3. runs every test three times per item, and stops if the cost reaches the cap
   (`--max-cost`, default 5 US dollars);
4. writes `results/runs/<model>.json` and a Markdown report beside it;
5. rebuilds the leaderboard and the research site in `site/`;
6. with `--publish`, commits the results and the site and pushes them. The
   hosting service then puts the new pages live.

Other commands: `teanga-bench validate` checks the dataset files,
`teanga-bench leaderboard` rebuilds the leaderboard, `teanga-bench site`
rebuilds the site, and `teanga-bench publish` publishes existing results.

## What is public and what is private

Public, in this repository: the code, the scoring rules, the dataset build
scripts, the methodology, 20 sample items for each test (`samples/`), and all
results.

Private, never in this repository: the full item sets (`data/private/`). The
benchmark runs on the full sets when they are present, and on the public
samples when they are not. Each results file says which was used.

To rebuild the full sets you need the source content on the build machine. See
`scripts/_common.py` for the paths.

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
