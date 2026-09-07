"""Comprehensive End-to-End Test Suite for SkillProof Acceptance Criteria.

Validates:
1. Problem variation generation & 100% reference solution validation.
2. Isolated subprocess execution & timeout handling.
3. One-shot submission constraint enforcement (rejects attempt #2 with 409).
4. Objective scoring & dimensional breakdown.
5. Skill Passport generation with audit version tags.
6. TinyML training on validated observations, frozen benchmark gate, & guardrail protection.
"""

from __future__ import annotations

import json
from fastapi.testclient import TestClient

from app import app
import db
from ml.model import get_active_model
from ml.train import load_frozen_benchmark, evaluate_on_benchmark
from services.challenge_generator import generate_challenge, load_seed_problems
from services.executor import execute_solution_tests
from services.problem_validator import validate_problem

client = TestClient(app)


def test_health_endpoint():
    """Verify health endpoint returns status ok and active versions."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "active_calibration_version" in data
    assert "active_model_version" in data


def test_all_seed_problems_exist_and_validate():
    """Verify all 8 seed problems exist and their reference solutions pass 100% of tests."""
    seeds = load_seed_problems()
    assert len(seeds) >= 8, f"Expected >= 8 seed problems, found {len(seeds)}"

    for seed in seeds:
        is_valid, report = validate_problem(seed)
        assert is_valid, f"Seed problem {seed['id']} failed validation: {report}"
        assert report["tests_passed"] == report["tests_total"]


def test_challenge_generator_produces_novel_variation():
    """Verify variation engine creates transformed problem with validated reference solution."""
    variation = generate_challenge(difficulty="intermediate")
    assert variation["id"].startswith("SP-")
    assert len(variation["tests"]) >= 4
    # Validate reference solution on the newly generated test suite
    is_valid, report = validate_problem(variation)
    assert is_valid, f"Generated variation failed validation: {report}"


def test_subprocess_sandbox_timeout():
    """Verify execution sandbox safely times out infinite loops within limit."""
    infinite_loop_code = """
def solve(*args, **kwargs):
    while True:
        pass
"""
    dummy_tests = [{"name": "Infinite Loop Test", "input": [1, 2], "expected": 3}]
    res = execute_solution_tests(infinite_loop_code, dummy_tests, timeout_seconds=1.5)
    assert res["success"] is False
    assert "timed out" in res["error"].lower()
    assert res["tests_passed"] == 0


def test_one_shot_assessment_lifecycle_and_rejection():
    """
    Candidate takes one-shot assessment:
    1. Assessment is created.
    2. Candidate submits working solution -> succeeds.
    3. Candidate tries to submit again -> REJECTED with 409 Conflict.
    4. Passport is generated and contains audit version stamps.
    """
    cand_id = "test-candidate-001"

    # 1. Create assessment
    create_res = client.post(
        "/api/assessment",
        json={"candidate_id": cand_id, "difficulty": "intermediate"},
    )
    assert create_res.status_code == 201
    asm_data = create_res.json()
    assessment_id = asm_data["id"]
    problem_id = asm_data["problem"]["id"]

    # Fetch reference solution for this problem from DB
    problem_row = db.get_problem(problem_id)
    assert problem_row is not None
    ref_solution = problem_row["reference_solution"]

    # 2. First submission (Valid attempt)
    submit_res = client.post(
        f"/api/assessment/{assessment_id}/submit",
        json={"solution": ref_solution, "time_taken": 45.0},
    )
    assert submit_res.status_code == 200
    res_data = submit_res.json()
    assert res_data["tests_passed"] == res_data["tests_total"]
    assert res_data["overall_score"] >= 70.0
    assert "problem_version" in res_data
    assert "calibration_version" in res_data
    assert "evaluation_model_version" in res_data

    # 3. Second submission attempt (MUST BE REJECTED - One-Shot Rule)
    second_submit = client.post(
        f"/api/assessment/{assessment_id}/submit",
        json={"solution": ref_solution, "time_taken": 50.0},
    )
    assert second_submit.status_code == 409, "Second submission attempt must be rejected with 409 Conflict"
    assert "already been submitted" in second_submit.json()["detail"].lower()

    # 4. Skill Passport Retrieval
    passport_res = client.get(f"/api/passport/{cand_id}")
    assert passport_res.status_code == 200
    passport = passport_res.json()
    assert passport["candidate_id"] == cand_id
    assert passport["overall_score"] == res_data["overall_score"]
    assert passport["verified"] is True
    assert "Problem Solving" in passport["competencies"]
    assert passport["evidence"]["tests_passed"] == f"{res_data['tests_total']}/{res_data['tests_total']}"
    assert passport["calibration_version"] == res_data["calibration_version"]


def test_tinyml_calibration_and_frozen_benchmark():
    """
    Verify TinyML calibration loop:
    1. Cold-start model v1.0 passes frozen benchmark.
    2. Adding validated observations.
    3. Triggering retrain updates model to v1.1 if benchmark score and guardrails pass.
    """
    # 1. Check calibration status
    status_res = client.get("/api/calibration/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["benchmark_score"] >= 75.0

    # 2. Ensure at least 3 valid observations exist in the buffer
    for i in range(3):
        obs_payload = {
            "assessment_id": f"test-asm-obs-{i}",
            "problem_id": "array_frequency_k",
            "features": {
                "tests_passed_ratio": 1.0,
                "runtime_ms": 15.0,
                "lines_of_code": 12,
                "ast_nodes": 55,
                "cyclomatic_complexity": 2,
                "attempt_duration_sec": 300.0,
                "has_type_annotations": 1,
                "has_docstring": 1,
            },
            "result_metrics": {
                "overall_score": 88.0,
                "tests_passed": 5,
                "tests_total": 5,
            },
            "validity_flags": {
                "completed_submission": True,
                "non_trivial_runtime": True,
                "sufficient_duration": True,
            },
        }
        client.post("/api/calibration/observation", json=obs_payload)

    # 3. Trigger retrain
    retrain_res = client.post("/api/calibration/retrain")
    assert retrain_res.status_code == 200
    retrain_data = retrain_res.json()
    assert retrain_data["success"] is True
    assert retrain_data["proposed_version"] == "v1.1"
    assert retrain_data["benchmark_score"] >= 75.0

    # Verify active model is now v1.1
    status_after = client.get("/api/calibration/status").json()
    assert status_after["active_model_version"] == "v1.1"


if __name__ == "__main__":
    print("Running SkillProof E2E Acceptance Tests...")
    test_health_endpoint()
    print(" [PASS] Health endpoint")
    test_all_seed_problems_exist_and_validate()
    print(" [PASS] 8 Seed problems exist and reference solutions validate 100%")
    test_challenge_generator_produces_novel_variation()
    print(" [PASS] Template variation engine produces novel validated problems")
    test_subprocess_sandbox_timeout()
    print(" [PASS] Subprocess execution sandbox & timeout guard")
    test_one_shot_assessment_lifecycle_and_rejection()
    print(" [PASS] One-shot lifecycle, objective evaluation & 409 duplicate rejection")
    test_tinyml_calibration_and_frozen_benchmark()
    print(" [PASS] TinyML continuous calibration & frozen benchmark guardrails")
    print("\nALL ACCEPTANCE CRITERIA SUCCESSFULLY VERIFIED!")

