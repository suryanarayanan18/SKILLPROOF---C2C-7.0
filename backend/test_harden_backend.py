"""Comprehensive test suite verifying all hardened backend requirements for SkillProof."""

from __future__ import annotations

import concurrent.futures
import sqlite3
from typing import List
from fastapi.testclient import TestClient

import db
from app import app
from ml.model import get_active_model
from services.calibration import get_calibration_status, trigger_calibration_retrain
from services.challenge_generator import (
    generate_challenge,
    get_canonical_fallback_problem,
    load_seed_problems,
)
from services.executor import execute_solution_tests
from services.problem_validator import validate_problem

client = TestClient(app)


def test_api_contract_routes_exist():
    """Verify all 9 endpoints match the required API contract and obsolete routes are removed."""
    # 1. GET /api/health
    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"

    # 2. POST /api/assessment
    r_create = client.post("/api/assessment", json={"skill": "python", "difficulty": "intermediate"})
    assert r_create.status_code == 201
    asm_id = r_create.json()["id"]

    # 3. GET /api/assessment/{id}
    r_get = client.get(f"/api/assessment/{asm_id}")
    assert r_get.status_code == 200
    assert r_get.json()["id"] == asm_id

    # 4. POST /api/assessment/{id}/submit
    r_submit = client.post(f"/api/assessment/{asm_id}/submit", json={"solution": "def solve(*a, **k): return 0"})
    assert r_submit.status_code == 200

    # 5. GET /api/assessment/{id}/result
    r_result = client.get(f"/api/assessment/{asm_id}/result")
    assert r_result.status_code == 200
    assert r_result.json()["assessment_id"] == asm_id

    # 6. GET /api/passport/{candidate_id}
    cand_id = r_create.json()["candidate_id"]
    r_pass = client.get(f"/api/passport/{cand_id}")
    assert r_pass.status_code == 200
    assert r_pass.json()["candidate_id"] == cand_id

    # 7. POST /api/calibration/observation
    r_asmt_obs = client.post("/api/assessment", json={"skill": "python", "difficulty": "intermediate"})
    obs_asm_id = r_asmt_obs.json()["id"]
    obs_prob_id = r_asmt_obs.json()["problem"]["id"]
    r_obs = client.post(
        "/api/calibration/observation",
        json={
            "assessment_id": obs_asm_id,
            "problem_id": obs_prob_id,
            "features": {
                "tests_passed_ratio": 1.0,
                "runtime_ms": 15.0,
                "lines_of_code": 12,
                "ast_nodes": 45,
                "cyclomatic_complexity": 2,
                "attempt_duration_sec": 300.0,
                "has_type_annotations": 1,
                "has_docstring": 1,
            },
            "result_metrics": {"overall_score": 85.0, "tests_passed": 5, "tests_total": 5},
            "validity_flags": {"completed_submission": True, "quality_gate_passed": True},
        },
    )
    assert r_obs.status_code == 201

    # 8. GET /api/calibration/status
    r_calib = client.get("/api/calibration/status")
    assert r_calib.status_code == 200

    # 9. POST /api/calibration/retrain
    r_retrain = client.post("/api/calibration/retrain")
    assert r_retrain.status_code == 200

    # Verify obsolete routes return 404 or are absent from primary API surface
    assert client.get("/api/challenges").status_code == 404 or client.get("/api/challenges").status_code == 405
    assert client.get("/api/assessments/dummy").status_code == 404


