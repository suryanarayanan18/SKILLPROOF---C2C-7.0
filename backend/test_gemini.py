from services.gemini import generate_text


prompt = """
You are testing the SkillProof AI system.

Respond with exactly:
SkillProof Gemini connection successful.
"""

result = generate_text(prompt)

print(result)