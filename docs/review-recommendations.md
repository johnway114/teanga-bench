# Review recommendations

This note records an outside review of Teanga Bench as it stands on `main`.
Each point was checked against the files in this repository. Where a claim
did not match those files, the text below says what the files show.

The published scores below come from the nine complete runs in
`results/runs/`. Item counts come from `data/build-reports/`.

## 1. Full item sets are missing from a normal checkout

**Found.** The full item sets are written to `data/private/`, and that
directory is git-ignored. This checkout has no `data/private/`. The build
scripts look for the source trees under the home directory:
`~/Documents/blas`, `~/Documents/blas-english`, and
`~/Documents/language-data` (`scripts/_common.py`). The repository does not
name which machine holds those trees.

When a private file is missing, `teanga_bench/datasets.py` loads
`samples/<suite>/<test>.jsonl` and marks the run `public_sample`. Each public
file has 20 items. `docs/HARNESS.md` says a sample run is not comparable with
a full-set run.

CI does not run the benchmark. `.github/workflows/tests.yml` runs `pytest`
only. A benchmark command on that runner, or on any other machine without
`data/private/`, would score the 20-item samples. The nine published results
files are marked `dataset: "full"`, so they were produced where the private
files were present. `results/leaderboard.md` warns that sample runs and
full-set runs are not comparable.

**Why it matters.** A fresh clone cannot reproduce the published scores. A
sample run can still be written beside the full-set leaderboard and be read
as the same benchmark.

**Files.** `.gitignore`, `teanga_bench/datasets.py`, `scripts/_common.py`,
`docs/HARNESS.md`, `docs/methodology.md`, `README.md`,
`.github/workflows/tests.yml`, `results/leaderboard.md`, `results/runs/*.json`.

**Suggested fix.** Say, next to the run command in the README, that a
checkout without `data/private/` scores 20 items per test and must not be
compared with the published leaderboard. Keep sample runs out of
`results/runs/`, or make the leaderboard refuse them. Keep a second copy of
the private sets, and document the source paths for a machine that is not the
one that built them.

## 2. Linux has to set the API key itself

**Found.** `teanga_bench/apikey.py` reads `OPENROUTER_API_KEY` first. If that
is empty it runs `security find-generic-password -s omp-openrouter -w`, the
macOS keychain. If `security` is missing, the error is caught and the run
stops. The README and `docs/HARNESS.md` already name both paths.
`.env.example` leads with the keychain and does not say that Linux has no
keychain to fall back on.

**Why it matters.** On Linux, including a CI runner, a run with no
environment variable fails. The message still points at a Mac keychain item.

**Files.** `teanga_bench/apikey.py`, `.env.example`, `README.md`,
`docs/HARNESS.md`.

**Suggested fix.** In `.env.example` and the harness section on the key, say
that Linux and CI must set `OPENROUTER_API_KEY`, and that the
`omp-openrouter` keychain item exists only on macOS.

## 3. Tutor error sentences are mostly synthetic

**Found.** Every tutor item has `real_learner_error` set to false. Both
builders write that flag on every item.

Blas `tutor_accuracy` has 180 items
(`data/build-reports/blas_tutor_accuracy.json`):

- 113 `distractor-derived-unverified` (a wrong exercise option put into the sentence)
- 7 `planted-typo` (a doubled letter, all of them Welsh)
- 60 `blas-app-only` sentences with no error

Tonada `tutor_accuracy` has 360 items
(`data/build-reports/tonada_tutor_accuracy.json`):

- 210 `tonada-app-distractor-machine-reviewed`
- 44 `wikipedia-revision-silver-unreviewed`
- 106 `tonada-app-answer-machine-reviewed` sentences with no error

Of the 44 Wikipedia items, 30 are error edits and 14 are clean Wikipedia
sentences. Those 30 edits are the only error sentences in either suite that
were not made by the build scripts. They are silver and unreviewed.
`docs/methodology.md` says some of them are changes of style, not clear
errors.

The Blas build report records a machine reading, not a reading by a speaker,
of 30 random distractor items. Two of the 30 were also grammatical: a
genitive plural equal to the nominative plural, and a superlative where the
gold answer was a comparative. The report gives a 95 percent interval of
about 1 to 22 percent for that rate. Those 30 items sit in the private set,
which is not in this checkout, so that reading was not repeated here.