def test_normal_assessment_creation_and_fields():
    """Verify problem generation produces all 12 required problem fields."""
    resp = client.post(
        "/api/assessment",
        json={"skill": "python", "difficulty": "intermediate"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("asm-")
    assert data["candidate_id"].startswith("cand-")
    assert data["submitted_at"] is None
    assert data["attempt_number"] == 1

    problem = data["problem"]
    required_fields = [
        "id",
        "seed_problem_id",
        "title",
        "description",
        "difficulty",
        "concepts",
        "algorithm_family",
        "constraints",
        "starter_code",
        "version",
    ]
    for field in required_fields:
        assert field in problem, f"Missing field {field} in problem"
        assert problem[field] is not None, f"Field {field} should not be None"


def test_valid_submission_deterministic_scoring_persistence():
    """Verify valid reference submission results in deterministic score and immutable persistence."""
    # Create assessment
    res = client.post("/api/assessment", json={"skill": "python", "difficulty": "intermediate"})
    assert res.status_code == 201
    asm = res.json()
    asm_id = asm["id"]
    cand_id = asm["candidate_id"]

    # Get problem definition with reference solution from DB
    problem_record = db.get_problem(asm["problem"]["id"])
    assert problem_record is not None
    ref_sol = problem_record["reference_solution"]

    # Submit reference solution
    submit_res = client.post(
        f"/api/assessment/{asm_id}/submit",
        json={"solution": ref_sol, "time_taken": 25.0},
    )
    assert submit_res.status_code == 200
    result_data = submit_res.json()

    # Verify deterministic scoring and all tests passed
    assert result_data["assessment_id"] == asm_id
    assert result_data["tests_passed"] == result_data["tests_total"]
    assert result_data["tests_total"] > 0
    assert result_data["overall_score"] >= 70.0
    assert result_data["passed_threshold"] is True

    # Check stamped audit versions
    active_m = get_active_model()
    assert result_data["problem_version"] == problem_record.get("version", "1.0")
    assert result_data["calibration_version"] == asm["calibration_version"]
    assert result_data["evaluation_model_version"] == active_m.version

    # Verify breakdown components
    bd = result_data["breakdown"]
    assert "problem_solving" in bd
    assert "algorithmic_thinking" in bd
    assert "efficiency" in bd
    assert "code_quality" in bd

    # Verify retrieval via GET /api/assessment/{id}/result
    get_res = client.get(f"/api/assessment/{asm_id}/result")
    assert get_res.status_code == 200
    assert get_res.json()["overall_score"] == result_data["overall_score"]

    # Verify Skill Passport reflects verified status
    passport_res = client.get(f"/api/passport/{cand_id}")
    assert passport_res.status_code == 200
    passport = passport_res.json()
    assert passport["verified"] is True
    assert passport["overall_score"] == result_data["overall_score"]
    assert passport["competencies"]["Problem Solving"] == bd["problem_solving"]


def test_one_shot_submission_enforcement_409():
    """Verify second submission attempt is strictly rejected with HTTP 409 Conflict."""
    res = client.post("/api/assessment", json={"skill": "python", "difficulty": "intermediate"})
    asm_id = res.json()["id"]

    # First submission
    sub1 = client.post(f"/api/assessment/{asm_id}/submit", json={"solution": "def solve(*args): return 0"})
    assert sub1.status_code == 200

    # Second submission must fail with 409
    sub2 = client.post(f"/api/assessment/{asm_id}/submit", json={"solution": "def solve(*args): return 1"})
    assert sub2.status_code == 409
    assert "already been submitted" in sub2.json()["detail"].lower() or "finalized" in sub2.json()["detail"].lower()

    # Third submission must also fail with 409
    sub3 = client.post(f"/api/assessment/{asm_id}/submit", json={"solution": "def solve(*args): return 2"})
    assert sub3.status_code == 409


def test_race_condition_concurrent_submissions():
    """Verify concurrent submission requests allow exactly ONE to succeed and reject others with 409."""
    res = client.post("/api/assessment", json={"skill": "python", "difficulty": "intermediate"})
    asm_id = res.json()["id"]

    num_threads = 6
    statuses = []

    def attempt_submit(worker_idx: int):
        with TestClient(app) as test_c:
            return test_c.post(
                f"/api/assessment/{asm_id}/submit",
                json={"solution": f"def solve(*args):\n    return {worker_idx}", "time_taken": 5.0},
            ).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(attempt_submit, i) for i in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            statuses.append(f.result())

    # Exactly 1 request should succeed (200), and all others must be 409
    success_count = statuses.count(200)
    conflict_count = statuses.count(409)

    assert success_count == 1, f"Expected exactly 1 success, got {success_count} (all statuses: {statuses})"
    assert conflict_count == num_threads - 1, f"Expected {num_threads - 1} conflicts, got {conflict_count}"


def test_immutable_result_persistence():
    """Verify that Result records cannot be overwritten after creation."""
    res = client.post("/api/assessment", json={"skill": "python", "difficulty": "intermediate"})
    asm_id = res.json()["id"]

    sub = client.post(f"/api/assessment/{asm_id}/submit", json={"solution": "def solve(*args): return 0"})
    assert sub.status_code == 200
    original_score = sub.json()["overall_score"]

    # Directly attempt to overwrite the result in db via save_result
    fake_result = {
        "assessment_id": asm_id,
        "tests_passed": 999,
        "tests_total": 999,
        "runtime": 0.001,
        "memory": 1.0,
        "time_taken": 1.0,
        "code_metrics": {},
        "overall_score": 100.0,
        "problem_version": "9.9",
        "calibration_version": "v9.9",
        "evaluation_model_version": "v9.9",
        "breakdown": {},
        "submission_code": "TAMPERED",
    }

    raised = False
    try:
        db.save_result(fake_result)
    except sqlite3.IntegrityError:
        raised = True
    assert raised, "Expected sqlite3.IntegrityError when attempting to overwrite result"

    # Confirm original result was not modified
    stored = db.get_result(asm_id)
    assert stored is not None
    assert stored["overall_score"] == original_score
    assert stored["tests_passed"] != 999


def test_sandbox_failure_cases_no_api_crash():
    """Verify syntax error, infinite loop timeout, and runtime exceptions return deterministic score without crashing API."""
    # 1. Syntax Error
    asm1 = client.post("/api/assessment", json={"skill": "python", "difficulty": "intermediate"}).json()
    res1 = client.post(f"/api/assessment/{asm1['id']}/submit", json={"solution": "def solve( incomplete syntax:"})
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["tests_passed"] == 0
    assert data1["passed_threshold"] is False
    assert data1["overall_score"] < 50.0

    # 2. Infinite Loop Timeout
    asm2 = client.post("/api/assessment", json={"skill": "python", "difficulty": "intermediate"}).json()
    res2 = client.post(
        f"/api/assessment/{asm2['id']}/submit",
        json={"solution": "def solve(*args, **kwargs):\n    while True:\n        pass\n"},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["tests_passed"] == 0
    assert data2["passed_threshold"] is False
    assert any("timed out" in str(t.get("error", "")).lower() for t in data2["test_runs"])

    # 3. Unhandled Runtime Exception
    asm3 = client.post("/api/assessment", json={"skill": "python", "difficulty": "intermediate"}).json()
    res3 = client.post(
        f"/api/assessment/{asm3['id']}/submit",
        json={"solution": "def solve(*args, **kwargs):\n    raise ZeroDivisionError('simulated crash')\n"},
    )
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["tests_passed"] == 0
    assert any("ZeroDivisionError" in str(t.get("error", "")) for t in data3["test_runs"])


def test_problem_reference_solution_self_validation():
    """Verify all hand-authored seed reference solutions cleanly pass 100% of their test cases."""
    problems = load_seed_problems()
    assert len(problems) >= 8, f"Expected at least 8 seed problems, found {len(problems)}"

    for p in problems:
        is_valid, report = validate_problem(p)
        assert is_valid, f"Seed problem {p['id']} failed self-validation: {report}"
        assert report["tests_passed"] == report["tests_total"]
        assert report["tests_total"] > 0

    # Test fallback problem generator
    fallback = get_canonical_fallback_problem()
    fb_valid, fb_report = validate_problem(fallback)
    assert fb_valid, f"Canonical fallback problem failed validation: {fb_report}"


def test_calibration_observation_and_guardrails():
    """Verify observation ingestion, quality gates, and guardrail enforcement during retrain."""
    import tempfile
    from pathlib import Path
    from ml.model import set_active_model
    from ml.train import bootstrap_v1_model

    old_db = db.DB_PATH
    temp_dir = tempfile.mkdtemp()
    db.DB_PATH = Path(temp_dir) / "test_harden_calib.sqlite3"
    db.init_db()
    set_active_model(None)
    m1 = bootstrap_v1_model()
    set_active_model(m1)

    try:
        status_data = get_calibration_status()
        assert "guardrails" in status_data
        assert status_data["guardrails"]["min_observations_required"] == 3

        # Retrain with insufficient observations should fail guardrails safely
        retrain_res = client.post("/api/calibration/retrain")
        assert retrain_res.status_code == 200
        retrain_data = retrain_res.json()
        assert retrain_data["success"] is False
        assert retrain_data["status"] == "rejected"
        assert "Insufficient observations" in retrain_data["message"]

        # Record validated observations
        for i in range(3):
            r_create_obs = client.post("/api/assessment", json={"skill": "python", "difficulty": "intermediate"})
            cur_asmt_id = r_create_obs.json()["id"]
            cur_prob_id = r_create_obs.json()["problem"]["id"]
            obs_res = client.post(
                "/api/calibration/observation",
                json={
                    "assessment_id": cur_asmt_id,
                    "problem_id": cur_prob_id,
                    "features": {
                        "tests_passed_ratio": 0.8 + (i % 2) * 0.2,
                        "runtime_ms": 15.0,
                        "lines_of_code": 15,
                        "ast_nodes": 50,
                        "cyclomatic_complexity": 2,
                        "attempt_duration_sec": 120.0,
                        "has_type_annotations": 1,
                        "has_docstring": 1,
                    },
                    "result_metrics": {
                        "overall_score": 82.0 + i * 3.0,
                        "tests_passed": 4 + (i % 2),
                        "tests_total": 5,
                    },
                    "validity_flags": {
                        "completed_submission": True,
                        "quality_gate_passed": True,
                        "non_trivial_runtime": True,
                        "sufficient_duration": True,
                    },
                },
            )
            assert obs_res.status_code == 201
            assert "observation_id" in obs_res.json()

        # Now with >= 3 observations, trigger retraining
        retrain_res2 = client.post("/api/calibration/retrain")
        assert retrain_res2.status_code == 200
        retrain_data2 = retrain_res2.json()
        assert retrain_data2["guardrail_results"]["observation_count_check"] is True
        assert retrain_data2["guardrail_results"]["frozen_benchmark_check"] is True
        assert retrain_data2["guardrail_results"]["drift_guardrail_check"] is True
        assert retrain_data2["success"] is True
        assert retrain_data2["status"] == "activated"
    finally:
        db.DB_PATH = old_db


def test_frontend_complete_flow():
    """Verify complete end-to-end frontend client flow from landing to passport."""
    # 1. Verify all frontend static pages serve 200 OK
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
    ]
    for page in pages:
        r = client.get(page)
        assert r.status_code == 200, f"Page {page} failed to serve: {r.status_code}"

    # 2. Step 1: Candidate selects skill and difficulty -> creates assessment
    cand_id = "cand-test-flow-88"
    r_create = client.post(
        "/api/assessment",
        json={"skill": "python", "difficulty": "intermediate", "candidate_id": cand_id},
    )
    assert r_create.status_code == 201
    asm_data = r_create.json()
    asm_id = asm_data["id"]
    problem = asm_data["problem"]
    assert asm_data["candidate_id"] == cand_id
    assert "title" in problem
    assert "constraints" in problem
    assert "starter_code" in problem

    # 3. Step 2: Candidate workspace loads assessment
    r_fetch = client.get(f"/api/assessment/{asm_id}")
    assert r_fetch.status_code == 200
    fetched_prob = r_fetch.json()["problem"]
    assert fetched_prob["title"] == problem["title"]
    assert "tests" not in fetched_prob  # Never exposed to client

    # 4. Step 3: Candidate submits solution in workspace
    r_submit = client.post(
        f"/api/assessment/{asm_id}/submit",
        json={"solution": problem["starter_code"] + "\n    return True\n", "time_taken": 25.0},
    )
    assert r_submit.status_code == 200
    sub_data = r_submit.json()
    assert "overall_score" in sub_data
    assert "tests_passed" in sub_data
    assert "tests_total" in sub_data
    assert "breakdown" in sub_data
    assert "problem_solving" in sub_data["breakdown"]
    assert "algorithmic_thinking" in sub_data["breakdown"]
    assert "efficiency" in sub_data["breakdown"]
    assert "code_quality" in sub_data["breakdown"]
    assert "problem_version" in sub_data
    assert "calibration_version" in sub_data
    assert "evaluation_model_version" in sub_data

    # 5. Step 4: Resubmission attempt must return 409 Conflict
    r_conflict = client.post(
        f"/api/assessment/{asm_id}/submit",
        json={"solution": "def different(): pass"},
    )
    assert r_conflict.status_code == 409
    assert "already been submitted" in r_conflict.json()["detail"].lower()

    # 6. Step 5: Evaluation screen fetches result
    r_res = client.get(f"/api/assessment/{asm_id}/result")
    assert r_res.status_code == 200
    res_data = r_res.json()
    assert res_data["overall_score"] == sub_data["overall_score"]

    # 7. Step 6: Passport screen fetches candidate passport
    r_pass = client.get(f"/api/passport/{cand_id}")
    assert r_pass.status_code == 200
    pass_data = r_pass.json()
    assert pass_data["candidate_id"] == cand_id
    assert pass_data["overall_score"] == sub_data["overall_score"]
    assert "passport_id" in pass_data
    assert "competencies" in pass_data
    assert "evidence" in pass_data
    assert "tests_passed" in pass_data["evidence"]
    assert "runtime_seconds" in pass_data["evidence"]
    assert "memory_mb" in pass_data["evidence"]
    assert "problem_version" in pass_data
    assert "calibration_version" in pass_data
    assert "evaluation_model_version" in pass_data

    # 8. Unassessed candidate returns 404
    r_empty = client.get("/api/passport/unassessed-candidate-xyz")
    assert r_empty.status_code == 404

    # 9. Analytics dashboard gets calibration status
    r_calib = client.get("/api/calibration/status")
    assert r_calib.status_code == 200
    calib_data = r_calib.json()
    assert "active_model_version" in calib_data
    assert "calibration_version" in calib_data
    assert "benchmark_score" in calib_data
    assert "observation_count" in calib_data
    assert "guardrails" in calib_data



if __name__ == "__main__":
    import inspect
    import sys

    print("Running test_harden_backend.py suite...")
    current_module = sys.modules[__name__]
    test_funcs = [
        obj for name, obj in inspect.getmembers(current_module)
        if inspect.isfunction(obj) and name.startswith("test_")
    ]

    passed = 0
    failed = 0
    for fn in test_funcs:
        print(f"-> Running {fn.__name__}...", end=" ", flush=True)
        try:
            fn()
            print("PASSED")
            passed += 1
        except Exception as e:
            print(f"FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\nSummary: {passed} passed, {failed} failed out of {len(test_funcs)} tests.")
    if failed > 0:
        sys.exit(1)

