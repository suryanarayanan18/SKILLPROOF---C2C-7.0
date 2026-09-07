/**
 * SkillProof Flow Orchestrator & State Management
 * 
 * Manages user progression across screens:
 * Landing -> Skill Selection -> Difficulty Selection -> Setup -> Workspace -> Evaluation -> Passport
 */

// Purge legacy unscoped draft storage to prevent cross-assessment state contamination
try {
  localStorage.removeItem("skillproof_solution_code");
} catch (e) {}

const SkillProofFlow = {
  getCandidateId() {
    let id = localStorage.getItem("skillproof_candidate_id");
    if (!id) {
      id = "cand-" + Math.random().toString(36).substring(2, 10);
      localStorage.setItem("skillproof_candidate_id", id);
    }
    return id;
  },

  setCandidateId(id) {
    if (id) {
      localStorage.setItem("skillproof_candidate_id", id);
    }
  },

  getSkill() {
    return localStorage.getItem("skillproof_selected_skill") || "python";
  },

  setSkill(skillKey) {
    localStorage.setItem("skillproof_selected_skill", skillKey);
  },

  getDifficulty() {
    return localStorage.getItem("skillproof_selected_difficulty") || "intermediate";
  },

  setDifficulty(diffKey) {
    localStorage.setItem("skillproof_selected_difficulty", diffKey);
  },

  getAssessmentId() {
    return localStorage.getItem("skillproof_assessment_id") || null;
  },

  setAssessment(assessment) {
    if (!assessment) return;
    const id = assessment.assessment_id || assessment.id;
    if (id) {
      localStorage.setItem("skillproof_assessment_id", id);
    }
    if (assessment.candidate_id) {
      this.setCandidateId(assessment.candidate_id);
    }
    localStorage.setItem("skillproof_active_assessment", JSON.stringify(assessment));
  },

  getStoredAssessment() {
    try {
      return JSON.parse(localStorage.getItem("skillproof_active_assessment") || "null");
    } catch (error) {
      return null;
    }
  },

  getActiveChallenge() {
    return this.getStoredAssessment() || {};
  },

  // --- Assessment-Scoped Draft Management ---
  getDraftCode(assessmentId) {
    if (!assessmentId) return null;
    return localStorage.getItem(`skillproof_draft_${assessmentId}`) || null;
  },

  setDraftCode(assessmentId, code) {
    if (!assessmentId || code === undefined || code === null) return;
    localStorage.setItem(`skillproof_draft_${assessmentId}`, code);
  },

  clearDraftCode(assessmentId) {
    if (!assessmentId) return;
    localStorage.removeItem(`skillproof_draft_${assessmentId}`);
  },

  // Legacy compatibility helpers: strictly scoped when assessmentId provided, never cross-contaminates
  getSolutionCode(assessmentId) {
    if (assessmentId) {
      return this.getDraftCode(assessmentId);
    }
    return null;
  },

  setSolutionCode(code, assessmentId) {
    if (assessmentId) {
      this.setDraftCode(assessmentId, code);
    }
    try {
      localStorage.removeItem("skillproof_solution_code");
    } catch (e) {}
  },

  resetSession(clearDrafts = false) {
    localStorage.removeItem("skillproof_selected_skill");
    localStorage.removeItem("skillproof_selected_difficulty");
    localStorage.removeItem("skillproof_solution_code");
    localStorage.removeItem("skillproof_assessment_id");
    localStorage.removeItem("skillproof_active_assessment");
    if (clearDrafts) {
      try {
        const keysToRemove = [];
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          if (k && k.startsWith("skillproof_draft_")) {
            keysToRemove.push(k);
          }
        }
        keysToRemove.forEach(k => localStorage.removeItem(k));
      } catch (e) {}
    }
  }
};

window.SkillProofFlow = SkillProofFlow;

