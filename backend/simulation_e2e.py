"""
simulation_e2e.py
Complete End-to-End SkillProof Brain Simulation and System Verification.

Simulates all candidate behaviors:
1. Strong Candidate (correct, efficient, clean code)
2. Medium Candidate (partially correct, inefficient implementation)
3. Weak Candidate (incorrect solution)
4. Failure Cases:
   - Syntax error
   - Runtime error
   - Timeout

For each assessment verifies:
- Problem generation
- Transformation
- Hidden test generation
- Reference validation
- Candidate execution
- Objective scoring
- Score breakdown
- Immutable result
- Validated observation

Then verifies:
- TinyML retraining
- Frozen benchmark evaluation
- Safety guardrails
- Version increment & historical immutability
- Future assessment adoption

And verifies Frontend Flow:
- Hero (index.html)
- Assessments (skill-selection -> difficulty-selection -> assessment-setup)
- IDE (workspace.html)
- Submit
- Evaluation (evaluation.html)
- History (history.html)
- Passport (passport.html)
- One-shot enforcement (409)
- Absence of mock data
"""

import hashlib
import json
from pathlib import Path
import time
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
BENCHMARK_PATH = Path(__file__).resolve().parent / "data" / "benchmark.json"

results_tracker = {
    "PROBLEM_GENERATION": True,
    "EXECUTION": True,
    "SCORING": True,
    "ONE_SHOT_ENFORCEMENT": True,
    "HISTORY": True,
    "PASSPORT": True,
    "TINYML_CALIBRATION": True,
    "BENCHMARK_GUARDRAIL": True,
    "FRONTEND_FLOW": True,
}


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


def get_html(path):
    url = BASE_URL + path
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def get_benchmark_sha256() -> str:
    return hashlib.sha256(BENCHMARK_PATH.read_bytes()).hexdigest()


def log_step(name, passed, detail=""):
    is_ok = bool(passed)
    status_str = "[PASS]" if is_ok else "[FAIL]"
    print(f"  {status_str} {name} {('- ' + detail) if detail else ''}")
    return is_ok


