"""Takeaway sentences and the small statistics behind the site's charts.

Every chart on the research site opens with one sentence computed here from
the data. Nothing is hard-coded: the functions take plain numbers and names
and return plain text (the caller escapes it). The wording follows one rule
from the methodology: when two 95% ranges overlap, the gap may be chance, so
the sentence says "tied" or "not clear" rather than "better".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

MIN_ITEMS = 20  # no point is plotted from fewer items


@dataclass(frozen=True)
class Est:
    """A score with its 95% range and the number of items behind it."""

    score: float
    ci: tuple[float, float] | None = None
    n: int | None = None


Named = tuple[str, Est]


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def overlaps(a: Est, b: Est) -> bool:
    """True when the two 95% ranges overlap. Without a range a difference
    cannot be called clear, so a missing range counts as overlapping."""
    if not a.ci or not b.ci:
        return True
    return a.ci[0] <= b.ci[1] and b.ci[0] <= a.ci[1]


def names(items: Sequence[str]) -> str:
    """'A', 'A and B', 'A, B and C'."""
    items = list(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _by_score(items: Sequence[Named]) -> list[Named]:
    return sorted(items, key=lambda item: (-item[1].score, item[0]))


def _share(k: int, n: int, noun: str = "models") -> str:
    """'all 9 models' or '7 of 9 models'."""
    return f"all {n} {noun}" if k == n and n > 2 else f"{k} of {n} {noun}"


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def tie_groups(items: Sequence[Named]) -> list[list[str]]:
    """Group models from the top down. A group is its highest-scoring model
    and every model left whose 95% range overlaps that model's range."""
    left = _by_score(items)
    groups: list[list[str]] = []
    while left:
        top = left[0]
        members = [name for name, est in left if name == top[0] or overlaps(top[1], est)]
        groups.append(members)
        left = [item for item in left if item[0] not in members]
    return groups


def tied_with(name: str, items: Sequence[Named]) -> list[str]:
    """Every other model whose 95% range overlaps this model's, highest first."""
    own = dict(items)[name]
    return [other for other, est in _by_score(items) if other != name and overlaps(own, est)]


def leader_sentence(items: Sequence[Named]) -> str:
    """Who scores highest, and whether anyone is tied with them."""
    ranked = _by_score(items)
    if not ranked:
        return "No model has a complete result yet."
    lead, est = ranked[0]
    if len(ranked) == 1:
        return f"{lead} is the only model with a complete result: {pct(est.score)}."
    tied = tied_with(lead, ranked)
    if not tied:
        return f"{lead} scores highest ({pct(est.score)}) and is clearly ahead: no other model's 95% range overlaps its own."
    if len(tied) == len(ranked) - 1 and len(ranked) > 2:
        return (
            f"{lead} scores highest ({pct(est.score)}), but all {len(ranked)} models' 95% ranges overlap its own, "
            "so none is clearly ahead."
        )
    who = names(tied) if len(tied) <= 4 else f"{len(tied)} other models"
    return f"{lead} scores highest ({pct(est.score)}) but is tied with {who}: their 95% ranges overlap."


def matrix_sentence(tests: Sequence[tuple[str, Sequence[Named]]]) -> str:
    """Which model leads the most tests, and how many leads are ties."""
    tests = [(title, items) for title, items in tests if items]
    if not tests:
        return "No model has a complete result yet."
    models = {name for _, items in tests for name, _ in items}
    if len(models) == 1:
        (only,) = models
        weakest = min(tests, key=lambda t: (t[1][0][1].score, t[0]))
        return f"{only} is the only ranked model; its lowest score is in {weakest[0]} ({pct(weakest[1][0][1].score)})."
    wins: dict[str, int] = {}
    tied_tops = 0
    for _, items in tests:
        lead = _by_score(items)[0][0]
        wins[lead] = wins.get(lead, 0) + 1
        if tied_with(lead, items):
            tied_tops += 1
    most = max(wins.values())
    leaders = sorted(name for name, count in wins.items() if count == most)
    total = len(tests)
    verb = "has" if len(leaders) == 1 else "each have"
    head = f"{names(leaders)} {verb} the highest score in {most} of {total} tests"
    if tied_tops == 0:
        return f"{head}, and every top score is clear of the next model's 95% range."
    if tied_tops == total:
        return f"{head}, but in every test the top score is tied with at least one other model (95% ranges overlap)."
    return f"{head}, but in {tied_tops} of the {total} tests the top score is tied with at least one other model (95% ranges overlap)."


