/** API integration layer for the original Stitch frontend. */
(function () {
  function errorMessage(error, fallback) {
    if (typeof error === "string") return error;
    if (error && typeof error.message === "string") return error.message;
    if (error && typeof error.detail === "string") return error.detail;
    if (error && error.detail) return JSON.stringify(error.detail);
    return fallback;
  }

  function demoAssessment() {
    const challenge = window.SkillProofFlow?.getDemoChallenge?.() || window.SkillProofFlow?.getActiveChallenge?.() || {};
    const assessmentId = `demo-${Date.now()}`;
    return { ...challenge, assessment_id: assessmentId, challenge_id: assessmentId, evaluation: null, submitted_solution: null, time_elapsed_seconds: null };
  }

  function demoEvaluation(solution) {
    const source = String(solution || "").toLowerCase();
    const signals = [
      /process_cart\s*\(/.test(source),
      /for\s+\w+\s+in/.test(source),
      /quantity\s*(<=|>|>=)/.test(source),
      source.includes("category") && source.includes("discount"),
      source.includes("subtotal"),
      source.includes("threshold") || source.includes("0.1"),
      source.includes("max(0"),
      source.includes("return {") || source.includes("return{"),
    ];
    const count = signals.filter(Boolean).length;
    const score = Math.min(100, 45 + count * 7);
    return {
      overall_score: score,
      correctness: score,
      problem_solving: Math.min(100, score + 2),
      code_quality: Math.max(0, Math.min(100, score - 1)),
      efficiency: Math.min(100, score + 1),
      understanding: score,
      practical_application: Math.min(100, score + 1),
      summary: `Demo evaluation identified ${count} of ${signals.length} expected implementation signals.`,
      strengths: ["The solution was reviewed against the deterministic demo rubric."],
      weaknesses: count === signals.length ? ["Add more edge-case tests."] : ["Cover the missing cart requirements before resubmitting."],
      feedback: "Demo mode performs source inspection only; submitted code was not executed in a sandbox.",
      recommended_next_step: "Test zero quantities, category discounts, threshold boundaries, and non-negative totals.",
    };
  }

  function shouldUseDemo(error) {
    return !error || !error.status || [429, 502, 503, 504].includes(error.status);
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
      throw error;
    }
    return body;
  }

  window.SkillProofApi = {
    createAssessment({ skill, difficulty, previousPerformance, targetWeakness } = {}) {
      return request("/api/challenges", {
        method: "POST",
        body: JSON.stringify({ skill, difficulty, previous_performance: previousPerformance || null, target_weakness: targetWeakness || null }),
      }).catch((error) => {
        if (!shouldUseDemo(error)) throw error;
        const assessment = demoAssessment();
        window.SkillProofFlow?.setAssessment?.(assessment);
        return assessment;
      });
    },
    getAssessment(assessmentId) {
      return request(`/api/assessments/${encodeURIComponent(assessmentId)}`).catch((error) => {
        const stored = window.SkillProofFlow?.getStoredAssessment?.();
        if (shouldUseDemo(error) && stored?.assessment_id === assessmentId) return stored;
        throw error;
      });
    },
    submitSolution(assessmentId, { solution, timeElapsedSeconds } = {}) {
      return request(`/api/assessments/${encodeURIComponent(assessmentId)}/submit`, {
        method: "POST",
        body: JSON.stringify({ solution, time_elapsed_seconds: timeElapsedSeconds ?? null }),
      });
    },
    getPassport() {
      return request("/api/passport").catch((error) => {
        const stored = window.SkillProofFlow?.getStoredAssessment?.();
        if (shouldUseDemo(error) && stored?.evaluation) {
          return { assessment_id: stored.assessment_id, skill: stored.skill || "Python", difficulty: stored.difficulty || "beginner", overall_score: stored.evaluation.overall_score, verified: stored.evaluation.overall_score >= 75, summary: stored.evaluation.summary };
        }
        throw error;
      });
    },
  };
})();
