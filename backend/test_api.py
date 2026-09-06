"""API contract tests. Gemini calls are patched; no live key or network is used."""

import unittest
import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import ASSESSMENTS, app


CHALLENGE_TEXT = """TITLE:
Record Counter

PROBLEM:
Count valid records in a list.

TASK:
Write count_records(records).

CONSTRAINTS:
- Use one pass
- Return an integer

STARTER_CODE:
def count_records(records):
    pass
"""

EVALUATION_TEXT = """OVERALL SCORE:
85

CORRECTNESS:
90

PROBLEM SOLVING:
84

CODE QUALITY:
80

EFFICIENCY:
88

UNDERSTANDING:
86

PRACTICAL APPLICATION:
82

STRENGTHS:
- Correct one-pass solution

WEAKNESSES:
- Add more tests

FEEDBACK:
Clear and correct.

RECOMMENDED NEXT STEP:
Practice edge cases.
"""


class SkillProofApiTests(unittest.TestCase):
    def setUp(self):
        ASSESSMENTS.clear()
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["provider"], "mock")

    def test_frontend_static_mount(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Proof, Not Paper.", response.text)
        index = self.client.get("/index.html")
        self.assertEqual(index.status_code, 200)
        self.assertEqual(index.text, response.text)
        self.assertEqual(self.client.get("/js/flow.js").status_code, 200)

    def test_challenge_request_validation(self):
        response = self.client.post("/api/challenges", json={"skill": "Python", "difficulty": "expert"})
        self.assertEqual(response.status_code, 422)
        unsupported = self.client.post("/api/challenges", json={"skill": "JavaScript", "difficulty": "beginner"})
        self.assertEqual(unsupported.status_code, 422)

    @patch("app.generate_challenge", return_value=CHALLENGE_TEXT)
    def test_create_challenge_and_submit_solution(self, mock_challenge):
        create = self.client.post("/api/challenges", json={"skill": "Python", "difficulty": "beginner"})
        self.assertEqual(create.status_code, 201)
        body = create.json()
        self.assertEqual(body["title"], "Record Counter")
        self.assertEqual(body["constraints"], ["Use one pass", "Return an integer"])
        mock_challenge.assert_called_once()

        with patch("app.evaluate_solution", return_value=EVALUATION_TEXT):
            submit = self.client.post(
                f"/api/assessments/{body['assessment_id']}/submit",
                json={"solution": "def count_records(records): return len(records)", "time_elapsed_seconds": 12},
            )
        self.assertEqual(submit.status_code, 200)
        self.assertEqual(submit.json()["evaluation"]["efficiency"], 88)
        evaluate = self.client.post(
            "/api/evaluate",
            json={"assessment_id": body["assessment_id"], "solution": "def count_records(records): return len(records)"},
        )
        self.assertEqual(evaluate.status_code, 200)
        passport = self.client.get("/api/passport")
        self.assertEqual(passport.status_code, 200)
        self.assertEqual(passport.json()["assessment_id"], body["assessment_id"])

    def test_unknown_assessment(self):
        response = self.client.get("/api/assessments/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get("/api/passport").status_code, 200)

    @patch("app.generate_challenge", return_value=CHALLENGE_TEXT)
    def test_get_stored_assessment(self, mock_challenge):
        create = self.client.post("/api/challenges", json={"skill": "Python", "difficulty": "beginner"})
        assessment_id = create.json()["assessment_id"]
        stored = self.client.get(f"/api/assessments/{assessment_id}")
        self.assertEqual(stored.status_code, 200)
        self.assertEqual(stored.json()["task"], "Write count_records(records).")

    def test_submission_validation(self):
        response = self.client.post("/api/assessments/does-not-exist/submit", json={"solution": ""})
        self.assertEqual(response.status_code, 422)

    def test_default_mock_provider_does_not_call_gemini(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SKILLPROOF_PROVIDER", None)
            with patch("services.gemini.generate_text", side_effect=AssertionError("Gemini called in mock mode")):
                response = self.client.post("/api/challenges", json={"skill": "Python", "difficulty": "beginner"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["title"], "E-Commerce Shopping Cart Calculator")

    def test_mock_challenge_changes_with_difficulty(self):
        titles = []
        for difficulty in ("beginner", "intermediate", "advanced"):
            response = self.client.post("/api/challenges", json={"skill": "Python", "difficulty": difficulty})
            self.assertEqual(response.status_code, 201)
            titles.append(response.json()["title"])
            self.assertEqual(response.json()["difficulty"], difficulty)
        self.assertEqual(len(set(titles)), 3)

    @patch("app.generate_challenge", side_effect=RuntimeError("429 RESOURCE_EXHAUSTED"))
    def test_provider_failure_falls_back_to_mock_challenge(self, mock_generator):
        response = self.client.post("/api/challenges", json={"skill": "Python", "difficulty": "advanced"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["title"], "Concurrent Token Bucket Rate Limiter")

    @patch("app.generate_challenge", side_effect=RuntimeError("429 RESOURCE_EXHAUSTED"))
    def test_provider_failure_falls_back_to_mock_evaluation(self, mock_generator):
        assessment = self.client.post("/api/challenges", json={"skill": "Python", "difficulty": "beginner"}).json()
        with patch("app.evaluate_solution", side_effect=RuntimeError("429 RESOURCE_EXHAUSTED")):
            response = self.client.post(
                f"/api/assessments/{assessment['assessment_id']}/submit",
                json={"solution": "def process_cart(items, category_discounts): return {}"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json()["evaluation"]["overall_score"], int)

    @patch.dict(os.environ, {"SKILLPROOF_PROVIDER": "gemini"})
    @patch("app.generate_challenge", return_value=CHALLENGE_TEXT)
    def test_gemini_quota_failure_returns_error(self, mock_challenge):
        assessment = self.client.post("/api/challenges", json={"skill": "Python", "difficulty": "beginner"}).json()
        with patch("app.evaluate_solution", side_effect=RuntimeError("429 RESOURCE_EXHAUSTED")):
            response = self.client.post(
                f"/api/assessments/{assessment['assessment_id']}/submit",
                json={"solution": "def count_records(records): return len(records)"},
            )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"], "Gemini API limit reached. Please try again later.")

    def test_mock_scores_strong_solution_higher_than_incomplete_solution(self):
        strong = self.client.post("/api/challenges", json={"skill": "Python", "difficulty": "beginner"}).json()
        strong_solution = """
def process_cart(items, category_discounts, store_discount_threshold=100):
    subtotal = 0
    total_quantity = 0
    for item in items:
        quantity = item['quantity']
        if quantity <= 0:
            continue
        total_quantity += quantity
        discount = category_discounts.get(item['category'], 0)
        subtotal += item['price'] * quantity * (1 - discount / 100)
    store_discount = subtotal * 0.1 if subtotal > store_discount_threshold else 0
    tax = (subtotal - store_discount) * 0.08
    total = max(0, subtotal - store_discount + tax)
    return {'subtotal': round(subtotal, 2), 'total_quantity': total_quantity,
            'discount': round(store_discount, 2), 'tax': round(tax, 2), 'total': round(total, 2)}
"""
        strong_result = self.client.post(
            f"/api/assessments/{strong['assessment_id']}/submit",
            json={"solution": strong_solution, "time_elapsed_seconds": 120},
        )
        weak = self.client.post("/api/challenges", json={"skill": "Python", "difficulty": "beginner"}).json()
        weak_result = self.client.post(
            f"/api/assessments/{weak['assessment_id']}/submit",
            json={"solution": "def process_cart(items, category_discounts):\n    return {}", "time_elapsed_seconds": 30},
        )
        self.assertEqual(strong_result.status_code, 200)
        self.assertEqual(weak_result.status_code, 200)
        self.assertGreater(strong_result.json()["evaluation"]["overall_score"], weak_result.json()["evaluation"]["overall_score"])


if __name__ == "__main__":
    unittest.main()
