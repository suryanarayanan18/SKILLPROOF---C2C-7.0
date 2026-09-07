"""SkillProof Brain â€” Comprehensive Verification Test Suite.

Tests the full objective evaluation pipeline:
  Generated Problem â†’ Hidden Tests â†’ Candidate Code Execution â†’ Objective Evaluation
  â†’ Score Breakdown â†’ Skill Evidence â†’ Validated Observation â†’ TinyML Calibration

Proves:
  1. A correct solution scores highly.
  2. A partially correct solution scores lower.
  3. An incorrect solution scores low.
  4. Syntax errors are handled.
  5. Runtime errors are handled.
  6. Timeout is handled.
  7. Hidden tests are actually used.
  8. Reference solution passes generated tests.
  9. Same code + same problem version produces the same result (determinism).
  10. Second submission returns HTTP 409.
  11. Historical result cannot be overwritten.
"""

import json
import time
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"

# ---- Test counters ----
_pass_count = 0
_fail_count = 0
_test_num = 0


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
    """Assert a condition and track pass/fail counts."""
    global _pass_count, _fail_count, _test_num
    _test_num += 1
    if condition:
        _pass_count += 1
        print(f"  âœ“ [{_test_num}] {description}")
    else:
        _fail_count += 1
        print(f"  âœ— [{_test_num}] FAILED: {description}")


def create_assessment(seed_problem_id=None, difficulty="intermediate"):
    """Helper: create an assessment and return (assessment_id, problem)."""
    payload = {"skill": "python", "difficulty": difficulty}
    if seed_problem_id:
        payload["seed_problem_id"] = seed_problem_id
    status, body = make_req("/api/assessment", "POST", payload)
    assert status == 201, f"Assessment creation failed: {status} {body}"
    return body["id"], body["problem"], body


def submit(assessment_id, code, time_taken=30.0):
    """Helper: submit code to an assessment."""
    return make_req(
        f"/api/assessment/{assessment_id}/submit",
        "POST",
        {"solution": code, "time_taken": time_taken},
    )


def run_code(assessment_id, code):
    """Helper: run code in sandbox."""
    return make_req(
        f"/api/assessment/{assessment_id}/run",
        "POST",
        {"solution": code},
    )


