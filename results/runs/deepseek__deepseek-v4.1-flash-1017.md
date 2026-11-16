# Teanga Bench report: deepseek/deepseek-v4.1-flash-1017

deepseek/deepseek-v4.1-flash-1017 ran 7 of 7 tests with 3 epochs per item, and the run status is complete. The overall score is 78.5% (95% interval 77.2% to 79.8%), with each completed test weighted equally. The best test was tonada/exercises at 97.9% and the weakest was blas/round_trip at 66.7%. On the tutor test the rule-only headline is 69.4%, and the explanation was not scored (not_scored_same_family_as_judge). The run cost $0.7675 against a cap of $1.50, of which $0.0000 was judge spend.

Run kind: live. Status: complete. Generated 2026-11-16T01:31:57+00:00.

## Suite: blas

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| lesson_exercises | 94.2% | 91.9% to 96.0% | 360 | $0.1515 |
| morphology | 80.6% | 77.1% to 84.2% | 360 | $0.1740 |
| round_trip | 66.7% | 63.7% to 69.6% | 240 | $0.2995 |
| translation | 68.2% | 65.6% to 70.9% | 360 | $0.0417 |
| tutor_accuracy | 69.4% | 63.3% to 75.0% | 180 | $0.0380 |

## Suite: tonada

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| exercises | 97.9% | 96.4% to 99.2% | 400 | $0.0145 |
| tutor_accuracy | 72.2% | 67.8% to 76.3% | 360 | $0.0485 |

## By language

| Language | Score | 95% interval | Items |
| --- | --- | --- | --- |
| breton | 73.7% | 70.2% to 77.0% | 220 |
| cornish | 76.5% | 72.5% to 80.1% | 220 |
| english | 85.1% | 82.8% to 87.2% | 760 |
| irish | 78.9% | 75.4% to 82.2% | 280 |
| manx | 64.2% | 60.6% to 67.8% | 220 |
| scots-gaelic | 78.3% | 74.9% to 81.4% | 280 |
| welsh | 84.6% | 81.6% to 87.3% | 280 |

## Failure examples

Examples come only from items published in `samples/`.

### blas/lesson_exercises

No public failure examples for this test.

### blas/morphology

