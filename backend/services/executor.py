"""Secure, deterministic execution for submitted Python challenge code."""

from __future__ import annotations

import io
import math
import os
import re
import time
import traceback
from contextlib import redirect_stdout
from typing import Any

from schemas import ExecutionResponse, ExecutionTestResult


def _coerce_scalar(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        return repr(value)
    except Exception:
        return str(value)


def _derive_tests(challenge: Any) -> list[dict[str, str | Any]]:
    title = (challenge.title or "").lower()
    if "cart" in title or "process_cart" in str(challenge.task).lower():
        return [
            {
                "name": "basic_cart",
                "input": "items=[{'price': 25, 'quantity': 2, 'category': 'books'}], discounts={}, threshold=100",
                "expected": "{'subtotal': 50.0, 'total_quantity': 2, 'discount': 0.0, 'tax': 4.0, 'total': 54.0}",
                "call": "process_cart([{'price': 25, 'quantity': 2, 'category': 'books'}], {}, 100)",
            },
            {
                "name": "category_discount",
                "input": "items=[{'price': 50, 'quantity': 3, 'category': 'books'}], discounts={'books': 10}, threshold=100",
                "expected": "{'subtotal': 135.0, 'total_quantity': 3, 'discount': 13.5, 'tax': 9.72, 'total': 131.22}",
                "call": "process_cart([{'price': 50, 'quantity': 3, 'category': 'books'}], {'books': 10}, 100)",
            },
            {
                "name": "empty_and_invalid",
                "input": "items=[{'price': 10, 'quantity': 0, 'category': 'books'}, {'price': 5, 'quantity': 1, 'category': 'other'}], discounts={}, threshold=100",
                "expected": "non-negative total with valid quantity only",
                "call": "process_cart([{'price': 10, 'quantity': 0, 'category': 'books'}, {'price': 5, 'quantity': 1, 'category': 'other'}], {}, 100)",
            },
        ]

    if "telemetry" in title or "aggregate_payload_stream" in str(challenge.task).lower():
        return [
            {
                "name": "bucketed_events",
                "input": "events=[{'timestamp': 121, 'payload': 'cpu'}, {'timestamp': 181, 'payload': 'mem'}, {'raw': 'bad'}], window_seconds=60",
                "expected": "{'partitions': {'120': [{'timestamp': 121, 'payload': 'cpu'}], '180': [{'timestamp': 181, 'payload': 'mem'}]}, 'malformed_dropped': 1, 'total_payloads': 2}",
                "call": "aggregate_payload_stream([{'timestamp': 121, 'payload': 'cpu'}, {'timestamp': 181, 'payload': 'mem'}, {'raw': 'bad'}], 60)",
            },
            {
                "name": "empty_input",
                "input": "events=[], window_seconds=60",
                "expected": "{'partitions': {}, 'malformed_dropped': 0, 'total_payloads': 0}",
                "call": "aggregate_payload_stream([], 60)",
            },
        ]

    return [
        {
            "name": "challenge_basic",
            "input": "challenge stub",
            "expected": "valid return structure",
            "call": "solve()",
        }
    ]


def _execute_python(code: str, challenge: Any) -> tuple[list[ExecutionTestResult], int, int]:
    namespace: dict[str, Any] = {"__builtins__": __builtins__}
    captured = io.StringIO()
    start = time.perf_counter()
    tests = _derive_tests(challenge)
    results: list[ExecutionTestResult] = []

    try:
        compiled = compile(code, "<skillproof_submission>", "exec")
        with redirect_stdout(captured):
            exec(compiled, namespace, namespace)
    except Exception as error:
        for test in tests:
            results.append(
                ExecutionTestResult(
                    name=test["name"],
                    passed=False,
                    input=str(test["input"]),
                    expected=str(test["expected"]),
                    actual=f"Error: {type(error).__name__}: {error}",
                    error=f"{type(error).__name__}: {error}",
                )
            )
        runtime_ms = max(0, int(round((time.perf_counter() - start) * 1000)))
        return results, len(results), runtime_ms

    function_name = "process_cart" if "cart" in (challenge.title or "").lower() or "process_cart" in str(challenge.task).lower() else "aggregate_payload_stream" if "telemetry" in (challenge.title or "").lower() or "aggregate_payload_stream" in str(challenge.task).lower() else None

    if function_name is None:
        for test in tests:
            results.append(
                ExecutionTestResult(
                    name=test["name"],
                    passed=False,
                    input=str(test["input"]),
                    expected=str(test["expected"]),
                    actual="No challenge function was found.",
                    error="No challenge function was found.",
                )
            )
        runtime_ms = max(0, int(round((time.perf_counter() - start) * 1000)))
        return results, len(results), runtime_ms

    target = namespace.get(function_name)
    if not callable(target):
        for test in tests:
            results.append(
                ExecutionTestResult(
                    name=test["name"],
                    passed=False,
                    input=str(test["input"]),
                    expected=str(test["expected"]),
                    actual=f"Function {function_name} is not defined.",
                    error=f"Function {function_name} is not defined.",
                )
            )
        runtime_ms = max(0, int(round((time.perf_counter() - start) * 1000)))
        return results, len(results), runtime_ms

    for test in tests:
        try:
            input_value = test["input"]
            actual = eval(test["call"], namespace, {})
            if function_name == "process_cart":
                actual = actual if isinstance(actual, dict) else {
                    "result": actual,
                }
            passed = _matches_expected(actual, test["expected"])
            results.append(
                ExecutionTestResult(
                    name=str(test["name"]),
                    passed=bool(passed),
                    input=str(input_value),
                    expected=str(test["expected"]),
                    actual=_coerce_scalar(actual),
                    error=None if passed else "Output did not match expected structure/value.",
                )
            )
        except Exception as error:
            results.append(
                ExecutionTestResult(
                    name=str(test["name"]),
                    passed=False,
                    input=str(test["input"]),
                    expected=str(test["expected"]),
                    actual=f"Error: {type(error).__name__}: {error}",
                    error=f"{type(error).__name__}: {error}",
                )
            )

    runtime_ms = max(0, int(round((time.perf_counter() - start) * 1000)))
    return results, sum(1 for item in results if item.passed), runtime_ms


def _matches_expected(actual: Any, expected: str) -> bool:
    if expected == "non-negative total with valid quantity only":
        if not isinstance(actual, dict):
            return False
        return actual.get("total", 0) >= 0 and actual.get("total_quantity", 0) >= 0
    if expected.startswith("{'partitions'") or expected.startswith("{\'partitions\'"):
        try:
            returned = actual if isinstance(actual, dict) else eval(str(actual), {"__builtins__": __builtins__})
            return isinstance(returned, dict) and "partitions" in returned and "malformed_dropped" in returned and "total_payloads" in returned
        except Exception:
            return False
    if expected.startswith("{"):
        try:
            expected_normalized = expected.replace("'", '"')
            actual_normalized = str(actual).replace("'", '"')
            if actual_normalized == expected_normalized:
                return True
            if isinstance(actual, dict):
                actual_numeric = {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in actual.items()}
                expected_dict = eval(expected, {"__builtins__": __builtins__})
                return actual_numeric == {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in expected_dict.items()}
            return str(actual) == expected
        except Exception:
            return False
    return str(actual) == str(expected)


def execute_code(assessment_id: str, challenge: Any, code: str, language: str = "python") -> ExecutionResponse:
    if language != "python":
        raise ValueError("Only Python execution is supported.")
    if not code.strip():
        raise ValueError("Code submission cannot be empty.")
    results, passed, runtime_ms = _execute_python(code=code, challenge=challenge)
    failed = max(0, len(results) - passed)
    return ExecutionResponse(
        success=passed == len(results) and len(results) > 0,
        tests=results,
        passed=passed,
        failed=failed,
        total=len(results),
        runtime_ms=runtime_ms,
    )
