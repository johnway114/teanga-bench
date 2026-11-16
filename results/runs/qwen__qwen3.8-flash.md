# Teanga Bench report: qwen/qwen3.8-flash

qwen/qwen3.8-flash ran 4 of 7 tests with 3 epochs per item, and the run status is cost_cap_reached. The overall score is 48.2% (95% interval 46.3% to 50.0%), with each completed test weighted equally. The best test was blas/lesson_exercises at 83.8% and the weakest was blas/morphology at 27.4%. The run cost $2.50 against a cap of $2.50, of which $0.0000 was judge spend.

Run kind: live. Status: cost_cap_reached. Generated 2026-11-16T01:22:32+00:00.

## Suite: blas

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| lesson_exercises | 83.8% | 80.3% to 87.1% | 360 | $0.2873 |
| morphology | 27.4% | 23.6% to 31.3% | 360 | $0.8383 |
| round_trip | 36.6% | 32.6% to 40.7% | 240 | $0.6863 |
| translation | 44.8% | 41.3% to 48.4% | 360 | $0.6099 |
| tutor_accuracy (incomplete) | n/a | n/a | 0 | $0.0759 |

## Suite: tonada

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| exercises (incomplete) | n/a | n/a | 0 | $0.0000 |
| tutor_accuracy (incomplete) | n/a | n/a | 0 | $0.0000 |

## By language

| Language | Score | 95% interval | Items |
| --- | --- | --- | --- |
| breton | 45.7% | 41.6% to 49.7% | 220 |
| cornish | 35.0% | 31.6% to 38.6% | 220 |
| irish | 58.0% | 53.5% to 62.3% | 220 |
| manx | 28.8% | 25.6% to 32.2% | 220 |
| scots-gaelic | 62.1% | 57.7% to 66.3% | 220 |
| welsh | 59.3% | 55.3% to 63.4% | 220 |

## Failure examples

Examples come only from items published in `samples/`.

### blas/lesson_exercises

- `blx-manx-gv_flow_ch09_u02_grammar_v2-sc1` score 0.00
  - Prompt: This is a sentence-building exercise from the Manx course of a language-learning app. Arrange the tiles into the Manx phrase that means “fetch the cake”. Use the tiles in the right order (some tiles are decoys and do not belong in the phra…
  - Expected: cur lesh y verreen
  - Model output: 
- `blx-welsh-cy_ch31_lost_property_recall_v3-s1d4` score 0.00
  - Prompt: This is a fill-in-the-blank exercise from the Welsh course of a language-learning app. Supply the missing Welsh word(s) for the blank (____); the English in the exercise tells you what is meant. Exercise: Fill in the question word: "___ o'…
  - Expected: Faint
  - Model output: 
- `blx-scots-gaelic-gd_b1_c05_u04_lesson_v1-sc2` score 0.00
  - Prompt: This is an exercise from the Scottish Gaelic course of a language-learning app on how a word changes in a phrase (mutation or other change to its beginning or form). The word in its basic form is “ceannach”. Fill the blank with the form th…
  - Expected: cheannach
  - Model output: 

### blas/morphology

- `blas-morph:breton:verb_present:br-verb-kregiñ:2p` score 0.00
  - Prompt: Language: Breton Task: Give the present form of the verb for the person given. Write one word: the inflected verb form, with no pronoun, particle or auxiliary. Verb: kregiñ Meaning: to start Tense: present Person: 2nd person plural (severa…
  - Expected: krogit
  - Model output: 
- `blas-morph:cornish:noun_plural:kw-decl-breselores` score 0.00
  - Prompt: Language: Cornish Task: Give the plural (nominative plural) of the noun below. Noun: breselores Meaning: militant Gender: feminine Reply with the answer on one line, in this exact form: ANSWER: <answer>
  - Expected: breseloresow
  - Model output: 
- `blas-morph:cornish:number_cardinal:kw-num-17` score 0.00
  - Prompt: Language: Cornish Task: Give the cardinal numeral for the number below: the standalone numeral, the form used to name the number (SWF Main). Number: 17 (seventeen) Reply with the answer on one line, in this exact form: ANSWER: <answer>
  - Expected: seytek
  - Model output: 

### blas/round_trip

- `blas-round_trip-breton-br-sent-0288` score 0.00
  - Prompt: Translate this Breton sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Breton: Hennezh n'eo ket ma c'hazh. Ma hini a zo gwenn e dreid.
  - Expected: Hennezh n'eo ket ma c'hazh. Ma hini a zo gwenn e dreid.
  - Model output: 
  - Pivot text: This is not my cat. Mine has white paws.
- `blas-round_trip-cornish-kw-sent-tat-0552` score 0.00
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Mar pe dy’Sul hedhyw, ni a wrussa mos dhe byskessa.
  - Expected: Mar pe dy’Sul hedhyw, ni a wrussa mos dhe byskessa.
  - Model output: 
  - Pivot text: If today were Sunday, we would go fishing.
- `blas-round_trip-cornish-kw-sent-tat-2363` score 0.00
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: My re bia owth oberi ena rag tri mis.
  - Expected: My re bia owth oberi ena rag tri mis.
  - Model output: 

### blas/translation

- `blas-translation-cornish-kw-sent-tat-1356-from_english` score 0.00
  - Prompt: Translate this English sentence into Cornish. Reply with the Cornish translation only, on one line, with no notes or explanation. English: Do you like dogs?
  - Expected: Yw da genes keun?
  - Model output: 
- `blas-translation-cornish-kw-sent-tat-2332-from_english` score 0.00
  - Prompt: Translate this English sentence into Cornish. Reply with the Cornish translation only, on one line, with no notes or explanation. English: I was trying to remember the name of the book.
  - Expected: Yth esen vy owth assaya perthi kov hanow an lyver.
  - Model output: 
- `blas-translation-manx-gv-sent-parallel-14165-from_english` score 0.00
  - Prompt: Translate this English sentence into Manx. Reply with the Manx translation only, on one line, with no notes or explanation. English: The house has stood a hundred and six years.
  - Expected: Ta'n thie er hassoo keead blein as shey.
  - Model output: 

### blas/tutor_accuracy

No public failure examples for this test.

### tonada/exercises

No public failure examples for this test.

### tonada/tutor_accuracy

No public failure examples for this test.

## Tutor detail: blas/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): n/a. Found n/a, fixed n/a, no over-correction n/a.

Explanation, judge-marked, not human-validated: not scored (not_scored_same_family_as_judge).
