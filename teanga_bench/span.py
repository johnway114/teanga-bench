"""Single-span edit between a learner sentence and its recorded correction."""

from __future__ import annotations


def single_replacement(source: str, target: str) -> tuple[str, str] | None:
    """Return (span, replacement) if one substitution turns source into target."""
    if source == target or not source:
        return None
    limit = min(len(source), len(target))
    prefix = 0
    while prefix < limit and source[prefix] == target[prefix]:
        prefix += 1
    suffix = 0
    while (
        suffix < len(source) - prefix
        and suffix < len(target) - prefix
        and source[-1 - suffix] == target[-1 - suffix]
    ):
        suffix += 1
    end_source = len(source) - suffix if suffix else len(source)
    end_target = len(target) - suffix if suffix else len(target)
    span = source[prefix:end_source]
    replacement = target[prefix:end_target]
    if not span:
        return None
    if source.replace(span, replacement, 1) != target:
        return None
    return span, replacement
