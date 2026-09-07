"""SQLite database connection, schema initialization, and CRUD helpers for SkillProof."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent / "data" / "db.sqlite3"


def get_db_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize database tables according to the SkillProof data model."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS problems (
            id TEXT PRIMARY KEY,
            seed_problem_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            concepts TEXT NOT NULL,          -- JSON list of strings
            algorithm_family TEXT NOT NULL,
            constraints TEXT NOT NULL,       -- JSON list of strings
            reference_solution TEXT NOT NULL,
            tests TEXT NOT NULL,             -- JSON list of test cases
            starter_code TEXT NOT NULL,
            version TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS assessments (
            id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            problem_id TEXT NOT NULL,
            calibration_version TEXT NOT NULL,
            started_at TEXT NOT NULL,
            submitted_at TEXT,
            attempt_number INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (problem_id) REFERENCES problems(id)
        );

        CREATE TABLE IF NOT EXISTS results (
            assessment_id TEXT PRIMARY KEY,
            tests_passed INTEGER NOT NULL,
            tests_total INTEGER NOT NULL,
            runtime REAL NOT NULL,           -- seconds
            memory REAL NOT NULL,            -- KB or MB
            time_taken REAL NOT NULL,        -- seconds
            code_metrics TEXT NOT NULL,      -- JSON dict of code quality metrics
            overall_score REAL NOT NULL,
            problem_version TEXT NOT NULL,
            calibration_version TEXT NOT NULL,
            evaluation_model_version TEXT NOT NULL,
            breakdown TEXT NOT NULL,         -- JSON dict of dimension scores
            submission_code TEXT,
            FOREIGN KEY (assessment_id) REFERENCES assessments(id)
        );

        CREATE TABLE IF NOT EXISTS calibration_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assessment_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL DEFAULT '',
            problem_id TEXT NOT NULL,
            features TEXT NOT NULL,          -- JSON list/dict of features
            result_metrics TEXT NOT NULL,    -- JSON dict of metrics
            validity_flags TEXT NOT NULL,    -- JSON dict of checks passed
            timestamp TEXT NOT NULL,
            FOREIGN KEY (assessment_id) REFERENCES assessments(id)
        );

        CREATE TABLE IF NOT EXISTS model_versions (
            version TEXT PRIMARY KEY,
            benchmark_score REAL NOT NULL,
            validation_metrics TEXT NOT NULL, -- JSON dict
            created_at TEXT NOT NULL,
            status TEXT NOT NULL             -- 'active', 'archived', 'rejected'
        );
        """
    )

    # Ensure seed_problem_id column exists if table was pre-existing
    cursor.execute("PRAGMA table_info(problems)")
    existing_cols = [row["name"] for row in cursor.fetchall()]
    if "seed_problem_id" not in existing_cols:
        cursor.execute("ALTER TABLE problems ADD COLUMN seed_problem_id TEXT NOT NULL DEFAULT ''")

    # Ensure candidate_id column exists on calibration_observations
    cursor.execute("PRAGMA table_info(calibration_observations)")
    existing_obs_cols = [row["name"] for row in cursor.fetchall()]
    if "candidate_id" not in existing_obs_cols:
        cursor.execute("ALTER TABLE calibration_observations ADD COLUMN candidate_id TEXT NOT NULL DEFAULT ''")

    conn.close()


