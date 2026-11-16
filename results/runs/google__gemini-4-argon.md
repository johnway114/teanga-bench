# Teanga Bench report: google/gemini-4-argon

google/gemini-4-argon ran 7 of 7 tests with 3 epochs per item, and the run status is complete. The overall score is 84.4% (95% interval 83.3% to 85.6%), with each completed test weighted equally. The best test was tonada/exercises at 99.6% and the weakest was blas/round_trip at 70.0%. On the tutor test the rule-only headline is 84.1%, and the explanation score is 75.9% (judge-marked, not human-validated). The run cost $5.57 against a cap of $25.00, of which $0.7132 was judge spend.

Run kind: live. Status: complete. Generated 2026-11-16T02:31:02+00:00.

## Suite: blas

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| lesson_exercises | 98.2% | 96.9% to 99.3% | 360 | $0.5817 |
| morphology | 85.4% | 82.1% to 88.5% | 360 | $0.4253 |
| round_trip | 70.0% | 67.3% to 72.6% | 240 | $0.5855 |
| translation | 71.9% | 69.4% to 74.4% | 360 | $0.4442 |
| tutor_accuracy | 84.1% | 78.9% to 88.9% | 180 | $1.06 |

## Suite: tonada

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| exercises | 99.6% | 98.9% to 100.0% | 400 | $0.5477 |
| tutor_accuracy | 81.9% | 77.9% to 85.6% | 360 | $1.92 |

## By language

| Language | Score | 95% interval | Items |
| --- | --- | --- | --- |
| breton | 78.9% | 75.9% to 81.7% | 220 |
| cornish | 78.2% | 74.8% to 81.6% | 220 |
| english | 90.7% | 88.8% to 92.7% | 760 |
| irish | 87.3% | 84.5% to 89.8% | 280 |
| manx | 71.6% | 68.9% to 74.2% | 220 |
| scots-gaelic | 82.5% | 79.3% to 85.5% | 280 |
| welsh | 88.2% | 85.7% to 90.5% | 280 |

## Failure examples

Examples come only from items published in `samples/`.

### blas/lesson_exercises

No public failure examples for this test.

### blas/morphology

- `blas-morph:manx:number_ordinal:gv-num-12` score 0.00
  - Prompt: Language: Manx Task: Give the ordinal numeral for the number below: the ordinal ('first', 'second', ...), including the definite article yn as it stands before the ordinal. Number: 12 (twelve) Reply with the answer on one line, in this exa…
  - Expected: yn nah jeig
  - Model output: ANSWER: yn ghaa-yeigoo
- `blas-morph:scots-gaelic:copula:cop-gd-empha-04` score 0.00
  - Prompt: Language: Scottish Gaelic Task: Fill in the blank with the copula word (or copula particle) that the sentence needs. Write only the missing word(s). Sentence: ___ do Dhia a bhuineas slàinte. English: Salvation is God's affair. Reply with t…
  - Expected: 'S ann
  - Model output: ANSWER: Is ann
- `blas-morph:scots-gaelic:number_counting:gd-num-2` score 0.00
  - Prompt: Language: Scottish Gaelic Task: Give the counting numeral for the number below: the form used when counting aloud (not before a noun). Number: 2 (two) Reply with the answer on one line, in this exact form: ANSWER: <answer>
  - Expected: dhà
  - Model output: ANSWER: a dhà

### blas/round_trip

- `blas-round_trip-cornish-kw-sent-tat-1830` score 0.21
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Kas yw genev an traow na.
  - Expected: Kas yw genev an traow na.
  - Model output: Yma kas dhymm a'n taklow na.
  - Pivot text: I hate those things.
- `blas-round_trip-manx-gv-sent-parallel-6412` score 0.21
  - Prompt: Translate this Manx sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Manx: Nee eh costal queig keead stiagh as magh.
  - Expected: Nee eh costal queig keead stiagh as magh.
  - Model output: Bee eh kuse queig cheead ny smoo ny ny sloo.
  - Pivot text: It will cost five hundred more or less.
- `blas-round_trip-manx-gv-sent-parallel-2423` score 0.34
  - Prompt: Translate this Manx sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Manx: Dreill eh smaght er eh hene.
  - Expected: Dreill eh smaght er eh hene.
  - Model output: Chum eh smacht er hene.
  - Pivot text: He controlled himself.

