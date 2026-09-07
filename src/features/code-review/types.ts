export type ReviewLanguage = "javascript" | "typescript";

export type Difficulty = "beginner" | "intermediate" | "advanced";

export type Severity = "low" | "medium" | "high" | "critical";

export type VulnerabilityCategory =
  | "injection"
  | "authentication"
  | "authorization"
  | "secrets"
  | "input-validation"
  | "unsafe-api"
  | "cryptography"
  | "configuration"
  | "other";

export interface CodeReviewFile {
  path: string;
  language: ReviewLanguage;
  content: string;
}

export interface ExpectedVulnerability {
  id: string;
  title: string;
  description: string;
  category: VulnerabilityCategory;
  severity: Severity;
  filePath: string;
  startLine?: number;
  endLine?: number;
}

export interface CodeReviewChallenge {
  id: string;
  title: string;
  description: string;
  language: ReviewLanguage;
  difficulty: Difficulty;
  files: CodeReviewFile[];
  expectedVulnerabilities?: ExpectedVulnerability[];
  instructions?: string[];
}

export interface ReviewComment {
  id: string;
  filePath: string;
  line?: number;
  comment: string;
  category?: VulnerabilityCategory;
  severity?: Severity;
}

export interface RefactoredFile {
  path: string;
  content: string;
}

export interface CodeReviewSubmission {
  challengeId: string;
  reviewComments: ReviewComment[];
  refactoredFiles: RefactoredFile[];
  submittedAt?: string;
}

export interface CodeReviewEvaluation {
  overallScore: number;
  vulnerabilitiesFound: EvaluatedVulnerability[];
  vulnerabilitiesMissed: EvaluatedVulnerability[];
  securityAwarenessScore: number;
  reasoningScore: number;
  refactoringQualityScore: number;
  reasoning: string;
  feedback: string;
  nextChallengeFocus?: string;
}

export interface CodeReviewService {
  generateChallenge(): Promise<CodeReviewChallenge>;
  evaluateSubmission(
    submission: CodeReviewSubmission,
  ): Promise<CodeReviewEvaluation>;
}

export interface EvaluatedVulnerability {
  vulnerabilityId: string;
  identified: boolean;
  explanation?: string;
  severity?: Severity;
  accuracyScore?: number;
  severityAwarenessScore?: number;
  explanationQualityScore?: number;
}
