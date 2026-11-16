# Teanga Bench report: anthropic/claude-haiku-5.5

anthropic/claude-haiku-5.5 ran 7 of 7 tests with 3 epochs per item, and the run status is complete. The overall score is 72.1% (95% interval 70.7% to 73.6%), with each completed test weighted equally. The best test was tonada/exercises at 98.3% and the weakest was blas/translation at 57.9%. On the tutor test the rule-only headline is 66.9%, and the explanation score is 59.6% (judge-marked, not human-validated). The run cost $1.90 against a cap of $3.00, of which $0.7522 was judge spend.

Run kind: live. Status: complete. Generated 2026-11-16T01:49:22+00:00.

## Suite: blas

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| lesson_exercises | 87.5% | 84.4% to 90.5% | 360 | $0.1307 |
| morphology | 65.3% | 60.9% to 69.4% | 360 | $0.2222 |
| round_trip | 58.0% | 54.8% to 61.2% | 240 | $0.2146 |
| translation | 57.9% | 55.1% to 60.9% | 360 | $0.1536 |
| tutor_accuracy | 66.9% | 60.9% to 72.6% | 180 | $0.5090 |

## Suite: tonada

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| exercises | 98.3% | 97.1% to 99.3% | 400 | $0.0760 |
| tutor_accuracy | 71.2% | 66.4% to 75.9% | 360 | $0.5912 |

## By language

| Language | Score | 95% interval | Items |
| --- | --- | --- | --- |
| breton | 60.8% | 56.8% to 64.6% | 220 |
| cornish | 60.5% | 56.3% to 64.4% | 220 |
| english | 84.8% | 82.4% to 87.0% | 760 |
| irish | 73.6% | 70.0% to 77.0% | 280 |
| manx | 44.9% | 41.2% to 48.6% | 220 |
| scots-gaelic | 73.2% | 69.7% to 76.7% | 280 |
| welsh | 82.7% | 79.8% to 85.5% | 280 |

## Failure examples

Examples come only from items published in `samples/`.

### blas/lesson_exercises