Two public Tonada Wikipedia items are ordinary grammatical sentences, and the
test still marks them wrong. In `samples/tonada/tutor_accuracy.jsonl`:

- `wikiedits-error-650a5d50ea9cc2eb3269`: "Rice is a staple food of Mauritius." The gold changes "of" to "in".
- `wikiedits-error-c508bc8d60aa33ba26be`: "He served as the Registrar of the International Court of Justice from 2000 to 2019." The gold drops "the".

**Why it matters.** A high tutor score can mean the model matched a planted
edit, including an edit a speaker would accept. The Wikipedia slice is the
only real-edit evidence, and nobody has reviewed it.

**Files.** `data/build-reports/blas_tutor_accuracy.json`,
`data/build-reports/tonada_tutor_accuracy.json`,
`scripts/build_blas_tutor.py`, `scripts/build_tonada.py`,
`docs/methodology.md`, `samples/blas/tutor_accuracy.jsonl`,
`samples/tonada/tutor_accuracy.jsonl`.

**Suggested fix.** Have a speaker read the distractor items and drop the ones
that are also valid. Split the Wikipedia items into clear errors and style
edits, or drop the style edits. Until that is done, report tutor scores
separately for synthetic errors, planted typos, and Wikipedia edits.

## 4. Public samples ship app text, and the Manx text is GPL-3.0

**Found.** The 20-item samples are public on purpose. They also contain text
whose own licence field is `private-blas` or `private-tonada`. In the full
sets, every lesson item (360), every morphology item (360), 40 translation
items, 40 round-trip items, and 173 of 180 Blas tutor items are
`private-blas`. All 400 Tonada exercises and 316 of 360 Tonada tutor items
are `private-tonada`.

The samples in git include that text: all 20 lesson items, all 20 morphology
items, 4 round-trip items, 19 Blas tutor items, all 20 Tonada exercises, and
17 Tonada tutor items. `scripts/export_hf_bundle.py` copies every file under
`samples/` and does not read `data/private/`. The README and `CITATION.cff`
point at the Hugging Face dataset `johnconway114/teanga-bench` and at Zenodo
record `10.5281/zenodo.24305705`. This review did not open the Zenodo
archive. The export script is what the repository uses to build the public
bundle, and that bundle is the sample files.

Manx translation and round-trip text is GPL-3.0 from the Gaelg corpus: 60
translation items and 40 round-trip items in the full sets, and 4 plus 3
items in the public samples. The repository licence is Apache-2.0
(`LICENSE`, `pyproject.toml`, `CITATION.cff`, `docs/HARNESS.md`) and does not
set the sample text aside. Each item, and the attribution files beside the
samples, does name GPL-3.0. Apache-2.0 cannot be used to re-offer GPL-3.0
text. The two licences can sit in one repository if the Gaelg sentences stay
under GPL-3.0 and the Apache grant does not cover them. The top-level
licence files do not say that today.

**Why it matters.** The published 20 items per test can enter training data,
including rows tagged `private-blas` or `private-tonada`. A reader who follows
the Apache-2.0 grant can redistribute the Manx sentences under the wrong
licence.

**Files.** `samples/`, `samples/blas/translation.ATTRIBUTION.md`,
`samples/blas/round_trip.ATTRIBUTION.md`, `scripts/export_hf_bundle.py`,
`scripts/_common.py`, `data/build-reports/blas_translation.json`,
`data/build-reports/blas_round_trip.json`,
`data/build-reports/blas_lesson_exercises.json`,
`data/build-reports/tonada_exercises.json`,
`data/build-reports/tonada_tutor_accuracy.json`, `README.md`,
`CITATION.cff`, `LICENSE`, `docs/methodology.md`.

**Suggested fix.** Say in the README that the sample rows are public, so they
are a training-data exposure, including rows tagged `private-blas` and
`private-tonada`. Add a licence note that sample text keeps the licence on
the item, and that Gaelg sentences are GPL-3.0 and are outside the
Apache-2.0 grant. Put the same note in `CITATION.cff`. If that split is not
wanted, drop the Gaelg sentences from the public files.

## 5. Two tests sit near the ceiling, and language cells are small

