import json
import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from schemas import ChallengePayload
from services.challenge_generator import _parse_challenge, generate_challenge


VALID_CHALLENGE = {
    "title": "Record Counter",
    "overview": "Count valid records.",
    "task": "Implement count_records(records).",
    "constraints": ["Use one pass."],
    "starter_code": "def count_records(records):\n    pass\n",
    "examples": [{"input": "[1, 2]", "output": "2"}],
}


class ChallengeGeneratorTests(unittest.TestCase):
    def test_valid_nvidia_json(self):
        with patch.dict(os.environ, {"SKILLPROOF_PROVIDER": "nvidia", "NVIDIA_API_KEY": "test"}), patch(
            "services.nvidia.generate_text", return_value=json.dumps(VALID_CHALLENGE)
        ) as generate:
            result = generate_challenge()
        self.assertEqual(result, VALID_CHALLENGE)
        generate.assert_called_once()

    def test_nvidia_reasoning_then_json_is_normalized(self):
        response = "I need to reason about the task first.\n" + json.dumps(VALID_CHALLENGE)
        with patch.dict(os.environ, {"SKILLPROOF_PROVIDER": "nvidia", "NVIDIA_API_KEY": "test"}), patch(
            "services.nvidia.generate_text", return_value=response
        ):
            result = generate_challenge()
        self.assertEqual(result, VALID_CHALLENGE)

    def test_markdown_fenced_json_is_normalized(self):
        with patch.dict(os.environ, {"SKILLPROOF_PROVIDER": "nvidia", "NVIDIA_API_KEY": "test"}), patch(
            "services.nvidia.generate_text", return_value=f"```json\n{json.dumps(VALID_CHALLENGE)}\n```"
        ):
            result = generate_challenge()
        self.assertEqual(result, VALID_CHALLENGE)

    def test_malformed_json_is_rejected(self):
        with self.assertRaises(ValueError):
            _parse_challenge('{"title": "incomplete"')

    def test_invalid_nvidia_retries_then_uses_gemini(self):
        with patch.dict(
            os.environ,
            {"SKILLPROOF_PROVIDER": "nvidia", "NVIDIA_API_KEY": "test", "GEMINI_API_KEY": "test"},
        ), patch("services.nvidia.generate_text", return_value="thinking only") as nvidia, patch(
            "services.gemini.generate_text", return_value=json.dumps(VALID_CHALLENGE)
        ) as gemini:
            result = generate_challenge()
        self.assertEqual(result, VALID_CHALLENGE)
        self.assertEqual(nvidia.call_count, 2)
        gemini.assert_called_once()

    def test_both_ai_providers_unavailable_use_demo(self):
        with patch.dict(os.environ, {"SKILLPROOF_PROVIDER": "auto"}, clear=True), patch(
            "services.demo_provider.generate_challenge", wraps=lambda **kwargs: json.dumps(VALID_CHALLENGE)
        ) as demo:
            result = generate_challenge()
        self.assertEqual(result, VALID_CHALLENGE)
        demo.assert_called_once()

    def test_final_result_matches_challenge_schema(self):
        with patch.dict(os.environ, {"SKILLPROOF_PROVIDER": "demo"}, clear=True):
            result = generate_challenge(skill="Python", difficulty="beginner")
        validated = ChallengePayload.model_validate(result)
        self.assertEqual(validated.model_dump(), result)


if __name__ == "__main__":
    unittest.main()