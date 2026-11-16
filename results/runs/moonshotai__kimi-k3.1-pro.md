# Teanga Bench report: moonshotai/kimi-k3.1-pro

moonshotai/kimi-k3.1-pro ran 7 of 7 tests with 3 epochs per item, and the run status is complete. The overall score is 78.0% (95% interval 76.6% to 79.3%), with each completed test weighted equally. The best test was tonada/exercises at 98.8% and the weakest was blas/round_trip at 60.0%. On the tutor test the rule-only headline is 69.4%, and the explanation score is 61.3% (judge-marked, not human-validated). The run cost $34.76 against a cap of $45.00, of which $0.6239 was judge spend.

Run kind: live. Status: complete. Generated 2026-11-16T03:21:31+00:00.

## Suite: blas

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| lesson_exercises | 94.8% | 92.7% to 96.8% | 360 | $2.05 |
| morphology | 76.6% | 72.5% to 80.6% | 360 | $6.39 |
| round_trip | 60.0% | 56.7% to 63.3% | 240 | $6.93 |
| translation | 65.6% | 62.7% to 68.6% | 360 | $7.00 |
| tutor_accuracy | 69.4% | 63.7% to 75.0% | 180 | $5.44 |

## Suite: tonada

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| exercises | 98.8% | 97.8% to 99.7% | 400 | $1.67 |
| tutor_accuracy | 80.6% | 76.5% to 84.4% | 360 | $5.29 |

## By language

| Language | Score | 95% interval | Items |
| --- | --- | --- | --- |
| breton | 67.0% | 62.9% to 70.9% | 220 |
| cornish | 69.9% | 66.0% to 73.5% | 220 |
| english | 89.7% | 87.7% to 91.6% | 760 |
| irish | 80.4% | 76.9% to 83.6% | 280 |
| manx | 60.8% | 57.0% to 64.4% | 220 |
| scots-gaelic | 79.6% | 76.5% to 82.7% | 280 |
| welsh | 79.8% | 76.7% to 82.9% | 280 |

## Failure examples

Examples come only from items published in `samples/`.

### blas/lesson_exercises

