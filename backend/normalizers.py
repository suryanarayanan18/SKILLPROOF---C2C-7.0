"""Normalize the existing line-oriented Gemini responses for API clients."""

from __future__ import annotations

import json
import re

from schemas import ChallengeResponse, EvaluationResponse


SECTION_PATTERN = re.compile(r"^([A-Z][A-Z _/]+):\s*$", re.MULTILINE)


def _sections(text: str) -> dict[str, str]:
    """Parse the documented `SECTION:` format without trusting it completely."""
    matches = list(SECTION_PATTERN.finditer(text or ""))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result[match.group(1).strip()] = text[match.end() : end].strip()
    return result


def _json_object(text: str) -> dict[str, object]:
    """Extract a JSON object from plain text or a fenced Gemini response."""
    candidate = (text or "").strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate).strip()
    candidates = [candidate]
    start, end = candidate.find("{"), candidate.rfind("}")
    if start >= 0 and end > start:
        candidates.append(candidate[start : end + 1])
    for item in candidates:
        try:
            value = json.loads(item)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _lines(value: str) -> list[str]:
    return [line.strip().lstrip("-• ").strip() for line in value.splitlines() if line.strip().lstrip("-• ").strip()]


def _score(sections: dict[str, str], key: str, default: int) -> int:
    match = re.search(r"\d{1,3}", sections.get(key, ""))
    return min(100, max(0, int(match.group()))) if match else default


def normalize_challenge(
    text: str, *, assessment_id: str, challenge_id: str, skill: str, difficulty: str
) -> ChallengeResponse:
    data = _json_object(text)
    sections = _sections(text)
    problem = str(data.get("overview") or sections.get("PROBLEM", ""))
    task = str(data.get("task") or sections.get("TASK", "")) or problem or text.strip()
    overview = problem or task or f"A {difficulty} {skill} practical assessment."
    raw_constraints = data.get("constraints")
    constraints = [str(item).strip() for item in raw_constraints if str(item).strip()] if isinstance(raw_constraints, list) else _lines(sections.get("CONSTRAINTS", ""))
    raw_examples = data.get("examples")
    examples = [
        {"input": str(item.get("input", "")), "output": str(item.get("output", ""))}
        for item in raw_examples if isinstance(item, dict)
    ] if isinstance(raw_examples, list) else []
    return ChallengeResponse(
        assessment_id=assessment_id,
        challenge_id=challenge_id,
        skill=skill,
        difficulty=difficulty,
        title=str(data.get("title") or sections.get("TITLE", "").splitlines()[0].strip() or f"{skill} practical challenge"),
        overview=overview,
        task=task or "Complete the generated assessment task.",
        constraints=constraints,
        starter_code=str(data.get("starter_code") or sections.get("STARTER_CODE", "")),
        examples=examples,
    )


def normalize_evaluation(text: str) -> EvaluationResponse:
    data = _json_object(text)
    sections = _sections(text)
    def score(key: str, heading: str, default: int) -> int:
        value = data.get(key)
        if isinstance(value, (int, float)):
            return min(100, max(0, int(value)))
        if isinstance(value, str) and re.fullmatch(r"\s*\d{1,3}\s*", value):
            return min(100, max(0, int(value)))
        return _score(sections, heading, default)
    correctness = score("correctness", "CORRECTNESS", 0)
    problem_solving = score("problem_solving", "PROBLEM SOLVING", 0)
    code_quality = score("code_quality", "CODE QUALITY", 0)
    understanding = score("understanding", "UNDERSTANDING", 0)
    # Older evaluator prompts do not request these two dimensions. Derive a
    # conservative score so clients still receive the stable six-axis schema.
    efficiency = score("efficiency", "EFFICIENCY", round((correctness + problem_solving) / 2))
    practical_application = score(
        "practical_application", "PRACTICAL APPLICATION", round((correctness + understanding) / 2)
    )
    overall = score(
        "overall_score", "OVERALL SCORE",
        round((correctness + problem_solving + code_quality + efficiency + understanding + practical_application) / 6),
    )
    return EvaluationResponse(
        overall_score=overall,
        correctness=correctness,
        problem_solving=problem_solving,
        code_quality=code_quality,
        efficiency=efficiency,
        understanding=understanding,
        practical_application=practical_application,
        summary=str(data.get("summary") or sections.get("FEEDBACK", "").strip() or "Evaluation completed."),
        strengths=[str(item) for item in data.get("strengths", [])] if isinstance(data.get("strengths"), list) else _lines(sections.get("STRENGTHS", "")),
        weaknesses=[str(item) for item in data.get("weaknesses", [])] if isinstance(data.get("weaknesses"), list) else _lines(sections.get("WEAKNESSES", "")),
        feedback=str(data.get("feedback") or sections.get("FEEDBACK", "").strip() or "The evaluator did not provide written feedback."),
        recommended_next_step=str(
            data.get("recommended_next_step")
            or sections.get("RECOMMENDED NEXT STEP", "").strip()
            or "Review the challenge requirements and retry with additional edge cases."
        ),
    )
