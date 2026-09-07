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


class ChallengePayload(BaseModel):
    title: str
    overview: str
    task: str
    constraints: list[str]
    starter_code: str
    examples: list[dict[str, str]]


class ChallengeResponse(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "assessment_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                    "challenge_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "skill": "Python",
                    "difficulty": "beginner",
                    "title": "E-Commerce Shopping Cart Calculator",
                    "overview": "Calculate a shopping cart total with category discounts, invalid-quantity filtering, tax, and a store-wide threshold discount.",
                    "task": "Write process_cart(items, category_discounts, store_discount_threshold=100). Return subtotal, total_quantity, discount, tax, and total. Ignore quantities <= 0, apply category discounts, apply a 10% store discount above the threshold, and never return a negative total.",
                    "constraints": [
                        "Ignore items with quantity <= 0.",
                        "Apply category-specific discounts and a 10% store discount above the threshold.",
                        "Do not modify the input list.",
                        "Return monetary values rounded to 2 decimals.",
                    ],
                    "starter_code": "def process_cart(items: list, category_discounts: dict, store_discount_threshold: float = 100) -> dict:\n    # Return the cart totals as a dictionary.\n    pass\n",
                    "examples": [
                        {
                            "input": "items = [{'price': 25, 'quantity': 2, 'category': 'books'}]",
                            "output": "{'subtotal': 50.0, 'total_quantity': 2, 'discount': 0.0, 'tax': 4.0, 'total': 54.0}",
                        }
                    ],
                }
            ]
        }
    }

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


class ExecutionRequest(BaseModel):
    assessment_id: str = Field(min_length=1)
    code: str = Field(min_length=1, max_length=200_000)
    language: Literal["python"] = "python"


class ExecutionTestResult(BaseModel):
    name: str
    passed: bool
    input: str
    expected: str
    actual: str
    error: str | None = None


class ExecutionResponse(BaseModel):
    success: bool
    tests: list[ExecutionTestResult]
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    total: int = Field(ge=0)
    runtime_ms: int = Field(ge=0)


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
    provider: Literal["mock", "gemini", "nvidia", "auto"]


class PassportResponse(BaseModel):
    assessment_id: str
    skill: str
    difficulty: Difficulty
    overall_score: int
    verified: bool
    summary: str