# ---- Reference solutions for each seed problem (from the seed corpus) ----
CORRECT_SOLUTIONS = {
    "array_frequency_k": (
        "from collections import Counter\n\n"
        "def solve(items, k):\n"
        "    counts = Counter(items)\n"
        "    candidates = [val for val, count in counts.items() if count >= k]\n"
        "    return min(candidates) if candidates else -1\n"
    ),
    "sliding_window_anomaly": (
        "def solve(stream, window_size):\n"
        "    if not stream or window_size <= 0 or len(stream) < window_size:\n"
        "        return 0.0\n"
        "    w_sum = sum(stream[:window_size])\n"
        "    max_sum = w_sum\n"
        "    for i in range(window_size, len(stream)):\n"
        "        w_sum += stream[i] - stream[i - window_size]\n"
        "        if w_sum > max_sum:\n"
        "            max_sum = w_sum\n"
        "    return round(float(max_sum) / window_size, 2)\n"
    ),
    "interval_consolidation": (
        "def solve(intervals):\n"
        "    if not intervals:\n"
        "        return []\n"
        "    sorted_int = sorted(intervals, key=lambda x: x[0])\n"
        "    merged = [list(sorted_int[0])]\n"
        "    for cur in sorted_int[1:]:\n"
        "        prev = merged[-1]\n"
        "        if cur[0] <= prev[1]:\n"
        "            prev[1] = max(prev[1], cur[1])\n"
        "        else:\n"
        "            merged.append(list(cur))\n"
        "    return merged\n"
    ),
    "stack_syntax_validator": (
        "def solve(expression):\n"
        "    stack = []\n"
        "    matching = {')': '(', ']': '[', '}': '{'}\n"
        "    for ch in str(expression):\n"
        "        if ch in '([{':\n"
        "            stack.append(ch)\n"
        "        elif ch in ')]}':\n"
        "            if not stack or stack[-1] != matching[ch]:\n"
        "                return False\n"
        "            stack.pop()\n"
        "    return len(stack) == 0\n"
    ),
    "prefix_sum_anomaly": (
        "def solve(readings, target):\n"
        "    prefix_counts = {0: 1}\n"
        "    csum = 0\n"
        "    cnt = 0\n"
        "    for r in readings:\n"
        "        csum += r\n"
        "        diff = csum - target\n"
        "        if diff in prefix_counts:\n"
        "            cnt += prefix_counts[diff]\n"
        "        prefix_counts[csum] = prefix_counts.get(csum, 0) + 1\n"
        "    return cnt\n"
    ),
    "binary_search_threshold": (
        "def solve(workloads, k):\n"
        "    if not workloads:\n"
        "        return 0\n"
        "    if k >= len(workloads):\n"
        "        return max(workloads)\n"
        "    def feasible(max_load):\n"
        "        workers = 1\n"
        "        cur = 0\n"
        "        for w in workloads:\n"
        "            if cur + w > max_load:\n"
        "                workers += 1\n"
        "                cur = w\n"
        "                if workers > k:\n"
        "                    return False\n"
        "            else:\n"
        "                cur += w\n"
        "        return True\n"
        "    low, high = max(workloads), sum(workloads)\n"
        "    ans = high\n"
        "    while low <= high:\n"
        "        mid = (low + high) // 2\n"
        "        if feasible(mid):\n"
        "            ans = mid\n"
        "            high = mid - 1\n"
        "        else:\n"
        "            low = mid + 1\n"
        "    return ans\n"
    ),
    "lru_cache_expiry": (
        "from collections import OrderedDict\n\n"
        "def solve(operations, capacity):\n"
        "    cache = OrderedDict()\n"
        "    results = []\n"
        "    for op in operations:\n"
        "        action = op[0]\n"
        "        key = op[1]\n"
        "        if action == 'PUT':\n"
        "            val = op[2]\n"
        "            if key in cache:\n"
        "                cache.move_to_end(key)\n"
        "            elif len(cache) >= capacity:\n"
        "                cache.popitem(last=False)\n"
        "            cache[key] = val\n"
        "        elif action == 'GET':\n"
        "            if key in cache:\n"
        "                cache.move_to_end(key)\n"
        "                results.append(cache[key])\n"
        "            else:\n"
        "                results.append(None)\n"
        "    return results\n"
    ),
    "graph_dependency_resolver": (
        "import heapq\n"
        "from collections import defaultdict\n\n"
        "def solve(tasks, dependencies):\n"
        "    adj = defaultdict(list)\n"
        "    in_degree = {t: 0 for t in tasks}\n"
        "    for task, prereq in dependencies:\n"
        "        if task in in_degree and prereq in in_degree:\n"
        "            adj[prereq].append(task)\n"
        "            in_degree[task] += 1\n"
        "    heap = [t for t, deg in in_degree.items() if deg == 0]\n"
        "    heapq.heapify(heap)\n"
        "    order = []\n"
        "    while heap:\n"
        "        curr = heapq.heappop(heap)\n"
        "        order.append(curr)\n"
        "        for neighbor in adj[curr]:\n"
        "            in_degree[neighbor] -= 1\n"
        "            if in_degree[neighbor] == 0:\n"
        "                heapq.heappush(heap, neighbor)\n"
        "    return order if len(order) == len(tasks) else []\n"
    ),
}


# ======================================================================
# TEST 1: A correct solution scores highly
# ======================================================================
def test_1_correct_solution_scores_highly():
    print("\nâ”â”â” TEST 1: Correct solution scores highly â”â”â”")
    asm_id, prob, _ = create_assessment(seed_problem_id="array_frequency_k")
    code = CORRECT_SOLUTIONS["array_frequency_k"]
    status, result = submit(asm_id, code)
    check(status == 200, f"Submit returns 200 (got {status})")
    check(result["tests_passed"] == result["tests_total"], f"All tests pass ({result['tests_passed']}/{result['tests_total']})")
    check(result["overall_score"] >= 70.0, f"Score >= 70.0 (got {result['overall_score']})")
    check(result["passed_threshold"] is True, "Passed verification threshold")
    check(result["breakdown"]["problem_solving"] > 0, f"Problem Solving score populated ({result['breakdown']['problem_solving']})")
    check(result["breakdown"]["efficiency"] > 0, f"Efficiency score populated ({result['breakdown']['efficiency']})")
    check(result["breakdown"]["code_quality"] > 0, f"Code Quality score populated ({result['breakdown']['code_quality']})")
    check(result["breakdown"]["algorithmic_thinking"] > 0, f"Algorithmic Thinking score populated ({result['breakdown']['algorithmic_thinking']})")
    check("problem_version" in result, "Result contains problem_version")
    check("calibration_version" in result, "Result contains calibration_version")
    check("evaluation_model_version" in result, "Result contains evaluation_model_version")
    check(result.get("submission_code") == code, "Exact candidate code stored")


