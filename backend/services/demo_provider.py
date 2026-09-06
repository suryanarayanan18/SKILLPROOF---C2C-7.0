"""Deterministic local provider for the Review 1 demo.

This provider never calls an external service. It executes the submitted code
against fixed, challenge-specific fixtures and returns the normal evaluator
contract used by the Stitch results page.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable


DEMO_CHALLENGES = {
    "beginner": {
        "title": "E-Commerce Shopping Cart Calculator",
        "overview": "Calculate a shopping cart total with category discounts, invalid-quantity filtering, tax, and a store-wide threshold discount.",
        "task": "Write process_cart(items, category_discounts, store_discount_threshold=100). Return subtotal, total_quantity, discount, tax, and total. Ignore quantities <= 0, apply category discounts, apply a 10% store discount above the threshold, and never return a negative total.",
        "constraints": ["Ignore items with quantity <= 0.", "Apply category-specific discounts and a 10% store discount above the threshold.", "Do not modify the input list.", "Return monetary values rounded to 2 decimals."],
        "starter_code": "def process_cart(items: list, category_discounts: dict, store_discount_threshold: float = 100) -> dict:\n    # Return the cart totals as a dictionary.\n    pass\n",
        "examples": [{"input": "items = [{'price': 25, 'quantity': 2, 'category': 'books'}]", "output": "{'subtotal': 50.0, 'total_quantity': 2, 'discount': 0.0, 'tax': 4.0, 'total': 54.0}"}],
    },
    "intermediate": {
        "title": "Resilient Telemetry Window Aggregator",
        "overview": "Process unordered telemetry events into deterministic time windows while filtering malformed records and preserving useful audit information.",
        "task": "Write aggregate_payload_stream(events, window_seconds=60). Group valid records by timestamp window, ignore malformed envelopes, preserve event order inside each bucket, and return partitions plus malformed_dropped and total_payloads.",
        "constraints": ["Use deterministic bucket keys based on timestamp modulo window_seconds.", "Ignore records missing timestamp or payload without raising an exception.", "Preserve input order inside each partition.", "Return partitions, malformed_dropped, and total_payloads."],
        "starter_code": "def aggregate_payload_stream(events: list, window_seconds: int = 60) -> dict:\n    # Return deterministic partitions and audit counts.\n    pass\n",
        "examples": [{"input": "events = [{'timestamp': 121, 'payload': 'cpu'}, {'raw': 'bad'}]", "output": "{'partitions': {'120': [{'timestamp': 121, 'payload': 'cpu'}]}, 'malformed_dropped': 1, 'total_payloads': 1}"}],
    },
    "advanced": {
        "title": "Concurrent Token Bucket Rate Limiter",
        "overview": "Design a thread-safe token bucket that supports burst capacity, monotonic refill timing, and independent client state under concurrent access.",
        "task": "Implement TokenBucketLimiter with acquire(client_id, tokens=1) and refill(client_id). Enforce capacity, refill tokens using a monotonic clock, isolate clients, and make state mutations thread-safe.",
        "constraints": ["Use a lock around shared state mutations.", "Use time.monotonic() rather than wall-clock time.", "Support independent token balances for multiple clients.", "Never allow a bucket to exceed capacity or become negative."],
        "starter_code": "import time\nfrom threading import Lock\n\nclass TokenBucketLimiter:\n    def __init__(self, capacity: int, refill_rate: float):\n        pass\n\n    def acquire(self, client_id: str, tokens: int = 1) -> bool:\n        pass\n",
        "examples": [{"input": "limiter.acquire('client-1', tokens=2)", "output": "True while sufficient tokens remain; otherwise False"}],
    },
}


def generate_challenge(*, skill: str, difficulty: str, **_: object) -> str:
    challenge = dict(DEMO_CHALLENGES.get(difficulty, DEMO_CHALLENGES["beginner"]))
    challenge["skill"] = skill
    challenge["difficulty"] = difficulty
    return json.dumps(challenge)


def _run_solution(solution: str, function_name: str, cases: list[tuple[str, Callable[[dict[str, Any]], bool]]]) -> list[dict[str, str]]:
    namespace: dict[str, Any] = {}
    try:
        exec(compile(solution, "<submitted-solution>", "exec"), namespace)
        function = namespace.get(function_name)
        if not callable(function):
            raise ValueError(f"Define {function_name} before submitting.")
    except Exception as error:
        return [{"name": name, "status": "FAIL", "detail": f"Could not load solution: {error}"} for name, _ in cases]

    results = []
    for name, check in cases:
        try:
            passed = check({"function": function})
            results.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": "Assertions matched." if passed else "Output differed from the expected result."})
        except Exception as error:
            results.append({"name": name, "status": "FAIL", "detail": f"Raised {type(error).__name__}: {error}"})
    return results


def _cases_for(difficulty: str) -> tuple[str, list[tuple[str, Callable[[dict[str, Any]], bool]]]]:
    if difficulty == "beginner":
        def run(function: Any, items: list[dict[str, Any]], discounts: dict[str, float], threshold: float = 100) -> dict[str, Any]:
            return function(items, discounts, threshold)

        return "process_cart", [
            ("single category", lambda ctx: run(ctx["function"], [{"price": 25, "quantity": 2, "category": "books"}], {}) == {"subtotal": 50.0, "total_quantity": 2, "discount": 0.0, "tax": 4.0, "total": 54.0}),
            ("category discount", lambda ctx: run(ctx["function"], [{"price": 50, "quantity": 3, "category": "books"}], {"books": 10}, 100) == {"subtotal": 135.0, "total_quantity": 3, "discount": 13.5, "tax": 9.72, "total": 131.22}),
            ("invalid quantity", lambda ctx: run(ctx["function"], [{"price": 25, "quantity": 0, "category": "books"}], {})["total_quantity"] == 0),
            ("threshold boundary", lambda ctx: run(ctx["function"], [{"price": 100, "quantity": 1, "category": "other"}], {})["discount"] == 0.0),
            ("empty cart", lambda ctx: run(ctx["function"], [], {})["total"] == 0.0),
        ]
    if difficulty == "intermediate":
        def check(function: Any, events: list[dict[str, Any]], expected: dict[str, Any]) -> bool:
            result = function(events, 60)
            return result == expected

        return "aggregate_payload_stream", [
            ("temporal buckets", lambda ctx: check(ctx["function"], [{"timestamp": 121, "payload": "cpu"}, {"timestamp": 181, "payload": "mem"}, {"raw": "bad"}], {"partitions": {"120": [{"timestamp": 121, "payload": "cpu"}], "180": [{"timestamp": 181, "payload": "mem"}]}, "malformed_dropped": 1, "total_payloads": 2})),
            ("preserve bucket order", lambda ctx: check(ctx["function"], [{"timestamp": 125, "payload": "first"}, {"timestamp": 121, "payload": "second"}, {"raw": "bad"}], {"partitions": {"120": [{"timestamp": 125, "payload": "first"}, {"timestamp": 121, "payload": "second"}]}, "malformed_dropped": 1, "total_payloads": 2})),
            ("empty input", lambda ctx: ctx["function"]([], 60) == {"partitions": {}, "malformed_dropped": 0, "total_payloads": 0}),
        ]
    return "TokenBucketLimiter", [
        ("class exists", lambda ctx: callable(ctx["function"])),
    ]


def evaluate_solution(*, challenge: str, solution: str, skill: str = "Python", difficulty: str | None = None, **_: object) -> str:
    data = json.loads(challenge) if challenge.strip().startswith("{") else {}
    selected_difficulty = difficulty or str(data.get("difficulty", "beginner"))
    function_name, cases = _cases_for(selected_difficulty)
    results = _run_solution(solution, function_name, cases)
    passed = sum(result["status"] == "PASS" for result in results)
    total = len(results)
    score = round(45 + (passed / total) * 55) if total else 0
    competency = "Excellent" if score >= 90 else "Strong" if score >= 75 else "Developing"
    strengths = [f"Passed {passed} of {total} deterministic test cases."]
    if passed == total:
        strengths.append("Handles the supplied edge cases and expected output contract.")
    improvements = [result["name"] for result in results if result["status"] != "PASS"]
    if not improvements:
        improvements = ["Add additional tests for inputs outside the supplied fixtures."]
    return json.dumps({
        "overall_score": score,
        "correctness": score,
        "problem_solving": min(100, score + 2),
        "code_quality": min(100, score + (5 if "def " in solution and "return" in solution else 0)),
        "efficiency": min(100, score + 1),
        "understanding": score,
        "practical_application": score,
        "summary": f"Deterministic Review 1 completed with {passed}/{total} tests passing.",
        "strengths": strengths,
        "weaknesses": improvements,
        "improvements": improvements,
        "feedback": "The submitted Python was executed locally against fixed Review 1 fixtures; no AI service was used.",
        "recommended_next_step": "Review the failed cases and add focused boundary tests before attempting the next difficulty.",
        "status": "completed",
        "passed_tests": passed,
        "total_tests": total,
        "failed_tests": total - passed,
        "competency": competency,
        "next_difficulty": "intermediate" if selected_difficulty == "beginner" else "advanced" if selected_difficulty == "intermediate" else "advanced",
        "test_results": results,
    })
