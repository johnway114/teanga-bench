# Teanga Bench report: qwen/qwen3.8-flash

qwen/qwen3.8-flash ran 7 of 7 tests with 3 epochs per item, and the run status is complete. The overall score is 68.5% (95% interval 67.1% to 69.9%), with each completed test weighted equally. The best test was tonada/exercises at 98.7% and the weakest was blas/morphology at 50.6%. On the tutor test the rule-only headline is 58.0%, and the explanation was not scored (not_scored_same_family_as_judge). The run cost $10.98 against a cap of $12.00, of which $0.0000 was judge spend.

Run kind: live. Status: complete. Generated 2026-11-16T21:37:57+00:00.

## Suite: blas

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| lesson_exercises | 90.6% | 87.9% to 93.1% | 360 | $0.7380 |
| morphology | 50.6% | 46.2% to 55.1% | 360 | $4.13 |
| round_trip | 52.2% | 48.8% to 55.4% | 240 | $1.94 |
| translation | 56.9% | 54.2% to 59.9% | 360 | $1.63 |
| tutor_accuracy | 58.0% | 51.9% to 63.7% | 180 | $2.01 |

## Suite: tonada

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| exercises | 98.7% | 97.6% to 99.5% | 400 | $0.1311 |
| tutor_accuracy | 72.9% | 68.6% to 76.9% | 360 | $0.3929 |

## By language

| Language | Score | 95% interval | Items |
| --- | --- | --- | --- |
| breton | 61.5% | 57.7% to 65.2% | 220 |
| cornish | 49.6% | 45.8% to 53.4% | 220 |
| english | 85.8% | 83.7% to 87.8% | 760 |
| irish | 69.1% | 65.4% to 72.6% | 280 |
| manx | 45.0% | 41.4% to 48.5% | 220 |
| scots-gaelic | 71.2% | 67.5% to 74.5% | 280 |
| welsh | 69.9% | 66.4% to 73.4% | 280 |

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
  - Model output: ANSWER: Beth

### blas/morphology

- `blas-morph:breton:verb_present:br-verb-kregiñ:2p` score 0.00
  - Prompt: Language: Breton Task: Give the present form of the verb for the person given. Write one word: the inflected verb form, with no pronoun, particle or auxiliary. Verb: kregiñ Meaning: to start Tense: present Person: 2nd person plural (severa…
  - Expected: krogit
  - Model output: ANSWER: kregit
- `blas-morph:cornish:number_cardinal:kw-num-17` score 0.00
  - Prompt: Language: Cornish Task: Give the cardinal numeral for the number below: the standalone numeral, the form used to name the number (SWF Main). Number: 17 (seventeen) Reply with the answer on one line, in this exact form: ANSWER: <answer>
  - Expected: seytek
  - Model output: 
- `blas-morph:cornish:verb_imperative:kw-verb-bos:2p` score 0.00
  - Prompt: Language: Cornish Task: Give the imperative form of the verb for the person given. Write one word: the inflected verb form, with no pronoun, particle or auxiliary. Verb: bos Meaning: to be Tense: imperative Person: 2nd person plural (sever…
  - Expected: bedhewgh
  - Model output: 

### blas/round_trip

- `blas-round_trip-manx-gv-sent-parallel-4693` score 0.00
  - Prompt: Translate this Manx sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Manx: Va mee sheiltyn dy darragh eh.
  - Expected: Va mee sheiltyn dy darragh eh.
  - Model output: 
  - Pivot text: I thought it happened.
- `blas-round_trip-cornish-kw-sent-tat-0552` score 0.14
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Mar pe dy’Sul hedhyw, ni a wrussa mos dhe byskessa.
  - Expected: Mar pe dy’Sul hedhyw, ni a wrussa mos dhe byskessa.
  - Model output: Os o Dehow hedhyu, gwynsen ni myghi.
  - Pivot text: If today were Sunday, we would go fishing.
- `blas-round_trip-cornish-kw-sent-tat-1830` score 0.20
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Kas yw genev an traow na.
  - Expected: Kas yw genev an traow na.
  - Model output: My a gas an re na.
  - Pivot text: I hate those things.

### blas/translation

- `blas-translation-cornish-kw-sent-tat-1356-from_english` score 0.06
  - Prompt: Translate this English sentence into Cornish. Reply with the Cornish translation only, on one line, with no notes or explanation. English: Do you like dogs?
  - Expected: Yw da genes keun?
  - Model output: A gar'ta ky?
- `blas-translation-manx-gv-sent-parallel-15295-from_english` score 0.10
  - Prompt: Translate this English sentence into Manx. Reply with the Manx translation only, on one line, with no notes or explanation. English: I shall come back at ten o'clock at the latest.
  - Expected: Higym er-ash dyn s'anmee na jeih er y chlag.
  - Model output: Glooym ec feed ayns oyr.
- `blas-translation-manx-gv-sent-parallel-15649-from_english` score 0.16
  - Prompt: Translate this English sentence into Manx. Reply with the Manx translation only, on one line, with no notes or explanation. English: Have you made my bed?
  - Expected: Vel shiu er chiartaghey my lhiabbee?
  - Model output: Vel oo er my gyrvel y ymyd?

### blas/tutor_accuracy

- `blas-tutor-irish-clean-sent-9f6457b394` score 0.00
  - Prompt: You are a Irish language tutor checking a sentence written by a learner. Language: Irish The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Tá sé tábhachtach nach sárófaí a gcearta daonna.
  - Model output: response was not a JSON object
- `blas-tutor-scots-gaelic-clean-ex-943a0622b9` score 0.00
  - Prompt: You are a Scottish Gaelic language tutor checking a sentence written by a learner. Language: Scottish Gaelic The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact e…
  - Expected: Nach robh iad aig a' mhuir tron oidhche?
  - Model output: response was not a JSON object
- `blas-tutor-scots-gaelic-exd-6e0581d3d2` score 0.00
  - Prompt: You are a Scottish Gaelic language tutor checking a sentence written by a learner. Language: Scottish Gaelic The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact e…
  - Expected: Cha tèid agam air deagh Fhraingis a sgrìobhadh.
  - Model output: { "has_error": true, "error_span": "deagh Fraingis", "correction": "deagh Fhraingis", "corrected_sentence": "Cha tèid agam air deagh Fhraingis a sgrìobhadh.", "explanation": "Scottish Gaelic lenites Fraingis after the adjective deagh, so i…

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

Headline (rule-only: found AND fixed AND no over-correction): 58.0%. Found 58.9%, fixed 58.1%, no over-correction 64.3%.

Explanation, judge-marked, not human-validated: not scored (not_scored_same_family_as_judge).

## Tutor detail: tonada/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 72.9%. Found 75.3%, fixed 72.9%, no over-correction 88.6%.

Explanation, judge-marked, not human-validated: not scored (not_scored_same_family_as_judge).
