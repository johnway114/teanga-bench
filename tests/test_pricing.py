"""Live pricing parse and API key lookup. Nothing here touches the network or keychain."""

import io
import json
import subprocess
from decimal import Decimal

import pytest

from teanga_bench import apikey
from teanga_bench.pricing import Catalog, PricingError, fetch_catalog, pricing_from_entry


def test_prices_are_usd_per_token_with_cache_prices():
    pricing = pricing_from_entry(
        "x/y", {"pricing": {"prompt": "0.0000001", "completion": "0.0000005", "input_cache_read": "0.00000001", "input_cache_write": "0.000000125"}}
    )
    assert pricing.prompt == Decimal("0.0000001")
    assert pricing.cache_write == Decimal("0.000000125")
    assert pricing.cost(1_000_000, 2_000_000) == Decimal("1.1")


def test_reasoning_price_above_completion_raises_the_output_rate():
    pricing = pricing_from_entry("x/y", {"pricing": {"prompt": "1", "completion": "2", "internal_reasoning": "5"}})
    assert pricing.completion == Decimal("5")


def test_variable_price_routers_are_refused():
    with pytest.raises(PricingError, match="no fixed per-token price"):
        pricing_from_entry("openrouter/auto", {"pricing": {"prompt": "-1", "completion": "-1"}})
    with pytest.raises(PricingError):
        pricing_from_entry("x/y", {"pricing": {"prompt": "0.1"}})


def test_absent_model_fails_with_a_clear_message():
    catalog = Catalog(entries={}, retrieved_at="2026-11-15T00:00:00+00:00")
    with pytest.raises(PricingError, match="'x/missing' is not in the live OpenRouter model list"):
        catalog.pricing("x/missing")


def test_fetch_catalog_reads_the_models_payload_without_a_key():
    seen = {}

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opener(request, timeout):
        seen["headers"] = dict(request.header_items())
        return Response(json.dumps({"data": [{"id": "a/b", "pricing": {"prompt": "0.1", "completion": "0.2"}}]}).encode())

    catalog = fetch_catalog(opener=opener)
    assert "a/b" in catalog and catalog.retrieved_at
    assert "Authorization" not in seen["headers"]


def test_fetch_failure_is_a_pricing_error():
    def opener(request, timeout):
        raise OSError("offline")

    with pytest.raises(PricingError, match="Could not read the live OpenRouter model list"):
        fetch_catalog(opener=opener)


def test_env_key_wins_over_the_keychain(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("keychain must not be read"))
    assert apikey.resolve_api_key() == "env-key"


def test_keychain_is_the_fallback_and_the_key_is_never_in_an_error(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="sk-secret-from-keychain\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert apikey.resolve_api_key() == "sk-secret-from-keychain"
    assert calls == [["security", "find-generic-password", "-s", "omp-openrouter", "-w"]]

    monkeypatch.setattr(
        subprocess, "run", lambda c, **k: subprocess.CompletedProcess(c, 44, stdout="", stderr="not found")
    )
    with pytest.raises(apikey.ApiKeyError) as error:
        apikey.resolve_api_key()
    assert "omp-openrouter" in str(error.value)


def test_export_sets_the_environment_only(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(subprocess, "run", lambda c, **k: subprocess.CompletedProcess(c, 0, stdout="k1\n", stderr=""))
    apikey.export_api_key()
    import os

    assert os.environ["OPENROUTER_API_KEY"] == "k1"
    monkeypatch.delenv("OPENROUTER_API_KEY")
