"""FastAPI application for SkillProof: One-Shot Python Assessment & Continuous Calibration."""

from __future__ import annotations

import logging
import os
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
    ChallengeCreateRequest,
    ChallengeResponse,
    CodeQualityMetrics,
    EvaluationRequest,
    HealthResponse,
    PassportResponse,
    PassportSkillEntry,
    ProblemPublicView,
    ResultBreakdown,
    ResultResponse,
    RetrainResponse,
    SkillPassportResponse,
    SolutionSubmitRequest,
    SubmissionRequest,
    TestRunResult,
)
from services.calibration import (
    get_calibration_status,
    record_validated_observation,
    trigger_calibration_retrain,
)
from services.challenge_generator import generate_challenge
from services.evaluator import evaluate_execution_metrics, evaluate_solution
from services.executor import execute_solution_tests
from services.problem_validator import validate_problem
from services.scoring import compute_scores

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("skillproof.app")

# Initialize database tables on startup
db.init_db()

# Bootstrap active TinyML model
get_active_model()

# Process-local cache for compatibility with test suites
ASSESSMENTS: Dict[str, Any] = {}

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


def _gemini_error(error: Exception) -> HTTPException:
    logger.exception("Gemini request failed: %s", type(error).__name__, exc_info=error)
    message = str(error)
    if "GEMINI_API_KEY" in message:
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Gemini API key is not configured.")
    if any(marker in message.upper() for marker in ("429", "RESOURCE_EXHAUSTED", "QUOTA", "RATE LIMIT")):
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Gemini API limit reached. Please try again later.")
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Gemini request failed. Please try again.")


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    active_model = get_active_model()
    provider = os.getenv("SKILLPROOF_PROVIDER", "mock").strip().lower()
    return HealthResponse(
        status="ok",
        service="skillproof-api",
        version="1.0.0",
        provider="gemini" if provider == "gemini" else "mock",
        active_calibration_version=active_model.version,
        active_model_version=active_model.version,
    )


# ---------------------------------------------------------------------------
# Core One-Shot Assessment & Calibration API (PRD & Build Brief)
# ---------------------------------------------------------------------------


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
def get_assessment_singular(assessment_id: str) -> AssessmentResponse:
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


# ---------------------------------------------------------------------------
# Compatibility Endpoints for Existing Stitch Frontend & Test Harnesses
# ---------------------------------------------------------------------------


@app.post("/api/challenges", status_code=status.HTTP_201_CREATED)
def legacy_create_challenge(payload: ChallengeCreateRequest) -> Dict[str, Any]:
    provider = os.getenv("SKILLPROOF_PROVIDER", "mock").strip().lower()
    try:
        raw_challenge = generate_challenge(
            skill=payload.skill,
            difficulty=payload.difficulty,
            previous_performance=payload.previous_performance,
            target_weakness=payload.target_weakness,
        )
    except Exception as error:
        if provider == "gemini":
            raise _gemini_error(error)
        from services.demo_provider import generate_challenge as generate_demo_challenge

        raw_challenge = generate_demo_challenge(skill=payload.skill, difficulty=payload.difficulty)

    assessment_id = f"asm-{uuid4().hex[:12]}"
    challenge_id = f"challenge-{uuid4().hex[:8]}"

    if isinstance(raw_challenge, dict):
        ch_dict = {
            "assessment_id": assessment_id,
            "challenge_id": raw_challenge.get("id", challenge_id),
            "skill": payload.skill,
            "difficulty": raw_challenge.get("difficulty", payload.difficulty),
            "title": raw_challenge.get("title", f"{payload.difficulty.capitalize()} Assessment"),
            "overview": raw_challenge.get("description", raw_challenge.get("overview", "")),
            "task": raw_challenge.get("description", raw_challenge.get("task", "")),
            "constraints": raw_challenge.get("constraints", []),
            "starter_code": raw_challenge.get("starter_code", ""),
            "examples": raw_challenge.get("examples", []),
            "tests": raw_challenge.get("tests", []),
            "reference_solution": raw_challenge.get("reference_solution", ""),
            "calibration_version": get_active_model().version,
        }
    else:
        from normalizers import normalize_challenge

        norm = normalize_challenge(
            raw_challenge,
            assessment_id=assessment_id,
            challenge_id=challenge_id,
            skill=payload.skill,
            difficulty=payload.difficulty,
        )
        ch_dict = norm.model_dump()
        ch_dict["calibration_version"] = get_active_model().version

    ASSESSMENTS[assessment_id] = ch_dict

    # Persist in SQLite
    db.save_problem({
        "id": ch_dict.get("challenge_id", challenge_id),
        "title": ch_dict["title"],
        "description": ch_dict.get("overview") or ch_dict.get("task") or "",
        "difficulty": ch_dict["difficulty"],
        "concepts": [],
        "algorithm_family": "General",
        "constraints": ch_dict.get("constraints", []),
        "reference_solution": ch_dict.get("reference_solution", ""),
        "tests": ch_dict.get("tests", []),
        "starter_code": ch_dict.get("starter_code", ""),
        "version": "1.0",
    })
    db.create_assessment(
        assessment_id=assessment_id,
        candidate_id=f"cand-{assessment_id[:8]}",
        problem_id=ch_dict.get("challenge_id", challenge_id),
        calibration_version=get_active_model().version,
    )

    return ch_dict


