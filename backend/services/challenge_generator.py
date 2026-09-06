"""Generate practical challenges through the configured provider."""

import os

from services.gemini import generate_text


def generate_challenge(
    skill: str = "Python",
    difficulty: str = "beginner",
    previous_performance: str | None = None,
    target_weakness: str | None = None,
) -> str:
    """
    Generate a practical skill assessment challenge.

    Parameters:
        skill: The skill being assessed.
        difficulty: beginner, intermediate, or advanced.
        previous_performance: Optional summary of previous performance.
        target_weakness: Optional weakness that the challenge should target.

    Returns:
        A generated challenge as text.
    """

    if os.getenv("SKILLPROOF_PROVIDER", "mock").strip().lower() in {"mock", "demo"}:
        from services.demo_provider import generate_challenge as generate_demo_challenge

        return generate_demo_challenge(skill=skill, difficulty=difficulty)

    prompt = f"""
You are the Challenge Generator for SkillProof,
an AI-powered practical skill verification platform.

Your job is to create a practical assessment challenge
that tests real ability rather than memorization.

Skill:
{skill}

Difficulty:
{difficulty}

Previous performance:
{previous_performance or "No previous performance. This is the first challenge."}

Target weakness:
{target_weakness or "No specific weakness. Test a balanced set of skills."}

Create ONE practical challenge.

The challenge must:

1. Be appropriate for the selected difficulty.
2. Test practical problem-solving ability.
3. Require the user to actually produce a solution.
4. Avoid questions that can be answered through simple memorization.
5. Be realistic and useful for evaluating professional ability.

For a Python challenge, include:

- A clear problem statement.
- The user's task.
- Input/output expectations if applicable.
- Important constraints.
- At least one example.
- What skills are being tested.

Do NOT provide the solution.

Return ONLY a JSON object. Its fields must be:
title (string), overview (string), task (string), constraints (array of strings),
starter_code (string), and examples (array of objects with input and output strings).
Do not wrap the JSON in Markdown or include a solution.
"""

    return generate_text(prompt)


if __name__ == "__main__":
    challenge = generate_challenge(
        skill="Python",
        difficulty="beginner",
    )

    print("\n===== GENERATED CHALLENGE =====\n")
    print(challenge)
