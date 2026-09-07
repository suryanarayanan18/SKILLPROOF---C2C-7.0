"""Calibration service for observation management and continuous improvement loop."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import db
from ml.features import extract_feature_vector
from ml.model import get_active_model
from ml.train import train_and_validate_new_version

logger = logging.getLogger("skillproof.calibration")

ACTIVE_CALIBRATION_VERSION = "v1.0"


def record_validated_observation(
    assessment_id: str,
    problem_id: str,
    result_data: Dict[str, Any],
    time_taken: float,
) -> Optional[int]:
    """
    Quality-gates a candidate submission and records it as an anonymized
    calibration observation for the platform's TinyML learning loop.
    """
    # Quality Gate (Section 10 & 11)
    tests_total = result_data.get("tests_total", 0)
    has_submission = bool(result_data.get("submission_code", "").strip())
    # Require candidate to complete a valid assessment attempt
    completed_submission = has_submission and tests_total > 0

    validity_flags = {
        "completed_submission": completed_submission,
        "non_trivial_runtime": result_data.get("runtime", 0.0) >= 0.0,
        "sufficient_duration": time_taken >= 1.0,
    }

    if not all(validity_flags.values()):
        logger.info("Assessment %s failed calibration quality gate: %s", assessment_id, validity_flags)
        return None

    features = {
        "tests_passed_ratio": result_data.get("tests_passed", 0) / max(1, tests_total),
        "runtime_ms": result_data.get("runtime", 0.0) * 1000.0,
        "lines_of_code": result_data.get("code_metrics", {}).get("lines_of_code", 10),
        "ast_nodes": result_data.get("code_metrics", {}).get("ast_nodes", 40),
        "cyclomatic_complexity": result_data.get("code_metrics", {}).get("cyclomatic_complexity", 1),
        "attempt_duration_sec": time_taken,
        "has_type_annotations": 1 if result_data.get("code_metrics", {}).get("has_type_annotations") else 0,
        "has_docstring": 1 if result_data.get("code_metrics", {}).get("has_docstring") else 0,
    }

    obs_id = db.save_calibration_observation(
        assessment_id=assessment_id,
        problem_id=problem_id,
        features=features,
        result_metrics={
            "overall_score": result_data.get("overall_score", 0.0),
            "tests_passed": result_data.get("tests_passed", 0),
            "tests_total": tests_total,
        },
        validity_flags=validity_flags,
    )
    return obs_id


def get_calibration_status() -> Dict[str, Any]:
    """Retrieves active calibration version, benchmark status, and audit parameters."""
    active_model = get_active_model()
    observations = db.get_calibration_observations()
    all_versions = db.get_all_model_versions()

    return {
        "active_model_version": active_model.version,
        "calibration_version": active_model.version,
        "benchmark_score": active_model.benchmark_score,
        "observation_count": len(observations),
        "guardrails": {
            "frozen_benchmark": "backend/data/benchmark.json (immutable)",
            "min_observations_required": 3,
            "max_drift_threshold": 15.0,
            "min_benchmark_threshold": 75.0,
            "median_aggregate_enforced": True,
        },
        "available_versions": all_versions,
    }


def trigger_calibration_retrain(
    proposed_version: Optional[str] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Manually triggers the retraining loop using accumulated validated observations.
    Evaluates proposed model against frozen benchmark and enforces guardrails.
    """
    active_model = get_active_model()
    if not proposed_version:
        # Increment version: v1.0 -> v1.1
        if active_model.version == "v1.0":
            proposed_version = "v1.1"
        else:
            try:
                major, minor = active_model.version.lstrip("v").split(".")
                proposed_version = f"v{major}.{int(minor) + 1}"
            except Exception:
                proposed_version = f"{active_model.version}-next"

    observations = db.get_calibration_observations()

    success, new_model, guardrail_results = train_and_validate_new_version(
        proposed_version=proposed_version,
        observations=observations,
        current_active_model=active_model,
    )

    return success, guardrail_results
