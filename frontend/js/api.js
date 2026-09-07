/** API integration layer for SkillProof - Official Hardened API Contract. */
(function () {
  function errorMessage(error, fallback) {
    if (typeof error === "string") return error;
    if (error && typeof error.message === "string") return error.message;
    if (error && typeof error.detail === "string") return error.detail;
    if (error && error.detail) return JSON.stringify(error.detail);
    return fallback;
  }

  function baseUrl() {
    return (window.SkillProofApiBaseUrl || "").replace(/\/$/, "");
  }

  async function request(path, options) {
    const response = await fetch(baseUrl() + path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(errorMessage(body, `SkillProof API request failed (${response.status}).`));
      error.status = response.status;
      error.detail = body;
      throw error;
    }
    return body;
  }

  window.SkillProofApi = {
    async createAssessment({ skill, difficulty } = {}) {
      const res = await request("/api/assessment", {
        method: "POST",
        body: JSON.stringify({
          skill: skill || "python",
          difficulty: difficulty || "intermediate",
        }),
      });

      if (res.candidate_id) {
        localStorage.setItem("skillproof_candidate_id", res.candidate_id);
      }
      if (res.id) {
        localStorage.setItem("skillproof_assessment_id", res.id);
      }

      const prob = res.problem || {};
      const adapted = {
        ...res,
        assessment_id: res.id,
        challenge_id: prob.id || res.id,
        candidate_id: res.candidate_id,
        skill: "Python",
        difficulty: prob.difficulty || difficulty || "intermediate",
        title: prob.title || "Python Assessment",
        overview: prob.description || "Complete the practical Python assessment.",
        task: prob.description || "Implement the requested Python solution.",
        constraints: prob.constraints || [],
        starter_code: prob.starter_code || "def solve(*args):\n    pass\n",
        starterCode: prob.starter_code || "def solve(*args):\n    pass\n",
        tests: prob.tests || [],
        calibration_version: res.calibration_version,
        evaluation: null,
      };

      window.SkillProofFlow?.setAssessment?.(adapted);
      return adapted;
    },

    async getAssessment(assessmentId) {
      const res = await request(`/api/assessment/${encodeURIComponent(assessmentId)}`);
      const prob = res.problem || {};

      let evaluation = null;
      try {
        const resultRes = await request(`/api/assessment/${encodeURIComponent(assessmentId)}/result`);
        if (resultRes && resultRes.overall_score !== undefined) {
          evaluation = {
            overall_score: Math.round(resultRes.overall_score),
            correctness: Math.round(resultRes.breakdown?.problem_solving ?? resultRes.overall_score),
            problem_solving: Math.round(resultRes.breakdown?.problem_solving ?? resultRes.overall_score),
            code_quality: Math.round(resultRes.breakdown?.code_quality ?? 80),
            efficiency: Math.round(resultRes.breakdown?.efficiency ?? 80),
            understanding: Math.round(resultRes.breakdown?.algorithmic_thinking ?? 80),
            practical_application: Math.round(resultRes.breakdown?.problem_solving ?? 80),
            summary: `Assessment verified. Passed ${resultRes.tests_passed}/${resultRes.tests_total} tests with score ${resultRes.overall_score}/100.`,
            feedback: `Deterministic execution in isolated sandbox. Runtime: ${resultRes.runtime}s. Memory: ${resultRes.memory} MB. Model version: ${resultRes.evaluation_model_version}.`,
          };
        }
      } catch (e) {
        // Result not yet submitted or not found; evaluation remains null
      }

      return {
        ...res,
        assessment_id: res.id,
        challenge_id: prob.id || res.id,
        candidate_id: res.candidate_id,
        skill: "Python",
        difficulty: prob.difficulty || "intermediate",
        title: prob.title || "Assessment",
        overview: prob.description || "",
        task: prob.description || "",
        constraints: prob.constraints || [],
        starter_code: prob.starter_code || "",
        starterCode: prob.starter_code || "",
        tests: prob.tests || [],
        calibration_version: res.calibration_version,
        evaluation: evaluation,
      };
    },

    async submitSolution(assessmentId, { solution, timeElapsedSeconds } = {}) {
      const res = await request(`/api/assessment/${encodeURIComponent(assessmentId)}/submit`, {
        method: "POST",
        body: JSON.stringify({
          solution: solution,
          time_taken: timeElapsedSeconds ? Number(timeElapsedSeconds) : 0.0,
        }),
      });

      const evaluation = {
        overall_score: Math.round(res.overall_score),
        correctness: Math.round(res.breakdown?.problem_solving ?? res.overall_score),
        problem_solving: Math.round(res.breakdown?.problem_solving ?? res.overall_score),
        code_quality: Math.round(res.breakdown?.code_quality ?? 80),
        efficiency: Math.round(res.breakdown?.efficiency ?? 80),
        understanding: Math.round(res.breakdown?.algorithmic_thinking ?? 80),
        practical_application: Math.round(res.breakdown?.problem_solving ?? 80),
        summary: `Assessment evaluation complete. Passed ${res.tests_passed}/${res.tests_total} tests with score ${res.overall_score}/100.`,
        feedback: `Candidate solution executed in isolated subprocess sandbox. Total runtime: ${res.runtime}s. Memory: ${res.memory} MB. Model version: ${res.evaluation_model_version}.`,
      };

      const adapted = {
        ...res,
        assessment_id: assessmentId,
        evaluation: evaluation,
        submitted_solution: solution,
        time_elapsed_seconds: timeElapsedSeconds,
      };

      window.SkillProofFlow?.setAssessment?.(adapted);
      return adapted;
    },

    async getPassport(candidateId) {
      const candId = candidateId || localStorage.getItem("skillproof_candidate_id") || "latest";
      const res = await request(`/api/passport/${encodeURIComponent(candId)}`);
      return {
        ...res,
        overall_score: res.overall_score,
        skill: res.skill || "Python",
        difficulty: res.difficulty || "intermediate",
        calibration_version: res.calibration_version,
        evaluation_model_version: res.evaluation_model_version,
        problem_title: res.problem_title,
        competencies: res.competencies,
        passport_id: res.passport_id,
      };
    },

    async getCalibrationStatus() {
      return request("/api/calibration/status");
    },

    async triggerCalibrationRetrain() {
      return request("/api/calibration/retrain", { method: "POST" });
    },
  };
})();
