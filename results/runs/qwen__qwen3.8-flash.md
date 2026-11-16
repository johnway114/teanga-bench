# Teanga Bench report: qwen/qwen3.8-flash

qwen/qwen3.8-flash ran 7 of 7 tests with 3 epochs per item, and the run status is complete. The overall score is 55.2% (95% interval 53.7% to 56.7%), with each completed test weighted equally. The best test was tonada/exercises at 98.2% and the weakest was blas/tutor_accuracy at 25.6%. On the tutor test the rule-only headline is 25.6%, and the explanation was not scored (not_scored_same_family_as_judge). The run cost $3.20 against a cap of $6.00, of which $0.0000 was judge spend.

Run kind: live. Status: complete. Generated 2026-11-16T06:51:49+00:00.

## Suite: blas

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| lesson_exercises | 83.8% | 80.3% to 87.1% | 360 | $0.2873 |
| morphology | 27.4% | 23.6% to 31.3% | 360 | $0.8383 |
| round_trip | 36.6% | 32.6% to 40.7% | 240 | $0.6863 |
| translation | 44.8% | 41.3% to 48.4% | 360 | $0.6099 |
| tutor_accuracy | 25.6% | 20.6% to 30.7% | 180 | $0.4224 |

## Suite: tonada

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| exercises | 98.2% | 96.8% to 99.2% | 400 | $0.1140 |
| tutor_accuracy | 69.8% | 65.5% to 73.9% | 360 | $0.2426 |

## By language

| Language | Score | 95% interval | Items |
| --- | --- | --- | --- |
| breton | 45.7% | 41.6% to 49.7% | 220 |
| cornish | 35.0% | 31.6% to 38.6% | 220 |
| english | 84.0% | 81.9% to 86.1% | 760 |
| irish | 54.0% | 49.7% to 58.1% | 280 |
| manx | 28.8% | 25.6% to 32.2% | 220 |
| scots-gaelic | 54.3% | 50.5% to 58.3% | 280 |
| welsh | 50.6% | 47.0% to 54.2% | 280 |

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

- `blas-tutor-irish-clean-sent-9f6457b394` score 0.00
  - Prompt: You are a Irish language tutor checking a sentence written by a learner. Language: Irish The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Tá sé tábhachtach nach sárófaí a gcearta daonna.
  - Model output: response was not a JSON object
- `blas-tutor-irish-exd-51c5e10877` score 0.00
  - Prompt: You are a Irish language tutor checking a sentence written by a learner. Language: Irish The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: D'fhan muid i mbrú.
  - Model output: response was not a JSON object
- `blas-tutor-scots-gaelic-clean-ex-943a0622b9` score 0.00
  - Prompt: You are a Scottish Gaelic language tutor checking a sentence written by a learner. Language: Scottish Gaelic The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact e…
  - Expected: Nach robh iad aig a' mhuir tron oidhche?
  - Model output: response was not a JSON object

### tonada/exercises

- `en-ch31-u04-complaint-return-lesson-s4@vi` score 0.00
  - Prompt: This is an exercise from an English course for Vietnamese speakers. The learner sees the instruction in Vietnamese; the answer is in English. Instruction (Vietnamese): Chọn từ mô tả tình trạng món hàng. Sentence: The item is ____, so I wou…
  - Expected: unopened
  - Model output: 
- `en-ch12-u06-recall-plans-and-health-lesson-s4@ja` score 0.00
  - Prompt: This is an exercise from an English course for Japanese speakers. The learner sees the instruction in Japanese; the answer is in English. Instruction (Japanese): 空欄に入る語句を選びましょう。 Sentence: I'm going to ____ the doctor about my cough tomorro…
  - Expected: ask
  - Model output: ANSWER: call

### tonada/tutor_accuracy

- `wikiedits-error-650a5d50ea9cc2eb3269@vi` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: Rice is a staple food of Mauritius. Decide whether the sentence has an error. If …
  - Expected: Rice is a staple food in Mauritius.
  - Model output: {"has_error": false, "error_span": "", "correction": "", "corrected_sentence": "Rice is a staple food of Mauritius.", "explanation": "Câu này đúng vì ngữ pháp và cách dùng từ đều hợp lý. ‘a staple food’ là cách diễn đạt tự nhiên trong tiến…
- `wikiedits-error-c508bc8d60aa33ba26be@pt-BR` score 0.00
  - Prompt: A learner of English whose first language is Portuguese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: He served as the Registrar of the International Court of Justice from 2000 to 201…
  - Expected: He served as Registrar of the International Court of Justice from 2000 to 2019.
  - Model output: {"has_error": false, "error_span": "", "correction": "", "corrected_sentence": "He served as the Registrar of the International Court of Justice from 2000 to 2019.", "explanation": "A frase está correta. A estrutura e o uso do artigo estão…
- `en-ch07-c-vi-d4@vi:err` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: We are at board now. Decide whether the sentence has an error. If it does, give t…
  - Expected: We are on board now.
  - Model output: { "has_error": true, "error_span": "at board", "correction": "on board", "corrected_sentence": "We are on board now.", "explanation": "Cụm đúng là 'on board' hoặc 'aboard', còn 'at board' không tự nhiên trong tiếng Anh." }

## Tutor detail: blas/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 25.6%. Found 25.9%, fixed 25.6%, no over-correction 29.4%.

Explanation, judge-marked, not human-validated: not scored (not_scored_same_family_as_judge).

## Tutor detail: tonada/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 69.8%. Found 71.9%, fixed 69.8%, no over-correction 85.0%.

Explanation, judge-marked, not human-validated: not scored (not_scored_same_family_as_judge).
