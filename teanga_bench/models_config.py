"""The fixed judge pair and provider families from ``config/models.yaml``."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import yaml

from teanga_bench.paths import CONFIG

JUDGES_NEEDED = 2


@dataclass(frozen=True)
class JudgeChoice:
    id: str
    family: str


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    with CONFIG.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{CONFIG} did not contain a mapping")
    return data


def configured_judges() -> list[JudgeChoice]:
    """The fixed judge pair from config/models.yaml."""
    ids = [str(item) for item in load_config().get("judges") or []]
    if len(ids) != JUDGES_NEEDED or len(set(ids)) != JUDGES_NEEDED:
        raise ValueError(f"config/models.yaml must list exactly {JUDGES_NEEDED} different judges")
    return [JudgeChoice(id=item, family=family_of(item)) for item in ids]


def family_of(model_id: str, families: dict[str, str] | None = None) -> str:
    """Family of an OpenRouter id: its provider prefix, mapped through the config."""
    table = load_config().get("families", {}) if families is None else families
    prefix = model_id.removeprefix("openrouter/").split("/", 1)[0].lstrip("~")
    return str(table.get(prefix, prefix))
