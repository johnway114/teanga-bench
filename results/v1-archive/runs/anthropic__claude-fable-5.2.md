# Teanga Bench report: anthropic/claude-fable-5.2

anthropic/claude-fable-5.2 ran 7 of 7 tests with 3 epochs per item, and the run status is complete. The overall score is 87.5% (95% interval 86.4% to 88.5%), with each completed test weighted equally. The best test was tonada/exercises at 99.5% and the weakest was blas/round_trip at 74.3%. On the tutor test the rule-only headline is 88.5%, and the explanation score is 78.5% (judge-marked, not human-validated). The run cost $46.32 against a cap of $90.00, of which $0.7903 was judge spend.

Run kind: live. Status: complete. Generated 2026-11-16T06:03:04+00:00.

## Suite: blas

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| lesson_exercises | 98.5% | 97.1% to 99.5% | 360 | $3.96 |
| morphology | 94.1% | 91.7% to 96.2% | 360 | $6.18 |
| round_trip | 74.3% | 71.7% to 77.0% | 240 | $7.62 |
| translation | 75.1% | 72.5% to 77.6% | 360 | $6.24 |
| tutor_accuracy | 88.5% | 84.1% to 92.4% | 180 | $7.79 |

## Suite: tonada

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| exercises | 99.5% | 98.8% to 100.0% | 400 | $3.67 |
| tutor_accuracy | 82.6% | 78.6% to 86.2% | 360 | $10.86 |

## By language

| Language | Score | 95% interval | Items |
| --- | --- | --- | --- |
| breton | 83.4% | 80.9% to 85.9% | 220 |
| cornish | 86.3% | 83.5% to 89.0% | 220 |
| english | 91.0% | 89.0% to 92.9% | 760 |
| irish | 89.8% | 87.5% to 92.0% | 280 |
| manx | 74.8% | 71.5% to 77.9% | 220 |
| scots-gaelic | 86.6% | 84.0% to 89.2% | 280 |
| welsh | 91.5% | 89.4% to 93.4% | 280 |

## Failure examples

Examples come only from items published in `samples/`.

### blas/lesson_exercises

No public failure examples for this test.

### blas/morphology

- `blas-morph:manx:number_ordinal:gv-num-12` score 0.00
  - Prompt: Language: Manx Task: Give the ordinal numeral for the number below: the ordinal ('first', 'second', ...), including the definite article yn as it stands before the ordinal. Number: 12 (twelve) Reply with the answer on one line, in this exa…
  - Expected: yn nah jeig
  - Model output: ANSWER: yn daa-yeigoo
- `blas-morph:scots-gaelic:number_counting:gd-num-2` score 0.00
  - Prompt: Language: Scottish Gaelic Task: Give the counting numeral for the number below: the form used when counting aloud (not before a noun). Number: 2 (two) Reply with the answer on one line, in this exact form: ANSWER: <answer>
  - Expected: dhà
  - Model output: ANSWER: a dhà

### blas/round_trip

- `blas-round_trip-manx-gv-sent-parallel-6412` score 0.22
  - Prompt: Translate this Manx sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Manx: Nee eh costal queig keead stiagh as magh.
  - Expected: Nee eh costal queig keead stiagh as magh.
  - Model output: Costee eh mysh queig cheead, ny smoo ny ny sloo.
  - Pivot text: It will cost about five hundred, more or less.
- `blas-round_trip-cornish-kw-sent-tat-2363` score 0.27
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: My re bia owth oberi ena rag tri mis.
  - Expected: My re bia owth oberi ena rag tri mis.
  - Model output: Yth esen vy ow kweytha ena nans o tri mis.
  - Pivot text: I had been working there for three months.
- `blas-round_trip-cornish-kw-sent-tat-1830` score 0.26
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Kas yw genev an traow na.
  - Expected: Kas yw genev an traow na.
  - Model output: My a gas an taclow na.
  - Pivot text: I hate those things.

### blas/translation

- `blas-translation-scots-gaelic-gd-sent-0223-from_english` score 0.15
  - Prompt: Translate this English sentence into Scottish Gaelic. Reply with the Scottish Gaelic translation only, on one line, with no notes or explanation. English: He is a good carpenter.
  - Expected: Tha e na dheagh shaor.
  - Model output: 'S e saor math a th' ann.
