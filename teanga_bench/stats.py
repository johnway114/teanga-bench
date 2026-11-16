"""Score statistics: item means, bootstrap intervals, and consistency.

An item's score is its mean over epochs. The 95% interval resamples ITEMS with
replacement, 2000 times, with a fixed seed, and takes the 2.5th and 97.5th
percentiles of the resampled means. The same inputs always give the same
interval.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import numpy as np

SEED = 20261115
RESAMPLES = 2000
CONFIDENCE = 0.95
CONSISTENCY_DECIMALS = 4


def _rng(key: str) -> np.random.Generator:
    return np.random.default_rng([SEED, zlib.crc32(key.encode("utf-8"))])


def bootstrap_means(item_scores: Sequence[float], key: str) -> np.ndarray:
    """Means of ``RESAMPLES`` item resamples. ``key`` names the stream, so each
    test and each subgroup has its own fixed draw."""
    values = np.asarray(item_scores, dtype=float)
    if values.size == 0:
        return np.full(RESAMPLES, np.nan)
    indices = _rng(key).integers(0, values.size, size=(RESAMPLES, values.size))
    return values[indices].mean(axis=1)


def interval(replicates: np.ndarray) -> tuple[float, float] | None:
    if replicates.size == 0 or np.isnan(replicates).any():
        return None
    tail = (1.0 - CONFIDENCE) / 2.0 * 100.0
    low, high = np.percentile(replicates, [tail, 100.0 - tail])
    return float(low), float(high)


def item_score(epoch_scores: Iterable[float]) -> float:
    values = list(epoch_scores)
    return sum(values) / len(values)


def consistent(epoch_scores: Sequence[float]) -> bool:
    """Same result in every epoch, comparing scores rounded to 4 decimals."""
    rounded = {round(value, CONSISTENCY_DECIMALS) for value in epoch_scores}
    return len(rounded) == 1


@dataclass(frozen=True)
class ItemResult:
    """One item's per-epoch scores and the metadata used for breakdowns."""

    id: str
    epoch_scores: tuple[float, ...]
    attributes: dict[str, str]

    @property
    def score(self) -> float:
        return item_score(self.epoch_scores)


def group_stats(items: Sequence[ItemResult], key: str, epochs: int) -> dict[str, Any]:
    """Mean, 95% interval, n_items, epochs, and consistency for one set of items."""
    if not items:
        return {
            "score": None,
            "ci95": None,
            "n_items": 0,
            "epochs": epochs,
            "consistency": None,
        }
    scores = [item.score for item in items]
    ci = interval(bootstrap_means(scores, key))
    consistency = None
    if epochs >= 2:
        consistency = sum(1 for item in items if consistent(item.epoch_scores)) / len(items)
    return {
        "score": float(np.mean(scores)),
        "ci95": None if ci is None else [ci[0], ci[1]],
        "n_items": len(items),
        "epochs": epochs,
        "consistency": consistency,
    }


def breakdown(
    items: Sequence[ItemResult], attribute: str, key: str, epochs: int
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[ItemResult]] = {}
    for item in items:
        groups.setdefault(item.attributes.get(attribute, "unspecified"), []).append(item)
    return {
        name: group_stats(members, f"{key}|{attribute}={name}", epochs)
        for name, members in sorted(groups.items())
    }


def phenomenon_breakdown(
    items: Sequence[ItemResult], attribute: str, key: str, epochs: int
) -> dict[str, dict[str, dict[str, Any]]]:
    """Cross language (or learner L1) with phenomenon; suppress cells below five items."""
    groups: dict[str, dict[str, list[ItemResult]]] = {}
    for item in items:
        language = item.attributes.get(attribute, "unspecified")
        phenomenon = item.attributes.get("phenomenon", "unspecified")
        groups.setdefault(language, {}).setdefault(phenomenon, []).append(item)
    result = {}
    for language, phenomena in sorted(groups.items()):
        cells = {
            phenomenon: group_stats(
                members, f"{key}|{attribute}={language}|phenomenon={phenomenon}", epochs
            )
            for phenomenon, members in sorted(phenomena.items())
            if len(members) >= 5
        }
        if cells:
            result[language] = cells
    return result


def pooled(
    parts: Sequence[tuple[Sequence[float], str]],
) -> dict[str, Any] | None:
    """Mean of per-part means, with an interval from resampling items inside each part.

    ``parts`` is a list of (item scores, bootstrap key), one per test (or per
    test and language). Every part has equal weight.
    """
    parts = [(scores, key) for scores, key in parts if len(scores) > 0]
    if not parts:
        return None
    point = float(np.mean([np.mean(scores) for scores, _ in parts]))
    replicates = np.mean([bootstrap_means(scores, key) for scores, key in parts], axis=0)
    ci = interval(replicates)
    return {
        "score": point,
        "ci95": None if ci is None else [ci[0], ci[1]],
        "n_tests": len(parts),
        "n_items": sum(len(scores) for scores, _ in parts),
    }
