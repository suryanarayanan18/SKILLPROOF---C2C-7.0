"""API contract tests. Gemini calls are patched; no live key or network is used."""

import unittest
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

    def test_frontend_static_mount(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Proof, Not Paper.", response.text)

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
        passport = self.client.get("/api/passport")
        self.assertEqual(passport.status_code, 200)
        self.assertEqual(passport.json()["assessment_id"], body["assessment_id"])

    def test_unknown_assessment(self):
        response = self.client.get("/api/assessments/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get("/api/passport").status_code, 404)

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


if __name__ == "__main__":
    unittest.main()
