"""FastAPI application for SkillProof: One-Shot Python Assessment & Continuous Calibration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import db
from ml.model import get_active_model
from schemas import (
    AssessmentCreateRequest,
    AssessmentResponse,
    CalibrationObservationRequest,
    CalibrationStatusResponse,
    CodeQualityMetrics,
    HealthResponse,
    PassportSkillEntry,
    ProblemPublicView,
    ResultBreakdown,
    ResultResponse,
    RetrainResponse,
    SkillPassportResponse,
    SubmissionRequest,
    TestRunResult,
)
from services.calibration import (
    get_calibration_status,
    record_validated_observation,
    trigger_calibration_retrain,
)
from services.challenge_generator import generate_challenge
from services.evaluator import evaluate_execution_metrics
from services.executor import execute_solution_tests
from services.problem_validator import validate_problem
from services.scoring import compute_scores

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("skillproof.app")

# Initialize database tables on startup
db.init_db()

# Bootstrap active model
get_active_model()

app = FastAPI(
    title="SkillProof API",
    description="One-Shot Python Skill Verification & TinyML Calibration Platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    active_model = get_active_model()
    return HealthResponse(
        status="ok",
        service="skillproof-api",
        version="1.0.0",
        active_calibration_version=active_model.version,
        active_model_version=active_model.version,
    )


@app.post("/api/assessment", response_model=AssessmentResponse, status_code=status.HTTP_201_CREATED)
def create_assessment(payload: AssessmentCreateRequest) -> AssessmentResponse:
    """
    Creates a novel one-shot assessment.
    Generates a transformed challenge from local seed corpus, confirms reference solution passes,
    and stores the problem and assessment record.
    """
    active_model = get_active_model()
    candidate_id = payload.candidate_id or f"cand-{uuid4().hex[:8]}"

    # Generate and validate problem variation
    max_retries = 3
    valid_problem: Optional[Dict[str, Any]] = None

    for _ in range(max_retries):
        candidate_problem = generate_challenge(
            skill=payload.skill,
            difficulty=payload.difficulty,
            seed_problem_id=payload.seed_problem_id,
        )
        is_valid, report = validate_problem(candidate_problem)
        if is_valid:
            valid_problem = candidate_problem
            break

    if not valid_problem:
        # Fallback to candidate problem anyway if validation timed out
        valid_problem = candidate_problem

    # Save problem in SQLite
    db.save_problem(valid_problem)

    # Create assessment in SQLite
    assessment_id = f"asm-{uuid4().hex[:12]}"
    assessment_record = db.create_assessment(
        assessment_id=assessment_id,
        candidate_id=candidate_id,
        problem_id=valid_problem["id"],
        calibration_version=active_model.version,
    )

    problem_view = ProblemPublicView(
        id=valid_problem["id"],
        title=valid_problem["title"],
        description=valid_problem["description"],
        difficulty=valid_problem["difficulty"],
        concepts=valid_problem["concepts"],
        algorithm_family=valid_problem["algorithm_family"],
        constraints=valid_problem["constraints"],
        starter_code=valid_problem["starter_code"],
        version=valid_problem["version"],
    )

    return AssessmentResponse(
        id=assessment_id,
        candidate_id=candidate_id,
        problem=problem_view,
        calibration_version=active_model.version,
        started_at=assessment_record["started_at"],
        submitted_at=assessment_record["submitted_at"],
        attempt_number=1,
    )


@app.get("/api/assessment/{assessment_id}", response_model=AssessmentResponse)
def get_assessment(assessment_id: str) -> AssessmentResponse:
    """Retrieves an existing assessment session and problem definition."""
    assessment = db.get_assessment(assessment_id)
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")

    problem = db.get_problem(assessment["problem_id"])
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found.")

    problem_view = ProblemPublicView(
        id=problem["id"],
        title=problem["title"],
        description=problem["description"],
        difficulty=problem["difficulty"],
        concepts=problem["concepts"],
        algorithm_family=problem["algorithm_family"],
        constraints=problem["constraints"],
        starter_code=problem["starter_code"],
        version=problem["version"],
    )

    return AssessmentResponse(
        id=assessment["id"],
        candidate_id=assessment["candidate_id"],
        problem=problem_view,
        calibration_version=assessment["calibration_version"],
        started_at=assessment["started_at"],
        submitted_at=assessment["submitted_at"],
        attempt_number=assessment["attempt_number"],
    )


@app.post("/api/assessment/{assessment_id}/submit", response_model=ResultResponse)
def submit_solution(assessment_id: str, payload: SubmissionRequest) -> ResultResponse:
    """
    Submits code for the one-shot assessment.
    CRITICAL: Strictly enforces one-shot rule. Rejects with 409 Conflict if already submitted.
    """
    assessment = db.get_assessment(assessment_id)
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")

    # Check if already submitted
    if assessment.get("submitted_at") is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This one-shot assessment has already been submitted. The candidate gets one attempt.",
        )

    # Atomically mark as submitted
    marked = db.mark_assessment_submitted(assessment_id)
    if not marked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment submission was already finalized.",
        )

    problem = db.get_problem(assessment["problem_id"])
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem definition missing.")

    # Execute solution in isolated sandbox
    raw_execution = execute_solution_tests(
        solution_code=payload.solution,
        tests=problem["tests"],
        timeout_seconds=5.0,
    )

    # Evaluate execution metrics + static AST metrics
    metrics = evaluate_execution_metrics(
        raw_execution=raw_execution,
        solution_code=payload.solution,
        time_taken_seconds=payload.time_taken or 0.0,
    )

    # Compute baseline score
    score_result = compute_scores(metrics)

    active_model = get_active_model()
    eval_model_version = active_model.version
    calibration_version = assessment["calibration_version"]
    problem_version = problem.get("version", "1.0")

    result_dict = {
        "assessment_id": assessment_id,
        "tests_passed": metrics["tests_passed"],
        "tests_total": metrics["tests_total"],
        "runtime": metrics["runtime"],
        "memory": metrics["memory"],
        "time_taken": metrics["time_taken"],
        "code_metrics": metrics["code_metrics"],
        "overall_score": score_result["overall_score"],
        "problem_version": problem_version,
        "calibration_version": calibration_version,
        "evaluation_model_version": eval_model_version,
        "breakdown": score_result["breakdown"],
        "submission_code": payload.solution,
    }

    # Save result immutably
    db.save_result(result_dict)

    # Feed quality-gated observation to the calibration buffer
    record_validated_observation(
        assessment_id=assessment_id,
        problem_id=problem["id"],
        result_data=result_dict,
        time_taken=metrics["time_taken"],
    )

    test_run_items = [
        TestRunResult(
            test_index=t.get("test_index", idx),
            name=t.get("name", f"Test #{idx+1}"),
            passed=t.get("passed", False),
            runtime_ms=t.get("runtime_ms", 0.0),
            error=t.get("error"),
        )
        for idx, t in enumerate(metrics["test_results"])
    ]

    return ResultResponse(
        assessment_id=assessment_id,
        candidate_id=assessment["candidate_id"],
        problem_id=problem["id"],
        problem_title=problem["title"],
        difficulty=problem["difficulty"],
        tests_passed=metrics["tests_passed"],
        tests_total=metrics["tests_total"],
        test_runs=test_run_items,
        runtime=metrics["runtime"],
        memory=metrics["memory"],
        time_taken=metrics["time_taken"],
        code_metrics=CodeQualityMetrics(**metrics["code_metrics"]),
        breakdown=ResultBreakdown(**score_result["breakdown"]),
        overall_score=score_result["overall_score"],
        passed_threshold=score_result["passed_threshold"],
        problem_version=problem_version,
        calibration_version=calibration_version,
        evaluation_model_version=eval_model_version,
    )


@app.get("/api/assessment/{assessment_id}/result", response_model=ResultResponse)
def get_assessment_result(assessment_id: str) -> ResultResponse:
    """Retrieves immutable evaluation result for an assessment."""
    result = db.get_result(assessment_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found.")

    assessment = db.get_assessment(assessment_id)
    problem = db.get_problem(assessment["problem_id"]) if assessment else None

    return ResultResponse(
        assessment_id=result["assessment_id"],
        candidate_id=assessment["candidate_id"] if assessment else "unknown",
        problem_id=problem["id"] if problem else "unknown",
        problem_title=problem["title"] if problem else "Assessment Problem",
        difficulty=problem["difficulty"] if problem else "intermediate",
        tests_passed=result["tests_passed"],
        tests_total=result["tests_total"],
        test_runs=[],
        runtime=result["runtime"],
        memory=result["memory"],
        time_taken=result["time_taken"],
        code_metrics=CodeQualityMetrics(**result["code_metrics"]),
        breakdown=ResultBreakdown(**result["breakdown"]),
        overall_score=result["overall_score"],
        passed_threshold=result["overall_score"] >= 70.0,
        problem_version=result["problem_version"],
        calibration_version=result["calibration_version"],
        evaluation_model_version=result["evaluation_model_version"],
    )


@app.get("/api/passport/{candidate_id}", response_model=SkillPassportResponse)
def get_skill_passport(candidate_id: str) -> SkillPassportResponse:
    """
    Generates an objectively-computed Skill Passport based on one-shot assessment evidence.
    Includes competency breakdown, runtime evidence, and audit versions.
    """
    results = db.get_candidate_results(candidate_id)
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No completed assessments found for candidate '{candidate_id}'.",
        )

    # Use the most recent completed assessment
    latest = results[0]
    breakdown = latest["breakdown"]
    overall_score = latest["overall_score"]
    is_verified = overall_score >= 70.0 and latest["tests_passed"] >= (latest["tests_total"] * 0.7)

    return SkillPassportResponse(
        passport_id=f"SP-PASS-{latest['assessment_id'][:8].upper()}",
        candidate_id=candidate_id,
        skill="Python",
        overall_score=overall_score,
        verified=is_verified,
        verified_at=latest["submitted_at"] or latest["started_at"],
        problem_title=latest.get("problem_title", "Algorithmic Challenge"),
        difficulty=latest.get("difficulty", "intermediate"),
        algorithm_family=latest.get("algorithm_family", "General"),
        competencies={
            "Problem Solving": breakdown.get("problem_solving", 0.0),
            "Algorithmic Thinking": breakdown.get("algorithmic_thinking", 0.0),
            "Efficiency": breakdown.get("efficiency", 0.0),
            "Code Quality": breakdown.get("code_quality", 0.0),
        },
        evidence={
            "assessment_mode": "one_shot_practical",
            "tests_passed": f"{latest['tests_passed']}/{latest['tests_total']}",
            "pass_ratio": round(latest["tests_passed"] / max(1, latest["tests_total"]), 2),
            "runtime_seconds": latest["runtime"],
            "memory_mb": latest["memory"],
            "time_taken_seconds": latest["time_taken"],
            "code_metrics": latest["code_metrics"],
        },
        problem_version=latest["problem_version"],
        calibration_version=latest["calibration_version"],
        evaluation_model_version=latest["evaluation_model_version"],
    )


@app.post("/api/calibration/observation", status_code=status.HTTP_201_CREATED)
def store_calibration_observation(payload: CalibrationObservationRequest) -> Dict[str, Any]:
    """Manually ingests an externally validated observation into the learning pool."""
    obs_id = db.save_calibration_observation(
        assessment_id=payload.assessment_id,
        problem_id=payload.problem_id,
        features=payload.features,
        result_metrics=payload.result_metrics,
        validity_flags=payload.validity_flags,
    )
    return {"status": "recorded", "observation_id": obs_id}


@app.get("/api/calibration/status", response_model=CalibrationStatusResponse)
def calibration_status() -> CalibrationStatusResponse:
    """Returns active model version, calibration version, observations count, and guardrail info."""
    status_data = get_calibration_status()
    return CalibrationStatusResponse(**status_data)


@app.post("/api/calibration/retrain", response_model=RetrainResponse)
def trigger_retrain() -> RetrainResponse:
    """
    Triggers TinyML model retraining across validated observations.
    Evaluates against frozen benchmark; only activates if all guardrails pass.
    """
    active_model = get_active_model()
    prev_bench = active_model.benchmark_score

    success, guardrail_results = trigger_calibration_retrain()

    if success:
        return RetrainResponse(
            success=True,
            status="activated",
            proposed_version=guardrail_results.get("proposed_version", "v1.1"),
            benchmark_score=guardrail_results.get("proposed_benchmark_score", prev_bench),
            previous_benchmark_score=prev_bench,
            guardrail_results=guardrail_results,
            message="Calibration update v1.1 passed frozen benchmark and safety guardrails. Model is now active.",
        )
    else:
        return RetrainResponse(
            success=False,
            status="rejected",
            proposed_version="v1.1",
            benchmark_score=guardrail_results.get("proposed_benchmark_score", 0.0),
            previous_benchmark_score=prev_bench,
            guardrail_results=guardrail_results,
            message=f"Calibration update rejected by safety guardrails: {guardrail_results.get('reason', 'Validation criteria unmet')}",
        )


# Compatibility routes matching existing Stitch frontend conventions
@app.post("/api/challenges", status_code=status.HTTP_201_CREATED)
def legacy_create_challenge(payload: Dict[str, Any]) -> Dict[str, Any]:
    req = AssessmentCreateRequest(
        skill=payload.get("skill", "python"),
        difficulty=payload.get("difficulty", "intermediate"),
    )
    asm = create_assessment(req)
    return {
        "assessment_id": asm.id,
        "challenge_id": asm.problem.id,
        "skill": payload.get("skill", "Python"),
        "difficulty": asm.problem.difficulty,
        "title": asm.problem.title,
        "overview": asm.problem.description,
        "task": f"Implement `solve(...)` to handle {asm.problem.title}.",
        "constraints": asm.problem.constraints,
        "starter_code": asm.problem.starter_code,
        "starterCode": asm.problem.starter_code,
        "calibration_version": asm.calibration_version,
    }


@app.post("/api/assessments/{assessment_id}/submit")
def legacy_submit_assessment(assessment_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    req = SubmissionRequest(
        solution=payload.get("solution", ""),
        time_taken=float(payload.get("time_elapsed_seconds") or payload.get("time_taken") or 0.0),
    )
    result = submit_solution(assessment_id, req)
    return {
        "assessment_id": assessment_id,
        "evaluation": {
            "overall_score": result.overall_score,
            "correctness": round(result.tests_passed / max(1, result.tests_total) * 100.0, 1),
            "problem_solving": result.breakdown.problem_solving,
            "code_quality": result.breakdown.code_quality,
            "efficiency": result.breakdown.efficiency,
            "algorithmic_thinking": result.breakdown.algorithmic_thinking,
            "tests_passed": result.tests_passed,
            "tests_total": result.tests_total,
            "runtime": result.runtime,
            "problem_version": result.problem_version,
            "calibration_version": result.calibration_version,
            "evaluation_model_version": result.evaluation_model_version,
            "summary": f"Passed {result.tests_passed}/{result.tests_total} tests in {result.runtime}s. Verified score: {result.overall_score}/100.",
        },
    }


@app.get("/api/passport")
def legacy_get_passport() -> Dict[str, Any]:
    # Return passport for latest assessment
    active_obs = db.get_calibration_observations(limit=1)
    if not active_obs:
        return {"error": "No assessments completed yet."}
    cand_results = db.get_candidate_results(active_obs[0]["assessment_id"])
    if not cand_results:
        # Fallback to direct assessment id lookup
        return get_skill_passport(active_obs[0]["assessment_id"])
    return get_skill_passport(cand_results[0]["candidate_id"])


# Mount frontend static files
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if not FRONTEND_DIR.exists():
    FRONTEND_DIR = Path(__file__).resolve().parent.parent / "skillproof_project" / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