# ======================================================================
# TEST 2: Partially correct solution scores lower
# ======================================================================
def test_2_partially_correct_scores_lower():
    print("\nâ”â”â” TEST 2: Partially correct solution scores lower â”â”â”")
    asm_id, prob, _ = create_assessment(seed_problem_id="array_frequency_k")
    # Returns correct for positive items but returns 0 instead of -1 when no match
    partial_code = (
        "from collections import Counter\n\n"
        "def solve(items, k):\n"
        "    counts = Counter(items)\n"
        "    candidates = [val for val, count in counts.items() if count >= k]\n"
        "    return min(candidates) if candidates else 0\n"  # Bug: 0 instead of -1
    )
    status, result = submit(asm_id, partial_code)
    check(status == 200, f"Submit returns 200 (got {status})")
    check(0 < result["tests_passed"] < result["tests_total"], f"Some tests pass but not all ({result['tests_passed']}/{result['tests_total']})")
    # Score should be meaningful but lower than a perfect solution
    check(result["overall_score"] < 94.0, f"Score lower than perfect (got {result['overall_score']})")
    check(result["overall_score"] > 10.0, f"Score is not trivially low (got {result['overall_score']})")


# ======================================================================
# TEST 3: Incorrect solution scores low
# ======================================================================
def test_3_incorrect_solution_scores_low():
    print("\nâ”â”â” TEST 3: Incorrect solution scores low â”â”â”")
    asm_id, prob, _ = create_assessment(seed_problem_id="array_frequency_k")
    wrong_code = "def solve(*args, **kwargs):\n    return 9999999\n"
    status, result = submit(asm_id, wrong_code)
    check(status == 200, f"Submit returns 200 (got {status})")
    check(result["tests_passed"] == 0, f"No tests pass ({result['tests_passed']}/{result['tests_total']})")
    check(result["overall_score"] < 30.0, f"Score is low (got {result['overall_score']})")
    check(result["passed_threshold"] is False, "Does NOT pass verification threshold")


# ======================================================================
# TEST 4: Syntax errors are handled
# ======================================================================
def test_4_syntax_error_handled():
    print("\nâ”â”â” TEST 4: Syntax errors are handled â”â”â”")
    asm_id, prob, _ = create_assessment()
    syntax_code = "def solve(:\n    invalid syntax !!!\n"

    # Run Code should detect syntax error
    run_status, run_res = run_code(asm_id, syntax_code)
    check(run_status == 200, f"Run returns 200, not crash (got {run_status})")
    check(run_res["status"] == "syntax_error", f"Status is 'syntax_error' (got {run_res['status']})")
    check(run_res["tests_passed"] == 0, "No tests pass on syntax error")

    # Submit should also handle gracefully
    sub_status, sub_res = submit(asm_id, syntax_code)
    check(sub_status == 200, f"Submit returns 200 (got {sub_status})")
    check(sub_res["tests_passed"] == 0, "No tests pass on submitted syntax error")
    check(sub_res["overall_score"] < 30.0, f"Score is low ({sub_res['overall_score']})")