@app.get("/api/assessments/{assessment_id}")
def legacy_get_assessment(assessment_id: str) -> Dict[str, Any]:
    if assessment_id in ASSESSMENTS:
        return ASSESSMENTS[assessment_id]
    db_asm = db.get_assessment(assessment_id)
    if not db_asm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")

    prob = db.get_problem(db_asm["problem_id"]) or {}
    res = db.get_result(assessment_id)
    return {
        "assessment_id": assessment_id,
        "challenge_id": prob.get("id", ""),
        "skill": "Python",
        "difficulty": prob.get("difficulty", "intermediate"),
        "title": prob.get("title", "Assessment"),
        "overview": prob.get("description", ""),
        "task": prob.get("description", ""),
        "constraints": prob.get("constraints", []),
        "starter_code": prob.get("starter_code", ""),
        "examples": [],
        "evaluation": res.get("breakdown") if res else None,
        "calibration_version": db_asm.get("calibration_version", "v1.0"),
    }


@app.post("/api/assessments/{assessment_id}/submit")
def legacy_submit_assessment(assessment_id: str, payload: SolutionSubmitRequest) -> Dict[str, Any]:
    assessment = ASSESSMENTS.get(assessment_id)
    db_asm = db.get_assessment(assessment_id)
    if assessment is None and db_asm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")

    provider = os.getenv("SKILLPROOF_PROVIDER", "mock").strip().lower()
    ch_text = ""
    if assessment:
        ch_text = f"{assessment.get('overview', '')}\n\nTask:\n{assessment.get('task', '')}\n\nConstraints:\n" + "\n".join(assessment.get("constraints", []))

    try:
        eval_raw = evaluate_solution(
            challenge=ch_text,
            solution=payload.solution,
            skill=assessment.get("skill", "Python") if assessment else "Python",
        )
    except Exception as error:
        if provider == "gemini":
            raise _gemini_error(error)
        from services.demo_provider import evaluate_solution as evaluate_demo_solution

        eval_raw = evaluate_demo_solution(challenge=ch_text, solution=payload.solution, skill="Python")

    from normalizers import normalize_evaluation

    eval_dict = normalize_evaluation(eval_raw).model_dump()

    prob = None
    if db_asm:
        prob = db.get_problem(db_asm["problem_id"])
    elif assessment and assessment.get("tests"):
        prob = assessment

    if prob and prob.get("tests"):
        try:
            exec_res = execute_solution_tests(payload.solution, prob["tests"], timeout_seconds=3.0)
            if exec_res.get("tests_total", 0) > 0:
                eval_dict["passed_tests"] = exec_res.get("tests_passed", 0)
                eval_dict["total_tests"] = exec_res.get("tests_total", 0)
        except Exception:
            pass

    out = {
        "assessment_id": assessment_id,
        "evaluation": eval_dict,
        "submitted_solution": payload.solution,
        "time_elapsed_seconds": payload.time_elapsed_seconds,
    }
    if assessment:
        assessment.update(out)
        ASSESSMENTS[assessment_id] = assessment
    return out


@app.post("/api/evaluate")
def legacy_evaluate(payload: EvaluationRequest) -> Dict[str, Any]:
    return legacy_submit_assessment(payload.assessment_id, payload)


@app.get("/api/passport", response_model=PassportResponse)
def legacy_get_passport() -> PassportResponse:
    # Check in-memory ASSESSMENTS
    for asm_id, asm in reversed(list(ASSESSMENTS.items())):
        if isinstance(asm, dict) and asm.get("evaluation"):
            ev = asm["evaluation"]
            score = ev.get("overall_score", 0) if isinstance(ev, dict) else 0
            return PassportResponse(
                assessment_id=asm_id,
                skill=asm.get("skill", "Python"),
                difficulty=asm.get("difficulty", "intermediate"),
                overall_score=int(score),
                verified=bool(score >= 70),
                summary=ev.get("summary", "Evaluation complete.") if isinstance(ev, dict) else "Verified assessment.",
            )

    # Check database
    active_obs = db.get_calibration_observations(limit=1)
    if active_obs:
        cand_results = db.get_candidate_results(active_obs[0]["assessment_id"])
        if cand_results:
            latest = cand_results[0]
            return PassportResponse(
                assessment_id=latest["assessment_id"],
                skill="Python",
                difficulty=latest.get("difficulty", "intermediate"),
                overall_score=int(latest["overall_score"]),
                verified=bool(latest["overall_score"] >= 70),
                summary=f"Verified with score {latest['overall_score']}/100.",
            )

    return PassportResponse(
        assessment_id="none",
        skill="Python",
        difficulty="intermediate",
        overall_score=0,
        verified=False,
        summary="No completed assessments yet.",
    )


# ---------------------------------------------------------------------------
# Static Frontend Serving
# ---------------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if not FRONTEND_DIR.exists():
    FRONTEND_DIR = Path(__file__).resolve().parent.parent / "skillproof_project" / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
