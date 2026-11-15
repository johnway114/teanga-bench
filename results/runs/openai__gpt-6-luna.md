# Teanga Bench report: openai/gpt-6-luna

openai/gpt-6-luna ran 7 of 7 tests with 3 epochs per item, and the run status is complete. The overall score is 78.0% (95% interval 76.6% to 79.3%), with each completed test weighted equally. The best test was tonada/exercises at 98.0% and the weakest was blas/round_trip at 64.5%. On the tutor test the rule-only headline is 71.3%, and the explanation score is 57.4% (judge-marked, not human-validated). The run cost $1.30 against a cap of $3.00, of which $0.5902 was judge spend.

Run kind: live. Status: complete. Generated 2026-11-15T23:00:41+00:00.

## Suite: blas

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| lesson_exercises | 93.6% | 91.1% to 95.7% | 360 | $0.0545 |
| morphology | 80.5% | 76.9% to 84.1% | 360 | $0.1707 |
| round_trip | 64.5% | 61.7% to 67.4% | 240 | $0.1444 |
| translation | 68.0% | 65.4% to 70.8% | 360 | $0.1218 |
| tutor_accuracy | 71.3% | 65.4% to 77.0% | 180 | $0.2837 |

## Suite: tonada

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| exercises | 98.0% | 96.5% to 99.2% | 400 | $0.0333 |
| tutor_accuracy | 70.0% | 65.3% to 74.4% | 360 | $0.7755 |

## By language

| Language | Score | 95% interval | Items |
| --- | --- | --- | --- |
| breton | 72.6% | 68.8% to 76.1% | 220 |
| cornish | 70.0% | 66.1% to 73.9% | 220 |
| english | 84.0% | 81.7% to 86.2% | 760 |
| irish | 81.1% | 77.7% to 84.3% | 280 |
| manx | 66.9% | 63.6% to 70.0% | 220 |
| scots-gaelic | 78.4% | 75.0% to 81.8% | 280 |
| welsh | 83.5% | 80.6% to 86.2% | 280 |

## Failure examples

Examples come only from items published in `samples/`.

### blas/lesson_exercises

No public failure examples for this test.

### blas/morphology

