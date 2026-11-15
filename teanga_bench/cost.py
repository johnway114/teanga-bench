"""Hard cost cap for a run.

Every model call, candidate or judge, goes through ``CostGuard.call``. The
guard keeps one running total in USD. Before a call it reserves the worst-case
cost (input bytes as tokens, plus ``max_tokens`` at the completion price). If
the total spent, plus everything reserved by calls in flight, plus that worst
case would pass the cap, the call is not made and the run is stopped for good.
After a call the reservation is replaced by the cost of the usage the provider
reported. So spend cannot pass the cap unless a provider bills more than the
live per-token prices say.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from inspect_ai.model import ChatMessage, GenerateConfig, Model, ModelOutput

from teanga_bench.pricing import ZERO_PRICE, Pricing

PER_MESSAGE_OVERHEAD_TOKENS = 16


class CostCapReached(RuntimeError):
    """Raised instead of making a call that could take spend past the cap."""


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: Decimal = Decimal(0)

    def add(self, other: "Usage") -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.cost_usd += other.cost_usd

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cost_usd": float(self.cost_usd),
        }


def _input_size_tokens(messages: str | list[ChatMessage]) -> int:
    """Upper bound on input tokens: one token per UTF-8 byte."""
    if isinstance(messages, str):
        return len(messages.encode("utf-8")) + PER_MESSAGE_OVERHEAD_TOKENS
    total = 0
    for message in messages:
        total += len(message.text.encode("utf-8")) + PER_MESSAGE_OVERHEAD_TOKENS
    return total


@dataclass
class CostGuard:
    max_cost: Decimal
    prices: dict[str, Pricing] = field(default_factory=dict)
    spent: Decimal = Decimal(0)
    reserved: Decimal = Decimal(0)
    stopped: bool = False
    _ledger: dict[tuple[str, str, str], Usage] = field(default_factory=lambda: defaultdict(Usage))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def price_of(self, model_id: str) -> Pricing:
        return self.prices.get(model_id, ZERO_PRICE)

    def _reserve(self, model_id: str, messages: str | list[ChatMessage], max_tokens: int) -> Decimal:
        price = self.price_of(model_id)
        worst = price.prompt * _input_size_tokens(messages) + price.completion * max_tokens
        with self._lock:
            if self.stopped or self.spent + self.reserved + worst > self.max_cost:
                self.stopped = True
                raise CostCapReached(
                    f"cost cap ${self.max_cost} reached (spent ${self.spent:.6f}, "
                    f"in flight ${self.reserved:.6f}, next call could cost ${worst:.6f})"
                )
            self.reserved += worst
        return worst

    def _settle(self, worst: Decimal, model_id: str, role: str, test: str, usage: Usage) -> None:
        with self._lock:
            self.reserved -= worst
            self.spent += usage.cost_usd
            self._ledger[(test, role, model_id)].add(usage)

    async def call(
        self,
        *,
        model: Model,
        model_id: str,
        role: str,
        test: str,
        messages: str | list[ChatMessage],
        config: GenerateConfig,
    ) -> ModelOutput:
        """Generate once, inside the cap. ``role`` is "candidate" or "judge"."""
        if config.max_tokens is None:
            raise ValueError("every guarded call needs max_tokens")
        worst = self._reserve(model_id, messages, config.max_tokens)
        usage = Usage()
        try:
            output = await model.generate(messages, config=config)
            reported = output.usage
            if reported is not None:
                read = int(reported.input_tokens_cache_read or 0)
                write = int(reported.input_tokens_cache_write or 0)
                usage = Usage(
                    calls=1,
                    input_tokens=int(reported.input_tokens or 0),
                    output_tokens=int(reported.output_tokens or 0),
                    cache_read_tokens=read,
                    cache_write_tokens=write,
                )
                usage.cost_usd = self.price_of(model_id).cost(
                    usage.input_tokens, usage.output_tokens, read, write
                )
            else:
                usage.calls = 1
                usage.cost_usd = worst  # no usage reported: assume the worst case
            return output
        finally:
            self._settle(worst, model_id, role, test, usage)

    def total(self, test: str | None = None, role: str | None = None) -> Usage:
        total = Usage()
        with self._lock:
            for (t, r, _model), usage in self._ledger.items():
                if (test is None or t == test) and (role is None or r == role):
                    total.add(usage)
        return total

    def by_model(self) -> dict[str, Usage]:
        grouped: dict[str, Usage] = defaultdict(Usage)
        with self._lock:
            for (_test, _role, model_id), usage in self._ledger.items():
                grouped[model_id].add(usage)
        return dict(grouped)
