"""FastAPI application for SkillProof: One-Shot Python Assessment & Continuous Calibration."""

from __future__ import annotations

import logging
import os
import sqlite3
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
    ProblemPublicView,
    ResultBreakdown,
    ResultResponse,
    RetrainResponse,
    RunRequest,
    RunResponse,
    RunTestResult,
    SkillPassportResponse,
    SubmissionRequest,
    TestRunResult,
)
from services.calibration import (
    get_calibration_status,
    record_validated_observation,
    trigger_calibration_retrain,
    validate_observation_quality_gate,
)
from services.challenge_generator import (
    generate_challenge,
    generate_validated_challenge,
    get_canonical_fallback_problem,
)
from services.evaluator import evaluate_execution_metrics
from services.executor import execute_solution_tests
from services.problem_validator import validate_problem
from services.scoring import compute_scores

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("skillproof.app")

# Initialize database schema
db.init_db()

# Bootstrap active TinyML calibration model
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


# ---------------------------------------------------------------------------
# API Contract (Exact match per PRD & Hardening Specification)
# ---------------------------------------------------------------------------


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    active_model = get_active_model()
    return HealthResponse(
        status="ok",
        service="skillproof-api",
        version="1.0.0",
        provider="local-tinyml",
        active_calibration_version=active_model.version,
        active_model_version=active_model.version,
    )


