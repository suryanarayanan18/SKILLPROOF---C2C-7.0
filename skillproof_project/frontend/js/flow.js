/**
 * SkillProof Flow Orchestrator & State Management
 * 
 * Manages user progression across screens:
 * Landing -> Skill Selection -> Difficulty Selection -> Setup -> Workspace -> Evaluation -> Passport
 */

const SkillProofFlow = {
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
  getSolutionCode() {
    return localStorage.getItem("skillproof_solution_code") || null;
  },
  setSolutionCode(code) {
    localStorage.setItem("skillproof_solution_code", code);
  },
  getActiveChallenge() {
    const skill = this.getSkill();
    const diff = this.getDifficulty();
    const skillData = window.SkillProofData?.challenges[skill] || window.SkillProofData?.challenges.python;
    return skillData[diff] || skillData.intermediate || window.SkillProofData?.challenges.python.intermediate;
  },
  getEvaluation() {
    return window.SkillProofData?.evaluation || {};
  },
  resetSession() {
    localStorage.removeItem("skillproof_selected_skill");
    localStorage.removeItem("skillproof_selected_difficulty");
    localStorage.removeItem("skillproof_solution_code");
  }
};

window.SkillProofFlow = SkillProofFlow;
