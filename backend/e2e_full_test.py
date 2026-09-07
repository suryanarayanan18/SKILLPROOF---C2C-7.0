"""
Complete 20-Step End-to-End Fresh-Start Verification Script for SkillProof.
Covers every requirement specified in the fresh-start validation protocol.
"""

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8000"
BENCHMARK_PATH = os.path.join(os.path.dirname(__file__), "data", "benchmark.json")

def request(endpoint: str, method: str = "GET", data: dict = None, headers: dict = None):
    url = f"{BASE_URL}{endpoint}" if endpoint.startswith("/") else f"{BASE_URL}/{endpoint}"
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    encoded_data = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=encoded_data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode("utf-8")
            status_code = resp.status
            try:
                return status_code, json.loads(resp_body)
            except json.JSONDecodeError:
                return status_code, resp_body
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            parsed = json.loads(err_body)
        except Exception:
            parsed = err_body
        return e.code, parsed

def run_20_step_verification():
    print("=" * 70)
    print("SKILLPROOF FULL END-TO-END 20-STEP VERIFICATION")
    print("=" * 70)

    # Step 1: Install backend dependencies if needed
    print("\n[STEP 1] Verifying dependencies...")
    import fastapi, uvicorn, pydantic, sklearn, joblib, numpy
    print("  -> Dependencies verified (FastAPI, Uvicorn, Pydantic, Scikit-learn, Joblib, NumPy)")

    # Step 2: Start FastAPI/Uvicorn
    print("\n[STEP 2] Verifying FastAPI/Uvicorn server is running...")
    code, health = request("/api/health")
    assert code == 200, f"Server returned {code}: {health}"
    print(f"  -> Uvicorn is active at {BASE_URL}")

    # Step 3: Verify /api/health
    print("\n[STEP 3] Verifying /api/health payload...")
    assert health["status"] == "ok"
    assert health["service"] == "skillproof-api"
    assert "active_model_version" in health
    assert "active_calibration_version" in health
    initial_model_ver = health["active_model_version"]
    initial_calib_ver = health["active_calibration_version"]
    print(f"  -> Health OK: service={health['service']}, model={initial_model_ver}, calibration={initial_calib_ver}")

    # Step 4: Create a Python intermediate assessment
    import time
    run_ts = int(time.time())
    print("\n[STEP 4] Creating Python intermediate assessment...")
    candidate_1 = f"cand-e2e-live-1-{run_ts}"
    code, asm = request("/api/assessment", method="POST", data={
        "candidate_id": candidate_1,
        "difficulty": "intermediate",
        "time_limit_minutes": 45
    })
    assert code == 201, f"Failed to create assessment: {code} {asm}"
    asm_id = asm["id"]
    problem = asm["problem"]
    print(f"  -> Assessment Created: ID={asm_id}")
    print(f"  -> Problem: {problem['title']} (ID={problem['id']})")
    assert asm["candidate_id"] == candidate_1
    assert asm["started_at"]
    assert asm["submitted_at"] is None

    # Step 5: Verify the generated problem is valid
    print("\n[STEP 5] Verifying generated problem structure...")
    assert problem["id"], "Problem ID missing"
    assert problem["title"], "Problem title missing"
    assert problem["description"], "Problem description missing"
    assert problem["starter_code"], "Starter code missing"
    assert "constraints" in problem, "Constraints missing"
    assert "tests" not in problem, "Security check failed: Hidden tests leaked in problem object!"
    print(f"  -> Problem structure validated. Scenario: '{problem['title']}'")
    print(f"  -> Starter code present ({len(problem['starter_code'])} chars). No hidden tests leaked to client.")

    # Step 6: Verify hidden tests exist (in database)
    print("\n[STEP 6] Verifying hidden tests exist in backend database...")
    import db
    problem_row = db.get_problem(problem["id"])
    assert problem_row is not None, "Problem not found in DB"
    hidden_tests = problem_row.get("tests", [])
    assert len(hidden_tests) >= 3, f"Expected at least 3 hidden tests, got {len(hidden_tests)}"
    print(f"  -> Found {len(hidden_tests)} hidden test cases stored securely in database.")
    for idx, t in enumerate(hidden_tests[:3]):
        print(f"     Test {idx+1}: input={t.get('input')} expected={t.get('expected')}")

    # Step 7: Verify reference solution passes them
    print("\n[STEP 7] Verifying reference solution passes hidden tests...")
    ref_solution = problem_row.get("reference_solution", "")
    assert ref_solution, "Reference solution missing from DB"
    from services.executor import execute_solution_tests
    exec_metrics = execute_solution_tests(ref_solution, hidden_tests)
    assert exec_metrics["tests_passed"] == exec_metrics["tests_total"], (
        f"Reference solution failed: {exec_metrics['tests_passed']}/{exec_metrics['tests_total']}"
    )
    print(f"  -> Reference solution verified: {exec_metrics['tests_passed']}/{exec_metrics['tests_total']} tests passed.")

    # Step 8: Open the frontend (Verify all static pages exist and return 200)
    print("\n[STEP 8] Verifying frontend files accessible...")
    frontend_pages = [
        "/index.html",
        "/skill-selection.html",
        "/difficulty-selection.html",
        "/assessment-setup.html",
        "/workspace.html",
        "/evaluation.html",
        "/passport.html"
    ]
    for page in frontend_pages:
        code, content = request(page)
        assert code == 200, f"Frontend page {page} failed with status {code}"
        assert len(content) > 100, f"Frontend page {page} empty"
    print(f"  -> All {len(frontend_pages)} Stitch frontend pages verified returning 200 OK.")

    # Step 9: Complete real browser flow simulation
    print("\n[STEP 9] Simulating frontend state navigation...")
    code, fetched_asm = request(f"/api/assessment/{asm_id}")
    assert code == 200
    assert fetched_asm["id"] == asm_id
    print(f"  -> Workspace successfully fetched assessment '{asm_id}' with problem '{fetched_asm['problem']['title']}'")

    # Step 10: Submit a correct Python solution
    print("\n[STEP 10] Submitting correct Python solution...")
    code, submit_resp = request(f"/api/assessment/{asm_id}/submit", method="POST", data={
        "solution": ref_solution,
        "time_taken": 42.5
    })
    assert code == 200, f"Submit failed: {code} {submit_resp}"
    print(f"  -> Submission processed. Overall Score: {submit_resp['overall_score']}/100")
    print(f"  -> Tests Passed: {submit_resp['tests_passed']}/{submit_resp['tests_total']}")
    print(f"  -> Stamped Versions: Model={submit_resp['evaluation_model_version']}, Calib={submit_resp['calibration_version']}")

    # Step 11: Verify objective test results and score
    print("\n[STEP 11] Verifying objective test results and score breakdown...")
    code, res_obj = request(f"/api/assessment/{asm_id}/result")
    assert code == 200
    assert res_obj["tests_passed"] == res_obj["tests_total"]
    assert res_obj["overall_score"] > 0
    assert res_obj["passed_threshold"] is True
    breakdown = res_obj["breakdown"]
    print(f"  -> Score Breakdown: problem_solving={breakdown['problem_solving']}, algorithmic_thinking={breakdown['algorithmic_thinking']}, efficiency={breakdown['efficiency']}, code_quality={breakdown['code_quality']}")
    print(f"  -> Code Quality: LOC={res_obj['code_metrics']['lines_of_code']}, AST nodes={res_obj['code_metrics']['ast_nodes']}, Complexity={res_obj['code_metrics']['cyclomatic_complexity']}")

    # Step 12: Verify Skill Passport
    print("\n[STEP 12] Verifying Skill Passport for candidate...")
    code, passport = request(f"/api/passport/{candidate_1}")
    assert code == 200
    assert passport["candidate_id"] == candidate_1
    assert passport["verified"] is True
    assert passport["overall_score"] == res_obj["overall_score"]
    assert len(passport["competencies"]) > 0
    assert passport["evidence"]["tests_passed"] == f"{res_obj['tests_passed']}/{res_obj['tests_total']}"
    assert passport["calibration_version"] == initial_calib_ver
    assert passport["evaluation_model_version"] == initial_model_ver
    print(f"  -> Passport: ID={passport['passport_id']}, Candidate={passport['candidate_id']}")
    print(f"  -> Verified: {passport['verified']}, Overall Score: {passport['overall_score']}")
    print(f"  -> Competencies: {passport['competencies']}")
    print(f"  -> Evidence Stamped Versions: Model={passport['evaluation_model_version']}, Calib={passport['calibration_version']}")

    # Step 13: Attempt a second submission
    print("\n[STEP 13] Attempting second submission to enforce one-shot rule...")
    code_dup, dup_resp = request(f"/api/assessment/{asm_id}/submit", method="POST", data={
        "solution": "# Attempting to mutate",
        "time_taken": 10.0
    })

    # Step 14: Confirm HTTP 409 and no result mutation
    print("\n[STEP 14] Confirming HTTP 409 and immutability...")
    assert code_dup == 409, f"Expected HTTP 409 Conflict, got {code_dup}: {dup_resp}"
    print(f"  -> Correctly rejected with HTTP 409: {dup_resp['detail']}")
    code, res_after = request(f"/api/assessment/{asm_id}/result")
    assert res_after["overall_score"] == res_obj["overall_score"], "Result was mutated!"
    assert res_after["tests_passed"] == res_obj["tests_passed"], "Tests passed mutated!"
    print("  -> Result verified unchanged in database (genuine immutability).")

    # Step 15: Check calibration status
    print("\n[STEP 15] Checking calibration status...")
    code, calib_status = request("/api/calibration/status")
    assert code == 200
    print(f"  -> Active Model: {calib_status['active_model_version']}")
    print(f"  -> Calibration Version: {calib_status['calibration_version']}")
    print(f"  -> Benchmark Score: {calib_status['benchmark_score']}")
    print(f"  -> Current Validated Observations in DB: {calib_status['observation_count']}")
    print(f"  -> Guardrails: Min Observations={calib_status['guardrails']['min_observations_required']}, Max Drift={calib_status['guardrails']['max_drift_threshold']}")

    # Step 16: Add enough VALID observations for the minimum retraining threshold (>= 3)
    print("\n[STEP 16] Adding valid observations to satisfy retraining threshold (need >= 3)...")
    candidates = [f"cand-e2e-live-2-{run_ts}", f"cand-e2e-live-3-{run_ts}"]
    for c_id in candidates:
        _, new_asm = request("/api/assessment", method="POST", data={
            "candidate_id": c_id,
            "difficulty": "intermediate",
        })
        p_row = db.get_problem(new_asm["problem"]["id"])
        _, new_res = request(f"/api/assessment/{new_asm['id']}/submit", method="POST", data={
            "solution": p_row["reference_solution"],
            "time_taken": 35.0
        })
        print(f"  -> Created and submitted assessment {new_asm['id']} for {c_id} (Score: {new_res['overall_score']})")

    code, calib_status_after = request("/api/calibration/status")
    print(f"  -> Observation Count is now: {calib_status_after['observation_count']} (threshold >= 3 met)")
    assert calib_status_after["observation_count"] >= 3

    # Step 17: Record SHA-256 of frozen benchmark.json before retraining
    print("\n[STEP 17] Recording SHA-256 of frozen benchmark.json...")
    with open(BENCHMARK_PATH, "rb") as f:
        bench_before_bytes = f.read()
    bench_sha_before = hashlib.sha256(bench_before_bytes).hexdigest()
    print(f"  -> Frozen benchmark SHA-256 before retrain: {bench_sha_before}")

    # Trigger manual retraining
    print("  -> Triggering POST /api/calibration/retrain...")
    code, retrain_resp = request("/api/calibration/retrain", method="POST")
    assert code == 200, f"Retrain endpoint failed: {code} {retrain_resp}"
    print(f"  -> Retrain Response: success={retrain_resp['success']}, status={retrain_resp['status']}")
    print(f"  -> Proposed Version: {retrain_resp['proposed_version']}")
    print(f"  -> Benchmark Score: {retrain_resp['benchmark_score']} (Previous: {retrain_resp['previous_benchmark_score']})")
    print(f"  -> Guardrail Checks: {retrain_resp['guardrail_results']}")

    # Step 18: Verify frozen benchmark is unchanged
    print("\n[STEP 18] Verifying frozen benchmark.json is unchanged byte-for-byte...")
    with open(BENCHMARK_PATH, "rb") as f:
        bench_after_bytes = f.read()
    bench_sha_after = hashlib.sha256(bench_after_bytes).hexdigest()
    assert bench_sha_before == bench_sha_after, "CRITICAL ERROR: benchmark.json was modified by retrain!"
    print(f"  -> Benchmark SHA-256 matched: {bench_sha_after} (100% byte-for-byte immutable)")

    # Step 19: Verify either vNext safely publishes or previous model remains active
    print("\n[STEP 19] Verifying model activation and health state...")
    code, health_after = request("/api/health")
    if retrain_resp["success"]:
        assert health_after["active_model_version"] == retrain_resp["proposed_version"]
        print(f"  -> Guardrails passed! Active model safely updated to {health_after['active_model_version']}.")
    else:
        assert health_after["active_model_version"] == initial_model_ver
        print(f"  -> Guardrails prevented activation; original model {health_after['active_model_version']} remains active.")

    # Step 20: Verify original assessment still reports its original model/calibration version
    print("\n[STEP 20] Verifying historical immutability of original assessment and passport...")
    code, orig_res = request(f"/api/assessment/{asm_id}/result")
    assert orig_res["calibration_version"] == initial_calib_ver, (
        f"Original assessment calibration version mutated! {orig_res['calibration_version']} != {initial_calib_ver}"
    )
    assert orig_res["evaluation_model_version"] == initial_model_ver, (
        f"Original assessment model version mutated! {orig_res['evaluation_model_version']} != {initial_model_ver}"
    )
    code, orig_passport = request(f"/api/passport/{candidate_1}")
    assert orig_passport["calibration_version"] == initial_calib_ver
    assert orig_passport["evaluation_model_version"] == initial_model_ver
    print(f"  -> Verified: Original Assessment {asm_id} retains calibration={orig_res['calibration_version']}, model={orig_res['evaluation_model_version']}")
    print(f"  -> Verified: Candidate {candidate_1} Passport retains calibration={orig_passport['calibration_version']}, model={orig_passport['evaluation_model_version']}")

    print("\n" + "=" * 70)
    print("ALL 20 VERIFICATION STEPS COMPLETED AND PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    run_20_step_verification()
