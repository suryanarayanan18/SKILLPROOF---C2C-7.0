"""FastAPI entry point for the in-memory SkillProof prototype API."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from uuid import uuid4

from fastapi import Body, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles

from normalizers import normalize_evaluation
from schemas import (
    AssessmentResponse,
    ChallengeCreateRequest,
    ChallengePayload,
    ChallengeResponse,
    EvaluationRequest,
    ExecutionRequest,
    ExecutionResponse,
    HealthResponse,
    PassportResponse,
    SolutionSubmitRequest,
)
from services.challenge_generator import generate_challenge
from services.evaluator import evaluate_solution
from services.executor import execute_code

app = FastAPI(title="SkillProof API", version="0.1.0")
logger = logging.getLogger("skillproof.api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _openapi_with_null_challenge_context() -> dict:
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    example = schema["paths"]["/api/challenges"]["post"]["requestBody"]["content"]["application/json"]["examples"]["default"]["value"]
    example["previous_performance"] = None
    example["target_weakness"] = None
    app.openapi_schema = schema
    return schema


app.openapi = _openapi_with_null_challenge_context

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
    if provider not in {"mock", "gemini", "nvidia", "auto"}:
        provider = "mock"
    return HealthResponse(status="ok", service="skillproof-api", provider=provider)


@app.post("/api/challenges", response_model=ChallengeResponse, status_code=status.HTTP_201_CREATED)
def create_challenge(
    payload: ChallengeCreateRequest = Body(
        openapi_examples={
            "default": {
                "summary": "New Python challenge",
                "value": {
                    "skill": "Python",
                    "difficulty": "beginner",
                    "previous_performance": None,
                    "target_weakness": None,
                },
            }
        }
    ),
) -> ChallengeResponse:
    try:
        generated = generate_challenge(
            skill=payload.skill,
            difficulty=payload.difficulty,
            previous_performance=payload.previous_performance,
            target_weakness=payload.target_weakness,
        )
    except Exception as error:
        logger.exception("Challenge generation failed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Challenge provider is unavailable. No demo fallback is allowed for the configured provider.",
        ) from error

    assessment_id = str(uuid4())
    challenge = ChallengeResponse(
        assessment_id=assessment_id,
        challenge_id=str(uuid4()),
        skill=payload.skill,
        difficulty=payload.difficulty,
        **ChallengePayload.model_validate(generated).model_dump(),
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
            difficulty=assessment.difficulty,
        )
    except Exception as error:
        logger.exception("Evaluation provider failed.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI evaluation failed. Please retry or fix the provider configuration.",
        ) from error

    assessment.evaluation = normalize_evaluation(generated)
    assessment.submitted_solution = payload.solution
    assessment.time_elapsed_seconds = payload.time_elapsed_seconds
    return assessment


@app.post("/api/execute", response_model=ExecutionResponse)
def execute_assessment(payload: ExecutionRequest) -> ExecutionResponse:
    assessment = ASSESSMENTS.get(payload.assessment_id)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")
    if payload.language != "python":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only Python execution is supported in this prototype.")

    try:
        return execute_code(
            assessment_id=payload.assessment_id,
            challenge=assessment,
            code=payload.code,
            language=payload.language,
        )
    except Exception as error:
        logger.exception("Sandbox execution failed.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Execution failed: {error}") from error


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
