"""Hard cost cap for a run, and the pause on exhausted provider credit.

Every model call, candidate or judge, goes through ``CostGuard.call``. The
guard keeps one running total in USD. Before a call it reserves the worst-case
cost (input bytes as tokens, plus ``max_tokens`` at the completion price). If
the total spent, plus everything reserved by calls in flight, plus that worst
case would pass the cap, the call waits for calls in flight to settle and
checks again. Only when no call is in flight and the worst case still does not
fit is the call not made and the run stopped for good. After a call the
reservation is replaced by the cost of the usage the provider reported. So
spend cannot pass the cap unless a provider bills more than the live per-token
prices say, and the run stops at most one call's worst case short of the cap.

Waiting matters because the candidate answer limit is large: with eight calls
in flight, eight full worst cases can be more than a small cap. Stopping at the
first refusal would end such a run after a handful of calls.

A resumed run carries the spend of its earlier attempts forward, so the cap is
a cap on the true total.

A 402 (out of credit) or 429 (rate limited) reply does not fail the sample.
The guard pauses every new call of the run with one shared exponential
backoff and retries. When the run's wait budget is spent, the call raises
``CreditExhausted`` and so does every later call, so the run stops cleanly.
"""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Awaitable, Callable

import anyio
from inspect_ai.model import ChatMessage, GenerateConfig, Model, ModelOutput

from teanga_bench.pricing import ZERO_PRICE, Pricing

PER_MESSAGE_OVERHEAD_TOKENS = 16

BACKOFF_START_SECONDS = 15.0
BACKOFF_CAP_SECONDS = 120.0
BACKOFF_BUDGET_SECONDS = 20 * 60.0
CREDIT_STATUS_CODES = (402, 429)
_CREDIT_MESSAGE = re.compile(r"Error code: (402|429)\b")


class CostCapReached(RuntimeError):
    """Raised instead of making a call that could take spend past the cap."""


class CreditExhausted(RuntimeError):
    """The provider kept refusing calls for lack of credit (402) or rate (429)
    for the whole wait budget of the run."""


