"""FastAPI entry point for the in-memory SkillProof prototype API."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from normalizers import normalize_challenge, normalize_evaluation
from schemas import (
    AssessmentResponse,
    ChallengeCreateRequest,
    ChallengeResponse,
    EvaluationRequest,
    HealthResponse,
    PassportResponse,
    SolutionSubmitRequest,
)
from services.challenge_generator import generate_challenge
from services.demo_provider import generate_challenge as generate_demo_challenge
from services.demo_provider import evaluate_solution as evaluate_demo_solution
from services.evaluator import evaluate_solution

app = FastAPI(title="SkillProof API", version="0.1.0")
logger = logging.getLogger("skillproof.api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Deliberately process-local for the prototype. Restarting the server clears it.
ASSESSMENTS: dict[str, AssessmentResponse] = {}


def _gemini_error(error: Exception) -> HTTPException:
    # Log the complete exception for operators, but never reveal provider
    # internals or credentials to browser clients.
    logger.exception("Gemini request failed: %s", type(error).__name__, exc_info=error)
    message = str(error)
    if "GEMINI_API_KEY" in message:
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Gemini API key is not configured.")
    if any(marker in message.upper() for marker in ("429", "RESOURCE_EXHAUSTED", "QUOTA", "RATE LIMIT")):
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Gemini API limit reached. Please try again later.")
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Gemini request failed. Please try again.")


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    provider = os.getenv("SKILLPROOF_PROVIDER", "mock").strip().lower()
    return HealthResponse(status="ok", service="skillproof-api", provider="gemini" if provider == "gemini" else "mock")


@app.post("/api/challenges", response_model=ChallengeResponse, status_code=status.HTTP_201_CREATED)
def create_challenge(payload: ChallengeCreateRequest) -> ChallengeResponse:
    try:
        generated = generate_challenge(
            skill=payload.skill,
            difficulty=payload.difficulty,
            previous_performance=payload.previous_performance,
            target_weakness=payload.target_weakness,
        )
    except Exception as error:
        logger.exception("Challenge provider failed; using deterministic demo challenge.")
        generated = generate_demo_challenge(
            skill=payload.skill,
            difficulty=payload.difficulty,
        )

    assessment_id = str(uuid4())
    challenge = normalize_challenge(
        generated,
        assessment_id=assessment_id,
        challenge_id=f"challenge-{uuid4()}",
        skill=payload.skill,
        difficulty=payload.difficulty,
    )
    ASSESSMENTS[assessment_id] = AssessmentResponse(**challenge.model_dump())
    return challenge


@app.post("/api/assessments/{assessment_id}/submit", response_model=AssessmentResponse)
def submit_solution(assessment_id: str, payload: SolutionSubmitRequest) -> AssessmentResponse:
    assessment = ASSESSMENTS.get(assessment_id)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")
    try:
        generated = evaluate_solution(
            challenge=f"{assessment.overview}\n\nTask:\n{assessment.task}\n\nConstraints:\n" + "\n".join(assessment.constraints),
            solution=payload.solution,
            skill=assessment.skill,
        )
    except Exception as error:
        if os.getenv("SKILLPROOF_PROVIDER", "mock").strip().lower() in {"mock", "demo"}:
            logger.exception("Evaluation provider failed in demo mode; using deterministic demo evaluation.")
            generated = evaluate_demo_solution(
                challenge=f"{assessment.overview}\n\nTask:\n{assessment.task}\n\nConstraints:\n" + "\n".join(assessment.constraints),
                solution=payload.solution,
                skill=assessment.skill,
            )
        else:
            raise _gemini_error(error) from error

    assessment.evaluation = normalize_evaluation(generated)
    assessment.submitted_solution = payload.solution
    assessment.time_elapsed_seconds = payload.time_elapsed_seconds
    return assessment


@app.post("/api/evaluate", response_model=AssessmentResponse)
def evaluate_assessment(payload: EvaluationRequest) -> AssessmentResponse:
    """Compatibility endpoint for clients that submit by assessment_id."""
    return submit_solution(
        payload.assessment_id,
        SolutionSubmitRequest(
            solution=payload.solution,
            time_elapsed_seconds=payload.time_elapsed_seconds,
        ),
    )


@app.get("/api/assessments/{assessment_id}", response_model=AssessmentResponse)
def get_assessment(assessment_id: str) -> AssessmentResponse:
    assessment = ASSESSMENTS.get(assessment_id)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")
    return assessment


@app.get("/api/passport", response_model=PassportResponse)
def get_passport() -> PassportResponse:
    completed = [assessment for assessment in ASSESSMENTS.values() if assessment.evaluation]
    if not completed:
        if os.getenv("SKILLPROOF_PROVIDER", "mock").strip().lower() in {"mock", "demo"}:
            return PassportResponse(
                assessment_id="demo-passport",
                skill="Python",
                difficulty="beginner",
                overall_score=0,
                verified=False,
                summary="Complete a demo assessment to create your first SkillProof passport.",
            )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No completed assessment is available for a passport.")
    assessment = completed[-1]
    assert assessment.evaluation is not None
    return PassportResponse(
        assessment_id=assessment.assessment_id,
        skill=assessment.skill,
        difficulty=assessment.difficulty,
        overall_score=assessment.evaluation.overall_score,
        verified=assessment.evaluation.overall_score >= 75,
        summary=assessment.evaluation.summary,
    )


# Mount last: API routes above retain precedence while the existing static
# prototype can be served from the same localhost origin on port 3000.
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "skillproof_project" / "frontend"
if FRONTEND_DIR.is_dir():
    from fastapi.responses import FileResponse

    FRONTEND_ENTRY = FRONTEND_DIR / "index.html"

    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    def frontend_index() -> FileResponse:
        return FileResponse(FRONTEND_ENTRY)

    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