# ======================================================================
# TEST 5: Runtime errors are handled
# ======================================================================
def test_5_runtime_error_handled():
    print("\nâ”â”â” TEST 5: Runtime errors are handled â”â”â”")
    asm_id, prob, _ = create_assessment()
    runtime_code = "def solve(*args, **kwargs):\n    return 1 / 0\n"

    run_status, run_res = run_code(asm_id, runtime_code)
    check(run_status == 200, f"Run returns 200 (got {run_status})")
    check(run_res["tests_passed"] == 0, "No tests pass on runtime error")
    # Each test should individually report ZeroDivisionError
    if run_res.get("test_results"):
        first_test = run_res["test_results"][0]
        check("ZeroDivisionError" in (first_test.get("error") or ""), f"ZeroDivisionError reported in test results")
    
    sub_status, sub_res = submit(asm_id, runtime_code)
    check(sub_status == 200, f"Submit returns 200 (got {sub_status})")
    check(sub_res["tests_passed"] == 0, "No tests pass on submitted runtime error")
    check(sub_res["overall_score"] < 30.0, f"Score is low ({sub_res['overall_score']})")


# ======================================================================
# TEST 6: Timeout is handled
# ======================================================================
def test_6_timeout_handled():
    print("\nâ”â”â” TEST 6: Timeout is handled â”â”â”")
    asm_id, prob, _ = create_assessment()
    timeout_code = "import time\ndef solve(*args, **kwargs):\n    time.sleep(20)\n    return 0\n"

    run_status, run_res = run_code(asm_id, timeout_code)
    check(run_status == 200, f"Run returns 200, not crash (got {run_status})")
    check(run_res["status"] == "timeout", f"Status is 'timeout' (got {run_res['status']})")
    check(run_res["tests_passed"] == 0, "No tests pass on timeout")
    check("timed out" in (run_res.get("error") or "").lower(), "Error message mentions timeout")

    sub_status, sub_res = submit(asm_id, timeout_code)
    check(sub_status == 200, f"Submit returns 200 (got {sub_status})")
    check(sub_res["tests_passed"] == 0, "No tests pass on submitted timeout")


# ======================================================================
# TEST 7: Hidden tests are actually used
# ======================================================================
def test_7_hidden_tests_used():
    print("\nâ”â”â” TEST 7: Hidden tests are actually used â”â”â”")
    asm_id, prob, _ = create_assessment(seed_problem_id="array_frequency_k")

    # The public view should NOT expose hidden tests
    check("tests" not in prob or prob.get("tests") is None, "Hidden tests NOT exposed in public problem view")
    check("reference_solution" not in prob or prob.get("reference_solution") is None, "Reference solution NOT exposed in public problem view")

    # The problem should have examples (derived from first 2 test cases)
    examples = prob.get("examples", [])
    check(len(examples) > 0, f"Examples provided ({len(examples)} examples)")

    # Submission should test against the hidden test suite
    code = CORRECT_SOLUTIONS["array_frequency_k"]
    status, result = submit(asm_id, code)
    check(result["tests_total"] >= 5, f"Hidden test suite has >= 5 tests ({result['tests_total']})")
    check(result["tests_passed"] == result["tests_total"], f"All hidden tests pass ({result['tests_passed']}/{result['tests_total']})")


# ======================================================================
# TEST 8: Reference solution passes generated tests
# ======================================================================
def test_8_reference_solution_validates():
    print("\nâ”â”â” TEST 8: Reference solution passes generated tests (all 8 seed problems) â”â”â”")
    seed_ids = [
        "array_frequency_k", "sliding_window_anomaly", "interval_consolidation",
        "lru_cache_expiry", "graph_dependency_resolver", "prefix_sum_anomaly",
        "stack_syntax_validator", "binary_search_threshold",
    ]
    for seed_id in seed_ids:
        asm_id, prob, _ = create_assessment(seed_problem_id=seed_id)
        code = CORRECT_SOLUTIONS[seed_id]
        run_status, run_res = run_code(asm_id, code)
        passed = run_res.get("tests_passed", 0)
        total = run_res.get("tests_total", 0)
        check(
            passed == total and total > 0,
            f"{seed_id}: Reference solution passes {passed}/{total} hidden tests"
        )


