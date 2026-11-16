"""Bootstrap intervals are fixed by the seed; consistency and pooling."""

import numpy as np

from teanga_bench.stats import (
    RESAMPLES,
    ItemResult,
    bootstrap_means,
    breakdown,
    consistent,
    group_stats,
    pooled,
    phenomenon_breakdown,
)


def _items(scores_by_item, attributes=None):
    return [
        ItemResult(f"i{n}", tuple(scores), attributes[n] if attributes else {"language": "irish"})
        for n, scores in enumerate(scores_by_item)
    ]


def test_bootstrap_is_deterministic_for_a_fixed_seed_and_key():
    scores = [0, 1, 1, 0, 1, 0.5, 1, 0]
    first = bootstrap_means(scores, "blas/mutations")
    second = bootstrap_means(scores, "blas/mutations")
    assert first.shape == (RESAMPLES,)
    assert np.array_equal(first, second)
    assert not np.array_equal(first, bootstrap_means(scores, "blas/other"))


def test_group_stats_repeat_exactly_and_bracket_the_mean():
    items = _items([(1, 1, 1), (0, 0, 0), (1, 0, 1), (1, 1, 1), (0, 0, 1)])
    first = group_stats(items, "k", epochs=3)
    assert first == group_stats(items, "k", epochs=3)
    low, high = first["ci95"]
    assert low <= first["score"] <= high
    assert first["n_items"] == 5 and first["epochs"] == 3


def test_interval_resamples_items_not_epochs():
    """Item score is the mean over epochs; two items give only 4 possible means."""
    items = _items([(1, 1), (0, 0)])
    stats = group_stats(items, "k", epochs=2)
    assert stats["score"] == 0.5
    assert stats["ci95"] == [0.0, 1.0]


def test_constant_scores_give_a_degenerate_interval():
    stats = group_stats(_items([(1,), (1,), (1,)]), "k", epochs=1)
    assert stats["ci95"] == [1.0, 1.0]


def test_consistency_is_the_share_of_items_with_the_same_result_every_epoch():
    items = _items([(1, 1, 1), (0, 0, 0), (1, 0, 1), (0, 1, 0)])
    assert group_stats(items, "k", epochs=3)["consistency"] == 0.5
    assert consistent((0.5, 0.50001)) is True  # rounded to 4 decimals
    assert group_stats(_items([(1,)]), "k", epochs=1)["consistency"] is None


def test_breakdown_groups_by_attribute():
    attributes = [{"language": "irish"}, {"language": "irish"}, {"language": "welsh"}]
    result = breakdown(_items([(1,), (0,), (1,)], attributes), "language", "k", 1)
    assert result["irish"]["n_items"] == 2 and result["irish"]["score"] == 0.5
    assert result["welsh"]["score"] == 1.0


def test_pooled_weights_each_part_equally():
    result = pooled([([1.0, 1.0, 1.0, 1.0], "a"), ([0.0], "b")])
    assert result["score"] == 0.5
    assert result["n_tests"] == 2 and result["n_items"] == 5
    assert result == pooled([([1.0, 1.0, 1.0, 1.0], "a"), ([0.0], "b")])


def test_phenomenon_breakdown_uses_item_means_and_suppresses_small_cells():
    items = [
        ItemResult(
            f"{language}-{phenomenon}-{n}",
            (float(n % 2), 1.0),
            {"language": language, "phenomenon": phenomenon},
        )
        for language, phenomenon, count in (
            ("irish", "mutation", 5),
            ("irish", "syntax", 6),
            ("welsh", "mutation", 5),
            ("welsh", "syntax", 4),
        )
        for n in range(count)
    ]
    result = phenomenon_breakdown(items, "language", "test", 2)
    assert set(result) == {"irish", "welsh"}
    assert set(result["irish"]) == {"mutation", "syntax"}
    assert set(result["welsh"]) == {"mutation"}
    members = items[:5]
    assert result["irish"]["mutation"] == group_stats(
        members, "test|language=irish|phenomenon=mutation", 2
    )
    assert result["irish"]["mutation"]["score"] == 0.7
    assert result["irish"]["mutation"]["consistency"] == 0.4
    assert phenomenon_breakdown(items[-4:], "language", "test", 2) == {}
