# Teanga Bench report: moonshotai/kimi-k3.1-pro

moonshotai/kimi-k3.1-pro ran 7 of 7 tests with 3 epochs per item, and the run status is complete. The overall score is 81.7% (95% interval 80.5% to 82.9%), with each completed test weighted equally. The best test was tonada/exercises at 99.1% and the weakest was blas/round_trip at 65.3%. On the tutor test the rule-only headline is 79.3%, and the explanation score is 70.4% (judge-marked, not human-validated). The run cost $43.58 against a cap of $50.00, of which $0.6807 was judge spend.

Run kind: live. Status: complete. Generated 2026-11-16T22:49:16+00:00.

## Suite: blas

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| lesson_exercises | 95.8% | 93.9% to 97.6% | 360 | $2.31 |
| morphology | 82.1% | 78.4% to 85.6% | 360 | $8.93 |
| round_trip | 65.3% | 62.5% to 68.0% | 240 | $9.15 |
| translation | 69.4% | 66.9% to 72.0% | 360 | $8.55 |
| tutor_accuracy | 79.3% | 74.3% to 84.1% | 180 | $7.26 |

## Suite: tonada

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| exercises | 99.1% | 98.2% to 99.8% | 400 | $1.70 |
| tutor_accuracy | 80.6% | 76.5% to 84.4% | 360 | $5.68 |

## By language

| Language | Score | 95% interval | Items |
| --- | --- | --- | --- |
| breton | 71.2% | 67.4% to 74.8% | 220 |
| cornish | 75.3% | 71.8% to 78.5% | 220 |
| english | 89.9% | 87.9% to 91.7% | 760 |
| irish | 83.5% | 80.5% to 86.4% | 280 |
| manx | 68.6% | 65.1% to 71.9% | 220 |
| scots-gaelic | 82.1% | 79.1% to 85.0% | 280 |
| welsh | 85.0% | 82.4% to 87.6% | 280 |

## Failure examples

Examples come only from items published in `samples/`.

### blas/lesson_exercises

No public failure examples for this test.

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

- `blas-round_trip-cornish-kw-sent-tat-1830` score 0.17
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Kas yw genev an traow na.
  - Expected: Kas yw genev an traow na.
  - Model output: My a gas an taklow-na.
  - Pivot text: I hate those things.
- `blas-round_trip-manx-gv-sent-parallel-6412` score 0.20
  - Prompt: Translate this Manx sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Manx: Nee eh costal queig keead stiagh as magh.
  - Expected: Nee eh costal queig keead stiagh as magh.
  - Model output: Coshtys eh mysh queig cheead.
  - Pivot text: It will cost roughly five hundred.
- `blas-round_trip-breton-br-sent-0288` score 0.32
  - Prompt: Translate this Breton sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Breton: Hennezh n'eo ket ma c'hazh. Ma hini a zo gwenn e dreid.
  - Expected: Hennezh n'eo ket ma c'hazh. Ma hini a zo gwenn e dreid.
  - Model output: N’eo ket ma c’hazh. An hini din en deus pavioù gwenn.
  - Pivot text: That is not my cat. Mine has white paws.

### blas/translation

- `blas-translation-cornish-kw-sent-tat-1356-from_english` score 0.25
  - Prompt: Translate this English sentence into Cornish. Reply with the Cornish translation only, on one line, with no notes or explanation. English: Do you like dogs?
  - Expected: Yw da genes keun?
  - Model output: A wredh hwi kara keun?
- `blas-translation-scots-gaelic-gd-sent-0223-from_english` score 0.14
  - Prompt: Translate this English sentence into Scottish Gaelic. Reply with the Scottish Gaelic translation only, on one line, with no notes or explanation. English: He is a good carpenter.
  - Expected: Tha e na dheagh shaor.
  - Model output: Is saor math e.
- `blas-translation-manx-gv-sent-parallel-15649-from_english` score 0.41
  - Prompt: Translate this English sentence into Manx. Reply with the Manx translation only, on one line, with no notes or explanation. English: Have you made my bed?
  - Expected: Vel shiu er chiartaghey my lhiabbee?
  - Model output: Vel oo er n'yannoo my lhiabbee?

### blas/tutor_accuracy

- `blas-tutor-welsh-exd-facf492c47` score 0.00
  - Prompt: You are a Welsh language tutor checking a sentence written by a learner. Language: Welsh The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: y llyfr sydd ar y bwrdd
  - Model output: {"has_error":true,"error_span":"y llyfr mae","correction":"mae'r llyfr","corrected_sentence":"mae'r llyfr ar y bwrdd","explanation":"Welsh statements normally use verb-initial word order, and mae + y contracts to mae'r."}
- `blas-tutor-irish-clean-sent-9f6457b394` score 0.00
  - Prompt: You are a Irish language tutor checking a sentence written by a learner. Language: Irish The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Tá sé tábhachtach nach sárófaí a gcearta daonna.
  - Model output: {"has_error": true, "error_span": "nach sárófaí", "correction": "nach sáraítear", "corrected_sentence": "Tá sé tábhachtach nach sáraítear a gcearta daonna.", "explanation": "Baineann an abairt le riail ghinearálta sa chúlchaint láithreach,…
- `blas-tutor-welsh-exd-58b2c1cfa7` score 0.00
  - Prompt: You are a Welsh language tutor checking a sentence written by a learner. Language: Welsh The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Mae'n honni iddi gael ei magu yng nghanolbarth gorllewinol yr Unol Daleithiau.
  - Model output: {"has_error": true, "error_span": "iddi cael", "correction": "iddi gael", "corrected_sentence": "Mae'n honni iddi gael ei magu yng nghanolbarth gorllewinol yr Unol Daleithiau.", "explanation": "Yn y patrwm 'honni i + goddrych + berfenw', m…

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

Headline (rule-only: found AND fixed AND no over-correction): 79.3%. Found 79.6%, fixed 79.3%, no over-correction 88.0%.

Explanation, judge-marked, not human-validated: 70.4% (95% interval 64.7% to 76.0%). Judge agreement 93.4%. Judge failures 10. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.

## Tutor detail: tonada/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 80.6%. Found 84.3%, fixed 80.6%, no over-correction 89.5%.

Explanation, judge-marked, not human-validated: 64.4% (95% interval 59.6% to 69.0%). Judge agreement 93.2%. Judge failures 28. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.
