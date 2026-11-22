# Teanga Bench report: thinkingmachines/inkling-2-mini

thinkingmachines/inkling-2-mini ran 4 of 4 tests with 1 epochs per item, and the run status is complete. The overall score is 50.6% (95% interval 47.9% to 53.2%), with each completed test weighted equally. The best test was tonada/tutor_accuracy at 73.1% and the weakest was blas/morphology at 39.2%. On the tutor test the rule-only headline is 42.8%, and the explanation score is 33.0% (judge-marked, not human-validated). The run cost $0.6569 against a cap of $3.00, of which $0.3040 was judge spend.

Run kind: live. Status: complete. Generated 2026-11-21T19:48:36+00:00.

## Suite: blas

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| morphology | 39.2% | 33.9% to 44.2% | 360 | $0.1405 |
| translation | 47.3% | 44.0% to 50.7% | 360 | $0.1004 |
| tutor_accuracy | 42.8% | 35.6% to 50.0% | 180 | $0.1444 |

## Suite: tonada

| Test | Score | 95% interval | Items | Cost (USD) |
| --- | --- | --- | --- | --- |
| tutor_accuracy | 73.1% | 68.1% to 77.8% | 360 | $0.2715 |

## By language

| Language | Score | 95% interval | Items |
| --- | --- | --- | --- |
| breton | 41.9% | 35.0% to 48.7% | 120 |
| cornish | 26.6% | 20.5% to 33.2% | 120 |
| english | 73.1% | 68.3% to 77.5% | 360 |
| irish | 54.7% | 48.3% to 61.0% | 180 |
| manx | 13.0% | 9.1% to 17.3% | 120 |
| scots-gaelic | 52.0% | 45.9% to 58.1% | 180 |
| welsh | 54.7% | 48.6% to 60.9% | 180 |

## Failure examples

Examples come only from items published in `samples/`.

### blas/morphology

- `blas-morph:breton:prepositional_pronoun:pp-br-ouzh:2pl` score 0.00
  - Prompt: Language: Breton Task: Give the prepositional pronoun (the preposition fused with a personal pronoun) for the slot below. Write the standard simple form, not an emphatic form. Preposition: ouzh (against, at, to) Slot: 2nd person plural, me…
  - Expected: ouzhoc'h
  - Model output: ANSWER: ouzhhoc'h