def is_credit_error(exc: BaseException) -> bool:
    """True for a 402 or 429 reply, also when wrapped in another exception."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, "status_code", None) in CREDIT_STATUS_CODES:
            return True
        if _CREDIT_MESSAGE.search(str(current)):
            return True
        current = current.__cause__ or current.__context__
    return False


@dataclass
class CreditBackoff:
    """One pause shared by every call of a run.

    The first 402 or 429 starts a pause. Calls that fail while it is on do not
    lengthen it, and every new call waits for it to end, so the run pauses
    instead of hammering the provider. Pauses double from ``start`` up to
    ``cap``. A successful call resets the next pause to ``start``. The sum of
    all pauses in a run is at most ``budget``. A failure after that raises
    ``CreditExhausted``, and so does every later call. ``clock`` and ``sleep``
    are injectable for tests.
    """

    start: float = BACKOFF_START_SECONDS
    cap: float = BACKOFF_CAP_SECONDS
    budget: float = BACKOFF_BUDGET_SECONDS
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], Awaitable[Any]] = anyio.sleep  # Inspect may run on asyncio or trio
    waited: float = 0.0
    pauses: int = 0
    exhausted: bool = False
    _next: float | None = None
    _resume_at: float = float("-inf")
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _exhausted_error(self) -> CreditExhausted:
        return CreditExhausted(
            "the provider refused calls for lack of credit (HTTP 402) or rate (HTTP 429) "
            f"through {self.waited:.0f} s of backoff, the run's whole wait budget"
        )

    async def ready(self) -> None:
        """Wait until no pause is on. Raises once the budget is spent."""
        while True:
            with self._lock:
                if self.exhausted:
                    raise self._exhausted_error()
                wait = self._resume_at - self.clock()
            if wait <= 0:
                return
            await self.sleep(wait)

    def failed(self) -> None:
        """Record a 402 or 429: start a pause unless one is already on."""
        with self._lock:
            if self.exhausted:
                raise self._exhausted_error()
            now = self.clock()
            if now < self._resume_at:
                return
            remaining = self.budget - self.waited
            if remaining <= 0:
                self.exhausted = True
                raise self._exhausted_error()
            delay = min(self.start if self._next is None else self._next, remaining)
            self._next = min(delay * 2, self.cap)
            self._resume_at = now + delay
            self.waited += delay
            self.pauses += 1

    def succeeded(self) -> None:
        with self._lock:
            self._next = None


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

    def minus(self, other: "Usage") -> "Usage":
        return Usage(
            calls=self.calls - other.calls,
            input_tokens=self.input_tokens - other.input_tokens,
            output_tokens=self.output_tokens - other.output_tokens,
            cache_read_tokens=self.cache_read_tokens - other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens - other.cache_write_tokens,
            cost_usd=self.cost_usd - other.cost_usd,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Usage":
        return cls(
            calls=int(data.get("calls") or 0),
            input_tokens=int(data.get("input_tokens") or 0),
            output_tokens=int(data.get("output_tokens") or 0),
            cache_read_tokens=int(data.get("cache_read_tokens") or 0),
            cache_write_tokens=int(data.get("cache_write_tokens") or 0),
            cost_usd=Decimal(str(data.get("cost_usd") or 0)),
        )

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
    backoff: CreditBackoff = field(default_factory=CreditBackoff)
    in_flight: int = 0
    _waiters: list[anyio.Event] = field(default_factory=list)
    _ledger: dict[tuple[str, str, str], Usage] = field(default_factory=lambda: defaultdict(Usage))
    _carried: dict[tuple[str, str], Usage] = field(default_factory=dict)
    _carried_models: dict[str, Usage] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def credit_exhausted(self) -> bool:
        return self.backoff.exhausted

    def carry_forward(
        self, by_test_role: dict[tuple[str, str], Usage], by_model: dict[str, Usage], total: Decimal
    ) -> None:
        """Start from the spend of earlier attempts of the same run."""
        with self._lock:
            self._carried = dict(by_test_role)
            self._carried_models = dict(by_model)
            self.spent += total

    def price_of(self, model_id: str) -> Pricing:
        return self.prices.get(model_id, ZERO_PRICE)

    def worst_case(self, model_id: str, messages: str | list[ChatMessage], max_tokens: int) -> Decimal:
        price = self.price_of(model_id)
        return price.prompt * _input_size_tokens(messages) + price.completion * max_tokens

    def _wake_waiters(self) -> None:
        """Call with the lock held."""
        waiters, self._waiters = self._waiters, []
        for event in waiters:
            event.set()

    async def _reserve(self, model_id: str, messages: str | list[ChatMessage], max_tokens: int) -> Decimal:
        """Reserve the call's worst case. Waits while other calls in flight hold
        the room it needs; stops the run when it cannot fit even alone."""
        worst = self.worst_case(model_id, messages, max_tokens)
        while True:
            with self._lock:
                fits = self.spent + self.reserved + worst <= self.max_cost
                if not self.stopped and fits:
                    self.reserved += worst
                    self.in_flight += 1
                    return worst
                if self.stopped or self.in_flight == 0:
                    self.stopped = True
                    self._wake_waiters()
                    raise CostCapReached(
                        f"cost cap ${self.max_cost} reached (spent ${self.spent:.6f}, "
                        f"in flight ${self.reserved:.6f}, next call could cost ${worst:.6f})"
                    )
                settled = anyio.Event()
                self._waiters.append(settled)
            await settled.wait()

    def _settle(self, worst: Decimal, model_id: str, role: str, test: str, usage: Usage) -> None:
        with self._lock:
            self.reserved -= worst
            self.in_flight -= 1
            self.spent += usage.cost_usd
            self._ledger[(test, role, model_id)].add(usage)
            self._wake_waiters()

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
        """Generate once, inside the cap. ``role`` is "candidate" or "judge",
        ``test`` the ``suite/test`` name. A 402 or 429 waits in the shared
        backoff and is retried. A refused call is not billed."""
        if config.max_tokens is None:
            raise ValueError("every guarded call needs max_tokens")
        while True:
            await self.backoff.ready()
            worst = await self._reserve(model_id, messages, config.max_tokens)
            try:
                output = await model.generate(messages, config=config)
            except Exception as exc:
                self._settle(worst, model_id, role, test, Usage())
                if not is_credit_error(exc):
                    raise
                self.backoff.failed()
                continue
            usage = Usage(calls=1, cost_usd=worst)  # no usage reported: assume the worst case
            try:
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
            finally:
                self._settle(worst, model_id, role, test, usage)
            self.backoff.succeeded()
            return output

    def total(self, test: str | None = None, role: str | None = None) -> Usage:
        total = Usage()
        with self._lock:
            for (t, r, _model), usage in self._ledger.items():
                if (test is None or t == test) and (role is None or r == role):
                    total.add(usage)
            for (t, r), usage in self._carried.items():
                if (test is None or t == test) and (role is None or r == role):
                    total.add(usage)
        return total

    def by_model(self) -> dict[str, Usage]:
        grouped: dict[str, Usage] = defaultdict(Usage)
        with self._lock:
            for model_id, usage in self._carried_models.items():
                grouped[model_id].add(usage)
            for (_test, _role, model_id), usage in self._ledger.items():
                grouped[model_id].add(usage)
        return dict(grouped)
