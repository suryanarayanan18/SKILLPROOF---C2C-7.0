import json
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"

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

def test_all_scenarios():
    print("--- Starting IDE / Workspace Verification (Scenarios A - E) ---")

    # 1. Create an assessment with seed_problem_id = array_frequency_k
    status, asm = make_req("/api/assessment", "POST", {
        "skill": "python",
        "difficulty": "intermediate",
        "seed_problem_id": "array_frequency_k"
    })
    assert status == 201, f"Failed to create assessment: {asm}"
    asm_id = asm["id"]
    prob = asm["problem"]
    print(f"Created Assessment: {asm_id}")
    print(f"  Title: {prob['title']}")
    print(f"  Difficulty: {prob['difficulty']}")
    print(f"  Starter Code present: {bool(prob['starter_code'])}")
    print(f"  Examples present: {len(prob.get('examples', [])) > 0}")

    # 2. GET /api/assessment/{asm_id}
    status, fetched = make_req(f"/api/assessment/{asm_id}")
    assert status == 200, f"Failed to fetch assessment: {fetched}"
    assert fetched["id"] == asm_id

    # -------------------------------------------------------------
    # Scenario A: Run Code & Submit with CORRECT solution
    # -------------------------------------------------------------
    print("\n--- Testing Scenario A: Correct Solution ---")
    correct_code = (
        "from collections import Counter\n\n"
        "def solve(items, k):\n"
        "    counts = Counter(items)\n"
        "    candidates = [val for val, count in counts.items() if count >= k]\n"
        "    return min(candidates) if candidates else -1\n"
    )

    # Test Run Code endpoint
    run_status, run_res = make_req(f"/api/assessment/{asm_id}/run", "POST", {"solution": correct_code})
    print(f"Run Code status: {run_status}, status_str: {run_res.get('status')}, passed: {run_res.get('tests_passed')}/{run_res.get('tests_total')}")
    assert run_status == 200
    assert run_res["status"] == "ok"
    assert run_res["tests_passed"] == run_res["tests_total"]

    # Submit Solution
    sub_status, sub_res = make_req(f"/api/assessment/{asm_id}/submit", "POST", {"solution": correct_code, "time_taken": 45.0})
    print(f"Submit status: {sub_status}, overall_score: {sub_res.get('overall_score')}, tests_passed: {sub_res.get('tests_passed')}/{sub_res.get('tests_total')}")
    assert sub_status == 200
    assert sub_res["tests_passed"] == sub_res["tests_total"]
    assert sub_res["overall_score"] >= 70.0

    # Verify backend stored exact candidate code
    res_status, final_res = make_req(f"/api/assessment/{asm_id}/result")
    assert res_status == 200
    assert final_res.get("submission_code") == correct_code
    print("Exact candidate code verified in backend result record.")

    # -------------------------------------------------------------
    # Scenario E: Second submission on same assessment (HTTP 409)
    # -------------------------------------------------------------
    print("\n--- Testing Scenario E: Second Submission (HTTP 409) ---")
    sec_status, sec_res = make_req(f"/api/assessment/{asm_id}/submit", "POST", {"solution": correct_code})
    print(f"Second submit status: {sec_status}, detail: {sec_res.get('detail')}")
    assert sec_status == 409, f"Expected 409 Conflict, got {sec_status}"

    # Also verify Run Code is rejected on submitted assessment
    sec_run_status, sec_run_res = make_req(f"/api/assessment/{asm_id}/run", "POST", {"solution": correct_code})
    print(f"Second run status: {sec_run_status}, detail: {sec_run_res.get('detail')}")
    assert sec_run_status == 409

    # -------------------------------------------------------------
    # Scenario B: Incorrect Python Solution on fresh assessment
    # -------------------------------------------------------------
    print("\n--- Testing Scenario B: Incorrect Solution ---")
    status, asm_b = make_req("/api/assessment", "POST", {"skill": "python", "difficulty": "intermediate"})
    asm_b_id = asm_b["id"]
    incorrect_code = "def solve(*args, **kwargs):\n    return 9999999\n"

    run_b_status, run_b_res = make_req(f"/api/assessment/{asm_b_id}/run", "POST", {"solution": incorrect_code})
    print(f"Run Code status: {run_b_status}, status_str: {run_b_res.get('status')}, passed: {run_b_res.get('tests_passed')}/{run_b_res.get('tests_total')}")
    assert run_b_status == 200
    assert run_b_res["tests_passed"] < run_b_res["tests_total"]

    sub_b_status, sub_b_res = make_req(f"/api/assessment/{asm_b_id}/submit", "POST", {"solution": incorrect_code})
    print(f"Submit status: {sub_b_status}, overall_score: {sub_b_res.get('overall_score')}, tests_passed: {sub_b_res.get('tests_passed')}/{sub_b_res.get('tests_total')}")
    assert sub_b_status == 200
    assert sub_b_res["tests_passed"] < sub_b_res["tests_total"]

    # -------------------------------------------------------------
    # Scenario C: Syntax Error
    # -------------------------------------------------------------
    print("\n--- Testing Scenario C: Syntax Error ---")
    status, asm_c = make_req("/api/assessment", "POST", {"skill": "python", "difficulty": "intermediate"})
    asm_c_id = asm_c["id"]
    syntax_err_code = "def solve(:\n invalid syntax !!!\n"

    run_c_status, run_c_res = make_req(f"/api/assessment/{asm_c_id}/run", "POST", {"solution": syntax_err_code})
    print(f"Run Code status: {run_c_status}, status_str: {run_c_res.get('status')}, error: {run_c_res.get('error')[:60]}...")
    assert run_c_status == 200
    assert run_c_res["status"] == "syntax_error"

    sub_c_status, sub_c_res = make_req(f"/api/assessment/{asm_c_id}/submit", "POST", {"solution": syntax_err_code})
    print(f"Submit status: {sub_c_status}, overall_score: {sub_c_res.get('overall_score')}, tests_passed: {sub_c_res.get('tests_passed')}/{sub_c_res.get('tests_total')}")
    assert sub_c_status == 200
    assert sub_c_res["tests_passed"] == 0

    # -------------------------------------------------------------
    # Scenario D: Runtime Error
    # -------------------------------------------------------------
    print("\n--- Testing Scenario D: Runtime Error ---")
    status, asm_d = make_req("/api/assessment", "POST", {"skill": "python", "difficulty": "intermediate"})
    asm_d_id = asm_d["id"]
    runtime_err_code = "def solve(*args, **kwargs):\n    return 1 / 0\n"

    run_d_status, run_d_res = make_req(f"/api/assessment/{asm_d_id}/run", "POST", {"solution": runtime_err_code})
    err_msg = run_d_res.get('error') or "(per-test errors)"
    print(f"Run Code status: {run_d_status}, status_str: {run_d_res.get('status')}, error: {err_msg[:60]}...")
    assert run_d_status == 200
    # Runtime error inside solve() is caught per-test by the harness — top-level status may be "ok"
    # but all tests should fail
    assert run_d_res["tests_passed"] == 0

    sub_d_status, sub_d_res = make_req(f"/api/assessment/{asm_d_id}/submit", "POST", {"solution": runtime_err_code})
    print(f"Submit status: {sub_d_status}, overall_score: {sub_d_res.get('overall_score')}, tests_passed: {sub_d_res.get('tests_passed')}/{sub_d_res.get('tests_total')}")
    assert sub_d_status == 200
    assert sub_d_res["tests_passed"] == 0

    print("\n========================================================")
    print("ALL SCENARIOS A, B, C, D, E PASSED WITH 100% VERIFICATION!")
    print("========================================================\n")

if __name__ == "__main__":
    test_all_scenarios()
