from services.challenge_generator import generate_challenge
from services.evaluator import evaluate_solution


def main() -> None:
    print("\n===== SKILLPROOF =====\n")

    challenge = generate_challenge(skill="Python", difficulty="beginner")
    print("===== CHALLENGE =====\n")
    print(challenge)

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

    print("\n===== AI EVALUATION =====\n")
    print(evaluate_solution(challenge=challenge, solution="\n".join(lines), skill="Python"))


if __name__ == "__main__":
    main()