- `blas-morph:cornish:verb_imperative:kw-verb-bos:2p` score 0.00
  - Prompt: Language: Cornish Task: Give the imperative form of the verb for the person given. Write one word: the inflected verb form, with no pronoun, particle or auxiliary. Verb: bos Meaning: to be Tense: imperative Person: 2nd person plural (sever…
  - Expected: bedhewgh
  - Model output: ANSWER: bydhowgh
- `blas-morph:manx:number_ordinal:gv-num-12` score 0.00
  - Prompt: Language: Manx Task: Give the ordinal numeral for the number below: the ordinal ('first', 'second', ...), including the definite article yn as it stands before the ordinal. Number: 12 (twelve) Reply with the answer on one line, in this exa…
  - Expected: yn nah jeig
  - Model output: ANSWER: yn daa yeigoo
- `blas-morph:scots-gaelic:copula:cop-gd-empha-04` score 0.00
  - Prompt: Language: Scottish Gaelic Task: Fill in the blank with the copula word (or copula particle) that the sentence needs. Write only the missing word(s). Sentence: ___ do Dhia a bhuineas slàinte. English: Salvation is God's affair. Reply with t…
  - Expected: 'S ann
  - Model output: ANSWER: Is

### blas/round_trip

- `blas-round_trip-cornish-kw-sent-tat-1830` score 0.26
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Kas yw genev an traow na.
  - Expected: Kas yw genev an traow na.
  - Model output: My a gas an taklow na.
  - Pivot text: I hate those things.
- `blas-round_trip-manx-gv-sent-parallel-4693` score 0.00
  - Prompt: Translate this Manx sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Manx: Va mee sheiltyn dy darragh eh.
  - Expected: Va mee sheiltyn dy darragh eh.
  - Model output: 
  - Pivot text: I was thinking that he would come.
- `blas-round_trip-breton-br-sent-0288` score 0.00
  - Prompt: Translate this Breton sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Breton: Hennezh n'eo ket ma c'hazh. Ma hini a zo gwenn e dreid.
  - Expected: Hennezh n'eo ket ma c'hazh. Ma hini a zo gwenn e dreid.
  - Model output: 
  - Pivot text: That is not my cat. Mine has white paws.

### blas/translation

- `blas-translation-scots-gaelic-gd-sent-0223-from_english` score 0.00
  - Prompt: Translate this English sentence into Scottish Gaelic. Reply with the Scottish Gaelic translation only, on one line, with no notes or explanation. English: He is a good carpenter.
  - Expected: Tha e na dheagh shaor.
  - Model output: 
- `blas-translation-manx-gv-sent-parallel-14165-from_english` score 0.00
  - Prompt: Translate this English sentence into Manx. Reply with the Manx translation only, on one line, with no notes or explanation. English: The house has stood a hundred and six years.
  - Expected: Ta'n thie er hassoo keead blein as shey.
  - Model output: 
- `blas-translation-scots-gaelic-gd-sent-0255-from_english` score 0.15
  - Prompt: Translate this English sentence into Scottish Gaelic. Reply with the Scottish Gaelic translation only, on one line, with no notes or explanation. English: She used to drink beer.
  - Expected: B' àbhaist dhi leann òl.
  - Model output: Bhiodh i ag òl lionn.

### blas/tutor_accuracy

- `blas-tutor-scots-gaelic-exd-6e0581d3d2` score 0.00
  - Prompt: You are a Scottish Gaelic language tutor checking a sentence written by a learner. Language: Scottish Gaelic The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact e…
  - Expected: Cha tèid agam air deagh Fhraingis a sgrìobhadh.
  - Model output: {"has_error": true, "error_span": "deagh Fraingis", "correction": "deagh Fhraingis", "corrected_sentence": "Cha tèid agam air deagh Fhraingis a sgrìobhadh.", "explanation": "The adjective 'deagh' triggers lenition of the following noun, so…
- `blas-tutor-irish-clean-sent-9f6457b394` score 0.00
  - Prompt: You are a Irish language tutor checking a sentence written by a learner. Language: Irish The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Tá sé tábhachtach nach sárófaí a gcearta daonna.
  - Model output: response was not a JSON object
- `blas-tutor-scots-gaelic-clean-ex-943a0622b9` score 0.00
  - Prompt: You are a Scottish Gaelic language tutor checking a sentence written by a learner. Language: Scottish Gaelic The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact e…
  - Expected: Nach robh iad aig a' mhuir tron oidhche?
  - Model output: {"has_error": true, "error_span": "aig a' mhuir", "correction": "aig a' mhuir", "corrected_sentence": "Nach robh iad aig a' mhuir tron oidhche?", "explanation": "The sentence is actually correct as written; the erroneous substring field is…

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

- `en-ch07-c-vi-d4@vi:err` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: We are at board now. Decide whether the sentence has an error. If it does, give t…
  - Expected: We are on board now.
  - Model output: response was not a JSON object
- `en-ch42-c-pt-d1@pt-BR:err` score 0.00
  - Prompt: A learner of English whose first language is Portuguese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: We are unsure whether will the deal close. Decide whether the sentence has an err…
  - Expected: We are unsure whether the deal will close.
  - Model output: {"has_error": true, "error_span": "will the deal close", "correction": "the deal will close", "corrected_sentence": "We are unsure whether the deal will close.", "explanation": "Em perguntas indiretas introduzidas por “whether”, não se faz…
- `en-scr-ch05-u03-c1@vi:err` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: She starting at nine. Decide whether the sentence has an error. If it does, give …
  - Expected: She starts at nine.
  - Model output: {"has_error": true, "error_span": "starting", "correction": "is starting", "corrected_sentence": "She is starting at nine.", "explanation": "Câu thiếu động từ to be trước động từ đuôi -ing. Cần dùng thì hiện tại tiếp diễn: “She is starting…

## Tutor detail: blas/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 69.4%. Found 69.4%, fixed 69.6%, no over-correction 80.6%.

Explanation, judge-marked, not human-validated: not scored (not_scored_same_family_as_judge).

## Tutor detail: tonada/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 72.2%. Found 75.6%, fixed 72.2%, no over-correction 86.7%.

Explanation, judge-marked, not human-validated: not scored (not_scored_same_family_as_judge).
