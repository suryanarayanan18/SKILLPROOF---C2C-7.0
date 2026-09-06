/** Minimal HTTP client for the SkillProof prototype API. */
(function () {
  function baseUrl() {
    return (window.SkillProofApiBaseUrl || "").replace(/\/$/, "");
  }

  async function request(path, options) {
    const response = await fetch(baseUrl() + path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `SkillProof API request failed (${response.status}).`);
    return body;
  }

  window.SkillProofApi = {
    createAssessment({ skill, difficulty, previousPerformance, targetWeakness } = {}) {
      return request("/api/challenges", {
        method: "POST",
        body: JSON.stringify({ skill, difficulty, previous_performance: previousPerformance || null, target_weakness: targetWeakness || null }),
      });
    },
    getAssessment(assessmentId) {
      return request(`/api/assessments/${encodeURIComponent(assessmentId)}`);
    },
    submitSolution(assessmentId, { solution, timeElapsedSeconds } = {}) {
      return request(`/api/assessments/${encodeURIComponent(assessmentId)}/submit`, {
        method: "POST",
        body: JSON.stringify({ solution, time_elapsed_seconds: timeElapsedSeconds ?? null }),
      });
    },
    getPassport() {
      return request("/api/passport");
    },
  };
})();