# ======================================================================
# TEST 9: Same code + same problem version produces the same result (determinism)
# ======================================================================
def test_9_deterministic_scoring():
    print("\nâ”â”â” TEST 9: Deterministic scoring (same code + same problem = same score) â”â”â”")
    # Create two assessments with the same seed problem
    asm_id_1, prob_1, _ = create_assessment(seed_problem_id="stack_syntax_validator")
    asm_id_2, prob_2, _ = create_assessment(seed_problem_id="stack_syntax_validator")

    code = CORRECT_SOLUTIONS["stack_syntax_validator"]

    s1, r1 = submit(asm_id_1, code)
    s2, r2 = submit(asm_id_2, code)

    check(s1 == 200 and s2 == 200, "Both submissions return 200")
    check(r1["tests_passed"] == r1["tests_total"], f"Assessment 1: all tests pass ({r1['tests_passed']}/{r1['tests_total']})")
    check(r2["tests_passed"] == r2["tests_total"], f"Assessment 2: all tests pass ({r2['tests_passed']}/{r2['tests_total']})")

    # Scores should be the same since the code metrics are identical
    # (Different dynamic test counts are possible, but overall scoring rubric is deterministic)
    check(
        r1["overall_score"] == r2["overall_score"],
        f"Scores match: {r1['overall_score']} == {r2['overall_score']}"
    )
    check(
        r1["breakdown"] == r2["breakdown"],
        f"Breakdowns match: {r1['breakdown']} == {r2['breakdown']}"
    )


# ======================================================================
# TEST 10: Second submission returns HTTP 409
# ======================================================================
def test_10_second_submission_rejected():
    print("\nâ”â”â” TEST 10: Second submission returns HTTP 409 â”â”â”")
    asm_id, prob, _ = create_assessment(seed_problem_id="array_frequency_k")
    code = CORRECT_SOLUTIONS["array_frequency_k"]

    s1, r1 = submit(asm_id, code)
    check(s1 == 200, "First submission succeeds")
    original_score = r1["overall_score"]

    # Attempt second submission
    s2, r2 = submit(asm_id, "def solve(*a, **kw): return 42\n")
    check(s2 == 409, f"Second submission returns 409 (got {s2})")
    check("detail" in r2, "Error includes detail message")

    # Run Code should also be blocked
    run_s, run_r = run_code(asm_id, code)
    check(run_s == 409, f"Run Code also returns 409 after submission (got {run_s})")


# ======================================================================
# TEST 11: Historical result cannot be overwritten
# ======================================================================
def test_11_historical_result_immutable():
    print("\nâ”â”â” TEST 11: Historical result cannot be overwritten â”â”â”")
    asm_id, prob, _ = create_assessment(seed_problem_id="array_frequency_k")
    code = CORRECT_SOLUTIONS["array_frequency_k"]

    s1, r1 = submit(asm_id, code)
    check(s1 == 200, "First submission succeeds")
    original_score = r1["overall_score"]
    original_tests_passed = r1["tests_passed"]

    # Fetch the stored result
    res_s, res_r = make_req(f"/api/assessment/{asm_id}/result")
    check(res_s == 200, "Result fetch succeeds")
    check(res_r["overall_score"] == original_score, f"Score matches original ({res_r['overall_score']} == {original_score})")
    check(res_r["tests_passed"] == original_tests_passed, f"Tests passed matches original")
    check(res_r.get("submission_code") == code, "Stored code matches submitted code")

    # Try to submit again (should be rejected â€” result must remain unchanged)
    s2, r2 = submit(asm_id, "def solve(*a, **kw): return -999\n")
    check(s2 == 409, "Second submission is rejected with 409")

    # Re-fetch result â€” must be identical to original
    res2_s, res2_r = make_req(f"/api/assessment/{asm_id}/result")
    check(res2_s == 200, "Result still fetchable after rejected re-submission")
    check(res2_r["overall_score"] == original_score, f"Score unchanged after re-submit attempt ({res2_r['overall_score']})")
    check(res2_r["tests_passed"] == original_tests_passed, "Tests passed unchanged after re-submit attempt")
    check(res2_r.get("submission_code") == code, "Stored code unchanged after re-submit attempt")


