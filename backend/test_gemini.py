from services.gemini import generate_text


def run_live_check() -> None:
	prompt = """
You are testing the SkillProof AI system.

Respond with exactly:
SkillProof Gemini connection successful.
	"""
	result = generate_text(prompt)
	print(result)


if __name__ == "__main__":
	run_live_check()