**Found.** On `tonada/exercises` (400 items, 100 per first language) every
published model scores from 98.0% to 99.6%. The highest scores are 99.6%,
99.5%, 99.1%, and 99.0% (two models tie at 99.0%). The 95% intervals are
about ±0.5 to ±1.4 points and they overlap.

On `blas/lesson_exercises` (360 items, 60 per language) the highest score is
98.5% (`anthropic/claude-fable-5.2`) and the next is 98.2%. Four models are
above 96%. Lower on the same test, the weakest published score is 87.5%.

Tutor accuracy still separates models. The best Blas score is 88.5% and the
best Tonada score is 85.1%. The headline 95% interval on Blas tutor (180
items) is about ±4 to ±6 points. On Tonada tutor (360 items) it is about ±4
to ±5 points. The per-language cells are wider than ±4 points:

- Blas tutor has 60 items each for Irish, Scottish Gaelic, and Welsh. The half-width is about ±6 to ±11 points. Manx, Breton, and Cornish are not in this test.
- Tonada tutor has 90 items per first language, not 100. The half-width is about ±6 to ±9 points.
- The figure of 100 per first language is `tonada/exercises`, the test that is already at the ceiling.

**Why it matters.** `tonada/exercises` cannot separate current models. A
60-item or 90-item cell cannot support a claim that one model is a few
points ahead of another on one language.

**Files.** `results/leaderboard.md`, `results/runs/*.json`,
`data/build-reports/blas_lesson_exercises.json`,
`data/build-reports/blas_tutor_accuracy.json`,
`data/build-reports/tonada_exercises.json`,
`data/build-reports/tonada_tutor_accuracy.json`, `docs/methodology.md`.

**Suggested fix.** Treat `tonada/exercises` as saturated for current models,
and add harder items before using it to rank them. Show the interval beside
every language cell, and hold off ranking models inside one language while
those intervals overlap.

## 6. The explanation judges are not checked against people

**Found.** The explanation score uses one fixed pair:
`deepseek/deepseek-v4.1-flash-1017` and `qwen/qwen3.8-flash`
(`config/models.yaml`). An explanation passes only when both pass it.
`docs/methodology.md` and `docs/HARNESS.md` say no person has checked the
judges' marks. The repository has no human calibration set.

If the model under test shares a family with either judge, the explanation
is left unscored. Family is the provider prefix (`teanga_bench/models_config.py`,
`teanga_bench/runner.py`). The published DeepSeek and Qwen runs have
`explanation_status: "not_scored_same_family_as_judge"`. A newer DeepSeek or
Qwen model is dropped in the same way, because the rule follows the family
and not the exact judge id. The headline tutor score is still computed.

**Why it matters.** The explanation score measures agreement with these two
models. It has not been compared with a person's marks. Models from the two
judge families have no explanation score, including models that are not the
judges themselves.

**Files.** `config/models.yaml`, `teanga_bench/models_config.py`,
`teanga_bench/runner.py`, `teanga_bench/scorers.py`, `docs/methodology.md`,
`docs/HARNESS.md`, `results/leaderboard.md`.

**Suggested fix.** Have a person score a sample of explanations, and publish
how often that agrees with the two judges, before citing the explanation
score. To score a new DeepSeek or Qwen model, use a judge pair from other
families and mark that run as a different comparison. The leaderboard already
hides explanation scores when the judge pair is not the current one.

## 7. Accepted answers are few, and three languages rest on thin sources

**Found.** An answer is accepted when it matches a string the source record
lists. `docs/methodology.md` says few items list more than one, so a valid
dialect form that the source omits is marked wrong.

On morphology, items with more than one accepted answer are: Irish 0, Welsh
2, Scottish Gaelic 0, Manx 4, Breton 0, Cornish 1, out of 60 each. That is 7
of 360. The build report says no external dialect list is used. In the public
samples, every lesson item has one accepted form (20 of 20), and the Tonada
exercise sample has one form on 12 items and two forms on 8. The full lesson
and Tonada sets are not in this checkout, and their build reports do not
count accept-list length, so the one-or-two figure is confirmed for
morphology and for the public samples.