- `blas-morph:breton:verb_present:br-verb-kregiñ:2p` score 0.00
  - Prompt: Language: Breton Task: Give the present form of the verb for the person given. Write one word: the inflected verb form, with no pronoun, particle or auxiliary. Verb: kregiñ Meaning: to start Tense: present Person: 2nd person plural (severa…
  - Expected: krogit
  - Model output: ANSWER: kregit
- `blas-morph:cornish:noun_plural:kw-decl-breselores` score 0.00
  - Prompt: Language: Cornish Task: Give the plural (nominative plural) of the noun below. Noun: breselores Meaning: militant Gender: feminine Reply with the answer on one line, in this exact form: ANSWER: <answer>
  - Expected: breseloresow
  - Model output: ANSWER: breselores

### blas/translation

- `blas-translation-cornish-kw-sent-tat-3505-to_english` score 0.07
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Yth esa ev ow mires orthis.
  - Expected: He was looking at you.
  - Model output: Is he keeping this?
- `blas-translation-cornish-kw-sent-tat-1356-from_english` score 0.08
  - Prompt: Translate this English sentence into Cornish. Reply with the Cornish translation only, on one line, with no notes or explanation. English: Do you like dogs?
  - Expected: Yw da genes keun?
  - Model output: A yow plega y terys?
- `blas-translation-cornish-kw-sent-tat-3376-to_english` score 0.09
  - Prompt: Translate this Cornish sentence into English. Reply with the English translation only, on one line, with no notes or explanation. Cornish: Nyns o res dhyn gul henna.
  - Expected: We didn't need to do that.
  - Model output: Their names are good.

### blas/tutor_accuracy

- `blas-tutor-irish-clean-sent-9f6457b394` score 0.00
  - Prompt: You are a Irish language tutor checking a sentence written by a learner. Language: Irish The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: Tá sé tábhachtach nach sárófaí a gcearta daonna.
  - Model output: {"has_error": true, "error_span": "sárófaí", "correction": "shárófaí", "corrected_sentence": "Tá sé tábhachtach nach shárófaí a gcearta daonna.", "explanation": "After the negative particle \"nach\", the verb is lenited, so \"sárófaí\" sho…
- `blas-tutor-irish-exd-51c5e10877` score 0.00
  - Prompt: You are a Irish language tutor checking a sentence written by a learner. Language: Irish The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact erroneous substring a…
  - Expected: D'fhan muid i mbrú.
  - Model output: {"has_error": true, "error_span": "i mbrú", "correction": "i bhrú", "corrected_sentence": "Fhan muid i bhrú.", "explanation": "After the preposition \"i\", \"brú\" lenites, so it should be \"bhrú\"."}
- `blas-tutor-scots-gaelic-clean-ex-aa26e2dc62` score 0.00
  - Prompt: You are a Scottish Gaelic language tutor checking a sentence written by a learner. Language: Scottish Gaelic The sentence may contain one error, or it may already be correct. If it has an error, change only that one error: give the exact e…
  - Expected: Tha mi cinnteach gum biodh e toilichte.
  - Model output: {"has_error": true, "error_span": "gum biodh", "correction": "gum bi", "corrected_sentence": "Tha mi cinnteach gum bi e toilichte.", "explanation": "After \"Tha mi cinnteach\", the complement usually uses the future/optative \"gum bi\" (gu…

### tonada/tutor_accuracy

- `en-ch15-contrast-pt-lesson-s3@pt-BR:err` score 0.00
  - Prompt: A learner of English whose first language is Portuguese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: I have known him during 2019. Decide whether the sentence has an error. If it doe…
  - Expected: I have known him since 2019.
  - Model output: {"has_error": true, "error_span": "have known", "correction": "knew", "corrected_sentence": "I knew him during 2019.", "explanation": "\"During 2019\" indica um período passado concluído, então o passado simples é adequado, não o present p…
- `en-ch21-c-ja-d1@ja:err` score 0.00
  - Prompt: A learner of English whose first language is Japanese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: I have a little coins. Decide whether the sentence has an error. If it does, give t…
  - Expected: I have a few coins.
  - Model output: {"has_error": true, "error_span": "a little coins", "correction": "a few coins", "corrected_sentence": "I have a few coins.", "explanation": "可算名詞の複数形には「a little」ではなく「a few」を使います。「little」は不可算名詞や漠然とした少量で、複数の個別の硬貨には不適切です。"}
- `en-ch43-u02-dependent-prepositions-lesson-s4@vi:err` score 0.00
  - Prompt: A learner of English whose first language is Vietnamese wrote the English sentence below. The sentence may contain one error, or it may be correct. Sentence: She apologized on missing the tutorial. Decide whether the sentence has an error.…
  - Expected: She apologized for missing the tutorial.
  - Model output: {"has_error": true, "error_span": "on missing", "correction": "for missing", "corrected_sentence": "She apologized for missing the tutorial.", "explanation": "Cụm đúng phải là \"apologized for missing\" (xin lỗi vì đã...), không phải \"apo…

## Tutor detail: blas/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 42.8%. Found 45.6%, fixed 42.8%, no over-correction 55.6%.

Explanation, judge-marked, not human-validated: 33.0% (95% interval 26.3% to 40.2%). Judge agreement 98.7%. Judge failures 1. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.

## Tutor detail: tonada/tutor_accuracy

Headline (rule-only: found AND fixed AND no over-correction): 73.1%. Found 76.1%, fixed 73.1%, no over-correction 87.8%.

Explanation, judge-marked, not human-validated: 62.4% (95% interval 57.2% to 67.3%). Judge agreement 93.9%. Judge failures 14. Judges: deepseek/deepseek-v4.1-flash-1017, qwen/qwen3.8-flash.
