# Methodology

Teanga Bench measures how well a large language model does the work of a
language tutor. It has two suites.

- The **Blas suite** covers Irish, Welsh, Scottish Gaelic, Manx, Breton and
  Cornish.
- The **Tonada suite** covers English tutoring for learners whose first
  language is Portuguese, Spanish, Vietnamese or Japanese.

This page says where the test items come from, how answers are marked, and
what the scores can and cannot tell you.

## What we publish and what we keep private

The code, the scoring rules, the build scripts and this page are public. For
each test, 20 sample items are public. The full item sets are private. They
stay on the machine that runs the benchmark and are never put in the
repository. We do this so that the test items do not enter model training
data.

Failure examples on the model pages come only from the public sample items.

## Where the items come from

No answer in the benchmark was written by a language model for the benchmark.
A build script copies each answer from a source file, or derives it from a
source file by a rule that the script documents. Each item records its source,
the licence of the source, and how strong the evidence for its answer is.

The sources are:

- **Blas app content.** Lesson exercises, noun and verb tables, number tables,
  prepositional pronouns, gender practice, copula drills and sentences from
  the Blas language-learning app.
- **Tonada app content.** English lesson exercises from the Tonada app, with
  instructions in the learner's first language.
- **Parallel corpora.** Irish and English legislation from Gaois, Welsh and
  English text from the Senedd and Welsh legislation, and Breton and French
  text from Ofis Publik ar Brezhoneg.
- **Wikipedia edit history.** Real copy-edits to English Wikipedia, used as
  English error sentences.
- **Reference dictionaries.** BÚNaMo for Irish, and Kaikki (Wiktionary
  extracts) for Irish, Scottish Gaelic, Manx and Cornish. These are used to
  cross-check answers, not to write them.

### No human review

No person reviewed the items for this benchmark. Every item has
`human_checked: false`. The app content is itself largely machine-authored and
machine-reviewed. A score on an app-derived test therefore measures agreement
with the app content. It is not a score against a standard that an expert
signed off.

Each item carries an evidence label so that results can be split by it:

| Label | Meaning |
|---|---|
| `blas-app+bunamo` | The answer is in the app content, and every word of it is a form that BÚNaMo lists. |
| `blas-app+kaikki` | The answer is in the app content, and Kaikki lists it as a form. |
| `blas-app-only` | The answer is in the app content. We had no second source. All Welsh and Breton app items are in this group. |
| `blas-app-unverified` | The app content itself marks the sentence as not yet verified. All Cornish sentences in the translation tests are in this group. |
| `corpus-reference` | The reference translation comes from a published parallel corpus. |
| `distractor-derived-unverified` | The error sentence was made by putting a wrong option from an app exercise into the sentence. See "Tutor tests". |
| `planted-typo` | The error is a doubled letter that a script planted in a clean sentence. |
| `tonada-app-machine-reviewed` | The exercise is in the Tonada app content, and the app's automated review marks it verified. |
| `tonada-app-distractor-machine-reviewed` | The error sentence was made by putting a wrong option from a Tonada exercise into the sentence. |
| `tonada-app-answer-machine-reviewed` | A correct sentence from a Tonada exercise, used as a sentence with no error. |
| `wikipedia-revision-silver-unreviewed` | A real edit from the English Wikipedia history. Some are changes of style and not clear errors. |

A cross-check with BÚNaMo or Kaikki shows that a form exists. It does not show
that the form is the right one for the question.

### Licences

Each item records a licence. The app's own content is marked `private-blas`
or `private-tonada`. Where the app took a sentence from another source, the
item carries the licence of that source:

- Tatoeba sentences: CC BY 2.0 FR.
- Manx sentences from the Gaelg corpus: GPL-3.0.
- Senedd record and Welsh legislation: Open Government Licence v3.0.
- Gaois legislation and Ofis Publik ar Brezhoneg text: CC BY 4.0.
- Wikipedia sentences and Wiktionary text from Kaikki: CC BY-SA 4.0.
- English Wikipedia edit pairs: the text is CC BY-SA 4.0, and the
  WikiEdits-MultiGEC dataset that collected them is MIT. Both apply.

BÚNaMo, used for cross-checks, is under the Open Database Licence 1.0. Each
public sample file has an attribution file beside it that lists its sources,
licences and notices.

## The tests

The table of tests on this page is generated from the build reports. It shows
the number of items, the languages and the evidence counts for each test.

### Grammar forms and lesson exercises

The model is asked for one form or one answer: a genitive, a verb form, a
prepositional pronoun, a number, the right option in an exercise. The answer
is compared with a list of accepted answers after light normalisation (case,
apostrophe style and outer spaces do not matter). The list contains every
alternative that the source records.

Limit: if a valid dialect or variant form is not in the source, the model is
marked wrong for it. Few items have more than one accepted answer, because the
sources rarely list alternatives.

### Translation and round trip

