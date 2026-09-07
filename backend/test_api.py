"""API contract tests for the hardened SkillProof backend API."""

import unittest
from fastapi.testclient import TestClient
from app import app
import db


class SkillProofApiContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "skillproof-api")
        self.assertIn("active_model_version", data)
        self.assertIn("active_calibration_version", data)

    def test_frontend_static_mount(self):
        pages = [
            "/",
            "/index.html",
            "/skill-selection.html",
            "/difficulty-selection.html",
            "/assessment-setup.html",
            "/workspace.html",
            "/evaluation.html",
            "/passport.html",
            "/analytics.html",
            "/js/flow.js",
            "/js/api.js",
        ]
        for p in pages:
            res = self.client.get(p)
            self.assertEqual(res.status_code, 200, f"Page {p} returned {res.status_code}")

    def test_assessment_lifecycle_and_one_shot_409(self):
        # 1. Create assessment
        create_res = self.client.post("/api/assessment", json={
            "candidate_id": "api-test-cand-01",
            "skill": "python",
            "difficulty": "intermediate"
        })
        self.assertEqual(create_res.status_code, 201)
        asmt = create_res.json()
        asmt_id = asmt["id"]
        prob = asmt["problem"]
        self.assertIn("id", prob)
        self.assertIn("title", prob)
        self.assertIn("starter_code", prob)
        self.assertNotIn("tests", prob, "Hidden tests leaked in public problem view!")

        # 2. Get assessment
        get_res = self.client.get(f"/api/assessment/{asmt_id}")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["id"], asmt_id)

        # 3. Submit solution
        prob_row = db.get_problem(prob["id"])
        ref_sol = prob_row["reference_solution"]
        submit_res = self.client.post(f"/api/assessment/{asmt_id}/submit", json={
            "solution": ref_sol,
            "time_taken": 25.0
        })
        self.assertEqual(submit_res.status_code, 200)
        res_data = submit_res.json()
        self.assertEqual(res_data["tests_passed"], res_data["tests_total"])
        self.assertTrue(res_data["overall_score"] > 0)

        # 4. Result retrieval
        result_res = self.client.get(f"/api/assessment/{asmt_id}/result")
        self.assertEqual(result_res.status_code, 200)
        self.assertEqual(result_res.json()["overall_score"], res_data["overall_score"])

        # 5. One-shot duplicate rejection (HTTP 409)
        dup_res = self.client.post(f"/api/assessment/{asmt_id}/submit", json={
            "solution": "# Attempting duplicate submission",
            "time_taken": 5.0
        })
        self.assertEqual(dup_res.status_code, 409)

        # 6. Skill Passport retrieval
        pass_res = self.client.get("/api/passport/api-test-cand-01")
        self.assertEqual(pass_res.status_code, 200)
        self.assertTrue(pass_res.json()["verified"])

    def test_calibration_endpoints(self):
        # Calibration status
        status_res = self.client.get("/api/calibration/status")
        self.assertEqual(status_res.status_code, 200)
        st = status_res.json()
        self.assertIn("active_model_version", st)
        self.assertIn("benchmark_score", st)
        self.assertIn("observation_count", st)
        self.assertIn("guardrails", st)

        # Calibration retrain
        retrain_res = self.client.post("/api/calibration/retrain")
        self.assertEqual(retrain_res.status_code, 200)
        rt = retrain_res.json()
        self.assertIn("success", rt)
        self.assertIn("status", rt)

    def test_obsolete_legacy_routes_isolated(self):
        res = self.client.get("/api/challenges")
        self.assertEqual(res.status_code, 404)
        res2 = self.client.get("/api/assessments/dummy-id")
        self.assertEqual(res2.status_code, 404)


if __name__ == "__main__":
    unittest.main()
