# Teanga Bench report: google/gemini-4-hydrogen

google/gemini-4-hydrogen ran 7 of 7 tests with 3 epochs per item, and the run status is complete. The overall score is 86.5% (95% interval 85.4% to 87.5%), with each completed test weighted equally. The best test was tonada/exercises at 99.0% and the weakest was blas/translation at 72.4%. On the tutor test the rule-only headline is 88.1%, and the explanation score is 76.4% (judge-marked, not human-validated). The run cost $51.05 against a cap of $65.00, of which $0.7024 was judge spend.

Run kind: live. Status: complete. Generated 2026-11-16T23:16:59+00:00.

## Suite: blas

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| lesson_exercises | 97.3% | 95.6% to 98.8% | 360 | $3.42 |
| morphology | 91.1% | 88.3% to 93.6% | 360 | $11.14 |
| round_trip | 73.0% | 70.4% to 75.6% | 240 | $13.72 |
| translation | 72.4% | 69.9% to 75.0% | 360 | $10.66 |
| tutor_accuracy | 88.1% | 83.5% to 92.2% | 180 | $4.95 |

## Suite: tonada

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| exercises | 99.0% | 98.0% to 99.8% | 400 | $2.14 |
| tutor_accuracy | 84.4% | 80.4% to 88.0% | 360 | $5.01 |

## By language

| Language | Score | 95% interval | Items |
| --- | --- | --- | --- |
| breton | 80.9% | 78.0% to 83.8% | 220 |
| cornish | 83.1% | 79.7% to 86.3% | 220 |
| english | 91.7% | 89.7% to 93.5% | 760 |
| irish | 87.3% | 84.5% to 89.9% | 280 |
| manx | 74.3% | 71.6% to 77.1% | 220 |
| scots-gaelic | 86.1% | 83.5% to 88.6% | 280 |
| welsh | 89.4% | 87.1% to 91.6% | 280 |

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
  - Model output: ANSWER: Is