def profile_sentence(model: str, tests: Sequence[tuple[str, Sequence[Named]]]) -> str:
    """Where one model stands against the others, test by test."""
    rows = []
    for title, items in tests:
        own = dict(items).get(model)
        if own is None:
            continue
        ranked = _by_score(items)
        rank = 1 + sum(1 for _, est in ranked if est.score > own.score)
        best = ranked[0][1]
        # A first place is a tie when another model's range overlaps it; a lower place when it overlaps the top.
        tied = (
            any(other != model and overlaps(own, est) for other, est in items) if rank == 1 else overlaps(own, best)
        )
        rows.append((title, rank, len(ranked), own, best, tied))
    if not rows:
        return f"{model} has no complete test result yet."
    if all(row[2] == 1 for row in rows):
        top = max(rows, key=lambda r: (r[3].score, r[0]))
        return f"{model} is the only ranked model, so there is nothing to compare yet; its highest score is in {top[0]} ({pct(top[3].score)})."
    high = min(rows, key=lambda r: (r[1], -r[3].score, r[0]))
    low = max(rows, key=lambda r: (r[1], r[4].score - r[3].score, r[0]))
    ties = sum(1 for r in rows if r[5])
    if high[1] == low[1]:
        text = f"{model} ranks {ordinal(high[1])} in every test"
        if not ties:
            return text + (", clear of every other model's 95% range." if high[1] == 1 else ", clear of the top model's 95% range.")
        who = "another model is tied with it" if high[1] == 1 else "it is tied with the top"
        scope = "every one" if ties == len(rows) else f"{ties} of them"
        return f"{text}, but in {scope} {who} (95% ranges overlap)."

    def place(row, gap: bool) -> str:
        title, rank, n, own, best, tied = row
        text = f"{title} ({ordinal(rank)} of {n}"
        if rank > 1 and gap:
            text += f", {(best.score - own.score) * 100:.1f} points below the top"
        if tied:
            text += ", tied with another model" if rank == 1 else " but tied with it" if gap else ", tied with the top"
        return text + ")"

    note = "; tied means the 95% ranges overlap" if high[5] or low[5] else ""
    return f"{model} places best in {place(high, False)} and worst in {place(low, True)}{note}."


def level_sentence(levels: Sequence[str], models: Sequence[tuple[str, dict[str, Est]]]) -> str:
    """Do scores fall from the easiest plotted level to the hardest?"""
    if len(levels) < 2:
        return f"Fewer than two levels have {MIN_ITEMS} or more items, so there is no trend to read."
    first, last = levels[0], levels[-1]
    pairs = [(name, by[first], by[last]) for name, by in models if first in by and last in by]
    if not pairs:
        return "No model has scores at both ends of the level range."
    lower = [(name, a, b) for name, a, b in pairs if b.score < a.score]
    clear = [name for name, a, b in lower if not overlaps(a, b)]
    if len(pairs) == 1:
        name, a, b = pairs[0]
        direction = "lower" if b.score < a.score else "higher" if b.score > a.score else "the same"
        verdict = "the 95% ranges do not overlap" if not overlaps(a, b) else "the difference is not clear: the 95% ranges overlap"
        return f"{name} scores {direction} at {last} ({pct(b.score)}) than at {first} ({pct(a.score)}); {verdict}."
    if not lower:
        return f"No model scores lower at {last} than at {first}."
    head = _cap(f"{_share(len(lower), len(pairs))} score lower at {last} than at {first}")
    if not clear:
        return f"{head}, but none of these drops is clear: the 95% ranges overlap."
    return f"{head}; the drop is clear (95% ranges do not overlap) for {len(clear)} of them."


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def compare_sentence(
    models: Sequence[tuple[str, dict[str, Est]]],
    label: Callable[[str], str],
    noun: str,
    *,
    high_word: str = "highest-scoring",
    low_word: str = "lowest-scoring",
) -> str:
    """Compare the highest and lowest category (by mean over models) and say
    for how many models the gap between them is clear."""
    keys = sorted({key for _, by in models for key in by})
    if len(keys) < 2:
        return f"Fewer than two {noun}s have {MIN_ITEMS} or more items, so there is nothing to compare."
    means = {key: _mean([by[key].score for _, by in models if key in by]) for key in keys}
    high = max(keys, key=lambda k: (means[k], k))
    low = min(keys, key=lambda k: (means[k], k))
    pairs = [(by[high], by[low]) for _, by in models if high in by and low in by]
    clear = sum(1 for a, b in pairs if not overlaps(a, b))
    n_items = {key: next((by[key].n for _, by in models if key in by and by[key].n), None) for key in (high, low)}

    def part(key: str) -> str:
        count = f", {n_items[key]} items" if n_items[key] else ""
        return f"{label(key)} ({pct(means[key])}{count})"

    lead = "For the one model" if len(models) == 1 else f"Averaged over {len(models)} models"
    head = f"{lead}, the {high_word} {noun} is {part(high)} and the {low_word} is {part(low)}"
    if len(pairs) == 1:
        return head + ("; the gap is clear (95% ranges do not overlap)." if clear else "; the gap is not clear: the 95% ranges overlap.")
    if clear == 0:
        return f"{head}; for every model the two 95% ranges overlap, so the gap is not clear."
    return f"{head}; the gap is clear (95% ranges do not overlap) for {_share(clear, len(pairs))}."


