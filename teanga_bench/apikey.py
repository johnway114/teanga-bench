"""OpenRouter API key lookup.

The key comes from ``OPENROUTER_API_KEY``, else the macOS keychain item
``omp-openrouter``. It is held in memory and in the process environment only.
It is never printed, logged, or written to disk.
"""

from __future__ import annotations

import os
import subprocess

ENV_VAR = "OPENROUTER_API_KEY"
KEYCHAIN_SERVICE = "omp-openrouter"


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
            f"No OpenRouter key. Set {ENV_VAR}, or store one in the macOS keychain "
            f"under the service name {KEYCHAIN_SERVICE!r}."
        )
    return key


def export_api_key() -> None:
    """Make the key visible to Inspect's OpenRouter provider for this process."""
    os.environ[ENV_VAR] = resolve_api_key()
