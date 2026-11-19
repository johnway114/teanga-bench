"""API key lookup for OpenRouter and optional direct batch providers.

OpenRouter uses ``OPENROUTER_API_KEY``, or on macOS falls back to the keychain
item ``omp-openrouter``. Linux and CI must set ``OPENROUTER_API_KEY``. Direct
batch runs additionally verify the corresponding provider key and SDK. Keys are
held in memory and in the process environment only; they are never printed,
logged, or written to disk.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
from dataclasses import dataclass

ENV_VAR = "OPENROUTER_API_KEY"
KEYCHAIN_SERVICE = "omp-openrouter"


@dataclass(frozen=True)
class DirectBatchProvider:
    prefix: str
    inspect_prefix: str
    env_vars: tuple[str, ...]
    module: str
    install_hint: str


DIRECT_BATCH_PROVIDERS: dict[str, DirectBatchProvider] = {
    "openai": DirectBatchProvider(
        prefix="openai",
        inspect_prefix="openai",
        env_vars=("OPENAI_API_KEY",),
        module="openai",
        install_hint="openai",
    ),
    "anthropic": DirectBatchProvider(
        prefix="anthropic",
        inspect_prefix="anthropic",
        env_vars=("ANTHROPIC_API_KEY",),
        module="anthropic",
        install_hint="uv pip install -e '.[batch]'",
    ),
    "google": DirectBatchProvider(
        prefix="google",
        inspect_prefix="google",
        env_vars=("GOOGLE_API_KEY", "GEMINI_API_KEY"),
        module="google.genai",
        install_hint="uv pip install -e '.[batch]'",
    ),
}


class ApiKeyError(RuntimeError):
    pass


def resolve_api_key() -> str:
    key = os.environ.get(ENV_VAR, "").strip()
    if key:
        return key
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        result = None
    key = result.stdout.strip() if result is not None and result.returncode == 0 else ""
    if not key:
        raise ApiKeyError(
            f"No OpenRouter key. Set {ENV_VAR} (required on Linux and CI), or on macOS "
            f"store one in the keychain under the service name {KEYCHAIN_SERVICE!r}."
        )
    return key


def export_api_key() -> None:
    """Make the key visible to Inspect's OpenRouter provider for this process."""
    os.environ[ENV_VAR] = resolve_api_key()


def direct_batch_provider(model_id: str) -> DirectBatchProvider:
    """Return the direct Batch API provider for an OpenRouter model id, or raise ApiKeyError."""
    prefix = model_id.removeprefix("openrouter/").split("/", 1)[0].lstrip("~")
    provider = DIRECT_BATCH_PROVIDERS.get(prefix)
    if provider is None:
        supported = ", ".join(sorted(DIRECT_BATCH_PROVIDERS))
        raise ApiKeyError(
            f"--batch is supported only for direct providers ({supported}); {model_id!r} cannot use --batch."
        )
    return provider


def check_direct_batch_ready(model_id: str) -> str:
    """Verify key and SDK for direct batch inference and return the Inspect model id."""
    provider = direct_batch_provider(model_id)
    if importlib.util.find_spec(provider.module) is None:
        raise ApiKeyError(
            f"--batch for {model_id!r} requires Python package {provider.module!r}. "
            f"Install it with: {provider.install_hint}"
        )
    if not any(os.environ.get(var, "").strip() for var in provider.env_vars):
        names = " or ".join(provider.env_vars)
        raise ApiKeyError(
            f"--batch for {model_id!r} requires {names} to be set in the environment."
        )
    slug = model_id.removeprefix("openrouter/").split("/", 1)[1]
    return f"{provider.inspect_prefix}/{slug}"
