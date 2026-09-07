"""Feature extraction pipeline for candidate evaluation observations."""

from __future__ import annotations

from typing import Any, Dict, List
import numpy as np

FEATURE_NAMES = [
    "tests_passed_ratio",
    "runtime_ms",
    "lines_of_code",
    "ast_nodes",
    "cyclomatic_complexity",
    "attempt_duration_sec",
    "has_type_annotations",
    "has_docstring",
]


def extract_feature_vector(observation: Dict[str, Any]) -> List[float]:
    """
    Extracts a normalized numeric feature vector from an observation dictionary.
    Supports either direct features dict or nested evaluation metrics.
    """
    raw_feats = observation.get("features") or observation
    code_metrics = observation.get("code_metrics") or raw_feats.get("code_metrics") or {}

    # Extract or fallback safely
    pass_ratio = float(raw_feats.get("tests_passed_ratio", raw_feats.get("pass_ratio", 0.0)))
    runtime_ms = float(raw_feats.get("runtime_ms", raw_feats.get("avg_test_runtime_ms", 10.0)))
    loc = float(raw_feats.get("lines_of_code", code_metrics.get("lines_of_code", 15)))
    ast_nodes = float(raw_feats.get("ast_nodes", code_metrics.get("ast_nodes", 60)))
    cc = float(raw_feats.get("cyclomatic_complexity", code_metrics.get("cyclomatic_complexity", 2)))
    duration = float(raw_feats.get("attempt_duration_sec", observation.get("time_taken", 300.0)))
    has_types = 1.0 if (raw_feats.get("has_type_annotations") or code_metrics.get("has_type_annotations")) else 0.0
    has_doc = 1.0 if (raw_feats.get("has_docstring") or code_metrics.get("has_docstring")) else 0.0

    return [
        pass_ratio,
        runtime_ms,
        loc,
        ast_nodes,
        cc,
        duration,
        has_types,
        has_doc,
    ]


def to_numpy_matrix(observations: List[Dict[str, Any]]) -> np.ndarray:
    """Converts a list of observation dictionaries into a 2D numpy array."""
    vectors = [extract_feature_vector(obs) for obs in observations]
    return np.array(vectors, dtype=np.float32)
