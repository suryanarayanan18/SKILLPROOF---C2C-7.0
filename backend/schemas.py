"""Pydantic contracts for the SkillProof prototype API."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


Difficulty = Literal["beginner", "intermediate", "advanced"]


class ChallengeCreateRequest(BaseModel):
    skill: str = Field(min_length=1, max_length=100, examples=["Python"])
    difficulty: Difficulty
    previous_performance: str | None = Field(default=None, max_length=4000)
    target_weakness: str | None = Field(default=None, max_length=1000)

    @field_validator("skill")
    @classmethod
    def python_only(cls, value: str) -> str:
        if value.strip().lower() != "python":
            raise ValueError("Only Python assessments are currently supported.")
        return "Python"


class ChallengeResponse(BaseModel):
    assessment_id: str
    challenge_id: str
    skill: str
    difficulty: Difficulty
    title: str
    overview: str
    task: str
    constraints: list[str]
    starter_code: str
    examples: list[dict[str, str]] = Field(default_factory=list)


class SolutionSubmitRequest(BaseModel):
    solution: str = Field(min_length=1, max_length=100_000)
    time_elapsed_seconds: int | None = Field(default=None, ge=0)


class EvaluationRequest(SolutionSubmitRequest):
    assessment_id: str = Field(min_length=1)


class EvaluationResponse(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    correctness: int = Field(ge=0, le=100)
    problem_solving: int = Field(ge=0, le=100)
    code_quality: int = Field(ge=0, le=100)
    efficiency: int = Field(ge=0, le=100)
    understanding: int = Field(ge=0, le=100)
    practical_application: int = Field(ge=0, le=100)
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    feedback: str
    recommended_next_step: str
    status: Literal["completed"] = "completed"
    passed_tests: int = Field(default=0, ge=0)
    total_tests: int = Field(default=0, ge=0)
    failed_tests: int = Field(default=0, ge=0)
    competency: str = "Developing"
    improvements: list[str] = Field(default_factory=list)
    next_difficulty: Difficulty | None = None
    test_results: list[dict[str, str]] = Field(default_factory=list)


class AssessmentResponse(ChallengeResponse):
    evaluation: EvaluationResponse | None = None
    submitted_solution: str | None = None
    time_elapsed_seconds: int | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    provider: Literal["mock", "gemini"]


class PassportResponse(BaseModel):
    assessment_id: str
    skill: str
    difficulty: Difficulty
    overall_score: int
    verified: bool
    summary: str
