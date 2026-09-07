"""TinyML model wrapper: load, save, predict, and versioning."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import joblib
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.features import FEATURE_NAMES, extract_feature_vector

VERSIONS_DIR = Path(__file__).resolve().parent / "versions"


class SkillCalibrationModel:
    """TinyML calibration model combining StandardScaler and Ridge Regression."""

    def __init__(self, version: str = "v1.0"):
        self.version = version
        self.pipeline: Pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("regressor", Ridge(alpha=1.0, random_state=42)),
        ])
        self.is_fitted: bool = False
        self.benchmark_score: float = 0.0
        self.metadata: Dict[str, Any] = {}

    def fit(self, X: np.ndarray, y: np.ndarray) -> SkillCalibrationModel:
        self.pipeline.fit(X, y)
        self.is_fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            # Cold start fallback if not yet fitted: linear baseline estimate
            # X[:, 0] is tests_passed_ratio
            return np.clip(X[:, 0] * 80.0 + 15.0, 0.0, 100.0)
        preds = self.pipeline.predict(X)
        return np.clip(preds, 0.0, 100.0)

    def predict_observation(self, observation: Dict[str, Any]) -> float:
        feat_vec = extract_feature_vector(observation)
        X = np.array([feat_vec], dtype=np.float32)
        preds = self.predict(X)
        return float(round(preds[0], 2))

    def save(self, version_name: Optional[str] = None) -> Path:
        target_version = version_name or self.version
        VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
        file_path = VERSIONS_DIR / f"{target_version}.joblib"
        data = {
            "version": target_version,
            "pipeline": self.pipeline,
            "is_fitted": self.is_fitted,
            "benchmark_score": self.benchmark_score,
            "metadata": self.metadata,
            "feature_names": FEATURE_NAMES,
        }
        joblib.dump(data, file_path)
        return file_path

    @classmethod
    def load(cls, version_name: str) -> SkillCalibrationModel:
        file_path = VERSIONS_DIR / f"{version_name}.joblib"
        if not file_path.exists():
            raise FileNotFoundError(f"Model version {version_name} not found at {file_path}")
        data = joblib.load(file_path)
        model = cls(version=data["version"])
        model.pipeline = data["pipeline"]
        model.is_fitted = data["is_fitted"]
        model.benchmark_score = data.get("benchmark_score", 0.0)
        model.metadata = data.get("metadata", {})
        return model


_ACTIVE_MODEL: Optional[SkillCalibrationModel] = None


def get_active_model() -> SkillCalibrationModel:
    """Returns the currently active TinyML calibration model in memory."""
    global _ACTIVE_MODEL
    if _ACTIVE_MODEL is None:
        try:
            import db
            active_row = db.get_active_model_version()
            if active_row and active_row.get("version"):
                active_ver = active_row["version"]
                active_file = VERSIONS_DIR / f"{active_ver}.joblib"
                if active_file.exists():
                    _ACTIVE_MODEL = SkillCalibrationModel.load(active_ver)
                    return _ACTIVE_MODEL
        except Exception:
            pass

        # Fallback to loading v1.0, or initialize and fit default cold-start v1.0
        v1_path = VERSIONS_DIR / "v1.0.joblib"
        if v1_path.exists():
            try:
                _ACTIVE_MODEL = SkillCalibrationModel.load("v1.0")
                try:
                    import db
                    if not db.get_active_model_version():
                        meta = _ACTIVE_MODEL.metadata or {"version": "v1.0", "benchmark_score": _ACTIVE_MODEL.benchmark_score}
                        db.save_model_version("v1.0", _ACTIVE_MODEL.benchmark_score, meta, status="active")
                except Exception:
                    pass
                return _ACTIVE_MODEL
            except Exception:
                pass
        from ml.train import bootstrap_v1_model
        _ACTIVE_MODEL = bootstrap_v1_model()
    return _ACTIVE_MODEL


def set_active_model(model: SkillCalibrationModel) -> None:
    global _ACTIVE_MODEL
    _ACTIVE_MODEL = model
