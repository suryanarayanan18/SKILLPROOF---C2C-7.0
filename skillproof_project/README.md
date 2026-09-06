# SkillProof — Verifying Skills Without Certificates

> **Code2Create 7.0 (C2C 7.0) 48-Hour Hackathon Prototype**  
> *Demonstrating practical ability, not paper credentials.*

---

## 🎯 Project Overview

Millions of capable engineers and problem solvers lack traditional pedigree or formal certificates that demonstrate what they can truly achieve. Meanwhile, traditional static certifications fail to prove real-world engineering competence.

**SkillProof** flips the paradigm:
1. Presents an adaptive, context-driven coding challenge.
2. Runs code against sandbox microVM criteria.
3. Evaluates real-time performance using the **Google Gemini API** across **6 core competency axes**:
   - Correctness
   - Problem Solving Approach
   - Code Quality & Style
   - Algorithmic Efficiency
   - Deep Conceptual Understanding
   - Practical Real-World Application
4. Delivers an adaptive feedback loop with actionable improvement suggestions.
5. Issues a tamper-evident, cryptographically attested **Skill Passport**.

---

## 👥 Team & Responsibilities

- **Person 2 / Surya (`surya` branch)**: Frontend UI/UX, Google Stitch design integration, client flow state, developer workspace, and local preview engine.
- **Person 3 / Ani (`ani's-branch`)**: Gemini AI backend, challenge generator, and multi-axis performance evaluation microservice.
- **Team**: Firebase persistence, authentication, and platform integration.

---

## 🚀 Running the Frontend Locally

The frontend prototype is implemented in clean semantic HTML5, modern Tailwind CSS (via CDN), Google Fonts (Geist & JetBrains Mono), and vanilla JavaScript. **No Node.js, npm, or complex build tools are required.**

### Option A: Using the Python Server Runner (Recommended)

Run the included runner from the project root:

```bash
python serve.py
```

This starts a lightweight server at `http://localhost:3000` and automatically opens your default browser.

### Option B: Using Python's Built-in HTTP Server

```bash
python -m http.server 3000 --directory frontend
```
Then visit: [http://localhost:3000](http://localhost:3000)

---

## 🔄 Complete User Flow

The prototype provides a complete end-to-end interactive journey:

1. **Landing Page (`frontend/index.html`)**  
   Obsidian liquid-glass hero presentation, feature cards, and immediate call-to-action ("Begin Verification").
2. **Skill Selection (`frontend/skill-selection.html`)**  
   Interactive selection of competency tracks (Python Backend Architecture, React, System Design, Data Structures).
3. **Difficulty Selection (`frontend/difficulty-selection.html`)**  
   Choice of assessment tiers: *Foundational*, *Intermediate (Applied)*, and *Senior (High Throughput)*.
4. **Assessment Setup / Preflight (`frontend/assessment-setup.html`)**  
   Dynamic blueprint generation, parameter breakdown, and automated environment provisioning.
5. **Challenge Workspace (`frontend/workspace.html`)**  
   Two-panel developer environment featuring:
   - Challenge specification, constraints, and sandbox test scenarios.
   - Code editor with starter template, tab key support, reset, and local test runner.
   - Active countdown timer and real-time telemetry.
   - Radiant **"Submit Solution"** button with multi-stage Gemini AI evaluation animation overlay.
6. **AI Evaluation Report (`frontend/evaluation.html`)**  
   Holistic score dial, interactive 6-axis performance radar chart, Gemini insight rationale, strengths & weaknesses, and telemetry summary.
7. **Skill Passport (`frontend/passport.html`)**  
   Attestation badge, verified metadata, immutable verification hash (SHA-256), download proof option, and quick restart flow.
8. **Assessment History & Analytics (`frontend/history.html`, `frontend/analytics.html`)**  
   Audit trail, attestation logs, and historical performance tracking.

---

## 🔌 Developer & Backend Integration Guide (For Person 3 / Ani)

The frontend has been designed to make connecting the Python Gemini backend seamless:

### 1. Mock Data Source: `frontend/js/mock_data.js`
All dynamic challenges and evaluation schemas are isolated in `frontend/js/mock_data.js`:
- `window.SkillProofData.challenges`: Challenge definitions by skill and difficulty.
- `window.SkillProofData.evaluation`: Complete 6-axis scorecard, strengths, weaknesses, rationale, and next steps.
- `window.SkillProofData.passport`: Attestation details and candidate profile.

### 2. State & Flow Orchestration: `frontend/js/flow.js`
Manages `sessionStorage` state persistence across pages:
- `SkillProofFlow.getSelectedSkill()`
- `SkillProofFlow.getSelectedDifficulty()`
- `SkillProofFlow.getChallenge()`
- `SkillProofFlow.getEvaluation()`

### 3. Wiring Gemini Endpoints
To connect live backend endpoints from `backend/services/`:
- **Generate Challenge**: In `frontend/assessment-setup.html` or `frontend/workspace.html`, replace `SkillProofFlow.getChallenge()` with a `POST /api/challenges/generate` call passing `{ skill, difficulty }`.
- **Evaluate Solution**: In `frontend/workspace.html` under `submitSolution()`, replace the mock evaluation timer with a `POST /api/evaluations/submit` call passing `{ code, challengeId, timeElapsed }`. Store the returned JSON in `SkillProofFlow.setEvaluation(apiResult)` before redirecting to `evaluation.html`.

---

## 🎨 Design System

- **Design Philosophy**: Obsidian Veracity / Liquid Glass Aesthetic.
- **Color Palette**: Deep Obsidian (`#131314`, `#0e0e0f`), Terracotta/Coral highlights (`#ffb4a5`, `#773124`), Rosy Burgundy (`#cb7a83`, `#571c26`).
- **Typography**: Geist Sans + JetBrains Mono for code.
- **Icons**: Google Material Symbols Outlined.