- `blas-morph:cornish:verb_imperative:kw-verb-bos:2p` score 0.00
  - Prompt: Language: Cornish Task: Give the imperative form of the verb for the person given. Write one word: the inflected verb form, with no pronoun, particle or auxiliary. Verb: bos Meaning: to be Tense: imperative Person: 2nd person plural (sever…
  - Expected: bedhewgh
  - Model output: ANSWER: bydhewgh

### blas/round_trip

- `blas-round_trip-manx-gv-sent-parallel-6412` score 0.21
  - Prompt: Translate this Manx sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Manx: Nee eh costal queig keead stiagh as magh.
  - Expected: Nee eh costal queig keead stiagh as magh.
  - Model output: Cosnee eh queig cheead, ny smoo ny ny sloo.
  - Pivot text: It will cost five hundred, more or less.
- `blas-round_trip-cornish-kw-sent-tat-1830` score 0.26
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Kas yw genev an traow na.
  - Expected: Kas yw genev an traow na.
  - Model output: My a gas an taklow na.
  - Pivot text: I hate those things.
- `blas-round_trip-manx-gv-sent-parallel-4693` score 0.52
  - Prompt: Translate this Manx sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Manx: Va mee sheiltyn dy darragh eh.
  - Expected: Va mee sheiltyn dy darragh eh.
  - Model output: Smooinee mee dy darragh eh.
  - Pivot text: I thought he would come.

### blas/translation

- `blas-translation-scots-gaelic-gd-sent-0223-from_english` score 0.15
  - Prompt: Translate this English sentence into Scottish Gaelic. Reply with the Scottish Gaelic translation only, on one line, with no notes or explanation. English: He is a good carpenter.
  - Expected: Tha e na dheagh shaor.
  - Model output: 'S e saor math a th' ann.
- `blas-translation-manx-gv-sent-parallel-15649-from_english` score 0.41
  - Prompt: Translate this English sentence into Manx. Reply with the Manx translation only, on one line, with no notes or explanation. English: Have you made my bed?
  - Expected: Vel shiu er chiartaghey my lhiabbee?
  - Model output: Vel oo er n'yannoo my lhiabbee?
- `blas-translation-breton-br-sent-0397-from_english` score 0.44
  - Prompt: Translate this English sentence into Breton. Reply with the Breton translation only, on one line, with no notes or explanation. English: I'm from Australia.
  - Expected: Dont a ran eus Aostralia.
  - Model output: Eus Aostralia on.

### blas/tutor_accuracy

- `blas-tutor-welsh-exd-facf492c47` score 0.00
  - Prompt: You are a Welsh language tutor checking a sentence written by a learner. Language: Welsh The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: y llyfr sydd ar y bwrdd
  - Model output: {"has_error": true, "error_span": "y llyfr mae", "correction": "mae'r llyfr", "corrected_sentence": "mae'r llyfr ar y bwrdd", "explanation": "In Welsh, a normal declarative sentence follows Verb-Subject-Object (VSO) word order, so the verb…
- `blas-tutor-welsh-exd-d6fa3b01fb` score 0.00
  - Prompt: You are a Welsh language tutor checking a sentence written by a learner. Language: Welsh The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Byddai yna adar y tu allan er na fyddai merlod na defaid.
  - Model output: {"has_error": true, "error_span": "er i", "correction": "er na", "corrected_sentence": "Byddai yna adar y tu allan er na fyddai merlod na defaid.", "explanation": "After 'er' (although), a negative finite verb like 'fyddai' requires the ne…

### tonada/exercises

- `en-ch12-u06-recall-plans-and-health-lesson-s4@ja` score 0.00
  - Prompt: This is an exercise from an English course for Japanese speakers. The learner sees the instruction in Japanese; the answer is in English. Instruction (Japanese): 空欄に入る語句を選びましょう。 Sentence: I'm going to ____ the doctor about my cough tomorro…
  - Expected: ask
  - Model output: ANSWER: call
- `en-ch31-u04-complaint-return-lesson-s4@vi` score 0.00
  - Prompt: This is an exercise from an English course for Vietnamese speakers. The learner sees the instruction in Vietnamese; the answer is in English. Instruction (Vietnamese): Chọn từ mô tả tình trạng món hàng. Sentence: The item is ____, so I wou…
  - Expected: unopened
  - Model output: ANSWER: opened

### tonada/tutor_accuracy

- `en-ch36-r02-mgmt-recall-b-lesson-s4@vi:err` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: As long as the dependencies are clear, the prototype staying on schedule. Decide …
  - Expected: As long as the dependencies are clear, the prototype stays on schedule.
  - Model output: {"has_error": true, "error_span": "staying", "correction": "is staying", "corrected_sentence": "As long as the dependencies are clear, the prototype is staying on schedule.", "explanation": "Mệnh đề chính thiếu động từ chia thì trước phân …
- `en-scr-ch05-u03-c1@vi:err` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: She starting at nine. Decide whether the sentence has an error. If it does, give …
  - Expected: She starts at nine.
  - Model output: {"has_error": true, "error_span": "starting", "correction": "is starting", "corrected_sentence": "She is starting at nine.", "explanation": "Câu này thiếu động từ to be \"is\" trước động từ thêm \"-ing\" để tạo thành thì hiện tại tiếp diễn…
- `wikiedits-error-650a5d50ea9cc2eb3269@vi` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: Rice is a staple food of Mauritius. Decide whether the sentence has an error. If …
  - Expected: Rice is a staple food in Mauritius.
  - Model output: {"has_error": false, "error_span": "", "correction": "", "corrected_sentence": "Rice is a staple food of Mauritius.", "explanation": "Câu này đúng về mặt ngữ pháp và cách diễn đạt. Danh từ không đếm được \"Rice\" đi với động từ số ít \"is\…

## Tutor detail: blas/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 88.1%. Found 88.3%, fixed 88.1%, no over-correction 91.3%.

Explanation, judge-marked, not human-validated: 76.4% (95% interval 70.4% to 82.0%). Judge agreement 95.1%. Judge failures 29. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.

## Tutor detail: tonada/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 84.4%. Found 88.3%, fixed 84.4%, no over-correction 89.6%.

Explanation, judge-marked, not human-validated: 63.9% (95% interval 59.2% to 68.3%). Judge agreement 92.2%. Judge failures 35. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.