Scottish Gaelic, Manx, and Cornish have no parallel corpus in the translation
build. Irish, Welsh, and Breton do. After filters, Scottish Gaelic has 611
sentence candidates, 605 of them Tatoeba, from 6,588 raw rows, with 5,831
dropped on quality flags. Manx translation comes from the Gaelg corpus, which
the methodology describes as mostly dictionary examples, some of them
archaic. Several Manx verb cells have fewer than 15 candidates (imperative
7, present 9, future indicative 3). Every Cornish sentence in the source is
`evidence-deferred`, and every selected Cornish translation and round-trip
item is in the deferred, unverified tier. The tutor test drops Manx, Breton,
and Cornish because there were too few rule-governed exercise errors. The
methodology also notes that Cornish uses more than one spelling system.

**Why it matters.** A correct dialect or spelling that the app did not list
scores 0. Scores for Scottish Gaelic, Manx, and Cornish rest on Tatoeba,
dictionary examples, or unverified app text.

**Files.** `data/build-reports/blas_morphology.json`,
`data/build-reports/blas_translation.json`,
`data/build-reports/blas_round_trip.json`,
`data/build-reports/blas_tutor_accuracy.json`, `docs/methodology.md`,
`samples/blas/lesson_exercises.jsonl`, `samples/blas/morphology.jsonl`,
`samples/tonada/exercises.jsonl`, `scripts/build_blas_morphology.py`,
`scripts/build_blas_lesson_exercises.py`.

**Suggested fix.** Add attested dialect and spelling variants to the accept
lists, and publish how many items still have a single form. For Scottish
Gaelic, Manx, and Cornish, bring in a stronger source, or label those
languages as a thin-source slice so a high score is read with that limit.

## 8. No item has been human-checked

**Found.** Every build report has `human_checked: 0`. The seven tests sum to
2,260 items. Every public sample row has `human_checked: false`. The builders
set the flag only when a source record says a person reviewed it, and the
reports say no source record does.

Of the 360 Blas lesson items, 257 are `blas-app-only`, 96 are
`blas-app+kaikki`, and 7 are `blas-app+bunamo`. The 7 BÚNaMo checks are all
Irish. Welsh and Breton lesson items are all `blas-app-only` (60 each).
Morphology matches that pattern: Welsh and Breton are all `blas-app-only`
(60 each), BÚNaMo covers 11 Irish items, and Kaikki covers 176. A Kaikki or
BÚNaMo hit means the words occur in that word list. It does not mean they are
the right answer for the question. The methodology already says this.

**Why it matters.** A lesson score is agreement with app content that no
person signed off for this benchmark. Welsh and Breton have no second source.
The files already keep `human_checked` false. The risk is citing a score as
if a person had reviewed the items.

**Files.** `data/build-reports/blas_lesson_exercises.json`,
`data/build-reports/blas_morphology.json`, `data/build-reports/*.json`,
`docs/methodology.md`, `scripts/build_blas_lesson_exercises.py`,
`scripts/build_blas_morphology.py`, `scripts/build_blas_tutor.py`,
`scripts/build_tonada.py`, `samples/`.

**Suggested fix.** Leave `human_checked` false until a person has reviewed
that item. Review Welsh and Breton first, because they have no second source.
Do not treat a BÚNaMo or Kaikki word-form hit as a review.

## 9. Work lands on main, and publish pushes the live site

**Found.** The history of `main` is a straight line of commits. The
repository has no other branches and no pull requests. `teanga-bench publish`
rebuilds the leaderboard and the site, commits `results/` and `site/`,
rebases, and pushes to the current branch's upstream
(`teanga_bench/publish.py`). It refuses any other staged path, including
`data/private/`. The README says the hosting service then puts the new pages
live. `vercel.json` serves `site/` with no build step, for
`research.blasapp.com` and `research.tonadaapp.com`. Methodology commits in
the same history were also made on `main`. `--publish` does not commit those
paths, and nothing in the repository asks for a pull request before they
land.

**Why it matters.** A bad results file becomes the public site as soon as
publish pushes. A methodology or data change becomes the cited method with
no review step.

**Files.** `teanga_bench/publish.py`, `vercel.json`, `README.md`,
`docs/HARNESS.md`, `.github/workflows/tests.yml`.

**Suggested fix.** Use pull requests for changes to data, methodology, and
scoring. Keep `--publish` for results, and push that commit to a branch so
the live site updates from `main` only after the branch is merged. CI already
runs the offline tests on pull requests.
