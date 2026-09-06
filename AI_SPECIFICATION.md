# SkillProof AI Specification

## 1. Purpose

SkillProof is an AI-driven skill verification platform designed to verify demonstrated practical ability rather than relying on certificates or self-declared skills.

The AI system evaluates:

- Problem-solving ability
- Correctness
- Code quality
- Efficiency
- Understanding
- Ability to improve after feedback
- Practical application of knowledge

The prototype will initially focus on Python so that the team can demonstrate a complete working assessment flow within the hackathon.

The architecture should be designed so that additional skills can be added in future versions.

### Initial Prototype Skill

- Python

### Initial Difficulty Levels

- Beginner
- Intermediate
- Advanced

---

# 2. AI System Architecture

The SkillProof AI system consists of the following components:

1. Challenge Generator
2. Solution Evaluator
3. Feedback Generator
4. Adaptive Challenge Generator
5. Improvement Tracker
6. Skill Passport Generator

The overall assessment flow is:

User selects skill and difficulty
        ↓
Challenge Generator
        ↓
User receives challenge
        ↓
User submits solution
        ↓
Solution Evaluator
        ↓
Feedback Generator
        ↓
User receives feedback
        ↓
User improves / attempts another challenge
        ↓
Adaptive Challenge Generator
        ↓
Targeted follow-up challenge
        ↓
New evaluation
        ↓
Improvement Tracking
        ↓
Skill Passport Generator
        ↓
Skill Passport

The system should use structured JSON between the frontend, backend, and AI components wherever possible.

---

# 3. Challenge Generator

## Purpose

Generate a practical challenge based on the user's selected skill and difficulty.

The challenge should test practical ability and problem-solving rather than simple memorization.

## Input

The Challenge Generator receives:

- `skill`
- `difficulty`
- `previousPerformance` (optional)
- `targetWeakness` (optional)
- `attemptedChallenges` (optional)

### Example Input

```json
{
  "skill": "Python",
  "difficulty": "intermediate",
  "previousPerformance": null,
  "targetWeakness": null,
  "attemptedChallenges": []
}

docs: add AI system specification
