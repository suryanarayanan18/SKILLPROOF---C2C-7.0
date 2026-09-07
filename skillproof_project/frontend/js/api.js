/** API integration layer for the original Stitch frontend. */
(function () {
  function errorMessage(error, fallback) {
    if (typeof error === "string") return error;
    if (error && typeof error.message === "string") return error.message;
    if (error && typeof error.detail === "string") return error.detail;
    if (error && Array.isArray(error.detail)) {
      return error.detail.map((item) => `${item.loc?.slice(-1)?.[0] || "field"}: ${item.msg || "invalid value"}`).join("; ");
    }
    if (error && error.detail) return JSON.stringify(error.detail);
    return fallback;
  }

  function formatError(error) {
    return errorMessage(error, "SkillProof could not complete that request. Please try again.");
  }

  function demoAssessment() {
    const challenge = window.SkillProofFlow?.getDemoChallenge?.() || window.SkillProofFlow?.getActiveChallenge?.() || {};
    const assessmentId = `demo-${Date.now()}`;
    return { ...challenge, assessment_id: assessmentId, challenge_id: assessmentId, evaluation: null, submitted_solution: null, time_elapsed_seconds: null };
  }

  function demoEvaluation(solution, challenge = {}) {
    const source = String(solution || "").toLowerCase();
    const isAggregator = String(challenge.title || challenge.task || "").toLowerCase().includes("telemetry") || source.includes("aggregate_payload_stream");
    const signals = isAggregator ? [
      /aggregate_payload_stream\s*\(/.test(source),
      source.includes("for record in"),
      source.includes("timestamp"),
      source.includes("malformed") || source.includes("isinstance"),
      source.includes("partitions"),
      source.includes("window_seconds") || source.includes("% 60"),
      source.includes("total_payloads"),
      source.includes("return {"),
    ] : [
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
    const passed = Math.min(signals.length, count);
    return {
      overall_score: score,
      correctness: score,
      problem_solving: Math.min(100, score + 2),
      code_quality: Math.max(0, Math.min(100, score - 1)),
      efficiency: Math.min(100, score + 1),
      understanding: score,
      practical_application: Math.min(100, score + 1),
      summary: `Deterministic Review 1 completed with ${passed}/${signals.length} checks passing.`,
      strengths: [`Passed ${passed} of ${signals.length} deterministic checks.`],
      weaknesses: count === signals.length ? ["Add more edge-case tests."] : ["Cover the missing cart requirements before resubmitting."],
      feedback: "The local demo provider reviewed the submitted Python without using an external AI service.",
      recommended_next_step: "Test zero quantities, category discounts, threshold boundaries, and non-negative totals.",
      status: "completed",
      passed_tests: passed,
      total_tests: signals.length,
      failed_tests: signals.length - passed,
      competency: score >= 75 ? "Strong" : "Developing",
      improvements: count === signals.length ? ["Add more edge-case tests."] : ["Cover the missing cart requirements before resubmitting."],
      next_difficulty: "intermediate",
      test_results: signals.map((passedSignal, index) => ({ name: `deterministic check ${index + 1}`, status: passedSignal ? "PASS" : "FAIL", detail: passedSignal ? "Signal matched." : "Expected implementation signal was not found." })),
    };
  }

  function shouldUseDemo(error) {
    return !error || !error.status || [404, 429, 502, 503, 504].includes(error.status);
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
    formatError,
    createAssessment({ skill, difficulty, previousPerformance, targetWeakness } = {}) {
      return request("/api/challenges", {
        method: "POST",
        body: JSON.stringify({ skill, difficulty, previous_performance: previousPerformance || null, target_weakness: targetWeakness || null }),
      });
    },
    getAssessment(assessmentId) {
      return request(`/api/assessments/${encodeURIComponent(assessmentId)}`);
    },
    executeAssessment(assessmentId, { code, language = "python" } = {}) {
      return request("/api/execute", {
        method: "POST",
        body: JSON.stringify({ assessment_id: assessmentId, code, language }),
      });
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
