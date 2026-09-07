# SkillProof — Antigravity Build Brief

> **Paste this entire file as your first message to Antigravity.** It is the single source of truth for scope, stack, structure, and order of work for tonight. Deadline: 2 AM. Team: solo, possibly duo.

---

## 0. Mission (one line)

Build a working demo where a candidate takes a one-shot Python coding assessment, gets an objectively-computed Skill Passport, and a small TinyML model visibly improves the platform's calibration from validated results — **without any live external API or generative-AI runtime dependency.**

---

## 1. Tech stack — locked, do not swap mid-build

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn | fast to scaffold, auto docs at `/docs` for live testing |
| Database | SQLite via stdlib `sqlite3` | zero setup, single file, no ORM/migration overhead |
| Execution sandbox | `subprocess` + `resource` (RLIMIT_CPU, RLIMIT_AS) + `timeout=` | no Docker, no Judge0 — good enough for a demo, not production |
| ML | scikit-learn `LogisticRegression` / small `DecisionTreeClassifier` + `joblib` | tiny, fast to train, easy to version |
| Problem corpus | static JSON files, hand-authored | no live ingestion tonight |
| Frontend | **existing Stitch-generated frontend, reused as-is** | don't rebuild UI — wire it up |
| Deploy | localhost only | ngrok only if the judges need a remote link |

**Do not introduce:** Docker, Postgres/MySQL, Celery/background job queues, real Judge0, any LLM call inside the running app, auth/OAuth, a new frontend framework.

---

## 2. Repo structure — build exactly this

```
skillproof/
├── backend/
│   ├── app.py                  # FastAPI app, mounts all routes
│   ├── db.py                   # sqlite3 connection + schema init + CRUD helpers
│   ├── schemas.py               # pydantic request/response models
│   ├── services/
│   │   ├── challenge_generator.py   # template variation engine
│   │   ├── problem_validator.py     # runs reference solution vs hidden tests
│   │   ├── executor.py              # sandboxed subprocess runner
│   │   ├── evaluator.py             # turns raw run output into metrics
│   │   ├── scoring.py               # weighted baseline score
│   │   └── calibration.py           # observation storage + guardrail checks
│   ├── ml/
│   │   ├── features.py         # feature vector builder from observations
│   │   ├── model.py            # load/save/predict wrapper
│   │   ├── train.py            # train + validate against frozen benchmark
│   │   └── versions/           # saved model files (v1.0.joblib, v1.1.joblib, ...)
│   └── data/
│       ├── problems/            # 8-10 hand-authored problem JSON files
│       ├── benchmark.json       # frozen benchmark set — NEVER auto-modified
│       └── db.sqlite3           # generated at runtime, gitignored
├── frontend/                    # EXISTING Stitch export — see rules below
└── ANTIGRAVITY_BUILD_BRIEF.md
```

---

## 3. Do NOT touch / do NOT build tonight

- ❌ Frontend visual design, layout, components, styling — **only add API-calling glue code** (fetch/axios calls, state wiring). If the existing frontend's stack is unclear, inspect it first and adapt to it — don't replace it.
- ❌ Authentication, billing, user accounts beyond a bare candidate id.
- ❌ Any live call to Codeforces, LeetCode, or any external problem API.
- ❌ Any language other than Python for candidate code.
- ❌ Docker, Kubernetes, cloud deployment, CI/CD pipelines.
- ❌ Adversarial/fuzz test-case generation for the validation pipeline.
- ❌ Employer dashboard, shareable public credential links.
- ❌ A background job scheduler for retraining — a manual "Retrain" trigger (button or CLI command) is enough for the demo.
- ❌ Any generative-AI API call from the running backend (Google AI Pro / Gemini is for **you coding in Antigravity**, not for the shipped app).

If you're unsure whether something is in scope, check it against **Section 8 (Acceptance Criteria)** below — if it's not needed to satisfy one of those lines, don't build it tonight.

---

## 4. Build order with time checkpoints (8-hour window)

Offsets are relative to whenever you actually start. If solo, do Track A then Track B in order — they're deliberately independent so a second person can pick up Track B at any point.

| Checkpoint | Task | Track |
|---|---|---|
| 0:00 – 0:30 | Repo scaffold, FastAPI `/api/health`, SQLite schema init, first git commit | Either |
| 0:30 – 1:30 | Seed 8-10 problems as JSON (concept tags, algorithm family, reference solution, hidden test generator) + template variation engine | B |
| 0:30 – 2:30 | Execution sandbox (`executor.py`) + evaluator (tests passed, runtime, memory, errors, static metrics) | A |
| 1:30 – 3:00 | Problem validation pipeline (reference solution vs hidden tests) + Skill Passport endpoint | B |
| 2:30 – 3:30 | Scoring service (weighted baseline) + Assessment API: create / submit-once / result | A |
| 3:00 – 4:30 | TinyML: `features.py`, seed + bootstrapped training data, `train.py`, `model.py`, `/api/calibration/*` endpoints | B |
| 3:30 – 5:00 | Versioning wired end-to-end (problem/calibration/model version stamped on every result) | A |
| 5:00 – 6:30 | Wire existing frontend to backend (fetch calls only) — landing → skill select → one-shot workspace → submission → passport | Both |
| 6:30 – 7:15 | Seed demo data, confirm frozen benchmark, simulate a v1.1 calibration update passing benchmark | Either |
| 7:15 – 8:00 | Bug bash, rehearse the 3-minute demo script twice, buffer for surprises | Both |

---

## 5. Data model

- **Problem**: `id, title, description, difficulty, concepts, algorithm_family, constraints, reference_solution, tests, version`
- **Assessment**: `id, candidate_id, problem_id, calibration_version, started_at, submitted_at, attempt_number`
- **Result**: `assessment_id, tests_passed, tests_total, runtime, memory, time_taken, code_metrics, overall_score`
- **CalibrationObservation**: `assessment_id, problem_id, features, result_metrics, validity_flags, timestamp`
- **ModelVersion**: `version, benchmark_score, validation_metrics, created_at, status`

---

## 6. API contract

```
GET  /api/health
POST /api/assessment                        create assessment
GET  /api/assessment/{id}                    retrieve assessment
POST /api/assessment/{id}/submit             submit once (reject if already submitted)
GET  /api/assessment/{id}/result             result
GET  /api/passport/{candidate_id}            Skill Passport
POST /api/calibration/observation            store validated observation
GET  /api/calibration/status                 active model/calibration version
```

Every `Result` and `/passport` response must include `problem_version`, `calibration_version`, and `evaluation_model_version`.

---

## 7. Key implementation notes

- **Execution sandbox**: run candidate code as a subprocess with `subprocess.run([sys.executable, script], input=..., capture_output=True, timeout=5)`.
- **Variation engine**: plain string templating + parameter randomization within pre-validated bounds. No LLM call. Each template ships with its own reference solution and a hidden-test generator function.
- **Scoring**: `0.5×correctness + 0.2×efficiency + 0.15×algorithmic_evidence + 0.15×code_quality`. Keep the weights in a small versioned config, not hardcoded inline.
- **Guardrails to actually implement**:
  - frozen `benchmark.json` that training code never writes to
  - minimum observation count before a problem's difficulty can change
  - median/trimmed aggregate instead of raw mean
  - capped max movement per calibration update
  - reject a model update if it drops benchmark score below a fixed threshold
- **One-shot enforcement**: `POST /assessment/{id}/submit` must check `submitted_at IS NULL` before accepting; reject a second call with a clear error.
- **Historical immutability**: never update a `Result` row after it's written; new calibration only affects future assessments.