def direction_sentence(models: Sequence[tuple[str, Est, Est]]) -> str:
    """Into English against out of English, per model."""
    if not models:
        return "No model has scores in both directions yet."
    higher = [(name, a, b) for name, a, b in models if a.score > b.score]
    clear = [name for name, a, b in higher if not overlaps(a, b)]
    if len(models) == 1:
        name, a, b = models[0]
        verdict = "clear (95% ranges do not overlap)" if not overlaps(a, b) else "not clear: the 95% ranges overlap"
        word = "higher" if a.score > b.score else "lower"
        return f"{name} scores {word} translating into English ({pct(a.score)}) than out of English ({pct(b.score)}); the gap is {verdict}."
    if not higher:
        return "No model scores higher translating into English than out of English."
    head = _cap(f"{_share(len(higher), len(models))} score higher translating into English than out of English")
    if not clear:
        return f"{head}, but no gap is clear: the 95% ranges overlap."
    return f"{head}; the gap is clear (95% ranges do not overlap) for {len(clear)} of them."


TUTOR_STEPS = (
    ("found", "found the error"),
    ("fixed", "fixed it"),
    ("no_overcorrection", "changed nothing else"),
)


def tutor_sentence(models: Sequence[tuple[str, dict[str, float]]], explanations: Sequence[float]) -> str:
    """The weakest rule-marked step, and the judge-marked explanation apart."""
    if not models:
        return "No model has a complete tutor result yet."
    means = {
        key: _mean([parts[key] for _, parts in models if parts.get(key) is not None])
        for key, _ in TUTOR_STEPS
        if any(parts.get(key) is not None for _, parts in models)
    }
    if not means:
        return "The results hold no step-by-step tutor figures."
    words = dict(TUTOR_STEPS)
    weakest = min(means, key=lambda k: (means[k], k))
    strongest = max(means, key=lambda k: (means[k], k))
    lead = "For this model" if len(models) == 1 else f"Averaged over {len(models)} models"
    text = (
        f"{lead}, the weakest rule-marked step is ‘{words[weakest]}’ ({pct(means[weakest])}) "
        f"and the strongest is ‘{words[strongest]}’ ({pct(means[strongest])})"
    )
    if explanations:
        who = "the one model" if len(explanations) == 1 else f"the {len(explanations)} models"
        text += f"; the judge-marked explanation passes {pct(_mean(explanations))} on average for {who} with a comparable explanation score"
    return text + "."


def spread_sentence(items: Sequence[tuple[str, float]], what: str, fmt: Callable[[float], str], *, ratio: bool = False) -> str:
    """'<what> runs from <low> (<model>) to <high> (<model>)'."""
    if not items:
        return "No model has a complete result yet."
    ordered = sorted(items, key=lambda item: (item[1], item[0]))
    (low_name, low), (high_name, high) = ordered[0], ordered[-1]
    if len(ordered) == 1:
        return f"{low_name}: {what} {fmt(low)}."
    text = f"{what[0].upper()}{what[1:]} runs from {fmt(low)} ({low_name}) to {fmt(high)} ({high_name})"
    if ratio and low > 0:
        text += f", {high / low:.0f} times as much" if high / low >= 2 else f", {high / low:.1f} times as much"
    return text + "."


def group_sentence(averages: Sequence[tuple[str, float]], n_models: int, noun: str) -> str:
    """Highest and lowest group, averaged over models."""
    if not averages:
        return "No breakdown is available yet."
    ordered = sorted(averages, key=lambda item: (-item[1], item[0]))
    lead = "For the one ranked model" if n_models == 1 else f"Averaged over {n_models} models"
    if len(ordered) == 1:
        return f"{lead}, the only {noun} scores {pct(ordered[0][1])}."
    (high, hv), (low, lv) = ordered[0], ordered[-1]
    return f"{lead}, scores are highest for {high} ({pct(hv)}) and lowest for {low} ({pct(lv)})."


def value_sentence(items: Sequence[tuple[str, Est, float]]) -> str:
    """The cheapest model whose range overlaps the leader's. Items are
    (name, score, cost of a run)."""
    if not items:
        return "No model has a complete result yet."
    ranked = sorted(items, key=lambda item: (-item[1].score, item[2], item[0]))
    lead, lead_est, lead_cost = ranked[0]
    if len(ranked) == 1:
        return f"{lead} is the only ranked model: {pct(lead_est.score)} for ${lead_cost:,.2f}."
    level = [item for item in ranked if item[0] == lead or overlaps(lead_est, item[1])]
    name, est, cost = min(level, key=lambda item: (item[2], -item[1].score, item[0]))
    if name == lead:
        return f"{lead} scores highest and is also the cheapest of the models tied with it: {pct(lead_est.score)} for ${lead_cost:,.2f}."
    return (
        f"{name} is the cheapest model tied with the leader (95% ranges overlap): {pct(est.score)} for ${cost:,.2f}, "
        f"against {pct(lead_est.score)} for ${lead_cost:,.2f} from {lead}."
    )
