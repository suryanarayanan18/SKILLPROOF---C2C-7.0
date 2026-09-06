from services.evaluator import evaluate_solution

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

print("\n===== REAL SOLUTION EVALUATION =====\n")
print(result)