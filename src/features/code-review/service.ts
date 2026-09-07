import type {
  CodeReviewEvaluation,
  CodeReviewService,
  EvaluatedVulnerability,
  ExpectedVulnerability,
  ReviewComment,
  CodeReviewSubmission,
} from "./types";
import demoCodeReviewChallenge = require("./challenge");

/**
 * AI integration boundary for Interactive "Code Review" Roleplay.
 *
 * This file intentionally does not depend on Gemini, Firebase, React,
 * or any other implementation. P3 can replace this implementation
 * without changing the roleplay data flow.
 */
/** Local implementation for testing the complete roleplay flow. */
const mockCodeReviewService: CodeReviewService = {
  async generateChallenge() {
    return demoCodeReviewChallenge;
  },

  async evaluateSubmission(submission) {
    const expected = demoCodeReviewChallenge.expectedVulnerabilities ?? [];
    const results = expected.map((vulnerability) =>
      evaluateVulnerability(vulnerability, submission.reviewComments),
    );
    const vulnerabilitiesFound = results.filter((result) => result.identified);
    const vulnerabilitiesMissed = results.filter((result) => !result.identified);
    const securityAwarenessScore = scoreDetection(results);
    const reasoningScore = scoreReasoning(submission.reviewComments, results);
    const refactoringQualityScore = scoreRefactoring(submission);
    const firstMissed = vulnerabilitiesMissed[0];
    const nextChallengeFocus = firstMissed
      ? expected.find(
          (vulnerability) => vulnerability.id === firstMissed.vulnerabilityId,
        )?.category
      : undefined;

    const evaluation: CodeReviewEvaluation = {
      overallScore: Math.round(
        securityAwarenessScore * 0.5 +
          reasoningScore * 0.25 +
          refactoringQualityScore * 0.25,
      ),
      vulnerabilitiesFound,
      vulnerabilitiesMissed,
      securityAwarenessScore,
      reasoningScore,
      refactoringQualityScore,
      reasoning:
        "The local evaluator checks comments against expected issues by file, line, and security terminology. Explanations are rewarded when they describe both the risk and a safer direction.",
      feedback: firstMissed
        ? `You identified ${vulnerabilitiesFound.length} of ${expected.length} expected vulnerabilities. Focus next on ${firstMissed.severity} severity ${nextChallengeFocus} issues.`
        : "All expected issues were identified. Review the refactoring score for remaining implementation gaps.",
    };

    return nextChallengeFocus
      ? { ...evaluation, nextChallengeFocus }
      : evaluation;
  },
};

export = mockCodeReviewService;

const vulnerabilityTerms: Record<string, string[]> = {
  "vuln-sql-injection": ["sql", "injection", "parameter", "query"],
  "vuln-eval": ["eval", "arbitrary", "javascript", "code execution"],
  "vuln-secret": ["hardcoded", "credential", "secret", "api key", "environment"],
  "vuln-authorization": ["authorization", "authorized", "ownership", "permission", "access control"],
};

type ReviewCommentWithVulnerabilityId = ReviewComment & {
  vulnerabilityId?: string;
};

function evaluateVulnerability(
  vulnerability: ExpectedVulnerability,
  comments: ReviewComment[],
): EvaluatedVulnerability {
  const matchingComments = comments.filter(
    (comment) =>
      (!hasExplicitVulnerabilityId(comment) ||
        comment.vulnerabilityId === vulnerability.id) &&
      comment.filePath === vulnerability.filePath &&
      isNearVulnerability(comment, vulnerability),
  );
  const matchingComment = matchingComments.find((comment) =>
    (vulnerabilityTerms[vulnerability.id] ?? []).some((term) =>
      comment.comment.toLowerCase().includes(term),
    ),
  );

  if (!matchingComment) {
    return {
      vulnerabilityId: vulnerability.id,
      identified: false,
      severity: vulnerability.severity,
      accuracyScore: 0,
      severityAwarenessScore: 0,
      explanationQualityScore: 0,
    };
  }

  const explanation = matchingComment.comment.trim();
  const hasRisk = /risk|allow|expose|execute|read|access|unsafe|attack/i.test(explanation);
  const hasRemediation = /parameter|validate|sanitize|replace|remove|env|authorize|permission|allowlist|hash/i.test(explanation);
  const accuracyScore = hasRisk && hasRemediation ? 100 : hasRisk ? 80 : 60;
  const severityAwarenessScore = matchingComment.severity === vulnerability.severity
    ? 100
    : matchingComment.severity
      ? 50
      : /critical|high|medium|low/i.test(explanation)
        ? 70
        : 40;

  return {
    vulnerabilityId: vulnerability.id,
    identified: true,
    explanation,
    severity: vulnerability.severity,
    accuracyScore,
    severityAwarenessScore,
    explanationQualityScore: Math.round((accuracyScore + severityAwarenessScore) / 2),
  };
}

function hasExplicitVulnerabilityId(
  comment: ReviewComment,
): comment is ReviewCommentWithVulnerabilityId & { vulnerabilityId: string } {
  const vulnerabilityId = (comment as ReviewCommentWithVulnerabilityId)
    .vulnerabilityId;
  return typeof vulnerabilityId === "string";
}

function isNearVulnerability(
  comment: ReviewComment,
  vulnerability: ExpectedVulnerability,
) {
  return comment.line === undefined ||
    vulnerability.startLine === undefined ||
    vulnerability.endLine === undefined ||
    (comment.line >= vulnerability.startLine - 2 && comment.line <= vulnerability.endLine + 2);
}

function scoreDetection(results: ReturnType<typeof evaluateVulnerability>[]) {
  if (results.length === 0) return 0;
  return Math.round(
    results.reduce((total, result) => total + (result.accuracyScore ?? 0), 0) / results.length,
  );
}

function scoreReasoning(
  comments: ReviewComment[],
  results: ReturnType<typeof evaluateVulnerability>[],
) {
  if (comments.length === 0) return 0;
  const identified = results.filter((result) => result.identified);
  if (identified.length === 0) return 0;
  return Math.round(
    identified.reduce((total, result) => total + (result.explanationQualityScore ?? 0), 0) /
      identified.length,
  );
}

function scoreRefactoring(submission: CodeReviewSubmission) {
  const files = new Map(submission.refactoredFiles.map((file) => [file.path, file.content]));
  const checks = [
    !/SELECT\s+\*\s+FROM\s+users\s+WHERE\s+id\s*\+|\+\s*userId/i.test(files.get("userService.js") ?? ""),
    !/\beval\s*\(/i.test(files.get("userService.js") ?? ""),
    !/(sk_demo_|password123|apiKey\s*:\s*["'])/i.test(files.get("config.js") ?? ""),
    /authorize|authenticated|owner|permission|access/i.test(files.get("server.js") ?? ""),
  ];
  return Math.round((checks.filter(Boolean).length / checks.length) * 100);
}
