/**
 * SkillProof Flow Orchestrator & State Management
 * 
 * Manages user progression across screens:
 * Landing -> Skill Selection -> Difficulty Selection -> Setup -> Workspace -> Evaluation -> Passport
 */

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

  getSolutionCode() {
    return localStorage.getItem("skillproof_solution_code") || null;
  },

  setSolutionCode(code) {
    localStorage.setItem("skillproof_solution_code", code);
  },

  resetSession() {
    localStorage.removeItem("skillproof_selected_skill");
    localStorage.removeItem("skillproof_selected_difficulty");
    localStorage.removeItem("skillproof_solution_code");
    localStorage.removeItem("skillproof_assessment_id");
    localStorage.removeItem("skillproof_active_assessment");
  }
};

window.SkillProofFlow = SkillProofFlow;

