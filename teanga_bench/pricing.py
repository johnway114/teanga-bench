"""Live OpenRouter pricing.

Prices come from https://openrouter.ai/api/v1/models at the start of every
run. They are USD per token, as decimal strings in the payload.
"""

from __future__ import annotations

import json
import ssl
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

import certifi

MODELS_URL = "https://openrouter.ai/api/v1/models"
FETCH_TIMEOUT_SECONDS = 30
MILLION = Decimal(1_000_000)


class PricingError(RuntimeError):
    """The live model list could not be read, or the model has no usable price."""


@dataclass(frozen=True)
class Pricing:
    """USD per token. Cache prices are None when the model does not list them."""

    prompt: Decimal
    completion: Decimal
    cache_read: Decimal | None = None
    cache_write: Decimal | None = None

    def cost(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> Decimal:
        """Cost of one call. Inspect reports cache tokens separately from input_tokens."""
        total = self.prompt * input_tokens + self.completion * output_tokens
        if self.cache_read is not None:
            total += self.cache_read * cache_read_tokens
        else:
            total += self.prompt * cache_read_tokens
        if self.cache_write is not None:
            total += self.cache_write * cache_write_tokens
        else:
            total += self.prompt * cache_write_tokens
        return total

    def scaled(self, factor: Decimal) -> "Pricing":
        """Scale every listed price by ``factor`` (for example 0.5 for provider Batch APIs)."""
        return Pricing(
            prompt=self.prompt * factor,
            completion=self.completion * factor,
            cache_read=None if self.cache_read is None else self.cache_read * factor,
            cache_write=None if self.cache_write is None else self.cache_write * factor,
        )

    def as_dict(self) -> dict[str, float | None]:
        def number(value: Decimal | None) -> float | None:
            return None if value is None else float(value)

        return {
            "prompt_usd_per_token": number(self.prompt),
            "completion_usd_per_token": number(self.completion),
            "cache_read_usd_per_token": number(self.cache_read),
            "cache_write_usd_per_token": number(self.cache_write),
        }


ZERO_PRICE = Pricing(Decimal(0), Decimal(0))


@dataclass(frozen=True)
class Catalog:
    """The live model list: raw entries by id, plus when it was read."""

    entries: dict[str, dict[str, Any]]
    retrieved_at: str
    source: str = MODELS_URL

    def __contains__(self, model_id: str) -> bool:
        return model_id in self.entries

    def pricing(self, model_id: str) -> Pricing:
        if model_id not in self.entries:
            raise PricingError(
                f"Model id {model_id!r} is not in the live OpenRouter model list "
                f"({self.source}, read {self.retrieved_at}). Check the id for typos."
            )
        return pricing_from_entry(model_id, self.entries[model_id])

    def supported_parameters(self, model_id: str) -> set[str]:
        """Parameters the live OpenRouter entry advertises for ``model_id``."""
        entry = self.entries.get(model_id) or {}
        raw = entry.get("supported_parameters") or []
        return {str(param) for param in raw if isinstance(param, str)}


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def pricing_from_entry(model_id: str, entry: dict[str, Any]) -> Pricing:
    raw = entry.get("pricing") or {}
    prompt = _decimal(raw.get("prompt"))
    completion = _decimal(raw.get("completion"))
    if prompt is None or completion is None or prompt < 0 or completion < 0:
        raise PricingError(
            f"Model id {model_id!r} has no fixed per-token price in the live list "
            "(routers and variable-price entries cannot be cost-capped)."
        )
    reasoning = _decimal(raw.get("internal_reasoning"))
    if reasoning is not None and reasoning > completion:
        # Output tokens include reasoning tokens; bill them at the higher rate so
        # the cap errs on the side of stopping early.
        completion = reasoning
    return Pricing(
        prompt=prompt,
        completion=completion,
        cache_read=_decimal(raw.get("input_cache_read")),
        cache_write=_decimal(raw.get("input_cache_write")),
    )


def fetch_catalog(
    url: str = MODELS_URL,
    opener: Callable[..., Any] | None = None,
) -> Catalog:
    """Read the live model list. No API key is needed or sent."""
    request = urllib.request.Request(url, headers={"User-Agent": "teanga-bench"})
    try:
        if opener is not None:
            response_context = opener(request, timeout=FETCH_TIMEOUT_SECONDS)
        else:
            # Python builds from uv and python.org do not read the system certificate store.
            tls = ssl.create_default_context(cafile=certifi.where())
            response_context = urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS, context=tls)
        with response_context as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # network, TLS, JSON: all mean the same thing here
        raise PricingError(f"Could not read the live OpenRouter model list from {url}: {exc}") from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or not data:
        raise PricingError(f"The OpenRouter model list at {url} had no 'data' entries.")
    entries = {str(item["id"]): item for item in data if isinstance(item, dict) and "id" in item}
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return Catalog(entries=entries, retrieved_at=retrieved, source=url)
