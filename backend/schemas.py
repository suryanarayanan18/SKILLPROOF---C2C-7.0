"""Pydantic request and response schemas for SkillProof API."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


Difficulty = Literal["beginner", "intermediate", "advanced"]


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "skillproof-api"
    version: str = "1.0.0"
    provider: str = "mock"
    active_calibration_version: str = "v1.0"
    active_model_version: str = "v1.0"


class AssessmentCreateRequest(BaseModel):
    candidate_id: Optional[str] = None
    skill: str = "python"
    difficulty: str = "intermediate"
    seed_problem_id: Optional[str] = None


class ChallengeCreateRequest(BaseModel):
    skill: str = Field(min_length=1, max_length=100, default="Python")
    difficulty: Difficulty = "intermediate"
    previous_performance: Optional[str] = None
    target_weakness: Optional[str] = None

    @field_validator("skill")
    @classmethod
    def python_only(cls, value: str) -> str:
        if value.strip().lower() != "python":
            raise ValueError("Only Python assessments are currently supported.")
        return "Python"


class ChallengeResponse(BaseModel):
    assessment_id: str
    challenge_id: str
    skill: str = "Python"
    difficulty: str = "intermediate"
    title: str
    overview: str
    task: str
    constraints: List[str] = Field(default_factory=list)
    starter_code: str
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    calibration_version: Optional[str] = "v1.0"


class ProblemPublicView(BaseModel):
    id: str
    seed_problem_id: Optional[str] = None
    transformation_type: Optional[str] = None
    title: str
    description: str
    difficulty: str
    concepts: List[str]
    algorithm_family: str
    constraints: List[str]
    starter_code: str
    version: str
    metadata: Optional[Dict[str, Any]] = None



class AssessmentResponse(BaseModel):
    id: str
    candidate_id: str
    problem: ProblemPublicView
    calibration_version: str
    started_at: str
    submitted_at: Optional[str] = None
    attempt_number: int = 1


class SubmissionRequest(BaseModel):
    solution: str = Field(min_length=1)
    time_taken: Optional[float] = 0.0


class SolutionSubmitRequest(BaseModel):
    solution: str = Field(min_length=1, max_length=100_000)
    time_elapsed_seconds: Optional[int] = Field(default=None, ge=0)


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
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    feedback: str
    recommended_next_step: str
    status: Literal["completed"] = "completed"
    passed_tests: int = Field(default=0, ge=0)
    total_tests: int = Field(default=0, ge=0)
    failed_tests: int = Field(default=0, ge=0)
    competency: str = "Developing"
    improvements: List[str] = Field(default_factory=list)
    next_difficulty: Optional[Difficulty] = None
    test_results: List[Dict[str, Any]] = Field(default_factory=list)


class TestRunResult(BaseModel):
    test_index: int
    name: str
    passed: bool
    runtime_ms: float
    error: Optional[str] = None


class CodeQualityMetrics(BaseModel):
    lines_of_code: int
    ast_nodes: int
    cyclomatic_complexity: int
    has_type_annotations: bool
    has_docstring: bool
    clean_naming: bool


class ResultBreakdown(BaseModel):
    problem_solving: float
    algorithmic_thinking: float
    efficiency: float
    code_quality: float


class ResultResponse(BaseModel):
    assessment_id: str
    candidate_id: str
    problem_id: str
    problem_title: str
    difficulty: str
    tests_passed: int
    tests_total: int
    test_runs: List[TestRunResult] = Field(default_factory=list)
    runtime: float
    memory: float
    time_taken: float
    code_metrics: CodeQualityMetrics
    breakdown: ResultBreakdown
    overall_score: float
    passed_threshold: bool
    problem_version: str
    calibration_version: str
    evaluation_model_version: str


class PassportSkillEntry(BaseModel):
    name: str
    score: float
    benchmark_percentile: float


class SkillPassportResponse(BaseModel):
    passport_id: str
    candidate_id: str
    skill: str
    overall_score: float
    verified: bool
    verified_at: str
    problem_title: str
    difficulty: str
    algorithm_family: str
    competencies: Dict[str, float]
    evidence: Dict[str, Any]
    problem_version: str
    calibration_version: str
    evaluation_model_version: str


class PassportResponse(BaseModel):
    assessment_id: str
    skill: str
    difficulty: str
    overall_score: int
    verified: bool
    summary: str


class CalibrationObservationRequest(BaseModel):
    assessment_id: str
    problem_id: str
    features: Dict[str, Any]
    result_metrics: Dict[str, Any]
    validity_flags: Dict[str, Any]


class CalibrationStatusResponse(BaseModel):
    active_model_version: str
    calibration_version: str
    benchmark_score: float
    observation_count: int
    guardrails: Dict[str, Any]
    available_versions: List[Dict[str, Any]]
    previous_model_version: Optional[str] = None
    latest_retrain_result: Optional[Dict[str, Any]] = None


class RetrainResponse(BaseModel):
    success: bool
    status: str
    proposed_version: str
    benchmark_score: float
    previous_benchmark_score: float
    guardrail_results: Dict[str, Any]
    message: str
