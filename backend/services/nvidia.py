import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


# Resolve the repository-level .env explicitly, exactly like Gemini.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _get_client() -> OpenAI:
    """Create the NVIDIA client only when a request actually needs it."""
    api_key = os.getenv("NVIDIA_API_KEY")

    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY is not set.")

    return OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key,
    )


def generate_text(prompt: str) -> str:
    """Send a prompt to NVIDIA Nemotron and return the generated text."""

    client = _get_client()

    response = client.chat.completions.create(
        model="nvidia/nemotron-3.5-lightning-30b-a3b",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=0.2,
        top_p=0.95,
        max_tokens=2048,
    )

    return response.choices[0].message.content