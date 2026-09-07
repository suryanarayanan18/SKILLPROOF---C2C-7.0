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

  async function request(path, options = {}) {
    let response;
    try {
      response = await fetch(baseUrl() + path, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
    } catch (networkError) {
      const err = new Error("Backend connection failed. Please ensure the SkillProof server is running.");
      err.isNetworkError = true;
      throw err;
    }

    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const msg = errorMessage(body, `SkillProof API error (${response.status})`);
      const error = new Error(msg);
      error.status = response.status;
      error.detail = body;
      throw error;
    }
    return body;
  }

  window.SkillProofApi = {
    async createAssessment({ skill, difficulty } = {}) {
      const candidateId = window.SkillProofFlow?.getCandidateId?.() || undefined;
      const res = await request("/api/assessment", {
        method: "POST",
        body: JSON.stringify({
          skill: skill || "python",
          difficulty: difficulty || "intermediate",
          candidate_id: candidateId,
        }),
      });

      if (res.candidate_id && window.SkillProofFlow) {
        window.SkillProofFlow.setCandidateId(res.candidate_id);
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
        description: prob.description || "",
        overview: prob.description || "",
        task: prob.description || "",
        constraints: prob.constraints || [],
        starter_code: prob.starter_code || "def solve(*args):\n    pass\n",
        starterCode: prob.starter_code || "def solve(*args):\n    pass\n",
        concepts: prob.concepts || [],
        algorithm_family: prob.algorithm_family || "General",
        examples: prob.examples || [],
        problem_version: prob.version || "1.0",
        calibration_version: res.calibration_version,
      };

      window.SkillProofFlow?.setAssessment?.(adapted);
      return adapted;
    },

    async getAssessment(assessmentId) {
      const res = await request(`/api/assessment/${encodeURIComponent(assessmentId)}`);
      const prob = res.problem || {};

      let result = null;
      try {
        result = await request(`/api/assessment/${encodeURIComponent(assessmentId)}/result`);
      } catch (e) {
        // Not submitted yet, result remains null
      }

      const adapted = {
        ...res,
        assessment_id: res.id,
        challenge_id: prob.id || res.id,
        candidate_id: res.candidate_id,
        skill: "Python",
        difficulty: prob.difficulty || "intermediate",
        title: prob.title || "Assessment",
        description: prob.description || "",
        overview: prob.description || "",
        task: prob.description || "",
        constraints: prob.constraints || [],
        starter_code: prob.starter_code || "",
        starterCode: prob.starter_code || "",
        concepts: prob.concepts || [],
        algorithm_family: prob.algorithm_family || "General",
        examples: prob.examples || [],
        problem_version: prob.version || "1.0",
        calibration_version: res.calibration_version,
        result: result,
      };

      window.SkillProofFlow?.setAssessment?.(adapted);
      return adapted;
    },

    async runCode(assessmentId, code) {
      return request(`/api/assessment/${encodeURIComponent(assessmentId)}/run`, {
        method: "POST",
        body: JSON.stringify({ solution: code }),
      });
    },

    async submitSolution(assessmentId, { solution, timeElapsedSeconds } = {}) {
      const res = await request(`/api/assessment/${encodeURIComponent(assessmentId)}/submit`, {
        method: "POST",
        body: JSON.stringify({
          solution: solution,
          time_taken: timeElapsedSeconds ? Number(timeElapsedSeconds) : 0.0,
        }),
      });

      const adapted = {
        ...res,
        assessment_id: assessmentId,
        submitted_solution: solution,
        time_elapsed_seconds: timeElapsedSeconds,
      };

      const existing = window.SkillProofFlow?.getStoredAssessment?.() || {};
      window.SkillProofFlow?.setAssessment?.({
        ...existing,
        ...adapted,
        result: res,
      });

      return res;
    },

    async getAssessmentResult(assessmentId) {
      return request(`/api/assessment/${encodeURIComponent(assessmentId)}/result`);
    },

    async getPassport(candidateId) {
      const candId = candidateId || window.SkillProofFlow?.getCandidateId?.() || "latest";
      return request(`/api/passport/${encodeURIComponent(candId)}`);
    },

    async getHistory(candidateId) {
      const candId = candidateId || window.SkillProofFlow?.getCandidateId?.() || "all";
      return request(`/api/history/${encodeURIComponent(candId)}`);
    },

    async getCalibrationStatus() {
      return request("/api/calibration/status");
    },

    async triggerCalibrationRetrain() {
      return request("/api/calibration/retrain", { method: "POST" });
    },
  };
})();

