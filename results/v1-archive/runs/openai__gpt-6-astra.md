# Teanga Bench report: openai/gpt-6-astra

openai/gpt-6-astra ran 7 of 7 tests with 3 epochs per item, and the run status is complete. The overall score is 86.0% (95% interval 84.9% to 87.1%), with each completed test weighted equally. The best test was tonada/exercises at 99.0% and the weakest was blas/round_trip at 69.3%. On the tutor test the rule-only headline is 86.5%, and the explanation score is 69.9% (judge-marked, not human-validated). The run cost $36.70 against a cap of $110.00, of which $0.8384 was judge spend.

Run kind: live. Status: complete. Generated 2026-11-16T05:18:41+00:00.

## Suite: blas

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| lesson_exercises | 96.6% | 94.5% to 98.3% | 360 | $2.48 |
| morphology | 92.5% | 89.9% to 94.8% | 360 | $5.24 |
| round_trip | 69.3% | 66.6% to 72.1% | 240 | $7.86 |
| translation | 73.1% | 70.5% to 75.7% | 360 | $6.17 |
| tutor_accuracy | 86.5% | 82.0% to 90.7% | 180 | $5.21 |

## Suite: tonada

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| exercises | 99.0% | 98.0% to 99.8% | 400 | $2.41 |
| tutor_accuracy | 85.1% | 81.2% to 88.6% | 360 | $7.34 |

## By language

| Language | Score | 95% interval | Items |
| --- | --- | --- | --- |
| breton | 82.4% | 79.6% to 85.1% | 220 |
| cornish | 82.9% | 79.8% to 85.9% | 220 |
| english | 92.0% | 90.1% to 93.9% | 760 |
| irish | 86.6% | 83.8% to 89.3% | 280 |
| manx | 72.3% | 69.1% to 75.3% | 220 |
| scots-gaelic | 83.8% | 80.7% to 86.6% | 280 |
| welsh | 89.2% | 87.0% to 91.2% | 280 |

## Failure examples

Examples come only from items published in `samples/`.

### blas/lesson_exercises

No public failure examples for this test.

### blas/morphology

- `blas-morph:manx:number_ordinal:gv-num-12` score 0.00
  - Prompt: Language: Manx Task: Give the ordinal numeral for the number below: the ordinal ('first', 'second', ...), including the definite article yn as it stands before the ordinal. Number: 12 (twelve) Reply with the answer on one line, in this exa…
  - Expected: yn nah jeig
  - Model output: ANSWER: yn nah yeig
- `blas-morph:scots-gaelic:copula:cop-gd-empha-04` score 0.00
  - Prompt: Language: Scottish Gaelic Task: Fill in the blank with the copula word (or copula particle) that the sentence needs. Write only the missing word(s). Sentence: ___ do Dhia a bhuineas slàinte. English: Salvation is God's affair. Reply with t…
  - Expected: 'S ann
  - Model output: ANSWER: Is ann
- `blas-morph:scots-gaelic:number_counting:gd-num-2` score 0.00
  - Prompt: Language: Scottish Gaelic Task: Give the counting numeral for the number below: the form used when counting aloud (not before a noun). Number: 2 (two) Reply with the answer on one line, in this exact form: ANSWER: <answer>
  - Expected: dhà
  - Model output: ANSWER: a dhà

### blas/round_trip

- `blas-round_trip-cornish-kw-sent-tat-1830` score 0.16
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Kas yw genev an traow na.
  - Expected: Kas yw genev an traow na.
  - Model output: Yma kas dhymm orth an taklow-na.
  - Pivot text: I hate those things.
- `blas-round_trip-manx-gv-sent-parallel-4693` score 0.20
  - Prompt: Translate this Manx sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Manx: Va mee sheiltyn dy darragh eh.
  - Expected: Va mee sheiltyn dy darragh eh.
  - Model output: Smooinee mee dy jig eh.
  - Pivot text: I thought he would come.
- `blas-round_trip-manx-gv-sent-parallel-6412` score 0.43
  - Prompt: Translate this Manx sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Manx: Nee eh costal queig keead stiagh as magh.
  - Expected: Nee eh costal queig keead stiagh as magh.
  - Model output: Nee eh costal mysh queig cheead.
  - Pivot text: It will cost about five hundred.

### blas/translation

- `blas-translation-scots-gaelic-gd-sent-0223-from_english` score 0.15
  - Prompt: Translate this English sentence into Scottish Gaelic. Reply with the Scottish Gaelic translation only, on one line, with no notes or explanation. English: He is a good carpenter.
  - Expected: Tha e na dheagh shaor.
  - Model output: ’S e saor math a th’ ann.