- `blas-translation-manx-gv-sent-parallel-4509-from_english` score 0.18
  - Prompt: Translate this English sentence into Manx. Reply with the Manx translation only, on one line, with no notes or explanation. English: I don't know where to turn.
  - Expected: Cha nel fys aym cre dy yannoo.
  - Model output: Cha s'aym c'raad dy hyndaa.
- `blas-translation-manx-gv-sent-parallel-15649-from_english` score 0.41
  - Prompt: Translate this English sentence into Manx. Reply with the Manx translation only, on one line, with no notes or explanation. English: Have you made my bed?
  - Expected: Vel shiu er chiartaghey my lhiabbee?
  - Model output: Vel oo er n'yannoo my lhiabbee?

### blas/tutor_accuracy

- `blas-tutor-welsh-exd-d6fa3b01fb` score 0.00
  - Prompt: You are a Welsh language tutor checking a sentence written by a learner. Language: Welsh The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Byddai yna adar y tu allan er na fyddai merlod na defaid.
  - Model output: {"has_error": true, "error_span": "er i", "correction": "er na", "corrected_sentence": "Byddai yna adar y tu allan er na fyddai merlod na defaid.", "explanation": "A negative clause after 'er' with a conjugated verb takes the negative part…
- `blas-tutor-welsh-typo-6085cad894` score 0.00
  - Prompt: You are a Welsh language tutor checking a sentence written by a learner. Language: Welsh The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Geiriadur termau sy'n ymwneud â therapi galwedigaethol gan Delyth Prys a Owain Lloyd Davies (Golygyddion) yw Termau Therapi Galwedigaethol.
  - Model output: {"has_error": true, "error_span": "a Owain", "correction": "ac Owain", "corrected_sentence": "GGeiriadur termau sy'n ymwneud â therapi galwedigaethol gan Delyth Prys ac Owain Lloyd Davies (Golygyddion) yw Termau Therapi Galwedigaethol.", "…

### tonada/exercises

No public failure examples for this test.

### tonada/tutor_accuracy

- `wikiedits-error-22708bcbf22759d8f5f0@vi` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: It the region's major industrial and economic hub, home to some of Romania's larg…
  - Expected: It is the region's major industrial and economic hub, home to some of Romania's largest companies.
  - Model output: {"has_error": true, "error_span": "It the", "correction": "It is the", "corrected_sentence": "It is the region's major industrial and economic hub, home to some of Romania's largest companies.", "explanation": "Câu thiếu động từ \"is\" sau…
- `wikiedits-error-650a5d50ea9cc2eb3269@vi` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: Rice is a staple food of Mauritius. Decide whether the sentence has an error. If …
  - Expected: Rice is a staple food in Mauritius.
  - Model output: {"has_error": false, "error_span": "", "correction": "", "corrected_sentence": "Rice is a staple food of Mauritius.", "explanation": "Câu này đúng: chủ ngữ không đếm được \"Rice\" đi với động từ số ít \"is\", và cụm \"a staple food of Maur…
- `wikiedits-error-c508bc8d60aa33ba26be@pt-BR` score 0.00
  - Prompt: A learner of English whose first language is Portuguese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: He served as the Registrar of the International Court of Justice from 2000 to 201…
  - Expected: He served as Registrar of the International Court of Justice from 2000 to 2019.
  - Model output: {"has_error": false, "error_span": "", "correction": "", "corrected_sentence": "He served as the Registrar of the International Court of Justice from 2000 to 2019.", "explanation": "A frase está correta: \"served as\" indica a função exerc…

## Tutor detail: blas/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 88.5%. Found 88.5%, fixed 88.5%, no over-correction 93.0%.

Explanation, judge-marked, not human-validated: 78.5% (95% interval 72.9% to 84.1%). Judge agreement 93.5%. Judge failures 32. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.

## Tutor detail: tonada/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 82.6%. Found 85.9%, fixed 82.6%, no over-correction 89.2%.

Explanation, judge-marked, not human-validated: 63.7% (95% interval 58.8% to 68.4%). Judge agreement 91.8%. Judge failures 31. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.
