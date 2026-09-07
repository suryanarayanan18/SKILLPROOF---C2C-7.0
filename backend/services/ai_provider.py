"""Unified AI provider with automatic fallback support."""

import os

from services.gemini import generate_text as generate_gemini
from services.nvidia import generate_text as generate_nvidia


def _configured_provider() -> str:
    return os.getenv("SKILLPROOF_PROVIDER", "auto").strip().lower()


def generate_text(prompt: str) -> str:
    """
    Generate text using the configured AI provider.

    Supported modes:
        gemini  -> Gemini only
        nvidia  -> NVIDIA Nemotron only
        demo    -> local deterministic demo provider
        auto    -> NVIDIA -> Gemini -> demo fallback
    """

    provider = _configured_provider()

    if provider == "gemini":
        return generate_gemini(prompt)

    if provider == "nvidia":
        return generate_nvidia(prompt)

    if provider in {"demo", "mock"}:
        raise RuntimeError("Demo mode should be handled by the caller.")

    if provider == "auto":
        errors = []

        # Try NVIDIA first.
        try:
            return generate_nvidia(prompt)
        except Exception as exc:
            errors.append(f"NVIDIA failed: {exc}")

        # Fall back to Gemini.
        try:
            return generate_gemini(prompt)
        except Exception as exc:
            errors.append(f"Gemini failed: {exc}")

        raise RuntimeError(
            "All configured AI providers failed. "
            + " | ".join(errors)
        )

    raise RuntimeError(
        f"Unsupported SKILLPROOF_PROVIDER: {provider}. "
        "Use auto, gemini, nvidia, or demo."
    )