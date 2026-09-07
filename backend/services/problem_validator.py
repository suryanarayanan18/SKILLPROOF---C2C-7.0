"""Problem validation pipeline.

Ensures that every generated challenge variation's reference solution cleanly
passes 100% of its generated hidden tests before presenting it to a candidate.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Tuple
from services.executor import execute_solution_tests

logger = logging.getLogger("skillproof.validator")


def validate_problem(problem: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """
    Runs the problem's reference solution against its test suite.
    Returns (is_valid, validation_report).
    """
    ref_code = problem.get("reference_solution", "")
    tests = problem.get("tests") or problem.get("fixed_tests") or []

    if not ref_code or not tests:
        return False, {"error": "Missing reference solution or test cases."}

    execution_res = execute_solution_tests(
        solution_code=ref_code,
        tests=tests,
        timeout_seconds=3.0,
    )

    passed = execution_res.get("tests_passed", 0)
    total = execution_res.get("tests_total", 0)
    is_valid = (passed == total) and (total > 0)

    report = {
        "is_valid": is_valid,
        "tests_passed": passed,
        "tests_total": total,
        "wall_time": execution_res.get("wall_time", 0.0),
        "error": execution_res.get("error"),
    }

    if not is_valid:
        logger.warning(
            "Problem validation failed for %s: %d/%d passed. Error: %s",
            problem.get("id"),
            passed,
            total,
            execution_res.get("error"),
        )

    return is_valid, report
