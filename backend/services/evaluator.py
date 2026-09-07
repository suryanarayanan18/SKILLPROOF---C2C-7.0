"""Evaluate submitted solutions through the configured provider."""

import os

from services.ai_provider import generate_text


def evaluate_solution(
    challenge: str,
    solution: str,
    skill: str = "Python",
    difficulty: str | None = None,
) -> str:
    """Evaluate a candidate solution using the selected AI provider."""

    provider = os.getenv("SKILLPROOF_PROVIDER", "mock").strip().lower()
    if provider in {"mock", "demo"}:
        from services.demo_provider import evaluate_solution as evaluate_demo_solution

        return evaluate_demo_solution(challenge=challenge, solution=solution, skill=skill, difficulty=difficulty)

    prompt = f"""
You are the SkillProof AI Evaluator.

SkillProof is an AI-powered practical skill verification platform.
The goal is to evaluate REAL ability rather than certificates.

SKILL:
{skill}

DIFFICULTY:
{difficulty or 'beginner'}

CHALLENGE:
{challenge}

CANDIDATE'S SOLUTION:
{solution}

Evaluate the candidate's solution carefully.

IMPORTANT:
- Do not give credit simply because the code looks plausible.
- Check whether the solution actually solves the stated problem.
- Consider edge cases.
- Evaluate the candidate's reasoning and implementation quality.
- Be fair to the selected difficulty.
- The actual execution results must shape the score. If tests fail, the correctness score should be reduced.
- Do not invent requirements that were not present in the challenge.

Return ONLY a JSON object with overall_score, correctness, problem_solving,
code_quality, efficiency, understanding, practical_application (all integers
from 0 to 100), summary, strengths (array), weaknesses (array), feedback, and
recommended_next_step. Do not wrap the JSON in Markdown. Be concise but specific.
"""

    return generate_text(prompt)


if __name__ == "__main__":
    challenge = """
Write a Python function called calculate_total(cart, tax_rate).

Each cart item contains:
- price
- quantity
- discount

Calculate the discounted subtotal and then apply the tax rate.
Return the final amount rounded to 2 decimal places.
"""

    solution = """
def calculate_total(cart, tax_rate):
    subtotal = 0

    for item in cart:
        price = item["price"]
        quantity = item["quantity"]
        discount = item["discount"]

        subtotal += price * quantity * (1 - discount / 100)

    return round(subtotal * (1 + tax_rate / 100), 2)
"""

    print("\n===== SKILLPROOF EVALUATION =====\n")

    evaluation = evaluate_solution(
        challenge=challenge,
        solution=solution,
        skill="Python",
    )

    print(evaluation)