def save_problem(problem: Dict[str, Any]) -> None:
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO problems (
                id, seed_problem_id, title, description, difficulty, concepts,
                algorithm_family, constraints, reference_solution,
                tests, starter_code, version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                problem["id"],
                problem.get("seed_problem_id", problem["id"]),
                problem["title"],
                problem["description"],
                problem["difficulty"],
                json.dumps(problem.get("concepts", [])),
                problem.get("algorithm_family", "General"),
                json.dumps(problem.get("constraints", [])),
                problem["reference_solution"],
                json.dumps(problem.get("tests", [])),
                problem.get("starter_code", ""),
                problem.get("version", "1.0"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def get_problem(problem_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM problems WHERE id = ?", (problem_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["concepts"] = json.loads(d["concepts"])
    d["constraints"] = json.loads(d["constraints"])
    d["tests"] = json.loads(d["tests"])
    return d


def create_assessment(
    assessment_id: str,
    candidate_id: str,
    problem_id: str,
    calibration_version: str = "v1.0",
) -> Dict[str, Any]:
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO assessments (
                id, candidate_id, problem_id, calibration_version,
                started_at, submitted_at, attempt_number
            ) VALUES (?, ?, ?, ?, ?, NULL, 1)
            """,
            (assessment_id, candidate_id, problem_id, calibration_version, now_iso),
        )
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()

    return {
        "id": assessment_id,
        "candidate_id": candidate_id,
        "problem_id": problem_id,
        "calibration_version": calibration_version,
        "started_at": now_iso,
        "submitted_at": None,
        "attempt_number": 1,
    }


def get_assessment(assessment_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM assessments WHERE id = ?", (assessment_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def mark_assessment_submitted(assessment_id: str) -> bool:
    """
    Enforce one-shot submission atomically at the database level.
    Returns True if successfully marked, False if already submitted or not found.
    BEGIN IMMEDIATE guarantees atomic race-free check-and-set across threads and processes.
    """
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            UPDATE assessments
            SET submitted_at = ?
            WHERE id = ? AND submitted_at IS NULL
            """,
            (now_iso, assessment_id),
        )
        updated = cursor.rowcount > 0
        conn.execute("COMMIT")
        return updated
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        return False
    finally:
        conn.close()


def save_result(result: Dict[str, Any]) -> None:
    """
    Saves assessment result immutably.
    Strictly uses INSERT INTO results. Never overwrites an existing result.
    Raises sqlite3.IntegrityError if a result for this assessment_id already exists.
    """
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO results (
                assessment_id, tests_passed, tests_total, runtime,
                memory, time_taken, code_metrics, overall_score,
                problem_version, calibration_version, evaluation_model_version,
                breakdown, submission_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["assessment_id"],
                result["tests_passed"],
                result["tests_total"],
                result["runtime"],
                result["memory"],
                result["time_taken"],
                json.dumps(result.get("code_metrics", {})),
                result["overall_score"],
                result["problem_version"],
                result["calibration_version"],
                result["evaluation_model_version"],
                json.dumps(result.get("breakdown", {})),
                result.get("submission_code", ""),
            ),
        )
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def get_result(assessment_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM results WHERE assessment_id = ?", (assessment_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["code_metrics"] = json.loads(d["code_metrics"])
    d["breakdown"] = json.loads(d["breakdown"])
    return d


def get_candidate_results(candidate_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT r.*, a.candidate_id, a.problem_id, p.title as problem_title,
               p.difficulty, p.algorithm_family, a.started_at, a.submitted_at
        FROM results r
        JOIN assessments a ON r.assessment_id = a.id
        JOIN problems p ON a.problem_id = p.id
        WHERE a.candidate_id = ?
        ORDER BY a.started_at DESC
        """,
        (candidate_id,),
    )
    rows = cursor.fetchall()

    # Fallback to latest completed result if candidate_id is 'latest' or 'default'
    if not rows and candidate_id in ("latest", "default"):
        cursor.execute(
            """
            SELECT r.*, a.candidate_id, a.problem_id, p.title as problem_title,
                   p.difficulty, p.algorithm_family, a.started_at, a.submitted_at
            FROM results r
            JOIN assessments a ON r.assessment_id = a.id
            JOIN problems p ON a.problem_id = p.id
            ORDER BY a.started_at DESC
            LIMIT 1
            """
        )
        rows = cursor.fetchall()

    conn.close()
    results = []
    for row in rows:
        d = dict(row)
        d["code_metrics"] = json.loads(d["code_metrics"])
        d["breakdown"] = json.loads(d["breakdown"])
        results.append(d)
    return results


def get_candidate_history(candidate_id: str) -> List[Dict[str, Any]]:
    """Retrieves full assessment history with joined problem and result info for a candidate."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if candidate_id in ("all", "latest", "default", ""):
        cursor.execute(
            """
            SELECT a.id as assessment_id, a.candidate_id, a.problem_id, a.calibration_version,
                   a.started_at, a.submitted_at,
                   p.title as problem_title, p.difficulty, p.algorithm_family,
                   r.tests_passed, r.tests_total, r.runtime, r.memory, r.time_taken,
                   r.overall_score, r.evaluation_model_version
            FROM assessments a
            JOIN problems p ON a.problem_id = p.id
            JOIN results r ON a.id = r.assessment_id
            WHERE a.submitted_at IS NOT NULL AND r.overall_score IS NOT NULL
            ORDER BY a.submitted_at DESC
            """
        )
    else:
        cursor.execute(
            """
            SELECT a.id as assessment_id, a.candidate_id, a.problem_id, a.calibration_version,
                   a.started_at, a.submitted_at,
                   p.title as problem_title, p.difficulty, p.algorithm_family,
                   r.tests_passed, r.tests_total, r.runtime, r.memory, r.time_taken,
                   r.overall_score, r.evaluation_model_version
            FROM assessments a
            JOIN problems p ON a.problem_id = p.id
            JOIN results r ON a.id = r.assessment_id
            WHERE a.candidate_id = ? AND a.submitted_at IS NOT NULL AND r.overall_score IS NOT NULL
            ORDER BY a.submitted_at DESC
            """,
            (candidate_id,),
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def observation_exists_for_assessment(assessment_id: str) -> bool:
    """Checks if a calibration observation already exists for the given assessment."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM calibration_observations WHERE assessment_id = ? LIMIT 1", (assessment_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None


def save_calibration_observation(
    assessment_id: str,
    problem_id: str,
    features: Any,
    result_metrics: Dict[str, Any],
    validity_flags: Dict[str, Any],
    candidate_id: str = "",
) -> int:
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    if not candidate_id:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT candidate_id FROM assessments WHERE id = ?", (assessment_id,))
            asmt_row = cursor.fetchone()
            if asmt_row and asmt_row["candidate_id"]:
                candidate_id = asmt_row["candidate_id"]
        except Exception:
            pass

    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO calibration_observations (
                assessment_id, candidate_id, problem_id, features, result_metrics,
                validity_flags, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assessment_id,
                candidate_id,
                problem_id,
                json.dumps(features),
                json.dumps(result_metrics),
                json.dumps(validity_flags),
                now_iso,
            ),
        )
        obs_id = cursor.lastrowid
        conn.execute("COMMIT")
        return obs_id or 0
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def get_calibration_observations(limit: int = 1000) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM calibration_observations ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    results = []
    for row in rows:
        d = dict(row)
        d["features"] = json.loads(d["features"])
        d["result_metrics"] = json.loads(d["result_metrics"])
        d["validity_flags"] = json.loads(d["validity_flags"])
        results.append(d)
    return results


def save_model_version(
    version: str,
    benchmark_score: float,
    validation_metrics: Dict[str, Any],
    status: str = "active",
) -> None:
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        if status == "active":
            cursor.execute("UPDATE model_versions SET status = 'archived' WHERE status = 'active'")
        cursor.execute(
            """
            INSERT OR REPLACE INTO model_versions (
                version, benchmark_score, validation_metrics, created_at, status
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (version, benchmark_score, json.dumps(validation_metrics), now_iso, status),
        )
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def get_active_model_version() -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM model_versions WHERE status = 'active' ORDER BY created_at DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["validation_metrics"] = json.loads(d["validation_metrics"])
    return d


def get_all_model_versions() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM model_versions ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    results = []
    for row in rows:
        d = dict(row)
        d["validation_metrics"] = json.loads(d["validation_metrics"])
        results.append(d)
    return results
