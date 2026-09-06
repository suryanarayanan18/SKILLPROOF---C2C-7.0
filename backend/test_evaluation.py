from services.evaluator import evaluate_solution


def run_live_check() -> None:
    challenge = """
Write a Python function called add_numbers(a, b)
that returns the sum of a and b.
    """

    solution = """
def add_numbers(a, b):
    return a + b
    """

    result = evaluate_solution(
        challenge=challenge,
        solution=solution,
        skill="Python"
    )

    print("\n===== SOLUTION EVALUATION =====\n")
    print(result)


if __name__ == "__main__":
    run_live_check()