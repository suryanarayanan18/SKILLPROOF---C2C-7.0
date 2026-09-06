"""Deterministic provider used for local demos when Gemini is unavailable."""

from __future__ import annotations

import json
import re


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
    """Return a realistic, difficulty-specific challenge without network access."""
    challenge = dict(DEMO_CHALLENGES.get(difficulty, DEMO_CHALLENGES["intermediate"]))
    challenge["skill"] = skill
    challenge["difficulty"] = difficulty
    return json.dumps(challenge)


def evaluate_solution(*, challenge: str, solution: str, **_: object) -> str:
    """Score recognizable implementation choices without executing submitted code."""
    source = solution.lower()
    checks = {
        "function": bool(re.search(r"\b(process_cart|aggregate_payload_stream|acquire)\s*\(", source)),
        "iteration": any(token in source for token in ("for item in", "for record in", "for product in")),
        "quantity_filter": any(token in source for token in ("quantity <= 0", "quantity > 0", "if not quantity", "if quantity")),
        "category_discount": "category" in source and "discount" in source,
        "subtotal": "subtotal" in source and ("price" in source or "total" in source),
        "store_discount": "threshold" in source or "0.1" in source or "10%" in source,
        "non_negative": "max(0" in source or "max(0," in source or "never negative" in source,
        "structured_return": "return {" in source or "return{" in source,
    }
    completed = sum(checks.values())
    correctness = min(100, 45 + completed * 7)
    problem_solving = min(100, 50 + completed * 6)
    code_quality = min(100, 55 + (10 if "def " in source else 0) + (10 if "round(" in source else 0) + completed * 3)
    efficiency = min(100, 60 + (15 if checks["iteration"] else 0) + (10 if "sum(" in source else 0) + completed * 2)
    understanding = min(100, 48 + completed * 6)
    practical_application = min(100, 50 + completed * 6)
    overall = round((correctness + problem_solving + code_quality + efficiency + understanding + practical_application) / 6)
    strengths = ["Clear function structure and readable Python." if checks["function"] else "The submission contains a Python implementation."]
    if checks["iteration"]:
        strengths.append("Uses iteration to process assessment data.")
    if checks["category_discount"]:
        strengths.append("Accounts for category-specific discount logic.")
    weaknesses = []
    if not checks["quantity_filter"]:
        weaknesses.append("Add explicit filtering for invalid quantities or records.")
    if not checks["store_discount"]:
        weaknesses.append("Implement the threshold or refill rule described by the challenge.")
    if not checks["non_negative"]:
        weaknesses.append("Guard shared or final values so they cannot become negative.")
    if not weaknesses:
        weaknesses.append("Add more edge-case tests for unusual inputs.")
    return json.dumps({
        "overall_score": overall,
        "correctness": correctness,
        "problem_solving": problem_solving,
        "code_quality": code_quality,
        "efficiency": efficiency,
        "understanding": understanding,
        "practical_application": practical_application,
        "summary": f"Demo evaluation identified {completed} of {len(checks)} expected implementation signals.",
        "strengths": strengths,
        "weaknesses": weaknesses,
        "feedback": "This is a deterministic source review for the local demo; submitted code was not executed in a sandbox.",
        "recommended_next_step": "Add focused tests for edge cases and boundary behavior before resubmitting.",
    })