# ======================================================================
# BONUS: Score breakdown validation
# ======================================================================
def test_bonus_score_breakdown_weights():
    print("\nâ”â”â” BONUS: Score breakdown weights validation â”â”â”")
    asm_id, prob, _ = create_assessment(seed_problem_id="prefix_sum_anomaly")
    code = CORRECT_SOLUTIONS["prefix_sum_anomaly"]
    s, r = submit(asm_id, code)
    check(s == 200, "Submission succeeds")

    bd = r["breakdown"]
    # problem_solving is derived, not used in overall (it's correctness * 0.85 + algorithmic * 0.15)
    # overall = correctness*0.50 + efficiency*0.20 + algorithmic*0.15 + code_quality*0.15
    check(all(k in bd for k in ["problem_solving", "algorithmic_thinking", "efficiency", "code_quality"]),
          "All breakdown dimensions present")
    check(all(0 <= bd[k] <= 100 for k in bd), "All breakdown scores in [0, 100]")
    check(r["overall_score"] >= 0 and r["overall_score"] <= 100, f"Overall score in [0, 100] ({r['overall_score']})")

    # Code metrics should also be present
    cm = r.get("code_metrics", {})
    check("lines_of_code" in cm, "lines_of_code in code_metrics")
    check("cyclomatic_complexity" in cm, "cyclomatic_complexity in code_metrics")


# ======================================================================
# BONUS: Calibration observation is created after submission
# ======================================================================
def test_bonus_calibration_observation():
    print("\nâ”â”â” BONUS: Calibration observation created after submission â”â”â”")
    # Get initial observation count
    _, calib_before = make_req("/api/calibration/status")
    obs_before = calib_before.get("observation_count", 0)

    asm_id, prob, _ = create_assessment(seed_problem_id="interval_consolidation")
    code = CORRECT_SOLUTIONS["interval_consolidation"]
    submit(asm_id, code)

    # Get observation count after
    _, calib_after = make_req("/api/calibration/status")
    obs_after = calib_after.get("observation_count", 0)

    check(obs_after > obs_before, f"Observation count increased ({obs_before} -> {obs_after})")


# ======================================================================
# BONUS: Passport produced after successful assessment
# ======================================================================
def test_bonus_passport():
    print("\nâ”â”â” BONUS: Skill Passport produced after submission â”â”â”")
    asm_id, prob, asm_full = create_assessment(seed_problem_id="binary_search_threshold")
    cand_id = asm_full["candidate_id"]
    code = CORRECT_SOLUTIONS["binary_search_threshold"]
    submit(asm_id, code)

    ps, passport = make_req(f"/api/passport/{cand_id}")
    check(ps == 200, f"Passport fetch returns 200 (got {ps})")
    check(passport.get("verified") is True, "Passport marked verified for high-scoring solution")
    check(passport.get("overall_score", 0) >= 70.0, f"Passport score >= 70 ({passport.get('overall_score')})")
    check("competencies" in passport, "Competencies present in passport")
    check("evidence" in passport, "Evidence present in passport")
    check("problem_version" in passport, "problem_version in passport")
    check("calibration_version" in passport, "calibration_version in passport")


# ======================================================================
# Main Runner
# ======================================================================
def main():
    print("=" * 70)
    print("  SkillProof Brain â€” Comprehensive Verification Suite")
    print("=" * 70)

    # Verify server health first
    try:
        hs, hb = make_req("/api/health")
        assert hs == 200, f"Health check failed: {hs}"
        print(f"Server healthy: {hb['status']}, model: {hb['active_model_version']}")
    except Exception as e:
        print(f"FATAL: Cannot connect to server at {BASE_URL}: {e}")
        return

    test_1_correct_solution_scores_highly()
    test_2_partially_correct_scores_lower()
    test_3_incorrect_solution_scores_low()
    test_4_syntax_error_handled()
    test_5_runtime_error_handled()
    test_6_timeout_handled()
    test_7_hidden_tests_used()
    test_8_reference_solution_validates()
    test_9_deterministic_scoring()
    test_10_second_submission_rejected()
    test_11_historical_result_immutable()
    test_bonus_score_breakdown_weights()
    test_bonus_calibration_observation()
    test_bonus_passport()

    print("\n" + "=" * 70)
    print(f"  RESULTS: {_pass_count} passed, {_fail_count} failed, {_pass_count + _fail_count} total")
    print("=" * 70)
    if _fail_count == 0:
        print("  âœ… ALL BRAIN VERIFICATION TESTS PASSED")
    else:
        print(f"  âŒ {_fail_count} test(s) FAILED â€” see above for details")
    print("=" * 70)


if __name__ == "__main__":
    main()