@app.post("/api/assessment", response_model=AssessmentResponse, status_code=status.HTTP_201_CREATED)
def create_assessment(payload: AssessmentCreateRequest) -> AssessmentResponse:
    """
    Creates a novel one-shot assessment.
    Generates a transformed challenge from local seed corpus, confirms reference solution passes
    100% of tests before serving, or falls back to a verified canonical problem.
    """
    active_model = get_active_model()
    candidate_id = payload.candidate_id or f"cand-{uuid4().hex[:8]}"

    # Generate and validate problem variation (discards and regenerates if invalid)
    valid_problem = generate_validated_challenge(
        skill=payload.skill,
        difficulty=payload.difficulty,
        seed_problem_id=payload.seed_problem_id,
    )

    # Persist problem in SQLite (stores reference_solution and hidden tests securely)
    db.save_problem(valid_problem)

    # Create assessment record
    assessment_id = f"asm-{uuid4().hex[:12]}"
    assessment_record = db.create_assessment(
        assessment_id=assessment_id,
        candidate_id=candidate_id,
        problem_id=valid_problem["id"],
        calibration_version=active_model.version,
    )

    metadata = valid_problem.get("metadata", {
        "seed_problem_id": valid_problem.get("seed_problem_id", ""),
        "transformation_type": valid_problem.get("transformation_type", "domain_adaptation+parameter_scaling"),
        "problem_version": valid_problem.get("version", "1.0"),
    })

    raw_examples = valid_problem.get("examples")
    if not raw_examples and "tests" in valid_problem and len(valid_problem["tests"]) > 0:
        raw_examples = [
            {
                "input": t.get("input"),
                "output": t.get("expected"),
                "explanation": t.get("name", ""),
            }
            for t in valid_problem["tests"][:2]
        ]

    # Public problem view: NEVER contains reference_solution or tests!
    problem_view = ProblemPublicView(
        id=valid_problem["id"],
        seed_problem_id=valid_problem.get("seed_problem_id"),
        transformation_type=valid_problem.get("transformation_type", "domain_adaptation+parameter_scaling"),
        title=valid_problem["title"],
        description=valid_problem["description"],
        difficulty=valid_problem["difficulty"],
        concepts=valid_problem.get("concepts", []),
        algorithm_family=valid_problem.get("algorithm_family", "General"),
        constraints=valid_problem.get("constraints", []),
        starter_code=valid_problem.get("starter_code", ""),
        version=valid_problem.get("version", "1.0"),
        metadata=metadata,
        examples=raw_examples,
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


@app.get("/api/assessment/{id}", response_model=AssessmentResponse)
def get_assessment(id: str) -> AssessmentResponse:
    """Retrieves an existing assessment session and public problem view."""
    assessment = db.get_assessment(id)
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")

    problem = db.get_problem(assessment["problem_id"])
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found.")

    metadata = {
        "seed_problem_id": problem.get("seed_problem_id", problem.get("id")),
        "transformation_type": "domain_adaptation+parameter_scaling",
        "problem_version": problem.get("version", "1.0"),
    }

    raw_examples = problem.get("examples")
    if not raw_examples and "tests" in problem and len(problem["tests"]) > 0:
        raw_examples = [
            {
                "input": t.get("input"),
                "output": t.get("expected"),
                "explanation": t.get("name", ""),
            }
            for t in problem["tests"][:2]
        ]

    # Public problem view: NEVER contains reference_solution or tests!
    problem_view = ProblemPublicView(
        id=problem["id"],
        seed_problem_id=problem.get("seed_problem_id"),
        transformation_type="domain_adaptation+parameter_scaling",
        title=problem["title"],
        description=problem["description"],
        difficulty=problem["difficulty"],
        concepts=problem.get("concepts", []),
        algorithm_family=problem.get("algorithm_family", "General"),
        constraints=problem.get("constraints", []),
        starter_code=problem.get("starter_code", ""),
        version=problem.get("version", "1.0"),
        metadata=metadata,
        examples=raw_examples,
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


@app.post("/api/assessment/{id}/submit", response_model=ResultResponse)
def submit_solution(id: str, payload: SubmissionRequest) -> ResultResponse:
    """
    Submits code for the one-shot assessment.
    Strictly enforces one-shot rule atomically. Rejects second submissions with 409 Conflict.
    Failed code execution produces deterministic scores rather than crashing.
    """
    assessment = db.get_assessment(id)
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")

    # Reject if already marked submitted
    if assessment.get("submitted_at") is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This one-shot assessment has already been submitted. Second submission rejected.",
        )

    # Atomically lock and mark assessment submitted at the database level
    marked = db.mark_assessment_submitted(id)
    if not marked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment submission was already finalized.",
        )

    problem = db.get_problem(assessment["problem_id"])
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem definition missing.")

    # Execute solution in isolated subprocess sandbox
    raw_execution = execute_solution_tests(
        solution_code=payload.solution,
        tests=problem["tests"],
        timeout_seconds=5.0,
    )

    # Evaluate execution metrics + static AST metrics (resilient to syntax/timeout/runtime errors)
    metrics = evaluate_execution_metrics(
        raw_execution=raw_execution,
        solution_code=payload.solution,
        time_taken_seconds=payload.time_taken or 0.0,
    )

    # Compute baseline score using weighted rubric (50/20/15/15)
    score_result = compute_scores(metrics)

    active_model = get_active_model()
    eval_model_version = active_model.version
    calibration_version = assessment["calibration_version"]
    problem_version = problem.get("version", "1.0")

    result_dict = {
        "assessment_id": id,
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

    # Save result immutably (raises sqlite3.IntegrityError if duplicate)
    try:
        db.save_result(result_dict)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Result for this assessment has already been finalized and is immutable.",
        )

    # Feed quality-gated observation to the calibration buffer
    record_validated_observation(
        assessment_id=id,
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
        assessment_id=id,
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
        submission_code=payload.solution,
    )


