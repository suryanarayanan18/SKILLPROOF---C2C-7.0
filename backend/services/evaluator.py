"""Turns execution output and source code into objective metrics."""

from __future__ import annotations

import ast
from typing import Any, Dict, List


def analyze_code_structure(code: str) -> Dict[str, Any]:
    """Calculates deterministic AST and static quality metrics from candidate source code."""
    lines = [l.strip() for l in code.splitlines() if l.strip() and not l.strip().startswith("#")]
    loc = len(lines)

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {
            "lines_of_code": loc,
            "ast_nodes": 0,
            "cyclomatic_complexity": 1,
            "has_type_annotations": False,
            "has_docstring": False,
            "clean_naming": False,
        }

    # Count nodes
    ast_nodes = sum(1 for _ in ast.walk(tree))

    # Cyclomatic complexity: 1 + number of branching decisions
    branches = 0
    has_annotations = False
    has_docstring = False
    names = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler, ast.With, ast.Assert)):
            branches += 1
        elif isinstance(node, ast.BoolOp):
            branches += len(node.values) - 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node):
                has_docstring = True
            if node.returns:
                has_annotations = True
            for arg in node.args.args:
                if arg.annotation:
                    has_annotations = True
                names.append(arg.arg)
        elif isinstance(node, ast.Name):
            names.append(node.id)

    # Clean naming check
    single_char_allowlist = {"i", "j", "k", "v", "x", "y", "z", "w", "n", "m", "c", "t", "e", "f", "_"}
    meaningful_names = [n for n in names if len(n) > 1 or n in single_char_allowlist]
    clean_naming_ratio = (len(meaningful_names) / max(1, len(names))) >= 0.85

    return {
        "lines_of_code": loc,
        "ast_nodes": ast_nodes,
        "cyclomatic_complexity": branches + 1,
        "has_type_annotations": has_annotations,
        "has_docstring": has_docstring,
        "clean_naming": clean_naming_ratio,
    }


def evaluate_execution_metrics(
    raw_execution: Dict[str, Any],
    solution_code: str,
    time_taken_seconds: float = 0.0,
) -> Dict[str, Any]:
    """Combines execution results and static code analysis into normalized evaluation metrics."""
    code_metrics = analyze_code_structure(solution_code)

    tests_total = raw_execution.get("tests_total", 0)
    tests_passed = raw_execution.get("tests_passed", 0)
    test_results = raw_execution.get("test_results", [])
    wall_time = raw_execution.get("wall_time", 0.0)
    memory_mb = raw_execution.get("memory_mb", 12.0)

    # Average runtime per test in ms
    test_runtimes = [t.get("runtime_ms", 0.0) for t in test_results if "runtime_ms" in t]
    avg_test_runtime_ms = (sum(test_runtimes) / len(test_runtimes)) if test_runtimes else 0.0

    return {
        "tests_passed": tests_passed,
        "tests_total": tests_total,
        "test_results": test_results,
        "pass_ratio": (tests_passed / tests_total) if tests_total > 0 else 0.0,
        "runtime": wall_time,
        "avg_test_runtime_ms": round(avg_test_runtime_ms, 2),
        "memory": memory_mb,
        "time_taken": round(time_taken_seconds, 1),
        "code_metrics": code_metrics,
        "execution_error": raw_execution.get("error"),
    }