- `blx-manx-gv_flow_ch09_u02_grammar_v2-sc1` score 0.00
  - Prompt: This is a sentence-building exercise from the Manx course of a language-learning app. Arrange the tiles into the Manx phrase that means “fetch the cake”. Use the tiles in the right order (some tiles are decoys and do not belong in the phra…
  - Expected: cur lesh y verreen
  - Model output: 

### blas/morphology

- `blas-morph:breton:verb_present:br-verb-kregiñ:2p` score 0.00
  - Prompt: Language: Breton Task: Give the present form of the verb for the person given. Write one word: the inflected verb form, with no pronoun, particle or auxiliary. Verb: kregiñ Meaning: to start Tense: present Person: 2nd person plural (severa…
  - Expected: krogit
  - Model output: ANSWER: kregit
- `blas-morph:cornish:verb_imperative:kw-verb-bos:2p` score 0.00
  - Prompt: Language: Cornish Task: Give the imperative form of the verb for the person given. Write one word: the inflected verb form, with no pronoun, particle or auxiliary. Verb: bos Meaning: to be Tense: imperative Person: 2nd person plural (sever…
  - Expected: bedhewgh
  - Model output: ANSWER: byewgh
- `blas-morph:manx:number_ordinal:gv-num-12` score 0.00
  - Prompt: Language: Manx Task: Give the ordinal numeral for the number below: the ordinal ('first', 'second', ...), including the definite article yn as it stands before the ordinal. Number: 12 (twelve) Reply with the answer on one line, in this exa…
  - Expected: yn nah jeig
  - Model output: ANSWER: yn daa-yeigoo

### blas/round_trip

- `blas-round_trip-cornish-kw-sent-tat-0552` score 0.00
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Mar pe dy’Sul hedhyw, ni a wrussa mos dhe byskessa.
  - Expected: Mar pe dy’Sul hedhyw, ni a wrussa mos dhe byskessa.
  - Model output: 
  - Pivot text: If it were Sunday today, we would go fishing.
- `blas-round_trip-cornish-kw-sent-tat-1830` score 0.17
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Kas yw genev an traow na.
  - Expected: Kas yw genev an traow na.
  - Model output: My a gas an taklow-na.
  - Pivot text: I hate those things.
- `blas-round_trip-breton-br-sent-0288` score 0.00
  - Prompt: Translate this Breton sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Breton: Hennezh n'eo ket ma c'hazh. Ma hini a zo gwenn e dreid.
  - Expected: Hennezh n'eo ket ma c'hazh. Ma hini a zo gwenn e dreid.
  - Model output: 
  - Pivot text: That isn’t my cat. Mine has white paws.

### blas/translation

- `blas-translation-manx-gv-sent-parallel-14165-from_english` score 0.00
  - Prompt: Translate this English sentence into Manx. Reply with the Manx translation only, on one line, with no notes or explanation. English: The house has stood a hundred and six years.
  - Expected: Ta'n thie er hassoo keead blein as shey.
  - Model output: 
- `blas-translation-cornish-kw-sent-tat-1356-from_english` score 0.00
  - Prompt: Translate this English sentence into Cornish. Reply with the Cornish translation only, on one line, with no notes or explanation. English: Do you like dogs?
  - Expected: Yw da genes keun?
  - Model output: 
- `blas-translation-manx-gv-sent-parallel-15649-from_english` score 0.00
  - Prompt: Translate this English sentence into Manx. Reply with the Manx translation only, on one line, with no notes or explanation. English: Have you made my bed?
  - Expected: Vel shiu er chiartaghey my lhiabbee?
  - Model output: 

### blas/tutor_accuracy

- `blas-tutor-welsh-exd-58b2c1cfa7` score 0.00
  - Prompt: You are a Welsh language tutor checking a sentence written by a learner. Language: Welsh The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Mae'n honni iddi gael ei magu yng nghanolbarth gorllewinol yr Unol Daleithiau.
  - Model output: {"has_error": true, "error_span": "iddi cael", "correction": "iddi gael", "corrected_sentence": "Mae'n honni iddi gael ei magu yng nghanolbarth gorllewinol yr Unol Daleithiau.", "explanation": "Yn y patrwm 'honni i + goddrych + berfenw', m…
- `blas-tutor-welsh-exd-facf492c47` score 0.00
  - Prompt: You are a Welsh language tutor checking a sentence written by a learner. Language: Welsh The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: y llyfr sydd ar y bwrdd
  - Model output: {"has_error":true,"error_span":"y llyfr mae","correction":"mae'r llyfr","corrected_sentence":"mae'r
- `blas-tutor-irish-exd-51c5e10877` score 0.00
  - Prompt: You are a Irish language tutor checking a sentence written by a learner. Language: Irish The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: D'fhan muid i mbrú.
  - Model output: response was not a JSON object

### tonada/exercises

- `en-ch31-u04-complaint-return-lesson-s4@vi` score 0.00
  - Prompt: This is an exercise from an English course for Vietnamese speakers. The learner sees the instruction in Vietnamese; the answer is in English. Instruction (Vietnamese): Chọn từ mô tả tình trạng món hàng. Sentence: The item is ____, so I wou…
  - Expected: unopened
  - Model output: ANSWER: open

### tonada/tutor_accuracy

- `en-ch42-c-pt-d1@pt-BR:err` score 0.00
  - Prompt: A learner of English whose first language is Portuguese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: We are unsure whether will the deal close. Decide whether the sentence has an err…
  - Expected: We are unsure whether the deal will close.
  - Model output: {"has_error": true, "error_span": "will the deal close", "correction": "the deal will close", "corrected_sentence": "We are unsure whether the deal will close.", "explanation": "Em orações subordinadas introduzidas por 'whether', não se us…
- `wikiedits-error-650a5d50ea9cc2eb3269@vi` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: Rice is a staple food of Mauritius. Decide whether the sentence has an error. If …
  - Expected: Rice is a staple food in Mauritius.
  - Model output: {"has_error": false, "error_span": "", "correction": "", "corrected_sentence": "Rice is a staple food of Mauritius.", "explanation": "Câu này đúng ngữ pháp; cấu trúc “a staple food of Mauritius” diễn tả gạo là một loại lương thực chính của…
- `wikiedits-error-c508bc8d60aa33ba26be@pt-BR` score 0.00
  - Prompt: A learner of English whose first language is Portuguese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: He served as the Registrar of the International Court of Justice from 2000 to 201…
  - Expected: He served as Registrar of the International Court of Justice from 2000 to 2019.
  - Model output: {"has_error": false, "error_span": "", "correction": "", "corrected_sentence": "He served as the Registrar of the International Court of Justice from 2000 to 2019.", "explanation": "A frase está correta: “served as” indica adequadamente o …

## Tutor detail: blas/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 69.4%. Found 69.8%, fixed 69.4%, no over-correction 77.2%.

Explanation, judge-marked, not human-validated: 61.3% (95% interval 55.3% to 67.1%). Judge agreement 93.7%. Judge failures 7. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.

## Tutor detail: tonada/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 80.6%. Found 84.1%, fixed 80.6%, no over-correction 89.1%.

Explanation, judge-marked, not human-validated: 63.8% (95% interval 59.2% to 68.5%). Judge agreement 93.1%. Judge failures 27. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.
