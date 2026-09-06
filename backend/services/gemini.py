import os
from pathlib import Path

from google import genai
from dotenv import load_dotenv

# Resolve the repository-level file explicitly so Uvicorn's working directory
# cannot determine whether the key is discovered.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _get_client() -> genai.Client:
    """Create the Gemini client only when a request actually needs it."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    return genai.Client(api_key=api_key)


def generate_text(prompt: str) -> str:
    """Send a prompt to Gemini and return the generated text."""

    client = _get_client()
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
    )

    return response.text
