# Results

`runs/<model id with / as __>.json` is one benchmark run, with a Markdown report
beside it. `leaderboard.json`, `leaderboard.md` and `charts/*.svg` are rebuilt
from `runs/` by `teanga-bench leaderboard` and at the end of every `run`.

Mock runs go to `results/mock/`, which is git-ignored.

The field-by-field contract is `docs/results-schema.md`.
