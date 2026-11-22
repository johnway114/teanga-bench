# Results

`runs/<model id with / as __>.json` is one **v2** run (4 core tests, 1 epoch,
low reasoning), with a Markdown report beside it. `leaderboard.json`,
`leaderboard.md` and `charts/*.svg` are the v2 board, rebuilt from `runs/` by
`teanga-bench leaderboard` and at the end of every `run`.

`v1-archive/runs/` holds the nine published **v1** runs (7 tests, 3 epochs,
provider-default reasoning). `v1-archive/leaderboard.json`, `leaderboard.md`
and `charts/` are that board. v1 and v2 are not ranked together, and publishing
a v2 run does not rewrite the archive. The Zenodo deposit
[10.5281/zenodo.24305705](https://doi.org/10.5281/zenodo.24305705) records the
v1 result set.

Mock runs go to `results/mock/`, which is git-ignored.

The field-by-field contract is `docs/results-schema.md`.
