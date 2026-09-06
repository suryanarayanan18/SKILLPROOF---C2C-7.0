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
  getDemoChallenge() {
    const difficulty = this.getDifficulty();
    const source = window.SkillProofData?.challenges?.python?.[difficulty]
      || window.SkillProofData?.challenges?.python?.intermediate;
    return {
      assessment_id: `demo-${difficulty}`,
      challenge_id: source?.id || `demo-${difficulty}`,
      skill: "Python",
      difficulty,
      title: source?.title || `${difficulty[0].toUpperCase()}${difficulty.slice(1)} Assessment`,
      overview: source?.overview || "Complete the practical Python assessment.",
      task: source?.task || "Implement the requested Python solution.",
      constraints: source?.constraints || [],
      starter_code: source?.starterCode || "def solve(data):\n    pass\n",
      starterCode: source?.starterCode || "def solve(data):\n    pass\n",
      examples: source?.example ? [source.example] : [],
    };
  },
  getAssessmentId() {
    return localStorage.getItem("skillproof_assessment_id") || null;
  },
  setAssessment(assessment) {
    localStorage.setItem("skillproof_assessment_id", assessment.assessment_id);
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
    localStorage.removeItem("skillproof_assessment_id");
    localStorage.removeItem("skillproof_active_assessment");
  }
};

window.SkillProofFlow = SkillProofFlow;