- `blas-translation-scots-gaelic-gd-sent-0255-from_english` score 0.25
  - Prompt: Translate this English sentence into Scottish Gaelic. Reply with the Scottish Gaelic translation only, on one line, with no notes or explanation. English: She used to drink beer.
  - Expected: B' àbhaist dhi leann òl.
  - Model output: Bhiodh i ag òl leann.
- `blas-translation-manx-gv-sent-parallel-15649-from_english` score 0.41
  - Prompt: Translate this English sentence into Manx. Reply with the Manx translation only, on one line, with no notes or explanation. English: Have you made my bed?
  - Expected: Vel shiu er chiartaghey my lhiabbee?
  - Model output: Vel oo er n'yannoo my lhiabbee?

### blas/tutor_accuracy

- `blas-tutor-irish-exd-51c5e10877` score 0.00
  - Prompt: You are a Irish language tutor checking a sentence written by a learner. Language: Irish The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: D'fhan muid i mbrú.
  - Model output: {"has_error":false,"error_span":"","correction":"","corrected_sentence":"Fhan muid i mbrú.","explanation":"The sentence is correct. “Fhan” is the past tense of “fan”, and “i” correctly eclipses “brú” to “mbrú”."}
- `blas-tutor-welsh-clean-sent-d6e9a5c833` score 0.00
  - Prompt: You are a Welsh language tutor checking a sentence written by a learner. Language: Welsh The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Pleidlais, felly, ar welliant 12.
  - Model output: {"has_error":true,"error_span":"Pleidlais","correction":"Pleidleisiais","corrected_sentence":"Pleidleisiais, felly, ar welliant 12.","explanation":"“Pleidlais” is the noun “vote”; “Pleidleisiais” is the verb form meaning “I voted”."}
- `blas-tutor-welsh-exd-d6fa3b01fb` score 0.00
  - Prompt: You are a Welsh language tutor checking a sentence written by a learner. Language: Welsh The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Byddai yna adar y tu allan er na fyddai merlod na defaid.
  - Model output: {"has_error":true,"error_span":"er i","correction":"er na","corrected_sentence":"Byddai yna adar y tu allan er na fyddai merlod na defaid.","explanation":"Use 'er na' ('although … not') before the finite verb 'fyddai'. 'Er i' requires a di…

### tonada/exercises

- `en-ch31-u04-complaint-return-lesson-s4@vi` score 0.00
  - Prompt: This is an exercise from an English course for Vietnamese speakers. The learner sees the instruction in Vietnamese; the answer is in English. Instruction (Vietnamese): Chọn từ mô tả tình trạng món hàng. Sentence: The item is ____, so I wou…
  - Expected: unopened
  - Model output: ANSWER: opened

### tonada/tutor_accuracy

- `en-ch36-r02-mgmt-recall-b-lesson-s4@vi:err` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: As long as the dependencies are clear, the prototype staying on schedule. Decide …
  - Expected: As long as the dependencies are clear, the prototype stays on schedule.
  - Model output: {"has_error":true,"error_span":"staying","correction":"will stay","corrected_sentence":"As long as the dependencies are clear, the prototype will stay on schedule.","explanation":"“Staying” không thể tự làm động từ chính khi thiếu trợ động…
- `en-scr-ch05-u03-c1@vi:err` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: She starting at nine. Decide whether the sentence has an error. If it does, give …
  - Expected: She starts at nine.
  - Model output: {"has_error":true,"error_span":"starting","correction":"is starting","corrected_sentence":"She is starting at nine.","explanation":"Câu thiếu trợ động từ “is” trước “starting”. Thì hiện tại tiếp diễn cần cấu trúc “be + động từ-ing”."}
- `wikiedits-error-650a5d50ea9cc2eb3269@vi` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: Rice is a staple food of Mauritius. Decide whether the sentence has an error. If …
  - Expected: Rice is a staple food in Mauritius.
  - Model output: {"has_error":false,"error_span":"","correction":"","corrected_sentence":"Rice is a staple food of Mauritius.","explanation":"Câu đúng về ngữ pháp và cách dùng từ. Cụm “a staple food of Mauritius” diễn đạt rằng gạo là một loại lương thực ch…

## Tutor detail: blas/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 86.5%. Found 86.7%, fixed 86.5%, no over-correction 89.4%.

Explanation, judge-marked, not human-validated: 69.9% (95% interval 63.5% to 76.2%). Judge agreement 91.0%. Judge failures 17. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.

## Tutor detail: tonada/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 85.1%. Found 89.1%, fixed 85.1%, no over-correction 89.4%.

Explanation, judge-marked, not human-validated: 63.7% (95% interval 58.9% to 68.3%). Judge agreement 92.7%. Judge failures 17. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.
