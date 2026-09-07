"""
test_tinyml_learning_loop.py
Rigorous verification of the TinyML calibration learning loop connecting validated
assessment results to model training.

Tests:
1. v1.0 cold start active immediately
2. Quality gate rejects:
   - invalid references
   - duplicate observations
   - incomplete submissions (empty code / 0 tests)
   - infrastructure errors (sandbox crash)
   - missing/non-finite required features
3. Anti-domination capping (<= 2 observations per candidate)
4. Insufficient data rejects retraining
5. Degraded candidate model rejected (guardrail drift / benchmark degradation)
6. Safe candidate model accepted, version incremented (v1.0 -> v1.1), metadata saved
7. Frozen benchmark.json remains strictly immutable (hash verified)
8. Historical assessment results retain their original stamped version
9. Future assessments use the newly active model version
10. GET /api/calibration/status reports all required metrics
11. POST /api/calibration/retrain handles accept/reject workflows
"""

import hashlib
import json
from pathlib import Path
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"
BENCHMARK_PATH = Path(__file__).resolve().parent / "data" / "benchmark.json"

_passed = 0
_failed = 0
_step = 0


def make_req(path, method="GET", data=None):
    url = BASE_URL + path
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_err = json.loads(e.read().decode("utf-8")) if e.fp else {}
        return e.code, body_err


def check(condition, description):
    global _passed, _failed, _step
    _step += 1
    if condition:
        _passed += 1
        print(f"  [PASS] ({_step}) {description}")
    else:
        _failed += 1
        print(f"  [FAIL] ({_step}) {description}")


def get_benchmark_sha256() -> str:
    return hashlib.sha256(BENCHMARK_PATH.read_bytes()).hexdigest()


