import os
from services.gemini import generate_text


def run_live_check() -> None:
	if not os.getenv("GEMINI_API_KEY"):
		print("Skipping live Gemini check: zero runtime LLM dependency active per PRD.")
		return
	prompt = """
You are testing the SkillProof AI system.

Respond with exactly:
SkillProof Gemini connection successful.
	"""
	result = generate_text(prompt)
	print(result)


if __name__ == "__main__":
	run_live_check()