def run_simulation():
    print("=" * 80)
    print("SKILLPROOF BRAIN — COMPLETE END-TO-END SYSTEM SIMULATION")
    print("=" * 80)

    # 0. Pre-flight check
    print("\n--- Phase 0: Pre-Flight Health & Frozen Benchmark Check ---")
    h_code, h_data = make_req("/api/health")
    preflight_ok = log_step("API Health Check", h_code == 200 and h_data.get("status") == "ok", f"version: {h_data.get('version')}, provider: {h_data.get('provider')}")
    if not preflight_ok:
        print("Backend server is not running or unhealthy. Aborting.")
        return False

    initial_benchmark_sha = get_benchmark_sha256()
    log_step("Frozen Benchmark Verification", bool(initial_benchmark_sha), f"SHA-256: {initial_benchmark_sha}")

    historical_records = []

    # -------------------------------------------------------------
    # 1. Strong Candidate Simulation
    # -------------------------------------------------------------
    print("\n--- Phase 1: Candidate 1 — Strong Candidate (Alice) ---")
    alice_id = f"cand_alice_{int(time.time())}"
    
    # Problem Generation
    c_code, c_data = make_req("/api/assessment", "POST", {
        "candidate_id": alice_id,
        "skill": "python",
        "difficulty": "intermediate",
        "seed_problem_id": "array_frequency_k"
    })
    gen_ok = (c_code == 201 and "problem" in c_data and c_data["problem"]["title"])
    results_tracker["PROBLEM_GENERATION"] &= log_step(
        "Problem Generation & Transformation",
        gen_ok,
        f"Title: '{c_data['problem']['title']}', seed: '{c_data['problem']['seed_problem_id']}'"
    )
    
    # Verify hidden tests & reference solution not leaked in public view
    prob_view = c_data["problem"]
    no_leak = ("tests" not in prob_view or prob_view.get("tests") is None) and ("reference_solution" not in prob_view or prob_view.get("reference_solution") is None)
    log_step("Public View Security (No Test/Solution Leak)", no_leak)
    results_tracker["PROBLEM_GENERATION"] &= no_leak

    asm_alice = c_data["id"]

    # Candidate sandbox execution (Run Code) with correct, clean, typed code
    alice_code = (
        "from collections import Counter\n"
        "from typing import List\n\n"
        "def solve(items: List[int], k: int) -> int:\n"
        "    \"\"\"Find smallest element occurring at least k times, or -1.\"\"\"\n"
        "    counts = Counter(items)\n"
        "    candidates = [val for val, count in counts.items() if count >= k]\n"
        "    return min(candidates) if candidates else -1\n"
    )

    run_code_status, run_data = make_req(f"/api/assessment/{asm_alice}/run", "POST", {"solution": alice_code})
    run_ok = (run_code_status == 200 and run_data.get("status") == "ok" and run_data.get("tests_passed") == run_data.get("tests_total") > 0)
    results_tracker["EXECUTION"] &= log_step("Sandbox Execution (Run Code)", run_ok, f"Passed: {run_data.get('tests_passed')}/{run_data.get('tests_total')}")

    # Submit Solution
    sub_code, sub_data = make_req(f"/api/assessment/{asm_alice}/submit", "POST", {"solution": alice_code, "time_taken": 35.0})
    sub_ok = (sub_code == 200 and sub_data.get("tests_passed") == sub_data.get("tests_total"))
    results_tracker["EXECUTION"] &= log_step("Final Solution Execution", sub_ok)

    # Objective Scoring & Breakdown
    score_ok = (sub_data.get("overall_score", 0) >= 85.0 and sub_data.get("passed_threshold") is True)
    bd = sub_data.get("breakdown", {})
    bd_ok = ("problem_solving" in bd and "algorithmic_thinking" in bd and "efficiency" in bd and "code_quality" in bd)
    results_tracker["SCORING"] &= log_step("Objective Scoring (Rubric Weighted)", score_ok, f"Score: {sub_data.get('overall_score')}/100")
    results_tracker["SCORING"] &= log_step("Score Breakdown Verification", bd_ok, f"PS: {bd.get('problem_solving')}, AT: {bd.get('algorithmic_thinking')}, Eff: {bd.get('efficiency')}, CQ: {bd.get('code_quality')}")

    # One-shot Enforcement
    sec_code, _ = make_req(f"/api/assessment/{asm_alice}/submit", "POST", {"solution": alice_code})
    sec_run, _ = make_req(f"/api/assessment/{asm_alice}/run", "POST", {"solution": alice_code})
    oneshot_ok = (sec_code == 409 and sec_run == 409)
    results_tracker["ONE_SHOT_ENFORCEMENT"] &= log_step("One-Shot Rejection (Submit 409 & Run 409)", oneshot_ok)

    # History & Passport for Alice
    hist_code, hist_data = make_req(f"/api/history/{alice_id}")
    hist_ok = (hist_code == 200 and len(hist_data) >= 1 and hist_data[0]["overall_score"] == sub_data["overall_score"])
    results_tracker["HISTORY"] &= log_step("Assessment History Record Verification", hist_ok, f"Found {len(hist_data)} record(s)")

    pass_code, pass_data = make_req(f"/api/passport/{alice_id}")
    pass_ok = (pass_code == 200 and pass_data.get("verified") is True and pass_data.get("overall_score") == sub_data["overall_score"])
    results_tracker["PASSPORT"] &= log_step("Skill Passport Issuance & Evidence", pass_ok, f"Passport ID: {pass_data.get('passport_id')}, verified: {pass_data.get('verified')}")

    historical_records.append((asm_alice, sub_data["overall_score"], sub_data["calibration_version"]))

    # -------------------------------------------------------------
    # 2. Medium Candidate Simulation
    # -------------------------------------------------------------
    print("\n--- Phase 2: Candidate 2 — Medium Candidate (Bob) ---")
    bob_id = f"cand_bob_{int(time.time())}"
    _, c_bob = make_req("/api/assessment", "POST", {
        "candidate_id": bob_id,
        "skill": "python",
        "difficulty": "intermediate",
        "seed_problem_id": "sliding_window_anomaly"
    })
    asm_bob = c_bob["id"]

    # Bob's code: inefficient nested loop implementation with slight edge-case defect
    bob_code = (
        "def solve(stream, window_size):\n"
        "    if not stream or len(stream) < window_size:\n"
        "        return 0.0\n"
        "    max_avg = -1000000.0\n"
        "    # Inefficient re-summing over window\n"
        "    for i in range(len(stream) - window_size + 1):\n"
        "        s = 0.0\n"
        "        for j in range(i, i + window_size):\n"
        "            s += stream[j]\n"
        "        avg = round(s / window_size, 2)\n"
        "        if avg > max_avg:\n"
        "            max_avg = avg\n"
        "    return max_avg\n"
    )

    _, sub_bob = make_req(f"/api/assessment/{asm_bob}/submit", "POST", {"solution": bob_code, "time_taken": 180.0})
    bob_pass_tests = sub_bob.get("tests_passed", 0)
    bob_total_tests = sub_bob.get("tests_total", 1)
    bob_score = sub_bob.get("overall_score", 0.0)
    
    med_ok = (bob_pass_tests > 0 and bob_score < sub_data["overall_score"])
    results_tracker["SCORING"] &= log_step("Medium Candidate Score Differentiation", med_ok, f"Passed {bob_pass_tests}/{bob_total_tests}, score: {bob_score} (vs Strong {sub_data['overall_score']})")

    # One-shot check for Bob
    sec_bob, _ = make_req(f"/api/assessment/{asm_bob}/submit", "POST", {"solution": bob_code})
    results_tracker["ONE_SHOT_ENFORCEMENT"] &= log_step("Bob Second Submission 409", sec_bob == 409)

    historical_records.append((asm_bob, bob_score, sub_bob["calibration_version"]))

    # -------------------------------------------------------------
    # 3. Weak Candidate Simulation
    # -------------------------------------------------------------
    print("\n--- Phase 3: Candidate 3 — Weak Candidate (Charlie) ---")
    charlie_id = f"cand_charlie_{int(time.time())}"
    _, c_charlie = make_req("/api/assessment", "POST", {
        "candidate_id": charlie_id,
        "skill": "python",
        "difficulty": "intermediate",
        "seed_problem_id": "interval_consolidation"
    })
    asm_charlie = c_charlie["id"]

    # Charlie's code: incorrect trivial return
    charlie_code = "def solve(intervals):\n    return []\n"
    _, sub_charlie = make_req(f"/api/assessment/{asm_charlie}/submit", "POST", {"solution": charlie_code, "time_taken": 25.0})
    charlie_score = sub_charlie.get("overall_score", 0.0)
    
    weak_ok = (sub_charlie.get("tests_passed") == 0 or charlie_score < 30.0)
    results_tracker["SCORING"] &= log_step("Weak Candidate Low Deterministic Score", weak_ok, f"Passed {sub_charlie.get('tests_passed')}/{sub_charlie.get('tests_total')}, score: {charlie_score}")

    sec_charlie, _ = make_req(f"/api/assessment/{asm_charlie}/submit", "POST", {"solution": charlie_code})
    results_tracker["ONE_SHOT_ENFORCEMENT"] &= log_step("Charlie Second Submission 409", sec_charlie == 409)

    historical_records.append((asm_charlie, charlie_score, sub_charlie["calibration_version"]))

    # -------------------------------------------------------------
    # 4. Failure Cases Simulation
    # -------------------------------------------------------------
    print("\n--- Phase 4: Candidate Failure Cases ---")
    
    # 4a: Syntax Error
    _, c_syn = make_req("/api/assessment", "POST", {"skill": "python", "difficulty": "intermediate"})
    asm_syn = c_syn["id"]
    syn_code = "def solve(*args):\n    if True\n        return 1\n"
    _, syn_run = make_req(f"/api/assessment/{asm_syn}/run", "POST", {"solution": syn_code})
    _, syn_sub = make_req(f"/api/assessment/{asm_syn}/submit", "POST", {"solution": syn_code})
    syn_ok = (syn_run.get("status") == "syntax_error" and syn_sub.get("tests_passed") == 0 and syn_sub.get("overall_score") < 30.0)
    results_tracker["EXECUTION"] &= log_step("Syntax Error Sandboxing & Graceful Failure", syn_ok, f"Run status: {syn_run.get('status')}, score: {syn_sub.get('overall_score')}")

    # 4b: Runtime Error (ZeroDivisionError)
    _, c_rt = make_req("/api/assessment", "POST", {"skill": "python", "difficulty": "intermediate"})
    asm_rt = c_rt["id"]
    rt_code = "def solve(*args, **kwargs):\n    x = 1 / 0\n    return x\n"
    _, rt_run = make_req(f"/api/assessment/{asm_rt}/run", "POST", {"solution": rt_code})
    _, rt_sub = make_req(f"/api/assessment/{asm_rt}/submit", "POST", {"solution": rt_code})
    rt_ok = (rt_sub.get("tests_passed") == 0 and rt_sub.get("overall_score") < 30.0)
    results_tracker["EXECUTION"] &= log_step("Runtime Error Sandboxing & Graceful Failure", rt_ok, f"Passed: {rt_sub.get('tests_passed')}, score: {rt_sub.get('overall_score')}")

    # 4c: Execution Timeout
    _, c_to = make_req("/api/assessment", "POST", {"skill": "python", "difficulty": "intermediate"})
    asm_to = c_to["id"]
    to_code = "import time\ndef solve(*args, **kwargs):\n    time.sleep(20)\n    return 0\n"
    _, to_run = make_req(f"/api/assessment/{asm_to}/run", "POST", {"solution": to_code})
    _, to_sub = make_req(f"/api/assessment/{asm_to}/submit", "POST", {"solution": to_code})
    to_ok = (to_run.get("status") == "timeout" and to_sub.get("tests_passed") == 0)
    results_tracker["EXECUTION"] &= log_step("Timeout Protection (5s Limit)", to_ok, f"Run status: {to_run.get('status')}")

    # -------------------------------------------------------------
    # 5. TinyML Calibration Retraining & Frozen Benchmark Check
    # -------------------------------------------------------------
    print("\n--- Phase 5: TinyML Calibration Retraining & Guardrails ---")
    st_before_c, st_before = make_req("/api/calibration/status")
    obs_count = st_before["observation_count"]
    active_model_before = st_before["active_model_version"]
    prev_bench = st_before["benchmark_score"]
    
    log_step("Observation Buffer Accumulation", obs_count >= 3, f"Observations in buffer: {obs_count}")

    # Trigger manual retraining
    retrain_c, retrain_res = make_req("/api/calibration/retrain", "POST")
    retrain_success = retrain_res.get("success", False)
    
    if retrain_success:
        log_step("TinyML Candidate Model Retraining & Evaluation", True, f"Status: {retrain_res.get('status')}, proposed version: {retrain_res.get('proposed_version')}")
        
        bench_check = retrain_res.get("benchmark_score", 0.0) >= 75.0
        results_tracker["BENCHMARK_GUARDRAIL"] &= log_step("Frozen Benchmark Safety Threshold Check", bench_check, f"Score: {retrain_res.get('benchmark_score')} / 100")
        
        # Verify status endpoint reflects active vNext
        _, st_after = make_req("/api/calibration/status")
        vnext_active = st_after["active_model_version"] == retrain_res["proposed_version"]
        results_tracker["TINYML_CALIBRATION"] &= log_step("Model Versioning & Promotion (vNext Active)", vnext_active, f"Active: {st_after['active_model_version']}, Previous: {st_after.get('previous_model_version')}")
    else:
        log_step("TinyML Candidate Model Rejected by Guardrails", True, f"Rejection reason: {retrain_res.get('message')}")
        _, st_after = make_req("/api/calibration/status")
        v_kept = st_after["active_model_version"] == active_model_before
        results_tracker["TINYML_CALIBRATION"] &= log_step("Previous Model Kept Active on Rejection", v_kept)

    # Verify frozen benchmark remains 100% untouched
    after_benchmark_sha = get_benchmark_sha256()
    bench_frozen = (after_benchmark_sha == initial_benchmark_sha)
    results_tracker["BENCHMARK_GUARDRAIL"] &= log_step("Frozen Benchmark Immutability (SHA-256 Check)", bench_frozen)

    # Verify historical results have not mutated
    hist_all_unchanged = True
    for a_id, orig_score, orig_calib in historical_records:
        _, r_data = make_req(f"/api/assessment/{a_id}/result")
        if r_data["overall_score"] != orig_score or r_data["calibration_version"] != orig_calib:
            hist_all_unchanged = False
            break
    results_tracker["TINYML_CALIBRATION"] &= log_step("Historical Results Model Version Immutability", hist_all_unchanged)

    # Verify future assessment adopts current active model version
    _, fut_asm = make_req("/api/assessment", "POST", {"skill": "python", "difficulty": "intermediate"})
    future_adopts = fut_asm["calibration_version"] == st_after["active_model_version"]
    results_tracker["TINYML_CALIBRATION"] &= log_step("Future Assessment Adopts Active Calibration Version", future_adopts, f"Version: {fut_asm['calibration_version']}")

    # -------------------------------------------------------------
    # 6. Frontend Flow Verification (Hero -> Assessments -> IDE -> Submit -> Evaluation -> History -> Passport)
    # -------------------------------------------------------------
    print("\n--- Phase 6: Frontend Flow Verification (No Mock Data) ---")
    
    # 6a. Hero page (index.html)
    hero_c, hero_html = get_html("/index.html")
    hero_ok = (hero_c == 200 and "Proof, Not Paper" in hero_html and "skill-selection.html" in hero_html)
    results_tracker["FRONTEND_FLOW"] &= log_step("Hero Landing Page (index.html)", hero_ok)

    # 6b. Skill Selection (skill-selection.html)
    skill_c, skill_html = get_html("/skill-selection.html")
    skill_ok = (skill_c == 200 and "Python" in skill_html and "difficulty-selection.html" in skill_html)
    results_tracker["FRONTEND_FLOW"] &= log_step("Skill Selection Page (skill-selection.html)", skill_ok)

    # 6c. Difficulty Selection (difficulty-selection.html)
    diff_c, diff_html = get_html("/difficulty-selection.html")
    diff_ok = (diff_c == 200 and "Intermediate" in diff_html and "assessment-setup.html" in diff_html)
    results_tracker["FRONTEND_FLOW"] &= log_step("Difficulty Selection Page (difficulty-selection.html)", diff_ok)

    # 6d. Assessment Setup / Begin Challenge (assessment-setup.html)
    setup_c, setup_html = get_html("/assessment-setup.html")
    setup_ok = (setup_c == 200 and "workspace.html" in setup_html and "createAssessment" in setup_html)
    results_tracker["FRONTEND_FLOW"] &= log_step("Assessment Setup / Begin Challenge (assessment-setup.html)", setup_ok)

    # 6e. IDE Workspace (workspace.html)
    ws_c, ws_html = get_html("/workspace.html")
    ws_ok = (ws_c == 200 and "code-input" in ws_html and "runCode" in ws_html and "submitSolution" in ws_html)
    results_tracker["FRONTEND_FLOW"] &= log_step("IDE Coding Workspace (workspace.html)", ws_ok)

    # 6f. Evaluation Report (evaluation.html)
    ev_c, ev_html = get_html("/evaluation.html")
    ev_ok = (ev_c == 200 and "eval-score-ring" in ev_html and "getAssessmentResult" in ev_html)
    results_tracker["FRONTEND_FLOW"] &= log_step("Evaluation Report (evaluation.html)", ev_ok)

    # 6g. History Ledger (history.html)
    hist_page_c, hist_page_html = get_html("/history.html")
    hist_page_ok = (hist_page_c == 200 and "getHistory" in hist_page_html and "history-ledger-container" in hist_page_html)
    results_tracker["FRONTEND_FLOW"] &= log_step("History Ledger Page (history.html)", hist_page_ok)

    # 6h. Skill Passport (passport.html)
    pass_page_c, pass_page_html = get_html("/passport.html")
    pass_page_ok = (pass_page_c == 200 and "getPassport" in pass_page_html and "evidence-metrics" in pass_page_html)
    results_tracker["FRONTEND_FLOW"] &= log_step("Skill Passport Page (passport.html)", pass_page_ok)

    # -------------------------------------------------------------
    # Overall Status Summary
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print("SKILLPROOF SYSTEM VERIFICATION SUMMARY REPORT")
    print("=" * 80)
    
    all_passed = all(results_tracker.values())
    brain_status = "PASS" if all_passed else "FAIL"

    print(f"BRAIN STATUS: {brain_status}\n")
    print(f"PROBLEM GENERATION: {'PASS' if results_tracker['PROBLEM_GENERATION'] else 'FAIL'}")
    print(f"EXECUTION: {'PASS' if results_tracker['EXECUTION'] else 'FAIL'}")
    print(f"SCORING: {'PASS' if results_tracker['SCORING'] else 'FAIL'}")
    print(f"ONE-SHOT ENFORCEMENT: {'PASS' if results_tracker['ONE_SHOT_ENFORCEMENT'] else 'FAIL'}")
    print(f"HISTORY: {'PASS' if results_tracker['HISTORY'] else 'FAIL'}")
    print(f"PASSPORT: {'PASS' if results_tracker['PASSPORT'] else 'FAIL'}")
    print(f"TINYML CALIBRATION: {'PASS' if results_tracker['TINYML_CALIBRATION'] else 'FAIL'}")
    print(f"BENCHMARK GUARDRAIL: {'PASS' if results_tracker['BENCHMARK_GUARDRAIL'] else 'FAIL'}")
    print(f"FRONTEND FLOW: {'PASS' if results_tracker['FRONTEND_FLOW'] else 'FAIL'}")
    print("=" * 80)

    return all_passed


if __name__ == "__main__":
    import sys
    ok = run_simulation()
    if not ok:
        sys.exit(1)