### blas/translation

- `blas-translation-scots-gaelic-gd-sent-0223-from_english` score 0.15
  - Prompt: Translate this English sentence into Scottish Gaelic. Reply with the Scottish Gaelic translation only, on one line, with no notes or explanation. English: He is a good carpenter.
  - Expected: Tha e na dheagh shaor.
  - Model output: Is e saor math a th' ann.
- `blas-translation-manx-gv-sent-parallel-15649-from_english` score 0.30
  - Prompt: Translate this English sentence into Manx. Reply with the Manx translation only, on one line, with no notes or explanation. English: Have you made my bed?
  - Expected: Vel shiu er chiartaghey my lhiabbee?
  - Model output: Vel y lhiabbee aym jeant ayd?
- `blas-translation-cornish-kw-sent-tat-1356-from_english` score 0.25
  - Prompt: Translate this English sentence into Cornish. Reply with the Cornish translation only, on one line, with no notes or explanation. English: Do you like dogs?
  - Expected: Yw da genes keun?
  - Model output: A garowgh hwi keun?

### blas/tutor_accuracy

- `blas-tutor-irish-clean-sent-9f6457b394` score 0.00
  - Prompt: You are a Irish language tutor checking a sentence written by a learner. Language: Irish The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Tá sé tábhachtach nach sárófaí a gcearta daonna.
  - Model output: {"has_error": true, "error_span": "sárófaí", "correction": "sárófar", "corrected_sentence": "Tá sé tábhachtach nach sárófar a gcearta daonna.", "explanation": "Because the main verb 'Tá' is in the present tense, the verb in the subordinate…
- `blas-tutor-welsh-exd-bc34d0d6aa` score 0.00
  - Prompt: You are a Welsh language tutor checking a sentence written by a learner. Language: Welsh The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Mae'r dŵr yn lân.
  - Model output: {"has_error": true, "error_span": "yn glân", "correction": "yn lân", "corrected_sentence": "Mae'r dŵr yn lân.", "explanation": "Adjectives undergo a soft mutation after the predicative particle 'yn', so 'glân' becomes 'lân'."}

### tonada/exercises

No public failure examples for this test.

### tonada/tutor_accuracy

- `en-ch07-c-vi-d4@vi:err` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: We are at board now. Decide whether the sentence has an error. If it does, give t…
  - Expected: We are on board now.
  - Model output: {"has_error": true, "error_span": "at board", "correction": "on board", "corrected_sentence": "We are on board now.", "explanation": "Cụm từ cố định đúng trong tiếng Anh để chỉ việc đang ở trên tàu, thuyền hoặc máy bay là \"on board\", vì …
- `en-ch36-r02-mgmt-recall-b-lesson-s4@vi:err` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: As long as the dependencies are clear, the prototype staying on schedule. Decide …
  - Expected: As long as the dependencies are clear, the prototype stays on schedule.
  - Model output: {"has_error": true, "error_span": "staying", "correction": "will stay", "corrected_sentence": "As long as the dependencies are clear, the prototype will stay on schedule.", "explanation": "Mệnh đề chính thiếu động từ chia thì hoàn chỉnh vì…
- `wikiedits-error-650a5d50ea9cc2eb3269@vi` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: Rice is a staple food of Mauritius. Decide whether the sentence has an error. If …
  - Expected: Rice is a staple food in Mauritius.
  - Model output: {"has_error": false, "error_span": "", "correction": "", "corrected_sentence": "Rice is a staple food of Mauritius.", "explanation": "Câu này hoàn toàn chính xác. Cấu trúc ngữ pháp, mạo từ và giới từ đều được sử dụng đúng cách để diễn đạt …

## Tutor detail: blas/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 84.1%. Found 85.0%, fixed 84.1%, no over-correction 89.1%.

Explanation, judge-marked, not human-validated: 75.9% (95% interval 70.1% to 81.7%). Judge agreement 95.2%. Judge failures 37. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.

## Tutor detail: tonada/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 81.9%. Found 85.7%, fixed 81.9%, no over-correction 88.5%.

Explanation, judge-marked, not human-validated: 61.7% (95% interval 56.8% to 66.5%). Judge agreement 90.4%. Judge failures 27. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.