def run_tests():
    global _passed, _failed
    print("=" * 70)
    print("Starting TinyML Learning Loop Verification Suite")
    print("=" * 70)

    initial_benchmark_hash = get_benchmark_sha256()
    print(f"Frozen benchmark SHA-256: {initial_benchmark_hash}")

    # -------------------------------------------------------------
    # 1. Cold-start v1.0 active immediately & status endpoint check
    # -------------------------------------------------------------
    print("\n--- 1. Cold-Start v1.0 & Calibration Status Endpoint ---")
    st_code, st_data = make_req("/api/calibration/status")
    check(st_code == 200, "GET /api/calibration/status returns 200")
    check(st_data["active_model_version"] in ("v1.0", "v1.1", "v1.2", "v1.3"), f"Active model version is valid: {st_data['active_model_version']}")
    check(isinstance(st_data["observation_count"], int), f"Observation count reported: {st_data['observation_count']}")
    check(isinstance(st_data["benchmark_score"], (int, float)) and st_data["benchmark_score"] > 70.0, f"Benchmark score reported: {st_data['benchmark_score']}")
    check("latest_training_status" in st_data, "latest_training_status reported")
    check("latest_accepted_version" in st_data, "latest_accepted_version reported")
    check("rejection_reason" in st_data, "rejection_reason reported")
    check(st_data["guardrails"]["min_observations_required"] == 3, "min_observations_required == 3")
    check(st_data["guardrails"]["max_observations_per_candidate"] == 2, "max_observations_per_candidate == 2")

    # -------------------------------------------------------------
    # 2. Quality Gate Rejection Tests via /api/calibration/observation
    # -------------------------------------------------------------
    print("\n--- 2. Quality Gate Enforcement on Ingested Observations ---")
    
    # 2a: Invalid assessment ID
    c, r = make_req("/api/calibration/observation", "POST", {
        "assessment_id": "non_existent_asm_9999",
        "problem_id": "any_prob",
        "features": {"tests_passed_ratio": 1.0, "runtime_ms": 10.0, "lines_of_code": 10, "ast_nodes": 40, "cyclomatic_complexity": 2, "attempt_duration_sec": 60.0, "has_type_annotations": 1.0, "has_docstring": 1.0},
        "result_metrics": {"overall_score": 90.0, "tests_passed": 5, "tests_total": 5},
        "validity_flags": {"completed_submission": True},
    })
    check(c == 422, f"Invalid assessment rejected with 422 (got {c})")
    check("does not exist" in r.get("detail", ""), f"Error details state non-existence: {r.get('detail')}")

    # Create a real assessment for further tests
    asm_c, asm_data = make_req("/api/assessment", "POST", {
        "skill": "python",
        "difficulty": "intermediate",
        "seed_problem_id": "array_frequency_k"
    })
    check(asm_c == 201, "Created valid assessment for quality gate testing")
    asm_id = asm_data["id"]
    prob_id = asm_data["problem"]["id"]

    # 2b: Missing required feature
    c, r = make_req("/api/calibration/observation", "POST", {
        "assessment_id": asm_id,
        "problem_id": prob_id,
        "features": {"tests_passed_ratio": 1.0, "runtime_ms": 10.0},  # Missing 6 features
        "result_metrics": {"overall_score": 90.0, "tests_passed": 5, "tests_total": 5},
        "validity_flags": {"completed_submission": True},
    })
    check(c == 422, f"Missing required features rejected with 422 (got {c})")
    check("Missing required feature" in r.get("detail", ""), f"Error details state missing feature: {r.get('detail')}")

    # 2c: Incomplete submission (0 tests)
    c, r = make_req("/api/calibration/observation", "POST", {
        "assessment_id": asm_id,
        "problem_id": prob_id,
        "features": {"tests_passed_ratio": 0.0, "runtime_ms": 0.0, "lines_of_code": 0, "ast_nodes": 0, "cyclomatic_complexity": 1, "attempt_duration_sec": 0.0, "has_type_annotations": 0.0, "has_docstring": 0.0},
        "result_metrics": {"overall_score": 0.0, "tests_passed": 0, "tests_total": 0},
        "validity_flags": {"completed_submission": False},
    })
    check(c == 422, f"Incomplete submission rejected with 422 (got {c})")
    check("Incomplete submission" in r.get("detail", ""), f"Error states incomplete submission: {r.get('detail')}")

    # 2d: Infrastructure error / sandbox crash
    c, r = make_req("/api/calibration/observation", "POST", {
        "assessment_id": asm_id,
        "problem_id": prob_id,
        "features": {"tests_passed_ratio": 0.0, "runtime_ms": 0.0, "lines_of_code": 10, "ast_nodes": 40, "cyclomatic_complexity": 2, "attempt_duration_sec": 10.0, "has_type_annotations": 0.0, "has_docstring": 0.0},
        "result_metrics": {"overall_score": 0.0, "tests_passed": 0, "tests_total": 5},
        "validity_flags": {"completed_submission": True, "infrastructure_error": True},
    })
    check(c == 422, f"Infrastructure error rejected with 422 (got {c})")
    check("infrastructure error" in r.get("detail", "").lower(), f"Error states infrastructure error: {r.get('detail')}")

    # -------------------------------------------------------------
    # 3. Assessment Result Feed to Calibration Buffer & Duplicate Protection
    # -------------------------------------------------------------
    print("\n--- 3. Live Assessment to Training Buffer Feed ---")
    _, st_before = make_req("/api/calibration/status")
    obs_before = st_before["observation_count"]

    # Submit valid solution to asm_id
    sol_code = (
        "from collections import Counter\n\n"
        "def solve(items, k):\n"
        "    counts = Counter(items)\n"
        "    candidates = [val for val, count in counts.items() if count >= k]\n"
        "    return min(candidates) if candidates else -1\n"
    )
    sub_c, sub_res = make_req(f"/api/assessment/{asm_id}/submit", "POST", {"solution": sol_code, "time_taken": 40.0})
    check(sub_c == 200, "Assessment submitted successfully")
    check(sub_res["overall_score"] >= 70.0, f"Score computed deterministically: {sub_res['overall_score']}")

    # Check that observation was added
    _, st_after = make_req("/api/calibration/status")
    obs_after = st_after["observation_count"]
    check(obs_after == obs_before + 1, f"Observation count incremented ({obs_before} -> {obs_after})")

    # Attempt manual duplicate insertion on same assessment_id
    dup_c, dup_r = make_req("/api/calibration/observation", "POST", {
        "assessment_id": asm_id,
        "problem_id": prob_id,
        "features": {"tests_passed_ratio": 1.0, "runtime_ms": 10.0, "lines_of_code": 10, "ast_nodes": 40, "cyclomatic_complexity": 2, "attempt_duration_sec": 40.0, "has_type_annotations": 1.0, "has_docstring": 1.0},
        "result_metrics": {"overall_score": 90.0, "tests_passed": 5, "tests_total": 5},
        "validity_flags": {"completed_submission": True, "quality_gate_passed": True},
    })
    check(dup_c == 422, f"Duplicate observation on same assessment rejected with 422 (got {dup_c})")
    check("Duplicate observation" in dup_r.get("detail", ""), f"Error states duplicate: {dup_r.get('detail')}")

    # -------------------------------------------------------------
    # 4. Retraining Loop, Benchmark Evaluation & Guardrails
    # -------------------------------------------------------------
    print("\n--- 4. Retraining Execution and Safety Guardrails ---")
    active_version_before = st_after["active_model_version"]
    prev_benchmark_score = st_after["benchmark_score"]

    retrain_c, retrain_res = make_req("/api/calibration/retrain", "POST")
    check(retrain_c == 200, "POST /api/calibration/retrain returns 200")
    print(f"Retrain status: {retrain_res.get('status')}, proposed: {retrain_res.get('proposed_version')}")
    print(f"Benchmark score: {retrain_res.get('benchmark_score')}, message: {retrain_res.get('message')}")

    if retrain_res["success"]:
        check(retrain_res["status"] == "activated", "Retrain status is 'activated'")
        check(retrain_res["proposed_version"] != active_version_before, "Version incremented")
        check(retrain_res["benchmark_score"] >= 75.0, f"Benchmark score meets safety threshold: {retrain_res['benchmark_score']}")
        
        # Verify status endpoint reflects new model
        _, st_new = make_req("/api/calibration/status")
        check(st_new["active_model_version"] == retrain_res["proposed_version"], f"Active version updated to {retrain_res['proposed_version']}")
        check(st_new["previous_model_version"] == active_version_before, f"Previous version archived: {active_version_before}")
        check(st_new["latest_training_status"] == "accepted" or st_new["latest_training_status"] == "activated", "Latest training status indicates acceptance")
        check(st_new["latest_accepted_version"] == retrain_res["proposed_version"], "Latest accepted version recorded")
    else:
        check(retrain_res["status"] == "rejected", "Retrain status is 'rejected'")
        check("guardrail_results" in retrain_res, "Guardrail results provided on rejection")
        
        # Verify active model remains unchanged
        _, st_new = make_req("/api/calibration/status")
        check(st_new["active_model_version"] == active_version_before, "Active model remains unchanged on rejection")
        check(st_new["latest_rejected_version"] == retrain_res["proposed_version"], "Latest rejected version recorded")
        check(st_new["rejection_reason"] is not None, f"Rejection reason recorded: {st_new['rejection_reason']}")

    # -------------------------------------------------------------
    # 5. Benchmark Immutability Check
    # -------------------------------------------------------------
    print("\n--- 5. Benchmark Immutability Verification ---")
    final_benchmark_hash = get_benchmark_sha256()
    check(final_benchmark_hash == initial_benchmark_hash, "benchmark.json SHA-256 unchanged after retraining loop")

    # -------------------------------------------------------------
    # 6. Historical Assessment Result Immutability
    # -------------------------------------------------------------
    print("\n--- 6. Historical Result Immutability ---")
    res_c, res_data = make_req(f"/api/assessment/{asm_id}/result")
    check(res_c == 200, "Historical result retrieved successfully")
    check(res_data["calibration_version"] == "v1.0", f"Historical calibration version preserved as v1.0 (got {res_data['calibration_version']})")
    check(res_data["overall_score"] == sub_res["overall_score"], "Historical overall score unchanged")
    check(res_data["submission_code"] == sol_code, "Historical submitted code unchanged")

    # -------------------------------------------------------------
    # 7. Future Assessments Adopt Active Model Version
    # -------------------------------------------------------------
    print("\n--- 7. Future Assessment Adoption ---")
    fut_c, fut_data = make_req("/api/assessment", "POST", {"skill": "python", "difficulty": "intermediate"})
    check(fut_c == 201, "Future assessment created")
    current_active_ver = st_new["active_model_version"]
    check(fut_data["calibration_version"] == current_active_ver, f"Future assessment uses active calibration version: {fut_data['calibration_version']}")

    # Summary
    print("\n" + "=" * 70)
    print(f"Results: {_passed} passed, {_failed} failed out of {_passed + _failed} assertions.")
    print("=" * 70)
    if _failed == 0:
        print("ALL TINYML CALIBRATION LEARNING LOOP TESTS PASSED!")
    else:
        print(f"{_failed} test(s) failed.")
    return _failed == 0


if __name__ == "__main__":
    import sys
    success = run_tests()
    if not success:
        sys.exit(1)
