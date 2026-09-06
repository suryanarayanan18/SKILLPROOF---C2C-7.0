from services.challenge_generator import generate_challenge
from services.evaluator import evaluate_solution


print("\n===== SKILLPROOF =====\n")

# 1. Generate first challenge
challenge = generate_challenge(
    skill="Python",
    difficulty="beginner",
)

print("===== CHALLENGE =====\n")
print(challenge)


# 2. Candidate submits a solution
solution = input(
    "\n\nPaste the candidate's Python solution below.\n"
    "Type END on a new line when finished:\n\n"
)

lines = [solution]

while True:
    line = input()

    if line.strip() == "END":
        break

    lines.append(line)

solution = "\n".join(lines)


# 3. Evaluate solution
print("\n===== AI EVALUATION =====\n")

evaluation = evaluate_solution(
    challenge=challenge,
    solution=solution,
    skill="Python",
)

print(evaluation)