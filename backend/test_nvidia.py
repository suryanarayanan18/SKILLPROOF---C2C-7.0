from services.nvidia import generate_text


def main():
    prompt = """
You are the challenge-generation AI for SkillProof.

Generate ONE beginner Python assessment.

Return JSON only:

{
  "title": "...",
  "description": "...",
  "difficulty": "beginner",
  "language": "python",
  "starter_code": "...",
  "expected_concept": "..."
}

Do not use markdown.
Do not include explanations outside the JSON.
"""

    result = generate_text(prompt)

    print("\n========== SKILLPROOF NVIDIA TEST ==========")
    print(result)
    print("============================================\n")


if __name__ == "__main__":
    main()