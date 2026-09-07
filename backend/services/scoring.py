"""Weighted baseline scoring service with versioned configuration."""

from __future__ import annotations

from typing import Any, Dict

# Versioned, configurable scoring rubric weights
SCORING_CONFIG_V1 = {
    "version": "1.0",
    "weights": {
        "correctness": 0.50,
        "efficiency": 0.20,
        "algorithmic_evidence": 0.15,
        "code_quality": 0.15,
    },
    "verification_threshold": 70.0,
}


def calculate_correctness_score(pass_ratio: float) -> float:
    """Calculates correctness score (0 - 100)."""
    return round(max(0.0, min(100.0, pass_ratio * 100.0)), 1)


def calculate_efficiency_score(avg_runtime_ms: float, pass_ratio: float) -> float:
    """
    Calculates efficiency score based on average execution time.
    Faster execution yields higher efficiency, penalized if correctness is low.
    Zero if no tests passed.
    """
    if pass_ratio <= 0.0:
        return 0.0
    if pass_ratio < 0.2:
        return 10.0

    # Baseline: <= 10ms -> 95-100; <= 50ms -> 85; <= 200ms -> 70; > 500ms -> 40
    if avg_runtime_ms <= 5.0:
        base = 98.0
    elif avg_runtime_ms <= 25.0:
        base = 90.0 - (avg_runtime_ms - 5.0) * 0.4
    elif avg_runtime_ms <= 100.0:
        base = 82.0 - (avg_runtime_ms - 25.0) * 0.15
    elif avg_runtime_ms <= 500.0:
        base = 70.0 - (avg_runtime_ms - 100.0) * 0.075
    else:
        base = max(30.0, 40.0 - (avg_runtime_ms - 500.0) * 0.01)

    return round(max(0.0, min(100.0, base)), 1)


def calculate_algorithmic_score(pass_ratio: float, complexity: int) -> float:
    """
    Algorithmic evidence combines correctness with clean algorithmic control flow.
    Zero if no tests passed.
    """
    if pass_ratio <= 0.0:
        return 0.0
    if pass_ratio < 0.1:
        return 10.0

    base = pass_ratio * 85.0
    # Reward balanced complexity (2 to 7 is standard for these algorithms)
    if 2 <= complexity <= 7:
        base += 15.0
    elif complexity <= 10:
        base += 8.0
    else:
        base -= 5.0
    return round(max(0.0, min(100.0, base)), 1)


def calculate_code_quality_score(code_metrics: Dict[str, Any]) -> float:
    """Calculates code quality score from AST metrics. Returns 0 if syntax is invalid."""
    if not code_metrics.get("syntax_valid", True):
        return 0.0

    score = 40.0  # Base for syntactically valid parseable code

    if code_metrics.get("has_type_annotations"):
        score += 20.0
    if code_metrics.get("has_docstring"):
        score += 15.0
    if code_metrics.get("clean_naming"):
        score += 15.0

    # Penalize excessive cyclomatic complexity or extreme sprawl
    cc = code_metrics.get("cyclomatic_complexity", 1)
    if cc > 12:
        score -= 15.0
    elif cc > 8:
        score -= 5.0

    loc = code_metrics.get("lines_of_code", 10)
    if 5 <= loc <= 45:
        score += 10.0

    return round(max(0.0, min(100.0, score)), 1)


def compute_scores(
    evaluation_metrics: Dict[str, Any],
    config: Dict[str, Any] = SCORING_CONFIG_V1,
) -> Dict[str, Any]:
    """
    Computes overall score and dimensional breakdown using weighted rubric.
    Enforces that invalid/syntax error code or 0-pass submissions produce 0.0 score.
    """
    weights = config["weights"]
    pass_ratio = evaluation_metrics.get("pass_ratio", 0.0)
    tests_passed = evaluation_metrics.get("tests_passed", 0)
    tests_total = evaluation_metrics.get("tests_total", 0)
    avg_runtime_ms = evaluation_metrics.get("avg_test_runtime_ms", 50.0)
    code_metrics = evaluation_metrics.get("code_metrics", {})
    complexity = code_metrics.get("cyclomatic_complexity", 2)
    has_syntax_error = evaluation_metrics.get("has_syntax_error", False) or not code_metrics.get("syntax_valid", True)

    # Core Policy: Syntax errors or uncompilable code produce strictly 0.0
    if has_syntax_error or tests_total == 0:
        return {
            "overall_score": 0.0,
            "passed_threshold": False,
            "breakdown": {
                "problem_solving": 0.0,
                "algorithmic_thinking": 0.0,
                "efficiency": 0.0,
                "code_quality": 0.0,
            },
            "scoring_version": config.get("version", "1.0"),
        }

    # Core Policy: If zero tests pass, overall score is strictly 0.0
    if tests_passed == 0:
        return {
            "overall_score": 0.0,
            "passed_threshold": False,
            "breakdown": {
                "problem_solving": 0.0,
                "algorithmic_thinking": 0.0,
                "efficiency": 0.0,
                "code_quality": calculate_code_quality_score(code_metrics),
            },
            "scoring_version": config.get("version", "1.0"),
        }

    correctness = calculate_correctness_score(pass_ratio)
    efficiency = calculate_efficiency_score(avg_runtime_ms, pass_ratio)
    algorithmic = calculate_algorithmic_score(pass_ratio, complexity)
    code_quality = calculate_code_quality_score(code_metrics)

    # Problem solving is heavily correlated with correctness and robust handling
    problem_solving = round(correctness * 0.85 + algorithmic * 0.15, 1)

    overall = (
        correctness * weights["correctness"]
        + efficiency * weights["efficiency"]
        + algorithmic * weights["algorithmic_evidence"]
        + code_quality * weights["code_quality"]
    )
    overall_rounded = round(max(0.0, min(100.0, overall)), 1)

    threshold = config.get("verification_threshold", 70.0)
    passed_threshold = bool(overall_rounded >= threshold and pass_ratio >= 0.70)

    return {
        "overall_score": overall_rounded,
        "passed_threshold": passed_threshold,
        "breakdown": {
            "problem_solving": problem_solving,
            "algorithmic_thinking": algorithmic,
            "efficiency": efficiency,
            "code_quality": code_quality,
        },
        "scoring_version": config.get("version", "1.0"),
    }
