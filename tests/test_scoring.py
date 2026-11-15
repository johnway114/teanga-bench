"""Pure scorer tests: closed answers, tutor rules, judge verdicts, chrF++."""

import json

from teanga_bench.normalize import normalize_answer
from teanga_bench.scoring import (
    chrf_score,
    extract_translation,
    parse_judge_verdict,
    score_closed_answer,
    score_tutor_rules,
    tutor_headline,
)
from teanga_bench.span import single_replacement


def test_answer_line_is_case_and_space_insensitive():
    decision = score_closed_answer("Sure.\nANSWER:  An   Bhean. \n", {"accept": ["an bhean"]})
    assert decision.correct == 1
    assert decision.answer == normalize_answer("an bhean")


def test_any_accepted_variant_matches():
    metadata = {"accept": ["nghath", "ngath"]}
    assert score_closed_answer("ANSWER: ngath", metadata).correct == 1


def test_near_miss_and_prose_are_incorrect():
    assert score_closed_answer("ANSWER: an fhear", {"accept": ["an fear"]}).correct == 0
    assert score_closed_answer("The form is mo mháthair, I think.", {"accept": ["mo mháthair"]}).correct == 0


def test_curly_apostrophe_matches():
    assert score_closed_answer("ANSWER: m\u2019athair", {"accept": ["m'athair"]}).correct == 1


def _error_meta() -> dict:
    learner, gold = "CCosnaíonn sé.", "Cosnaíonn sé."
    span, correction = single_replacement(learner, gold)
    return {
        "has_error": True,
        "learner_sentence": learner,
        "error_span": span,
        "accept_spans": [span],
        "correction": correction,
        "accept_corrections": [correction],
        "acceptable_sentences": [gold],
    }


def _clean_meta(sentence: str = "Tá an cat anseo.") -> dict:
    return {
        "has_error": False,
        "learner_sentence": sentence,
        "error_span": "",
        "accept_spans": [""],
        "correction": "",
        "accept_corrections": [""],
        "acceptable_sentences": [sentence],
    }


def test_single_replacement_finds_a_doubled_letter():
    assert single_replacement("CCosnaíonn sé.", "Cosnaíonn sé.") == ("C", "")


def test_tutor_gold_edit_passes_the_rule_headline():
    meta = _error_meta()
    completion = json.dumps(
        {
            "has_error": True,
            "error_span": meta["error_span"],
            "correction": meta["correction"],
            "corrected_sentence": meta["acceptable_sentences"][0],
            "explanation": "A letter was doubled.",
        }
    )
    rules = score_tutor_rules("```json\n" + completion + "\n```", meta)
    assert (rules.parsed, rules.found, rules.fixed, rules.no_overcorrection) == (True, 1, 1, 1)
    assert tutor_headline(rules) == 1


def test_headline_ignores_the_explanation():
    """The headline is rule-only: an empty explanation does not change it."""
    meta = _error_meta()
    completion = json.dumps(
        {
            "has_error": True,
            "error_span": meta["error_span"],
            "correction": meta["correction"],
            "corrected_sentence": meta["acceptable_sentences"][0],
            "explanation": "",
        }
    )
    assert tutor_headline(score_tutor_rules(completion, meta)) == 1


def test_clean_sentence_fails_when_the_model_edits_it():
    completion = json.dumps(
        {
            "has_error": True,
            "error_span": "cat",
            "correction": "chat",
            "corrected_sentence": "Tá an chat anseo.",
            "explanation": "I lenited it.",
        }
    )
    rules = score_tutor_rules(completion, _clean_meta())
    assert rules.no_overcorrection == 0
    assert tutor_headline(rules) == 0


def test_clean_sentence_passes_when_reported_clean_and_unchanged():
    sentence = "Tá an cat anseo."
    completion = json.dumps(
        {"has_error": False, "error_span": "", "correction": "", "corrected_sentence": sentence, "explanation": "No error."}
    )
    rules = score_tutor_rules(completion, _clean_meta(sentence))
    assert (rules.found, rules.fixed, rules.no_overcorrection) == (1, 1, 1)
    assert tutor_headline(rules) == 1


def test_clean_sentence_fails_when_the_model_claims_an_error_but_leaves_it_unchanged():
    sentence = "Tá an cat anseo."
    completion = json.dumps(
        {"has_error": True, "error_span": "cat", "correction": "cat", "corrected_sentence": sentence, "explanation": "x"}
    )
    assert tutor_headline(score_tutor_rules(completion, _clean_meta(sentence))) == 0


def test_overcorrection_fails_the_headline():
    meta = _error_meta()
    completion = json.dumps(
        {
            "has_error": True,
            "error_span": meta["error_span"],
            "correction": meta["correction"],
            "corrected_sentence": "Cosnaíonn sí.",
            "explanation": "A letter was doubled.",
        }
    )
    rules = score_tutor_rules(completion, meta)
    assert (rules.found, rules.fixed, rules.no_overcorrection) == (1, 1, 0)
    assert tutor_headline(rules) == 0


def test_unparsed_tutor_reply_scores_zero():
    rules = score_tutor_rules("I think it is fine.", _error_meta())
    assert rules.parsed is False
    assert tutor_headline(rules) == 0


def test_judge_verdict_parsing():
    assert parse_judge_verdict('{"explanation_ok": true, "invented_extra_error": false, "reason": "ok"}') == (1, "ok")
    assert parse_judge_verdict('{"explanation_ok": true, "invented_extra_error": true, "reason": "extra"}')[0] == 0
    assert parse_judge_verdict('{"explanation_ok": false, "reason": "wrong"}')[0] == 0


def test_unusable_judge_reply_is_none_not_a_fail():
    assert parse_judge_verdict("Looks good to me.") is None
    assert parse_judge_verdict('{"reason": "no verdict key"}') is None


def test_chrf_is_one_for_an_exact_match_and_zero_for_nothing():
    assert chrf_score("Tá an cat anseo.", ["Tá an cat anseo."]) == 1.0
    assert chrf_score("", ["Tá an cat anseo."]) == 0.0
    assert chrf_score("anything", []) == 0.0


def test_chrf_partial_credit_is_between_zero_and_one():
    value = chrf_score("Tá an cat ann.", ["Tá an cat anseo."])
    assert 0.3 < value < 1.0


def test_chrf_takes_the_best_reference():
    refs = ["The dog is here.", "A completely different sentence"]
    assert chrf_score("The dog is here.", refs) == 1.0
    assert chrf_score("The dog is here.", list(reversed(refs))) == 1.0


def test_chrf_is_chrf_plus_plus():
    """Word order 2 makes the score depend on word n-grams, unlike plain chrF."""
    from sacrebleu.metrics import CHRF

    hyp, ref = "dog the here is", "the dog is here"
    plain = CHRF(word_order=0).sentence_score(hyp, [ref]).score / 100
    assert chrf_score(hyp, [ref]) != plain


def test_extract_translation_drops_labels():
    assert extract_translation("Translation: The cat.") == "The cat."
    assert extract_translation("ANSWER: The cat.") == "The cat."
    assert extract_translation('  "The cat."  ') == "The cat."
