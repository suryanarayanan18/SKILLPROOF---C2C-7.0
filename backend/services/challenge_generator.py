"""Generate practical challenges through the configured provider."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

from schemas import ChallengePayload


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


STRICT_JSON_SUFFIX = """

Your previous response was invalid. Return exactly one JSON object and nothing
else. Start with { and end with }. Do not include reasoning, analysis,
markdown fences, prose, or any text before or after the object. Every required
field must have the exact type requested above.

IMPORTANT:
- constraints MUST be an array of strings.
- examples MUST be an array of objects.
- Every example object MUST contain input and output as strings.
"""


def _extract_json_object(text: str) -> dict[str, Any]:
    """Return the first valid JSON object embedded in provider output."""
    decoder = json.JSONDecoder()
    source = text or ""

    for index, character in enumerate(source):
        if character != "{":
            continue

        try:
            value, end = decoder.raw_decode(source[index:])
        except json.JSONDecodeError:
            continue

        if isinstance(value, dict):
            return json.loads(source[index : index + end])

    raise ValueError("Provider response did not contain a valid JSON object.")


def _parse_challenge(text: str) -> ChallengePayload:
    """Parse and validate a provider response as a ChallengePayload."""
    try:
        data = _extract_json_object(text)

        # NVIDIA sometimes returns constraints as one string instead of
        # an array. Normalize that before Pydantic validation.
        if isinstance(data.get("constraints"), str):
            data["constraints"] = [data["constraints"]]

        # Make sure examples have the expected structure.
        if isinstance(data.get("examples"), list):
            normalized_examples = []

            for example in data["examples"]:
                if isinstance(example, dict):
                    normalized_examples.append(
                        {
                            "input": str(example.get("input", "")),
                            "output": str(example.get("output", "")),
                        }
                    )

            data["examples"] = normalized_examples

        return ChallengePayload.model_validate(data)

    except (ValueError, ValidationError, TypeError) as error:
        raise ValueError(
            "Provider response was not a valid challenge JSON object."
        ) from error


def _provider_key_configured(provider: str) -> bool:
    """Check whether the provider API key is configured."""
    return bool(os.getenv(f"{provider.upper()}_API_KEY"))


def _generate_from_provider(
    provider: str,
    prompt: str,
    strict_prompt: str,
) -> ChallengePayload:
    """Generate and validate a challenge using the selected provider."""
    from services.gemini import generate_text as generate_gemini
    from services.nvidia import generate_text as generate_nvidia

    generate = (
        generate_nvidia
        if provider == "nvidia"
        else generate_gemini
    )

    try:
        return _parse_challenge(generate(prompt))

    except Exception:
        try:
            return _parse_challenge(generate(strict_prompt))

        except Exception as error:
            raise RuntimeError(
                f"{provider} did not return a valid challenge."
            ) from error


def generate_challenge(
    skill: str = "Python",
    difficulty: str = "beginner",
    previous_performance: str | None = None,
    target_weakness: str | None = None,
) -> ChallengePayload:
    """
    Generate a practical skill assessment challenge.

    Parameters:
        skill: The skill being assessed.
        difficulty: beginner, intermediate, or advanced.
        previous_performance: Optional summary of previous performance.
        target_weakness: Optional weakness that the challenge should target.

    Returns:
        A validated challenge object.
    """

    provider = os.getenv(
        "SKILLPROOF_PROVIDER",
        "mock",
    ).strip().lower()

    if provider in {"mock", "demo"}:
        from services.demo_provider import (
            generate_challenge as generate_demo_challenge,
        )

        return _parse_challenge(
            generate_demo_challenge(
                skill=skill,
                difficulty=difficulty,
            )
        )

    # Keep the JSON structure outside the f-string.
    # This prevents Python from interpreting JSON braces as f-string fields.
    json_structure = """
{
  "title": "string",
  "overview": "string",
  "task": "string",
  "constraints": [
    "string",
    "string"
  ],
  "starter_code": "string",
  "examples": [
    {
      "input": "string",
      "output": "string"
    }
  ]
}
"""

    prompt = f"""
You are the Challenge Generator for SkillProof,
an AI-powered practical skill verification platform.

Your job is to create a practical assessment challenge
that tests real ability rather than memorization.

Skill:
{skill}

Difficulty:
{difficulty}

Previous performance:
{previous_performance or "No previous performance. This is the first challenge."}

Target weakness:
{target_weakness or "No specific weakness. Test a balanced set of skills."}

Create ONE practical challenge.

The challenge must:

1. Be appropriate for the selected difficulty.
2. Test practical problem-solving ability.
3. Require the user to actually produce a solution.
4. Avoid questions that can be answered through simple memorization.
5. Be realistic and useful for evaluating professional ability.

For a Python challenge, include:

- A clear problem statement.
- The user's task.
- Input/output expectations if applicable.
- Important constraints.
- At least one example.
- What skills are being tested.

Do NOT provide the solution.

Return ONLY a JSON object matching this exact structure:

{json_structure}

IMPORTANT:
- "title" MUST be a string.
- "overview" MUST be a string.
- "task" MUST be a string.
- "constraints" MUST be a JSON array of strings.
- "constraints" MUST NEVER be a single string.
- "starter_code" MUST be a string.
- "examples" MUST be a JSON array.
- Every example MUST be an object.
- Every example MUST contain "input" and "output".
- "input" MUST be a string.
- "output" MUST be a string.
- Return valid JSON only.
- Do not wrap the JSON in Markdown.
- Do not include a solution.
"""

    strict_prompt = prompt + STRICT_JSON_SUFFIX

    providers = (
        ["nvidia", "gemini"]
        if provider in {"auto", "nvidia"}
        else ["gemini"]
    )

    configured = [
        selected
        for selected in providers
        if _provider_key_configured(selected)
    ]

    if not configured:
        if provider == "auto":
            from services.demo_provider import (
                generate_challenge as generate_demo_challenge,
            )

            return _parse_challenge(
                generate_demo_challenge(
                    skill=skill,
                    difficulty=difficulty,
                )
            )
        raise RuntimeError(
            "No AI provider is configured. "
            "Set SKILLPROOF_PROVIDER to gemini or nvidia "
            "and provide the matching API key."
        )

    for selected_provider in configured:
        try:
            return _generate_from_provider(
                selected_provider,
                prompt,
                strict_prompt,
            )
        except RuntimeError:
            continue

    raise RuntimeError(
        "Configured AI providers failed to generate "
        "a valid challenge payload."
    )


if __name__ == "__main__":
    challenge = generate_challenge(
        skill="Python",
        difficulty="beginner",
    )

    print(json.dumps(challenge, indent=2))