@app.post("/api/assessment/{id}/run", response_model=RunResponse)
def run_solution_tests(id: str, payload: RunRequest) -> RunResponse:
    """
    Executes candidate's Python code in the sandbox without finalizing submission.
    Returns real test execution metrics (passed count, individual test status, runtime, errors).
    Does NOT mark assessment submitted and does NOT mutate results or calibration pool.
    """
    assessment = db.get_assessment(id)
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")

    if assessment.get("submitted_at") is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment has already been submitted and finalized. Sandbox execution locked.",
        )

    problem = db.get_problem(assessment["problem_id"])
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem definition missing.")

    # Execute candidate code in sandbox
    raw_execution = execute_solution_tests(
        solution_code=payload.solution,
        tests=problem.get("tests", []),
        timeout_seconds=5.0,
    )

    test_run_items = [
        RunTestResult(
            test_index=t.get("test_index", idx),
            name=t.get("name", f"Test #{idx+1}"),
            passed=t.get("passed", False),
            runtime_ms=t.get("runtime_ms", 0.0),
            error=t.get("error"),
        )
        for idx, t in enumerate(raw_execution.get("test_results", []))
    ]

    runtime_ms = round(raw_execution.get("runtime", raw_execution.get("wall_time", 0.0)) * 1000.0, 2)
    memory_mb = round(raw_execution.get("memory_mb", 0.0), 2)

    status_str = "ok"
    if raw_execution.get("error"):
        if "SyntaxError" in raw_execution["error"]:
            status_str = "syntax_error"
        elif "timed out" in raw_execution["error"].lower():
            status_str = "timeout"
        else:
            status_str = "runtime_error"

    return RunResponse(
        status=status_str,
        tests_passed=raw_execution.get("tests_passed", 0),
        tests_total=raw_execution.get("tests_total", len(problem.get("tests", []))),
        runtime_ms=runtime_ms,
        memory_mb=memory_mb,
        test_results=test_run_items,
        error=raw_execution.get("error"),
    )


@app.get("/api/assessment/{id}/result", response_model=ResultResponse)
def get_assessment_result(id: str) -> ResultResponse:
    """Retrieves immutable evaluation result for an assessment."""
    result = db.get_result(id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found.")

    assessment = db.get_assessment(id)
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
        submission_code=result.get("submission_code"),
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

    latest = results[0]
    breakdown = latest["breakdown"]
    overall_score = latest["overall_score"]
    is_verified = overall_score >= 70.0 and latest["tests_passed"] >= (latest["tests_total"] * 0.7)

    return SkillPassportResponse(
        passport_id=f"SP-PASS-{latest['assessment_id'][:8].upper()}",
        candidate_id=latest["candidate_id"],
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


@app.get("/api/history/{candidate_id}")
def get_candidate_history_endpoint(candidate_id: str) -> List[Dict[str, Any]]:
    """Returns assessment history for the given candidate from the database."""
    return db.get_candidate_history(candidate_id)


@app.get("/api/history")
def get_all_history_endpoint() -> List[Dict[str, Any]]:
    """Returns all assessment history records from the database."""
    return db.get_candidate_history("all")


@app.post("/api/calibration/observation", status_code=status.HTTP_201_CREATED)
def store_calibration_observation(payload: CalibrationObservationRequest) -> Dict[str, Any]:
    """Manually ingests an externally validated observation into the learning pool."""
    is_valid, reason, validated_features = validate_observation_quality_gate(
        assessment_id=payload.assessment_id,
        problem_id=payload.problem_id,
        features=payload.features,
        result_metrics=payload.result_metrics,
        validity_flags=payload.validity_flags,
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Observation rejected by quality gate: {reason}",
        )

    asmt = db.get_assessment(payload.assessment_id)
    cand_id = asmt.get("candidate_id", "") if asmt else ""

    obs_id = db.save_calibration_observation(
        assessment_id=payload.assessment_id,
        problem_id=payload.problem_id,
        features=validated_features,
        result_metrics=payload.result_metrics,
        validity_flags=payload.validity_flags,
        candidate_id=cand_id,
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
            message="Calibration update passed frozen benchmark and safety guardrails. Model is now active.",
        )
    else:
        return RetrainResponse(
            success=False,
            status="rejected",
            proposed_version=guardrail_results.get("proposed_version", "v1.1"),
            benchmark_score=guardrail_results.get("proposed_benchmark_score", 0.0),
            previous_benchmark_score=prev_bench,
            guardrail_results=guardrail_results,
            message=f"Calibration update rejected by safety guardrails: {guardrail_results.get('reason', 'Validation criteria unmet')}",
        )


# ---------------------------------------------------------------------------
# Static Frontend Serving
# ---------------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if not FRONTEND_DIR.exists():
    FRONTEND_DIR = Path(__file__).resolve().parent.parent / "skillproof_project" / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
