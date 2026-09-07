"""Subprocess execution sandbox for candidate Python solutions.

Executes user code in an isolated subprocess with strict timeouts,
POSIX resource limits (RLIMIT_CPU, RLIMIT_AS), and safe Windows-compatible fallbacks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

HARNESS_TEMPLATE = '''
import sys
import json
import time

# --- Resource Limits & Safe Windows Fallback ---
_memory_mb = 12.5
_memory_status = "estimated_windows_fallback"

try:
    import resource
    # RLIMIT_CPU (hard CPU seconds limit per process)
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    except Exception:
        pass
    # RLIMIT_AS (256 MB address space limit)
    try:
        as_limit = 256 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (as_limit, as_limit))
    except Exception:
        pass
    _memory_status = "posix_resource_active"
except (ImportError, AttributeError, ValueError, OSError):
    _memory_status = "estimated_windows_fallback"

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

# Peak resident memory measurement where supported
try:
    import resource
    ru = resource.getrusage(resource.RUSAGE_SELF)
    if sys.platform == "darwin":
        _memory_mb = round(ru.ru_maxrss / (1024.0 * 1024.0), 2)
    else:
        _memory_mb = round(ru.ru_maxrss / 1024.0, 2)
    _memory_status = "measured_posix"
except Exception:
    pass

output_payload = {{
    "test_results": results,
    "memory_mb": _memory_mb,
    "memory_status": _memory_status,
}}

print("__SKILLPROOF_OUTPUT_START__")
print(json.dumps(output_payload))
print("__SKILLPROOF_OUTPUT_END__")
'''


def execute_solution_tests(
    solution_code: str,
    tests: List[Dict[str, Any]],
    timeout_seconds: float = 5.0,
) -> Dict[str, Any]:
    """
    Runs the candidate solution against the test suite in a sandboxed subprocess.
    Enforces timeout and POSIX resource limits (RLIMIT_CPU, RLIMIT_AS) with safe Windows fallback.
    Returns structured metrics:
      tests_passed, tests_total, runtime, memory, memory_status, error, test_results.
    """
    tests_json = json.dumps(tests)
    script_content = HARNESS_TEMPLATE.format(
        candidate_code=solution_code,
        tests_json_repr=repr(tests_json),
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as temp_file:
        temp_file.write(script_content)
        temp_file_path = temp_file.name

    # Prepare POSIX preexec limits function if supported
    preexec_fn = None
    if sys.platform != "win32":
        try:
            import resource

            def _set_posix_limits() -> None:
                try:
                    # RLIMIT_CPU: timeout + 1 sec hard cutoff
                    cpu_limit = int(timeout_seconds) + 1
                    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
                    # RLIMIT_AS: 256 MB max virtual memory
                    as_limit = 256 * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_AS, (as_limit, as_limit))
                except Exception:
                    pass

            preexec_fn = _set_posix_limits
        except ImportError:
            preexec_fn = None

    start_time = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, temp_file_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            preexec_fn=preexec_fn,
        )
        wall_time = time.perf_counter() - start_time
        stdout = proc.stdout
        stderr = proc.stderr
        exit_code = proc.returncode

        if "__SKILLPROOF_OUTPUT_START__" in stdout and "__SKILLPROOF_OUTPUT_END__" in stdout:
            start_marker = "__SKILLPROOF_OUTPUT_START__\n"
            end_marker = "\n__SKILLPROOF_OUTPUT_END__"
            json_str = stdout.split(start_marker)[1].split(end_marker)[0]
            payload = json.loads(json_str)

            test_results = payload.get("test_results", [])
            memory_mb = payload.get("memory_mb", 12.5)
            memory_status = payload.get("memory_status", "estimated_windows_fallback" if sys.platform == "win32" else "measured_posix")
            passed_count = sum(1 for t in test_results if t.get("passed"))

            return {
                "success": exit_code == 0,
                "exit_code": exit_code,
                "wall_time": round(wall_time, 4),
                "runtime": round(wall_time, 4),
                "tests_passed": passed_count,
                "tests_total": len(tests),
                "test_results": test_results,
                "memory": memory_mb,
                "memory_mb": memory_mb,
                "memory_status": memory_status,
                "error": None if exit_code == 0 else stderr.strip(),
            }
        else:
            # Script crashed or exited before test runner completed
            error_msg = stderr.strip() or stdout.strip() or "Syntax or runtime error during execution"
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
                "runtime": round(wall_time, 4),
                "tests_passed": 0,
                "tests_total": len(tests),
                "test_results": failed_tests,
                "memory": 10.0,
                "memory_mb": 10.0,
                "memory_status": "estimated_windows_fallback" if sys.platform == "win32" else "crash_fallback",
                "error": error_msg,
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
            "runtime": round(wall_time, 4),
            "tests_passed": 0,
            "tests_total": len(tests),
            "test_results": timeout_tests,
            "memory": 16.0,
            "memory_mb": 16.0,
            "memory_status": "estimated_windows_fallback" if sys.platform == "win32" else "timeout_fallback",
            "error": f"Execution timed out after {timeout_seconds} seconds",
        }
    except Exception as exc:
        wall_time = time.perf_counter() - start_time
        return {
            "success": False,
            "exit_code": -1,
            "wall_time": round(wall_time, 4),
            "runtime": round(wall_time, 4),
            "tests_passed": 0,
            "tests_total": len(tests),
            "test_results": [],
            "memory": 0.0,
            "memory_mb": 0.0,
            "memory_status": "unsupported",
            "error": f"Sandbox execution error: {str(exc)}",
        }
    finally:
        try:
            os.remove(temp_file_path)
        except OSError:
            pass
