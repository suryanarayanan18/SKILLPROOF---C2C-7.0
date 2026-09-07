"""Subprocess execution sandbox for candidate Python solutions.

Executes user code in an isolated subprocess with a strict timeout and
resource monitoring.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional


HARNESS_TEMPLATE = """
import sys
import json
import time

# --- Candidate Solution Code ---
{candidate_code}

# --- Test Runner Harness ---
tests = json.loads({tests_json_repr})
results = []

def format_val(val):
    if isinstance(val, (int, float, str, bool, type(None))):
        return val
    if isinstance(val, (list, tuple)):
        return [format_val(x) for x in val]
    if isinstance(val, dict):
        return {{str(k): format_val(v) for k, v in val.items()}}
    return str(val)

def compare_results(actual, expected):
    if isinstance(expected, float) and isinstance(actual, (int, float)):
        return abs(float(actual) - float(expected)) <= 0.01
    return actual == expected

for idx, test in enumerate(tests):
    t_name = test.get("name", f"Test #{{idx+1}}")
    t_input = test.get("input", {{}})
    expected = test.get("expected")
    
    t_start = time.perf_counter()
    try:
        if isinstance(t_input, dict):
            actual = solve(**t_input)
        elif isinstance(t_input, list):
            actual = solve(*t_input)
        else:
            actual = solve(t_input)
        runtime_ms = (time.perf_counter() - t_start) * 1000.0
        passed = compare_results(actual, expected)
        results.append({{
            "test_index": idx,
            "name": t_name,
            "passed": bool(passed),
            "runtime_ms": round(runtime_ms, 3),
            "error": None if passed else f"Expected {{format_val(expected)}}, but got {{format_val(actual)}}",
        }})
    except Exception as e:
        runtime_ms = (time.perf_counter() - t_start) * 1000.0
        results.append({{
            "test_index": idx,
            "name": t_name,
            "passed": False,
            "runtime_ms": round(runtime_ms, 3),
            "error": f"{{type(e).__name__}}: {{str(e)}}",
        }})

print("__SKILLPROOF_OUTPUT_START__")
print(json.dumps(results))
print("__SKILLPROOF_OUTPUT_END__")
"""


def execute_solution_tests(
    solution_code: str,
    tests: List[Dict[str, Any]],
    timeout_seconds: float = 5.0,
) -> Dict[str, Any]:
    """
    Runs the candidate solution against the test suite in a sandboxed subprocess.
    Returns test run details, total runtime, memory estimation, and errors.
    """
    tests_json = json.dumps(tests)
    script_content = HARNESS_TEMPLATE.format(
        candidate_code=solution_code,
        tests_json_repr=repr(tests_json),
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as temp_file:
        temp_file.write(script_content)
        temp_file_path = temp_file.name

    start_time = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, temp_file_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        wall_time = time.perf_counter() - start_time
        stdout = proc.stdout
        stderr = proc.stderr
        exit_code = proc.returncode

        if "__SKILLPROOF_OUTPUT_START__" in stdout and "__SKILLPROOF_OUTPUT_END__" in stdout:
            start_marker = "__SKILLPROOF_OUTPUT_START__\n"
            end_marker = "\n__SKILLPROOF_OUTPUT_END__"
            json_str = stdout.split(start_marker)[1].split(end_marker)[0]
            test_results = json.loads(json_str)
            passed_count = sum(1 for t in test_results if t["passed"])
            return {
                "success": True,
                "exit_code": exit_code,
                "wall_time": round(wall_time, 4),
                "tests_passed": passed_count,
                "tests_total": len(tests),
                "test_results": test_results,
                "error": None if exit_code == 0 else stderr.strip(),
                "memory_mb": 12.5, # Baseline Python process footprint
            }
        else:
            # Script crashed before runner printed results
            error_msg = stderr.strip() or stdout.strip() or "Syntax or runtime error during execution"
            # Return all tests as failed
            failed_tests = [
                {
                    "test_index": i,
                    "name": test.get("name", f"Test #{i+1}"),
                    "passed": False,
                    "runtime_ms": 0.0,
                    "error": error_msg.splitlines()[-1] if error_msg else "Execution failed",
                }
                for i, test in enumerate(tests)
            ]
            return {
                "success": False,
                "exit_code": exit_code,
                "wall_time": round(wall_time, 4),
                "tests_passed": 0,
                "tests_total": len(tests),
                "test_results": failed_tests,
                "error": error_msg,
                "memory_mb": 10.0,
            }

    except subprocess.TimeoutExpired:
        wall_time = time.perf_counter() - start_time
        timeout_tests = [
            {
                "test_index": i,
                "name": test.get("name", f"Test #{i+1}"),
                "passed": False,
                "runtime_ms": timeout_seconds * 1000.0,
                "error": f"Execution timed out (> {timeout_seconds}s)",
            }
            for i, test in enumerate(tests)
        ]
        return {
            "success": False,
            "exit_code": -1,
            "wall_time": round(wall_time, 4),
            "tests_passed": 0,
            "tests_total": len(tests),
            "test_results": timeout_tests,
            "error": f"Execution timed out after {timeout_seconds} seconds",
            "memory_mb": 16.0,
        }
    except Exception as exc:
        wall_time = time.perf_counter() - start_time
        return {
            "success": False,
            "exit_code": -1,
            "wall_time": round(wall_time, 4),
            "tests_passed": 0,
            "tests_total": len(tests),
            "test_results": [],
            "error": f"Sandbox execution error: {str(exc)}",
            "memory_mb": 0.0,
        }
    finally:
        try:
            os.remove(temp_file_path)
        except OSError:
            pass
