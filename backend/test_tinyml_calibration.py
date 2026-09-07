"""
test_tinyml_calibration.py
Comprehensive verification of the TinyML calibration learning loop.

Verifies:
1. Benchmark.json is permanently frozen (assert SHA256 checksum remains identical).
2. Quality gate rejects:
   - incomplete submissions (0 tests, empty code)
   - failed execution due to infrastructure error (sandbox crash)
   - missing/non-finite required features
   - duplicate assessment submissions
   - invalid assessment / problem references
3. Anti-domination capping: single candidate cannot flood buffer (capped at <= 2 observations).
4. Insufficient observations (< 3 valid observations after capping) do not publish.
5. Degraded candidate model (drift > 15.0 or score drop > 2.0 or score < 75.0) is rejected, keeping previous model active.
6. Safe model publishes with sequential versioning (v1.0 -> v1.1) and full metadata saved.
7. Past assessment results retain their original stamped model version (historical immutability).
8. Future assessments adopt and evaluate using the newly active model version.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
import numpy as np

import db
from ml.model import SkillCalibrationModel, get_active_model, set_active_model, VERSIONS_DIR
from ml.train import (
    BENCHMARK_PATH,
    MIN_OBSERVATIONS_FOR_RETRAIN,
    MAX_OBSERVATIONS_PER_CANDIDATE,
    load_frozen_benchmark,
    train_and_validate_new_version,
)
from services.calibration import (
    get_calibration_status,
    record_validated_observation,
    trigger_calibration_retrain,
    validate_observation_quality_gate,
)
from services.challenge_generator import generate_validated_challenge


def get_benchmark_sha256() -> str:
    return hashlib.sha256(BENCHMARK_PATH.read_bytes()).hexdigest()


ORIGINAL_BENCHMARK_SHA256 = get_benchmark_sha256()


def setup_isolated_db():
    """Isolates SQLite DB and model versions for each test."""
    temp_dir = tempfile.mkdtemp()
    db_file = Path(temp_dir) / "test_calibration.sqlite3"
    db.DB_PATH = db_file
    db.init_db()

    # Reset in-memory active model
    set_active_model(None)

    # Initialize v1.0 in DB
    from ml.train import bootstrap_v1_model
    model_v1 = bootstrap_v1_model()
    set_active_model(model_v1)
    assert get_benchmark_sha256() == ORIGINAL_BENCHMARK_SHA256, "Frozen benchmark.json was altered!"


def create_test_assessment(candidate_id: str = "cand_test_1") -> tuple[str, str]:
    """Helper to seed a valid problem and assessment in the database."""
    import uuid
    problem = generate_validated_challenge("seed_two_sum")
    assert problem is not None
    db.save_problem(problem)
    active_m = get_active_model()
    asmt_id = f"asmt_{uuid.uuid4().hex[:8]}"
    asmt = db.create_assessment(
        assessment_id=asmt_id,
        candidate_id=candidate_id,
        problem_id=problem["id"],
        calibration_version=active_m.version,
    )
    return asmt["id"], problem["id"]


def test_frozen_benchmark_permanently_immutable():
    """Verify benchmark.json can be loaded and its SHA256 checksum remains 100% frozen."""
    setup_isolated_db()
    initial_hash = get_benchmark_sha256()
    X_bench, y_bench = load_frozen_benchmark()
    assert len(X_bench) > 0
    assert len(y_bench) == len(X_bench)
    assert get_benchmark_sha256() == initial_hash


def test_quality_gate_rejects_invalid_references():
    """Quality gate must reject observations with invalid assessment_id or problem_id."""
    setup_isolated_db()
    asmt_id, prob_id = create_test_assessment()

    # Non-existent assessment
    valid, reason, _ = validate_observation_quality_gate(
        assessment_id="non_existent_asmt",
        problem_id=prob_id,
        features={"tests_passed_ratio": 1.0, "runtime_ms": 10.0, "lines_of_code": 10, "ast_nodes": 40, "cyclomatic_complexity": 2, "attempt_duration_sec": 60.0, "has_type_annotations": 1.0, "has_docstring": 1.0},
        result_metrics={"overall_score": 90.0, "tests_passed": 5, "tests_total": 5},
    )
    assert not valid
    assert "does not exist" in reason

    # Non-existent problem
    valid, reason, _ = validate_observation_quality_gate(
        assessment_id=asmt_id,
        problem_id="non_existent_problem",
        features={"tests_passed_ratio": 1.0, "runtime_ms": 10.0, "lines_of_code": 10, "ast_nodes": 40, "cyclomatic_complexity": 2, "attempt_duration_sec": 60.0, "has_type_annotations": 1.0, "has_docstring": 1.0},
        result_metrics={"overall_score": 90.0, "tests_passed": 5, "tests_total": 5},
    )
    assert not valid
    assert "does not exist" in reason


def test_quality_gate_rejects_duplicate_observations():
    """Quality gate must reject duplicate observations for the same assessment."""
    setup_isolated_db()
    asmt_id, prob_id = create_test_assessment()

    # First observation should record successfully
    result_data = {
        "tests_passed": 5,
        "tests_total": 5,
        "runtime": 0.012,
        "submission_code": "def solution(arr, t): return [0, 1]",
        "overall_score": 95.0,
        "code_metrics": {"lines_of_code": 10, "ast_nodes": 40, "cyclomatic_complexity": 2, "has_type_annotations": False, "has_docstring": True},
    }
    obs_id = record_validated_observation(
        assessment_id=asmt_id,
        problem_id=prob_id,
        result_data=result_data,
        time_taken=45.0,
    )
    assert obs_id is not None

    # Second observation on the same assessment_id must be rejected
    valid, reason, _ = validate_observation_quality_gate(
        assessment_id=asmt_id,
        problem_id=prob_id,
        result_data=result_data,
        time_taken=45.0,
    )
    assert not valid
    assert "Duplicate observation" in reason


def test_quality_gate_rejects_incomplete_submissions():
    """Quality gate must reject observations with 0 tests or empty code."""
    setup_isolated_db()
    asmt_id, prob_id = create_test_assessment()

    # Empty submission code
    valid, reason, _ = validate_observation_quality_gate(
        assessment_id=asmt_id,
        problem_id=prob_id,
        result_data={
            "tests_passed": 0,
            "tests_total": 5,
            "submission_code": "   \n  ",
            "overall_score": 0.0,
        },
    )
    assert not valid
    assert "Incomplete submission" in reason

    # 0 tests total
    valid, reason, _ = validate_observation_quality_gate(
        assessment_id=asmt_id,
        problem_id=prob_id,
        result_data={
            "tests_passed": 0,
            "tests_total": 0,
            "submission_code": "def f(): pass",
            "overall_score": 0.0,
        },
    )
    assert not valid
    assert "Incomplete submission" in reason


def test_quality_gate_rejects_infrastructure_errors():
    """Quality gate must reject observations resulting from infrastructure/sandbox crashes."""
    setup_isolated_db()
    asmt_id, prob_id = create_test_assessment()

    valid, reason, _ = validate_observation_quality_gate(
        assessment_id=asmt_id,
        problem_id=prob_id,
        result_data={
            "tests_passed": 0,
            "tests_total": 5,
            "submission_code": "def f(): pass",
            "error": "Sandbox execution error: process killed by OS",
        },
    )
    assert not valid
    assert "infrastructure error" in reason.lower()

    # Exit code -1 (non-timeout)
    valid, reason, _ = validate_observation_quality_gate(
        assessment_id=asmt_id,
        problem_id=prob_id,
        result_data={
            "tests_passed": 0,
            "tests_total": 5,
            "submission_code": "def f(): pass",
            "raw_execution": {"exit_code": -1, "timeout": False},
        },
    )
    assert not valid
    assert "infrastructure" in reason.lower()


def test_quality_gate_rejects_missing_or_invalid_features():
    """Quality gate must reject observations missing required features or containing NaN/Inf."""
    setup_isolated_db()
    asmt_id, prob_id = create_test_assessment()

    # Missing feature 'cyclomatic_complexity'
    incomplete_features = {
        "tests_passed_ratio": 1.0,
        "runtime_ms": 10.0,
        "lines_of_code": 10,
        "ast_nodes": 40,
        "attempt_duration_sec": 60.0,
        "has_type_annotations": 0.0,
        "has_docstring": 1.0,
    }
    valid, reason, _ = validate_observation_quality_gate(
        assessment_id=asmt_id,
        problem_id=prob_id,
        features=incomplete_features,
        result_metrics={"tests_total": 5, "overall_score": 80.0},
    )
    assert not valid
    assert "Missing required feature" in reason

    # NaN in feature value
    nan_features = copy.deepcopy(incomplete_features)
    nan_features["cyclomatic_complexity"] = float("nan")
    valid, reason, _ = validate_observation_quality_gate(
        assessment_id=asmt_id,
        problem_id=prob_id,
        features=nan_features,
        result_metrics={"tests_total": 5, "overall_score": 80.0},
    )
    assert not valid
    assert "non-finite" in reason


def test_anti_domination_capping_and_insufficient_observations():
    """
    Verify anti-domination capping (<= 2 observations per candidate)
    and that fewer than 3 valid observations after capping reject retrain.
    """
    setup_isolated_db()
    # Create 5 assessments for candidate_spammer
    for i in range(5):
        asmt_id, prob_id = create_test_assessment(candidate_id="cand_spammer")
        record_validated_observation(
            assessment_id=asmt_id,
            problem_id=prob_id,
            result_data={
                "tests_passed": 5,
                "tests_total": 5,
                "runtime": 0.01,
                "submission_code": f"def solution_{i}(): pass",
                "overall_score": 85.0,
                "code_metrics": {"lines_of_code": 12, "ast_nodes": 45, "cyclomatic_complexity": 2, "has_type_annotations": True, "has_docstring": True},
            },
            time_taken=60.0,
        )

    status = get_calibration_status()
    assert status["observation_count"] == 5

    # Retrain attempt: Candidate spammer has 5 observations, but anti-domination caps at 2.
    # Because 2 < 3 (MIN_OBSERVATIONS_FOR_RETRAIN), retrain must reject!
    success, guardrail_results = trigger_calibration_retrain()
    assert not success
    assert guardrail_results["published"] is False
    assert guardrail_results["valid_observation_count"] == 2
    assert "Insufficient observations" in guardrail_results["reason"]

    # Active model must remain unchanged (v1.0)
    assert get_active_model().version == "v1.0"


def test_safe_model_publishing_and_metadata():
    """
    With >= 3 valid observations from distinct candidates, a safe model publishes
    as v1.1 with complete metadata and active status.
    """
    setup_isolated_db()
    # Seed 3 distinct candidates
    for i, cid in enumerate(["cand_alpha", "cand_beta", "cand_gamma"]):
        asmt_id, prob_id = create_test_assessment(candidate_id=cid)
        record_validated_observation(
            assessment_id=asmt_id,
            problem_id=prob_id,
            result_data={
                "tests_passed": 4 + (i % 2),
                "tests_total": 5,
                "runtime": 0.015,
                "submission_code": f"def valid_solution_{cid}(): return True",
                "overall_score": 82.0 + i * 3.0,
                "code_metrics": {"lines_of_code": 15, "ast_nodes": 50, "cyclomatic_complexity": 2, "has_type_annotations": True, "has_docstring": True},
            },
            time_taken=120.0,
        )

    # Retrain
    success, guardrail_results = trigger_calibration_retrain()
    assert success is True
    assert guardrail_results["published"] is True
    assert guardrail_results["proposed_version"] == "v1.1"

    # Verify active model is now v1.1
    active = get_active_model()
    assert active.version == "v1.1"
    assert active.benchmark_score >= 75.0
    assert active.metadata["previous_model_version"] == "v1.0"
    assert active.metadata["training_observation_count"] >= 3
    assert "median_drift" in active.metadata["validation_metrics"]
    assert "median_ae" in active.metadata["validation_metrics"]

    # Verify status reflects active v1.1
    status = get_calibration_status()
    assert status["active_model_version"] == "v1.1"


def test_degraded_model_is_rejected():
    """
    If observations would cause median prediction drift > 15.0 or benchmark score < 75.0,
    the model update is rejected and active model remains unchanged.
    """
    setup_isolated_db()
    active_before = get_active_model()
    prev_ver = active_before.version

    # Synthesize conflicting observations designed to distort predictions and drop benchmark score
    outlier_observations = []
    for i in range(25):
        outlier_observations.append({
            "assessment_id": f"asmt_outlier_{i}",
            "candidate_id": f"cand_outlier_{i}",
            "problem_id": "seed_two_sum",
            "features": {
                "tests_passed_ratio": 1.0,
                "runtime_ms": 5.0,
                "lines_of_code": 20,
                "ast_nodes": 80,
                "cyclomatic_complexity": 3,
                "attempt_duration_sec": 200.0,
                "has_type_annotations": 1.0,
                "has_docstring": 1.0,
            },
            "result_metrics": {
                "overall_score": 0.0,  # Extreme conflict: 100% pass but 0 overall score
                "tests_passed": 5,
                "tests_total": 5,
            },
            "validity_flags": {"completed_submission": True, "quality_gate_passed": True},
        })

    success, model, results = train_and_validate_new_version(
        proposed_version="v1.2",
        observations=outlier_observations,
        current_active_model=active_before,
    )

    # Must be rejected due to drift or benchmark score degradation
    assert success is False
    assert results["published"] is False
    assert "exceeds safety cap" in results.get("reason", "") or "degraded" in results.get("reason", "") or "below minimum" in results.get("reason", "")
    assert get_active_model().version == prev_ver


def test_historical_immutability_and_future_assessment_adoption():
    """
    Verify past assessment results permanently retain their stamped model version (v1.0),
    while new assessments created after retrain adopt and evaluate using v1.1.
    """
    setup_isolated_db()
    # 1. Candidate 1 takes assessment on v1.0
    asmt_id_1, prob_id_1 = create_test_assessment(candidate_id="historical_cand")
    asmt_record_1 = db.get_assessment(asmt_id_1)
    assert asmt_record_1["calibration_version"] == "v1.0"

    # Save historical result on v1.0
    historical_result = {
        "assessment_id": asmt_id_1,
        "tests_passed": 5,
        "tests_total": 5,
        "runtime": 0.01,
        "memory": 12.5,
        "time_taken": 60.0,
        "code_metrics": {"lines_of_code": 10, "ast_nodes": 40, "cyclomatic_complexity": 2, "has_type_annotations": True, "has_docstring": True, "clean_naming": True},
        "overall_score": 92.0,
        "problem_version": "1.0",
        "calibration_version": "v1.0",
        "evaluation_model_version": "v1.0",
        "breakdown": {"problem_solving": 90.0, "algorithmic_thinking": 92.0, "efficiency": 95.0, "code_quality": 90.0},
        "submission_code": "def solution(): pass",
    }
    db.save_result(historical_result)

    # 2. Add 3 valid observations and retrain platform to v1.1
    for i, cid in enumerate(["cand_retrain_1", "cand_retrain_2", "cand_retrain_3"]):
        asmt_id, prob_id = create_test_assessment(candidate_id=cid)
        record_validated_observation(
            assessment_id=asmt_id,
            problem_id=prob_id,
            result_data={
                "tests_passed": 4 + (i % 2),
                "tests_total": 5,
                "runtime": 0.015,
                "submission_code": f"def s_{i}(): pass",
                "overall_score": 82.0 + i * 3.0,
                "code_metrics": {"lines_of_code": 15, "ast_nodes": 50, "cyclomatic_complexity": 2, "has_type_annotations": True, "has_docstring": True},
            },
            time_taken=120.0,
        )

    success, _ = trigger_calibration_retrain()
    assert success is True
    assert get_active_model().version == "v1.1"

    # 3. Verify HISTORICAL result is 100% UNCHANGED and still has v1.0
    res_after = db.get_result(asmt_id_1)
    assert res_after["calibration_version"] == "v1.0"
    assert res_after["evaluation_model_version"] == "v1.0"

    # 4. Create a FUTURE assessment -> Must adopt newly active model version v1.1
    asmt_id_2, prob_id_2 = create_test_assessment(candidate_id="future_cand")
    asmt_record_2 = db.get_assessment(asmt_id_2)
    assert asmt_record_2["calibration_version"] == "v1.1"


if __name__ == "__main__":
    import inspect
    import sys

    print("Running test_tinyml_calibration.py suite...")
    current_module = sys.modules[__name__]
    test_funcs = [
        obj for name, obj in inspect.getmembers(current_module)
        if inspect.isfunction(obj) and name.startswith("test_")
    ]

    passed = 0
    failed = 0
    for fn in test_funcs:
        print(f"-> Running {fn.__name__}...", end=" ", flush=True)
        try:
            fn()
            print("PASSED")
            passed += 1
        except Exception as e:
            print(f"FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\nSummary: {passed} passed, {failed} failed out of {len(test_funcs)} tests.")
    if failed > 0:
        sys.exit(1)