In the translation test the model translates a sentence into English or from
English. In the Breton corpus items the other language is French. The score is
chrF++, a standard measure of character and word overlap with the reference
translation.

In the round-trip test the model translates a sentence into English, and then,
in a new conversation, translates its own English back. The score is chrF++
between the result and the original sentence.

Limits: an overlap measure gives a lower score to a correct translation that
uses different words. Most translation items have one reference. Round-trip
scores can be high when a model makes the same mistake in both directions.

### Tutor tests

The model sees a learner's sentence. The sentence has one error or no error.
The model must say if there is an error, give the wrong span, give the
correction, give the corrected sentence and explain the error.

The headline score is marked by rule. An item is correct when the model finds
the error, fixes it, and changes nothing else. For a sentence with no error,
the model must say so and leave the sentence as it is. About one third of the
items have no error.

The error sentences are not real learner errors. We found no corpus of real
learner errors for these languages. The errors come from three places:

- **Exercise distractors.** An app exercise gives a sentence with a blank, the
  right option and wrong options. We put a wrong option in the blank. We keep
  only grammatical contrasts, such as a missing mutation or a wrong particle.
  A wrong option is sometimes also valid in the sentence. We do not know how
  often. A machine reading of 30 random items, not a reading by a speaker,
  found 2 such items. For 2 of 30, the 95 percent interval is about 1 to 22
  percent.
- **Planted typos.** A script doubles one letter in a clean sentence. Only a
  few Welsh items use this source.
- **Real edits (English only).** Real copy-edits from the English Wikipedia
  edit history.

The Blas tutor test covers Irish, Welsh and Scottish Gaelic only. The app has
too few suitable exercises for Manx, Breton and Cornish, and a test built on
planted typos alone would mislead.

### The explanation score

The explanation is the only part that a model marks. Two judge models from two
different model families mark each explanation. The explanation passes only
when both judges pass it. The same two judges mark every model, so the scores
can be compared. A model from the same family as a judge gets no explanation
score.

No person has checked the judges' marks. For this reason the explanation score
is reported apart from the headline score, with the rate at which the two
judges agreed. If a judge call fails three times, the explanation is left
unscored. It is not counted as wrong.

## Runs, intervals and cost

- **Repeat runs.** Each item is run three times with the provider's default
  settings. An item's score is the mean of its three runs.
- **Confidence intervals.** Each score has a 95 percent interval from 2,000
  bootstrap resamples of the items. When two models' intervals overlap, do not
  read the difference between them as real.
- **Consistency.** We report the share of items where the model gave the same
  result in all three runs.
- **Cost.** Prices are read from OpenRouter at the start of the run. We report
  the cost of the run and the cost per correct answer. Each run has a hard
  cost cap.
- **Sampling.** Items are selected with a fixed random seed, spread evenly
  over languages and grammar topics. A rebuild from the same sources gives the
  same items.

## Contamination

A model may have seen some of the source text in training. Each translation
item is labelled `private` or `public-source`.

- The Irish sentences come from the Blas app's own sentence bank and are
  private.
- The sentences for the other five languages come from public sources, such
  as Tatoeba, the Senedd record and dictionary examples. Models may have seen
  them.
- The parallel corpora are published legal and administrative text.
- The app exercises and tables are not published as data, but the app itself
  is public.

## Known limits

- No human review, as described above.
- The Blas app content has known errors. A build script found one Irish
  exercise whose marked answer looks wrong. There will be others.
- Cornish text in the sources uses more than one spelling system. A single
  reference can mark a valid spelling as wrong.
- Manx translation sentences are mostly dictionary examples, and some are
  archaic.
- Welsh and Breton answers have no second source.
- Scores for small groups, such as one grammar topic in one language, have
  wide intervals.

## Notes on the first runs

- **Resumed runs.** Eight of the first nine runs stopped before the end. Seven
  stopped because the account ran out of credit, and one reached its cost
  cap. Each was resumed: answers already scored were kept, and only the
  missing ones were asked again. The answers in a resumed run were therefore
  given at two different times. Each results file records this in its
  `resumed` block.
- **One corrected file.** The results file for `openai/gpt-6-luna` was
  written before a cost-reporting bug was fixed. The cost shown for the
  Tonada tutor test also included the cost of the Blas tutor test. A script
  subtracted the duplicate amount in that one file. The file was not
  regenerated from the run logs. Its scores and its total cost did not
  change, and its `corrections` field records the edit.
- **Answer length limit.** The first runs gave each answer at most 2048
  tokens. Four models reason before they answer, and the reasoning counts
  towards that limit. They often used it all up and returned nothing, which
  scored 0. The limit is now 16000 tokens. For those four models, the answers
  that hit the old limit were asked again under the new one. Two other
  models hit the old limit a few times: `openai/gpt-6-luna` on 7 of 6,780
  answers and `anthropic/claude-haiku-5.5` on 2. Those answers were not asked
  again and still score 0. Models that never hit the limit were not re-run.
  Each results file of a re-run model records how many answers were asked
  again, under which limits.
