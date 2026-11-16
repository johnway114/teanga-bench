# Teanga Bench report: deepseek/deepseek-v4.1-flash-1017

deepseek/deepseek-v4.1-flash-1017 ran 7 of 7 tests with 3 epochs per item, and the run status is complete. The overall score is 81.0% (95% interval 79.8% to 82.3%), with each completed test weighted equally. The best test was tonada/exercises at 98.1% and the weakest was blas/round_trip at 68.5%. On the tutor test the rule-only headline is 76.1%, and the explanation was not scored (not_scored_same_family_as_judge). The run cost $1.14 against a cap of $1.50, of which $0.0000 was judge spend.

Run kind: live. Status: complete. Generated 2026-11-16T13:54:33+00:00.

## Suite: blas

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| lesson_exercises | 95.6% | 93.6% to 97.2% | 360 | $0.1947 |
| morphology | 87.0% | 83.9% to 90.1% | 360 | $0.3427 |
| round_trip | 68.5% | 65.7% to 71.1% | 240 | $0.3384 |
| translation | 68.8% | 66.2% to 71.4% | 360 | $0.0557 |
| tutor_accuracy | 76.1% | 70.6% to 81.3% | 180 | $0.1073 |

## Suite: tonada

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| exercises | 98.1% | 96.7% to 99.2% | 400 | $0.0228 |
| tutor_accuracy | 73.0% | 68.5% to 77.0% | 360 | $0.0757 |

## By language

| Language | Score | 95% interval | Items |
| --- | --- | --- | --- |
| breton | 77.2% | 74.1% to 80.4% | 220 |
| cornish | 78.9% | 75.2% to 82.2% | 220 |
| english | 85.5% | 83.3% to 87.6% | 760 |
| irish | 81.3% | 78.1% to 84.2% | 280 |
| manx | 68.6% | 65.3% to 71.8% | 220 |
| scots-gaelic | 81.8% | 78.6% to 84.7% | 280 |
| welsh | 86.7% | 84.1% to 89.1% | 280 |

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
- `blas-round_trip-cornish-kw-sent-tat-0552` score 0.37
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Mar pe dy’Sul hedhyw, ni a wrussa mos dhe byskessa.
  - Expected: Mar pe dy’Sul hedhyw, ni a wrussa mos dhe byskessa.
  - Model output: Mara pe hedhyw dy' Sul, ni a dhi dhe bysketa.
  - Pivot text: If today were Sunday, we would go fishing.
- `blas-round_trip-irish-ir-sent-2746` score 0.42
  - Prompt: Translate this Irish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Irish: Ba sa bhliain 1976 a cuireadh pionós an bháis ar ceal.
  - Expected: Ba sa bhliain 1976 a cuireadh pionós an bháis ar ceal.
  - Model output: Cuireadh deireadh le pionós an bháis i 1976.
  - Pivot text: The death penalty was abolished in 1976.

### blas/translation

- `blas-translation-scots-gaelic-gd-sent-0255-from_english` score 0.15
  - Prompt: Translate this English sentence into Scottish Gaelic. Reply with the Scottish Gaelic translation only, on one line, with no notes or explanation. English: She used to drink beer.
  - Expected: B' àbhaist dhi leann òl.
  - Model output: Bhiodh i ag òl lionn.
- `blas-translation-cornish-kw-sent-tat-1356-from_english` score 0.13
  - Prompt: Translate this English sentence into Cornish. Reply with the Cornish translation only, on one line, with no notes or explanation. English: Do you like dogs?
  - Expected: Yw da genes keun?
  - Model output: Osta fond a gŵn?
- `blas-translation-manx-gv-sent-parallel-15649-from_english` score 0.41
  - Prompt: Translate this English sentence into Manx. Reply with the Manx translation only, on one line, with no notes or explanation. English: Have you made my bed?
  - Expected: Vel shiu er chiartaghey my lhiabbee?
  - Model output: Vel oo er n'yannoo my lhiabbee?

### blas/tutor_accuracy

- `blas-tutor-scots-gaelic-exd-6e0581d3d2` score 0.00
  - Prompt: You are a Scottish Gaelic language tutor checking a sentence written by a learner. Language: Scottish Gaelic The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact e…
  - Expected: Cha tèid agam air deagh Fhraingis a sgrìobhadh.
  - Model output: {"has_error": true, "error_span": "deagh Fraingis", "correction": "deagh Fhraingis", "corrected_sentence": "Cha tèid agam air deagh Fhraingis a sgrìobhadh.", "explanation": "The adjective 'deagh' triggers lenition of the following noun, so…
- `blas-tutor-scots-gaelic-clean-ex-943a0622b9` score 0.00
  - Prompt: You are a Scottish Gaelic language tutor checking a sentence written by a learner. Language: Scottish Gaelic The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact e…
  - Expected: Nach robh iad aig a' mhuir tron oidhche?
  - Model output: {"has_error": true, "error_span": "aig a' mhuir", "correction": "aig a' mhuir", "corrected_sentence": "Nach robh iad aig a' mhuir tron oidhche?", "explanation": "The sentence is actually correct as written; the erroneous substring field is…
- `blas-tutor-scots-gaelic-exd-5821a3d892` score 0.00
  - Prompt: You are a Scottish Gaelic language tutor checking a sentence written by a learner. Language: Scottish Gaelic The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact e…
  - Expected: Tha biadh anns a' chidsin.
  - Model output: {"has_error": false, "error_span": "", "correction": "", "corrected_sentence": "Tha biadh anns a' cidsin.", "explanation": "The sentence is correct."}

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
  - Model output: {"has_error": true, "error_span": "at board", "correction": "on board", "corrected_sentence": "We are on board now.", "explanation": "Cụm đúng là “on board” (ở trên tàu/máy bay hoặc đã tham gia), không dùng “at board”."}
- `en-ch42-c-pt-d1@pt-BR:err` score 0.00
  - Prompt: A learner of English whose first language is Portuguese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: We are unsure whether will the deal close. Decide whether the sentence has an err…
  - Expected: We are unsure whether the deal will close.
  - Model output: {"has_error": true, "error_span": "will the deal close", "correction": "the deal will close", "corrected_sentence": "We are unsure whether the deal will close.", "explanation": "Em perguntas indiretas introduzidas por “whether”, não se faz…
- `en-scr-ch05-u03-c1@vi:err` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: She starting at nine. Decide whether the sentence has an error. If it does, give …
  - Expected: She starts at nine.
  - Model output: {"has_error": true, "error_span": "starting", "correction": "is starting", "corrected_sentence": "She is starting at nine.", "explanation": "Câu thiếu động từ to be trước động từ đuôi -ing. Cần dùng thì hiện tại tiếp diễn: “She is starting…

## Tutor detail: blas/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 76.1%. Found 76.1%, fixed 76.3%, no over-correction 88.1%.

Explanation, judge-marked, not human-validated: not scored (not_scored_same_family_as_judge).

## Tutor detail: tonada/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 73.0%. Found 76.7%, fixed 73.0%, no over-correction 88.0%.

Explanation, judge-marked, not human-validated: not scored (not_scored_same_family_as_judge).