- `blx-manx-gv_flow_ch09_u02_grammar_v2-sc1` score 0.00
  - Prompt: This is a sentence-building exercise from the Manx course of a language-learning app. Arrange the tiles into the Manx phrase that means “fetch the cake”. Use the tiles in the right order (some tiles are decoys and do not belong in the phra…
  - Expected: cur lesh y verreen
  - Model output: ANSWER: verreen y lhaih

### blas/morphology

- `blas-morph:cornish:verb_imperative:kw-verb-bos:2p` score 0.00
  - Prompt: Language: Cornish Task: Give the imperative form of the verb for the person given. Write one word: the inflected verb form, with no pronoun, particle or auxiliary. Verb: bos Meaning: to be Tense: imperative Person: 2nd person plural (sever…
  - Expected: bedhewgh
  - Model output: ANSWER: bydewgh
- `blas-morph:manx:number_ordinal:gv-num-12` score 0.00
  - Prompt: Language: Manx Task: Give the ordinal numeral for the number below: the ordinal ('first', 'second', ...), including the definite article yn as it stands before the ordinal. Number: 12 (twelve) Reply with the answer on one line, in this exa…
  - Expected: yn nah jeig
  - Model output: ANSWER: yn dooiney as jeih
- `blas-morph:manx:prepositional_pronoun:pp-gv-er:3sg_fem` score 0.00
  - Prompt: Language: Manx Task: Give the prepositional pronoun (the preposition fused with a personal pronoun) for the slot below. Write the standard simple form, not an emphatic form. Preposition: er (on) Slot: 3rd person singular feminine, meaning …
  - Expected: urree
  - Model output: ANSWER: urrey

### blas/round_trip

- `blas-round_trip-manx-gv-sent-parallel-2423` score 0.19
  - Prompt: Translate this Manx sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Manx: Dreill eh smaght er eh hene.
  - Expected: Dreill eh smaght er eh hene.
  - Model output: Ta'n lhean gheddyn hene.
  - Pivot text: A net catches itself.
- `blas-round_trip-cornish-kw-sent-tat-1830` score 0.20
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Kas yw genev an traow na.
  - Expected: Kas yw genev an traow na.
  - Model output: Yw an tra na ganso?
  - Pivot text: Does he have that thing?
- `blas-round_trip-manx-gv-sent-parallel-4693` score 0.16
  - Prompt: Translate this Manx sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Manx: Va mee sheiltyn dy darragh eh.
  - Expected: Va mee sheiltyn dy darragh eh.
  - Model output: Va aggle orrym jeh shen.
  - Pivot text: I was afraid of it.

### blas/translation

- `blas-translation-cornish-kw-sent-tat-1356-from_english` score 0.06
  - Prompt: Translate this English sentence into Cornish. Reply with the Cornish translation only, on one line, with no notes or explanation. English: Do you like dogs?
  - Expected: Yw da genes keun?
  - Model output: A wra ta hwithra kiow?
- `blas-translation-manx-gv-sent-parallel-15295-from_english` score 0.12
  - Prompt: Translate this English sentence into Manx. Reply with the Manx translation only, on one line, with no notes or explanation. English: I shall come back at ten o'clock at the latest.
  - Expected: Higym er-ash dyn s'anmee na jeih er y chlag.
  - Model output: Bee mee er tilgey ec yn dean cloc, ny smoo.
- `blas-translation-manx-gv-sent-parallel-15649-from_english` score 0.13
  - Prompt: Translate this English sentence into Manx. Reply with the Manx translation only, on one line, with no notes or explanation. English: Have you made my bed?
  - Expected: Vel shiu er chiartaghey my lhiabbee?
  - Model output: Ta oo er n-jannoo my leaby?

### blas/tutor_accuracy

- `blas-tutor-irish-clean-sent-9f6457b394` score 0.00
  - Prompt: You are a Irish language tutor checking a sentence written by a learner. Language: Irish The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Tá sé tábhachtach nach sárófaí a gcearta daonna.
  - Model output: {"has_error": true, "error_span": "sárófaí", "correction": "sárófar", "corrected_sentence": "Tá sé tábhachtach nach sárófar a gcearta daonna.", "explanation": "The conditional 'sárófaí' (would be violated) expresses a hypothetical, but the…
- `blas-tutor-scots-gaelic-exd-5821a3d892` score 0.00
  - Prompt: You are a Scottish Gaelic language tutor checking a sentence written by a learner. Language: Scottish Gaelic The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact e…
  - Expected: Tha biadh anns a' chidsin.
  - Model output: {"has_error": true, "error_span": "a' cidsin", "correction": "a' chidsin", "corrected_sentence": "Tha biadh anns a' chidsin.", "explanation": "After the article a' (here used with the preposition anns, 'in'), a feminine noun beginning with…
- `blas-tutor-scots-gaelic-exd-6e0581d3d2` score 0.00
  - Prompt: You are a Scottish Gaelic language tutor checking a sentence written by a learner. Language: Scottish Gaelic The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact e…
  - Expected: Cha tèid agam air deagh Fhraingis a sgrìobhadh.
  - Model output: {"has_error": true, "error_span": "deagh Fraingis", "correction": "deagh Fhraingis", "corrected_sentence": "Cha tèid agam air deagh Fhraingis a sgrìobhadh.", "explanation": "The adjective 'deagh' (good) lenites the noun that follows it, so…

### tonada/exercises

- `en-ch12-u06-recall-plans-and-health-lesson-s4@ja` score 0.00
  - Prompt: This is an exercise from an English course for Japanese speakers. The learner sees the instruction in Japanese; the answer is in English. Instruction (Japanese): 空欄に入る語句を選びましょう。 Sentence: I'm going to ____ the doctor about my cough tomorro…
  - Expected: ask
  - Model output: ANSWER: meet

### tonada/tutor_accuracy

- `en-ch07-c-vi-d4@vi:err` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: We are at board now. Decide whether the sentence has an error. If it does, give t…
  - Expected: We are on board now.
  - Model output: {"has_error": true, "error_span": "at board", "correction": "on board", "corrected_sentence": "We are on board now.", "explanation": "Cụm từ đúng là \"on board\" (trên máy bay, tàu hoặc phương tiện giao thông), không dùng \"at board\". Tiế…
- `en-ch21-k01-services-checkpoint-lesson-s4@ja:err` score 0.00
  - Prompt: A learner of English whose first language is Japanese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: I'm afraid the screen has stop working. Decide whether the sentence has an error. I…
  - Expected: I'm afraid the screen has stopped working.
  - Model output: {"has_error": true, "error_span": "has stop working", "correction": "has stopped working", "corrected_sentence": "I'm afraid the screen has stopped working.", "explanation": "現在完了形では過去分詞の「stopped」を使う必要があります。「has stop」は動詞の原形を使っているため誤りです。"}
- `en-ch35-c-vi-lesson-s4@vi:err` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: He is believes to be the owner. Decide whether the sentence has an error. If it d…
  - Expected: He is believed to be the owner.
  - Model output: {"has_error": true, "error_span": "is believes", "correction": "is believed", "corrected_sentence": "He is believed to be the owner.", "explanation": "Sau 'is' phải dùng quá khứ phân từ 'believed' để tạo thể bị động; 'believes' là dạng chi…

## Tutor detail: blas/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 66.9%. Found 68.1%, fixed 67.0%, no over-correction 76.5%.

Explanation, judge-marked, not human-validated: 59.6% (95% interval 53.1% to 65.8%). Judge agreement 95.2%. Judge failures 20. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.

## Tutor detail: tonada/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 71.2%. Found 73.8%, fixed 71.2%, no over-correction 88.5%.

Explanation, judge-marked, not human-validated: 62.2% (95% interval 57.4% to 66.8%). Judge agreement 92.8%. Judge failures 29. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.