- `blas-morph:cornish:verb_imperative:kw-verb-bos:2p` score 0.00
  - Prompt: Language: Cornish Task: Give the imperative form of the verb for the person given. Write one word: the inflected verb form, with no pronoun, particle or auxiliary. Verb: bos Meaning: to be Tense: imperative Person: 2nd person plural (sever…
  - Expected: bedhewgh
  - Model output: ANSWER: bysowgh
- `blas-morph:manx:verb_conditional:gv-verb-cur:dependent:2s` score 0.00
  - Prompt: Language: Manx Task: Give the conditional tense form of the verb: the dependent form (used after cha, nagh and the question particle). Write the verb form followed by the pronoun 'oo'. Verb: cur Meaning: to give, to put Tense: conditional …
  - Expected: derragh oo
  - Model output: ANSWER: deragh oo
- `blas-morph:scots-gaelic:copula:cop-gd-empha-04` score 0.00
  - Prompt: Language: Scottish Gaelic Task: Fill in the blank with the copula word (or copula particle) that the sentence needs. Write only the missing word(s). Sentence: ___ do Dhia a bhuineas slàinte. English: Salvation is God's affair. Reply with t…
  - Expected: 'S ann
  - Model output: ANSWER: Is ann

### blas/round_trip

- `blas-round_trip-cornish-kw-sent-tat-1830` score 0.17
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Kas yw genev an traow na.
  - Expected: Kas yw genev an traow na.
  - Model output: My a gas an taklow-na.
  - Pivot text: I hate those things.
- `blas-round_trip-manx-gv-sent-parallel-2423` score 0.19
  - Prompt: Translate this Manx sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Manx: Dreill eh smaght er eh hene.
  - Expected: Dreill eh smaght er eh hene.
  - Model output: Ren eh eh-hene y reirey.
  - Pivot text: He kept himself under control.
- `blas-round_trip-cornish-kw-sent-tat-0552` score 0.28
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Mar pe dy’Sul hedhyw, ni a wrussa mos dhe byskessa.
  - Expected: Mar pe dy’Sul hedhyw, ni a wrussa mos dhe byskessa.
  - Model output: Mar bije hedhyw Dy'Sul, ni a yje pesketa.
  - Pivot text: If today were Sunday, we would go fishing.

### blas/translation

- `blas-translation-scots-gaelic-gd-sent-0255-from_english` score 0.25
  - Prompt: Translate this English sentence into Scottish Gaelic. Reply with the Scottish Gaelic translation only, on one line, with no notes or explanation. English: She used to drink beer.
  - Expected: B' àbhaist dhi leann òl.
  - Model output: Bhiodh i ag òl leann.
- `blas-translation-cornish-kw-sent-tat-1356-from_english` score 0.26
  - Prompt: Translate this English sentence into Cornish. Reply with the Cornish translation only, on one line, with no notes or explanation. English: Do you like dogs?
  - Expected: Yw da genes keun?
  - Model output: A gar'ta keun?
- `blas-translation-manx-gv-sent-parallel-15649-from_english` score 0.41
  - Prompt: Translate this English sentence into Manx. Reply with the Manx translation only, on one line, with no notes or explanation. English: Have you made my bed?
  - Expected: Vel shiu er chiartaghey my lhiabbee?
  - Model output: Vel oo er n'yannoo my lhiabbee?

### blas/tutor_accuracy

- `blas-tutor-welsh-exd-73d43ee1db` score 0.00
  - Prompt: You are a Welsh language tutor checking a sentence written by a learner. Language: Welsh The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Bues i'n gweithio fel athro am bum mlynedd.
  - Model output: {"has_error":false,"error_span":"","correction":"","corrected_sentence":"Bues i'n gweithio fel athro am bum blynedd.","explanation":"The sentence is grammatically correct."}
- `blas-tutor-welsh-exd-d6fa3b01fb` score 0.00
  - Prompt: You are a Welsh language tutor checking a sentence written by a learner. Language: Welsh The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Byddai yna adar y tu allan er na fyddai merlod na defaid.
  - Model output: {"has_error":true,"error_span":"er i fyddai","correction":"er na fyddai","corrected_sentence":"Byddai yna adar y tu allan er na fyddai merlod na defaid.","explanation":"“Er na fyddai” means “although there would not be”; it correctly forms…
- `blas-tutor-welsh-exd-21c6c984df` score 0.00
  - Prompt: You are a Welsh language tutor checking a sentence written by a learner. Language: Welsh The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Cafodd ei anghofio gan bawb.
  - Model output: {"has_error":false,"error_span":"","correction":"","corrected_sentence":"Cafodd ei anghofio gan pawb.","explanation":"Mae’r frawddeg yn gywir: mae “Cafodd ei anghofio” yn ffurf oddefol, ac mae “gan bawb” yn gywir."}

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
  - Model output: {"has_error":true,"error_span":"board","correction":"the board","corrected_sentence":"We are at the board now.","explanation":"Cần dùng mạo từ “the” trước danh từ đếm được số ít “board” trong câu này."}
- `en-ch23-c-es-lesson-s4@es-419:err` score 0.00
  - Prompt: A learner of English whose first language is Spanish wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: He has taught at this school for 2021. Decide whether the sentence has an error. If …
  - Expected: He has taught at this school since 2021.
  - Model output: {"has_error":true,"error_span":"for 2021","correction":"since 2021","corrected_sentence":"He has taught at this school since 2021.","explanation":"Se usa “since” con un punto de inicio en el tiempo; “for” se usa con una duración."}
- `en-ch35-c-vi-lesson-s4@vi:err` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: He is believes to be the owner. Decide whether the sentence has an error. If it d…
  - Expected: He is believed to be the owner.
  - Model output: {"has_error":true,"error_span":"is believes","correction":"is believed","corrected_sentence":"He is believed to be the owner.","explanation":"Cụm “is believes” sai vì sau “is” cần dùng quá khứ phân từ trong cấu trúc bị động. Câu đúng là “i…

## Tutor detail: blas/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 71.3%. Found 72.2%, fixed 71.5%, no over-correction 82.6%.

Explanation, judge-marked, not human-validated: 57.4% (95% interval 50.6% to 64.2%). Judge agreement 93.2%. Judge failures 13. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.

## Tutor detail: tonada/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 70.0%. Found 73.5%, fixed 70.0%, no over-correction 87.0%.

Explanation, judge-marked, not human-validated: 58.6% (95% interval 53.7% to 63.4%). Judge agreement 91.9%. Judge failures 17. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.
