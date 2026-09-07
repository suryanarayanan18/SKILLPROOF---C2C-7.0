"""Pydantic request and response schemas for SkillProof API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "skillproof-api"
    version: str = "1.0.0"
    active_calibration_version: str = "v1.0"
    active_model_version: str = "v1.0"


class AssessmentCreateRequest(BaseModel):
    candidate_id: Optional[str] = None
    skill: str = "python"
    difficulty: str = "intermediate"
    seed_problem_id: Optional[str] = None


class ProblemPublicView(BaseModel):
    id: str
    title: str
    description: str
    difficulty: str
    concepts: List[str]
    algorithm_family: str
    constraints: List[str]
    starter_code: str
    version: str


class AssessmentResponse(BaseModel):
    id: str
    candidate_id: str
    problem: ProblemPublicView
    calibration_version: str
    started_at: str
    submitted_at: Optional[str] = None
    attempt_number: int = 1


class SubmissionRequest(BaseModel):
    solution: str
    time_taken: Optional[float] = 0.0


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


class RetrainResponse(BaseModel):
    success: bool
    status: str
    proposed_version: str
    benchmark_score: float
    previous_benchmark_score: float
    guardrail_results: Dict[str, Any]
    message: str
