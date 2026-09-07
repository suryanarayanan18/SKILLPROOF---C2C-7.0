import demoCodeReviewChallenge = require("./challenge");
import mockCodeReviewService = require("./service");
import type {
  CodeReviewEvaluation,
  CodeReviewSubmission,
  ReviewComment,
} from "./types";

const expectedVulnerabilityIds = [
  "vuln-sql-injection",
  "vuln-eval",
  "vuln-secret",
  "vuln-authorization",
];

type TestResult = {
  name: string;
  passed: boolean;
  reason?: string;
};

function assertTest(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

function getVulnerabilityIds(evaluation: CodeReviewEvaluation): string[] {
  return evaluation.vulnerabilitiesFound.map(
    (vulnerability) => vulnerability.vulnerabilityId,
  );
}

function printEvaluation(evaluation: CodeReviewEvaluation): void {
  console.log("overallScore:", evaluation.overallScore);
  console.log("securityAwarenessScore:", evaluation.securityAwarenessScore);
  console.log("refactoringQualityScore:", evaluation.refactoringQualityScore);
  console.log(
    "vulnerabilitiesFound:",
    evaluation.vulnerabilitiesFound.map(
      (vulnerability) => `${vulnerability.vulnerabilityId}: ${vulnerability.identified}`,
    ),
  );
  console.log(
    "vulnerabilitiesMissed:",
    evaluation.vulnerabilitiesMissed.map(
      (vulnerability) => `${vulnerability.vulnerabilityId}: ${vulnerability.identified}`,
    ),
  );
  console.log("feedback:", evaluation.feedback);
  console.log("nextChallengeFocus:", evaluation.nextChallengeFocus);
}

function strongReviewComments(prefix: string): ReviewComment[] {
  return [
    {
      id: `${prefix}-sql-injection`,
      filePath: "userService.js",
      line: 4,
      comment:
        "Critical SQL injection risk: concatenated user input allows unsafe database access. Replace it with a parameterized query.",
      category: "injection",
      severity: "critical",
    },
    {
      id: `${prefix}-eval`,
      filePath: "userService.js",
      line: 10,
      comment:
        "Critical unsafe eval permits arbitrary JavaScript execution from untrusted input. Remove eval and use a constrained allowlist-based parser.",
      category: "unsafe-api",
      severity: "critical",
    },
    {
      id: `${prefix}-secret`,
      filePath: "config.js",
      line: 2,
      comment:
        "High severity hardcoded credentials expose secrets in source control. Replace them with values loaded from environment configuration.",
      category: "secrets",
      severity: "high",
    },
    {
      id: `${prefix}-authorization`,
      filePath: "server.js",
      line: 9,
      comment:
        "High severity missing authorization allows access to another user's data. Add an ownership or permission check before returning the record.",
      category: "authorization",
      severity: "high",
    },
  ];
}

function strongRefactoredFiles(): CodeReviewSubmission["refactoredFiles"] {
  return [
    {
      path: "server.js",
      content:
        "const authenticatedUser = req.user;\nif (!authenticatedUser || authenticatedUser.id !== userId) {\n  return res.status(403).json({ error: \"Forbidden\" });\n}",
    },
    {
      path: "userService.js",
      content:
        "async function getUser(userId) {\n  return db.query(\"SELECT * FROM users WHERE id = ?\", [userId]);\n}\n\nfunction runUserFilter(filter) {\n  return filter;\n}",
    },
    {
      path: "config.js",
      content:
        "module.exports = {\n  databaseUrl: process.env.DATABASE_URL,\n  apiKey: process.env.API_KEY,\n};",
    },
  ];
}

function makeSubmission(
  reviewComments: ReviewComment[],
  refactoredFiles: CodeReviewSubmission["refactoredFiles"],
): CodeReviewSubmission {
  return {
    challengeId: demoCodeReviewChallenge.id,
    reviewComments,
    refactoredFiles,
  };
}

async function run(): Promise<void> {
  const challenge = demoCodeReviewChallenge;
  const testResults: TestResult[] = [];
  const recordTest = (name: string, passed: boolean, reason: string): void => {
    testResults.push(
      passed ? { name, passed } : { name, passed, reason },
    );
  };
  const runAdditionalTest = async (
    name: string,
    test: () => Promise<void>,
  ): Promise<void> => {
    try {
      await test();
      recordTest(name, true, "");
    } catch (error: unknown) {
      const reason = error instanceof Error ? error.message : String(error);
      console.error(`${name} failed:`, reason);
      recordTest(name, false, reason);
    }
  };

  console.log("title:", challenge.title);
  console.log("files:");
  for (const file of challenge.files) {
    console.log(file.path);
  }

  const submission: CodeReviewSubmission = {
    challengeId: challenge.id,
    reviewComments: [
      {
        id: "comment-sql-injection",
        filePath: "userService.js",
        line: 4,
        comment:
          "Critical SQL injection risk: user input is concatenated into the query. Use a parameterized query to prevent unsafe access.",
        category: "injection",
        severity: "critical",
      },
    ],
    refactoredFiles: [
      {
        path: "server.js",
        content: `const express = require("express");
const { getUser } = require("./userService");

const app = express();

app.get("/user", async (req, res) => {
  const userId = req.query.id;
  const authenticatedUser = req.user;

  if (!authenticatedUser || authenticatedUser.id !== userId) {
    return res.status(403).json({ error: "Forbidden" });
  }

  const user = await getUser(userId);

  if (!user) {
    return res.status(404).json({ error: "User not found" });
  }

  res.json(user);
});`,
      },
      {
        path: "userService.js",
        content: `const db = require("./db");

async function getUser(userId) {
  return db.query("SELECT * FROM users WHERE id = ?", [userId]);
}

function runUserFilter(filter) {
  return filter;
}

module.exports = {
  getUser,
  runUserFilter,
};`,
      },
      {
        path: "config.js",
        content: `module.exports = {
  databaseUrl: process.env.DATABASE_URL,
  apiKey: process.env.API_KEY,
};`,
      },
    ],
  };

  const evaluation = await mockCodeReviewService.evaluateSubmission(submission);

  console.log("overallScore:", evaluation.overallScore);
  console.log("vulnerabilitiesFound:", evaluation.vulnerabilitiesFound);
  console.log("vulnerabilitiesMissed:", evaluation.vulnerabilitiesMissed);
  console.log(
    "securityAwarenessScore:",
    evaluation.securityAwarenessScore,
  );
  console.log(
    "refactoringQualityScore:",
    evaluation.refactoringQualityScore,
  );
  console.log("feedback:", evaluation.feedback);
  console.log("nextChallengeFocus:", evaluation.nextChallengeFocus);

  const completeReviewSubmission: CodeReviewSubmission = {
    challengeId: challenge.id,
    reviewComments: [
      {
        id: "complete-comment-sql-injection",
        filePath: "userService.js",
        line: 4,
        comment:
          "Critical SQL injection risk: user input is concatenated into the query, allowing unsafe database access. Use a parameterized query.",
        category: "injection",
        severity: "critical",
      },
      {
        id: "complete-comment-unsafe-eval",
        filePath: "userService.js",
        line: 10,
        comment:
          "Critical unsafe eval allows arbitrary JavaScript execution from the filter input. Remove eval and use an allowlist or constrained parser.",
        category: "unsafe-api",
        severity: "critical",
      },
      {
        id: "complete-comment-hardcoded-secrets",
        filePath: "config.js",
        line: 2,
        comment:
          "High severity hardcoded credentials expose secrets in source control. Load the database URL and API key from environment configuration.",
        category: "secrets",
        severity: "high",
      },
      {
        id: "complete-comment-authorization",
        filePath: "server.js",
        line: 9,
        comment:
          "High severity missing authorization allows access to another user's data. Add an ownership or permission check before reading the user.",
        category: "authorization",
        severity: "high",
      },
    ],
    refactoredFiles: [],
  };

  const completeEvaluation =
    await mockCodeReviewService.evaluateSubmission(completeReviewSubmission);

  console.log("complete review evaluation:");
  console.log("overallScore:", completeEvaluation.overallScore);
  console.log(
    "securityAwarenessScore:",
    completeEvaluation.securityAwarenessScore,
  );
  console.log(
    "refactoringQualityScore:",
    completeEvaluation.refactoringQualityScore,
  );
  console.log(
    "vulnerabilitiesFound:",
    completeEvaluation.vulnerabilitiesFound,
  );
  console.log(
    "vulnerabilitiesMissed:",
    completeEvaluation.vulnerabilitiesMissed,
  );
  console.log("feedback:", completeEvaluation.feedback);

  const emptyReviewSubmission: CodeReviewSubmission = {
    challengeId: challenge.id,
    reviewComments: [],
    refactoredFiles: [],
  };

  const emptyEvaluation =
    await mockCodeReviewService.evaluateSubmission(emptyReviewSubmission);

  console.log("=== EMPTY SUBMISSION TEST ===");
  console.log("overallScore:", emptyEvaluation.overallScore);
  console.log(
    "securityAwarenessScore:",
    emptyEvaluation.securityAwarenessScore,
  );
  console.log(
    "refactoringQualityScore:",
    emptyEvaluation.refactoringQualityScore,
  );
  console.log("vulnerabilitiesFound:", emptyEvaluation.vulnerabilitiesFound);
  console.log("vulnerabilitiesMissed:", emptyEvaluation.vulnerabilitiesMissed);
  console.log("feedback:", emptyEvaluation.feedback);
  console.log("nextChallengeFocus:", emptyEvaluation.nextChallengeFocus);

  const perfectReviewSubmission: CodeReviewSubmission = {
    challengeId: challenge.id,
    reviewComments: [
      {
        id: "perfect-comment-sql-injection",
        filePath: "userService.js",
        line: 4,
        comment:
          "Critical SQL injection risk: concatenating user input into the query allows unsafe database access. Replace it with a parameterized query.",
        category: "injection",
        severity: "critical",
      },
      {
        id: "perfect-comment-unsafe-eval",
        filePath: "userService.js",
        line: 10,
        comment:
          "Critical unsafe eval permits arbitrary JavaScript execution from untrusted input. Remove eval and use a constrained allowlist-based parser.",
        category: "unsafe-api",
        severity: "critical",
      },
      {
        id: "perfect-comment-hardcoded-secrets",
        filePath: "config.js",
        line: 2,
        comment:
          "High severity hardcoded credentials expose secrets in source control. Replace them with values loaded from environment configuration.",
        category: "secrets",
        severity: "high",
      },
      {
        id: "perfect-comment-authorization",
        filePath: "server.js",
        line: 9,
        comment:
          "High severity missing authorization allows access to another user's data. Add an ownership or permission check before returning the record.",
        category: "authorization",
        severity: "high",
      },
    ],
    refactoredFiles: [
      {
        path: "server.js",
        content:
          "const authenticatedUser = req.user;\nif (!authenticatedUser || authenticatedUser.id !== userId) {\n  return res.status(403).json({ error: \"Forbidden\" });\n}",
      },
      {
        path: "userService.js",
        content:
          "async function getUser(userId) {\n  return db.query(\"SELECT * FROM users WHERE id = ?\", [userId]);\n}\n\nfunction runUserFilter(filter) {\n  return filter;\n}",
      },
      {
        path: "config.js",
        content:
          "module.exports = {\n  databaseUrl: process.env.DATABASE_URL,\n  apiKey: process.env.API_KEY,\n};",
      },
    ],
  };

  const perfectEvaluation =
    await mockCodeReviewService.evaluateSubmission(perfectReviewSubmission);

  console.log("=== PERFECT SUBMISSION TEST ===");
  console.log("overallScore:", perfectEvaluation.overallScore);
  console.log(
    "securityAwarenessScore:",
    perfectEvaluation.securityAwarenessScore,
  );
  console.log("vulnerabilitiesFound:", perfectEvaluation.vulnerabilitiesFound);
  console.log("vulnerabilitiesMissed:", perfectEvaluation.vulnerabilitiesMissed);
  console.log("feedback:", perfectEvaluation.feedback);

  const partialReviewSubmission: CodeReviewSubmission = {
    challengeId: challenge.id,
    reviewComments: [
      {
        id: "partial-comment-sql-injection",
        filePath: "userService.js",
        line: 4,
        comment:
          "Critical SQL injection risk: concatenated user input allows unsafe database access. Replace the string concatenation with a parameterized query.",
        category: "injection",
        severity: "critical",
      },
      {
        id: "partial-comment-unsafe-eval",
        filePath: "userService.js",
        line: 10,
        comment:
          "Critical unsafe eval allows arbitrary JavaScript execution from untrusted input. Remove eval and use a constrained allowlist-based parser.",
        category: "unsafe-api",
        severity: "critical",
      },
    ],
    refactoredFiles: [],
  };

  const partialEvaluation =
    await mockCodeReviewService.evaluateSubmission(partialReviewSubmission);

  console.log("=== PARTIAL SUBMISSION TEST ===");
  console.log("overallScore:", partialEvaluation.overallScore);
  console.log(
    "securityAwarenessScore:",
    partialEvaluation.securityAwarenessScore,
  );
  console.log("vulnerabilitiesFound:", partialEvaluation.vulnerabilitiesFound);
  console.log("vulnerabilitiesMissed:", partialEvaluation.vulnerabilitiesMissed);
  console.log("feedback:", partialEvaluation.feedback);
  console.log("nextChallengeFocus:", partialEvaluation.nextChallengeFocus);

  recordTest(
    "Test 1 — Empty submission",
    emptyEvaluation.vulnerabilitiesFound.length === 0 &&
      emptyEvaluation.vulnerabilitiesMissed.length === 4 &&
      emptyEvaluation.securityAwarenessScore === 0 &&
      emptyEvaluation.overallScore < 50 &&
      Boolean(emptyEvaluation.nextChallengeFocus) &&
      emptyEvaluation.feedback.includes("identified 0 of 4"),
    "Empty submission did not produce the expected low scores and missed-vulnerability feedback.",
  );
  recordTest(
    "Test 2 — Perfect vulnerability review",
    getVulnerabilityIds(completeEvaluation).length === 4 &&
      completeEvaluation.vulnerabilitiesMissed.length === 0 &&
      completeEvaluation.securityAwarenessScore === 100 &&
      completeEvaluation.vulnerabilitiesFound.every(
        (vulnerability) =>
          (vulnerability.accuracyScore ?? 0) >= 80 &&
          (vulnerability.severityAwarenessScore ?? 0) >= 80 &&
          (vulnerability.explanationQualityScore ?? 0) >= 80,
      ) &&
      completeEvaluation.overallScore >= 80 &&
      completeEvaluation.feedback.includes("All expected issues were identified"),
    "The perfect vulnerability review did not meet all expected evaluation thresholds.",
  );
  recordTest(
    "Test 3 — Partial review",
    getVulnerabilityIds(partialEvaluation).length === 2 &&
      partialEvaluation.vulnerabilitiesMissed.length === 2 &&
      partialEvaluation.securityAwarenessScore === 50 &&
      partialEvaluation.feedback.includes("identified 2 of 4") &&
      Boolean(partialEvaluation.nextChallengeFocus),
    "The partial review did not report exactly two found and two missed vulnerabilities.",
  );
  recordTest(
    "Test 4 — Good review + no refactoring",
    completeEvaluation.securityAwarenessScore === 100 &&
      completeEvaluation.vulnerabilitiesMissed.length === 0 &&
      completeEvaluation.refactoringQualityScore < 100 &&
      completeEvaluation.feedback.includes("refactoring"),
    "The no-refactoring review was not distinguished from a fully refactored review.",
  );
  recordTest(
    "Test 5 — Good review + strong refactoring",
    perfectEvaluation.securityAwarenessScore === 100 &&
      perfectEvaluation.vulnerabilitiesMissed.length === 0 &&
      perfectEvaluation.refactoringQualityScore === 100 &&
      perfectEvaluation.overallScore >= 90,
    "The strong-refactoring review did not receive the expected high evaluation.",
  );

  let badRefactoringScore = 0;

  await runAdditionalTest("Test 6 — Bad refactoring", async () => {
    const badRefactoringSubmission = makeSubmission(strongReviewComments("bad"), [
      {
        path: "server.js",
        content: "const userId = req.query.id;\nreturn getUser(userId);",
      },
      {
        path: "userService.js",
        content:
          "const query = \"SELECT * FROM users WHERE id = \" + userId;\nreturn db.query(query);\nreturn eval(filter);",
      },
      {
        path: "config.js",
        content:
          "module.exports = { databaseUrl: \"postgres://admin:password123@localhost/users\", apiKey: \"sk_demo_123456789\" };",
      },
    ]);
    const badRefactoringEvaluation =
      await mockCodeReviewService.evaluateSubmission(badRefactoringSubmission);
    badRefactoringScore = badRefactoringEvaluation.refactoringQualityScore;

    console.log("=== BAD REFACTORING TEST ===");
    printEvaluation(badRefactoringEvaluation);
    assertTest(
      getVulnerabilityIds(badRefactoringEvaluation).length === 4 &&
        badRefactoringEvaluation.vulnerabilitiesMissed.length === 0 &&
        badRefactoringEvaluation.refactoringQualityScore <
          perfectEvaluation.refactoringQualityScore &&
        badRefactoringEvaluation.overallScore < perfectEvaluation.overallScore,
      "Poor refactoring was not scored lower than the strong refactoring case.",
    );
  });

  await runAdditionalTest("Test 7 — Strong vs weak explanations", async () => {
    const weakComments: ReviewComment[] = [
      { id: "weak-sql", filePath: "userService.js", line: 4, comment: "sql" },
      { id: "weak-eval", filePath: "userService.js", line: 10, comment: "eval" },
      { id: "weak-secret", filePath: "config.js", line: 2, comment: "secret" },
      {
        id: "weak-authorization",
        filePath: "server.js",
        line: 9,
        comment: "authorization",
      },
    ];
    const strongExplanationEvaluation = await mockCodeReviewService.evaluateSubmission(
      makeSubmission(strongReviewComments("strong-explanations"), []),
    );
    const weakExplanationEvaluation = await mockCodeReviewService.evaluateSubmission(
      makeSubmission(weakComments, []),
    );

    console.log("=== STRONG VS WEAK EXPLANATIONS TEST ===");
    console.log("strong explanation evaluation:");
    printEvaluation(strongExplanationEvaluation);
    console.log("weak explanation evaluation:");
    printEvaluation(weakExplanationEvaluation);
    assertTest(
      getVulnerabilityIds(strongExplanationEvaluation).length === 4 &&
        getVulnerabilityIds(weakExplanationEvaluation).length === 4 &&
        strongExplanationEvaluation.reasoningScore >
          weakExplanationEvaluation.reasoningScore &&
        strongExplanationEvaluation.overallScore >
          weakExplanationEvaluation.overallScore,
      "Strong and weak explanations did not receive appropriately different scores.",
    );
  });

  await runAdditionalTest("Test 8 — Wrong vulnerability IDs", async () => {
    const wrongIdSource = strongReviewComments("wrong-id");
    const wrongIds = [
      "vuln-xss",
      "vuln-random",
      "vuln-fake",
      "vuln-unknown",
    ];
    const wrongIdComments: ReviewComment[] = wrongIdSource.map(
      (comment, index) => {
        const wrongId = wrongIds[index];
        if (!wrongId) {
          throw new Error("Missing wrong vulnerability ID fixture.");
        }
        return { ...comment, vulnerabilityId: wrongId };
      },
    );
    const wrongIdEvaluation = await mockCodeReviewService.evaluateSubmission(
      makeSubmission(wrongIdComments, []),
    );

    console.log("=== WRONG VULNERABILITY IDS TEST ===");
    printEvaluation(wrongIdEvaluation);
    assertTest(
      wrongIdEvaluation.vulnerabilitiesFound.length === 0 &&
        wrongIdEvaluation.vulnerabilitiesMissed.length === 4,
      "The current evaluator counted comments with unknown IDs based on their text.",
    );
  });

  await runAdditionalTest("Test 9 — Duplicate comments", async () => {
    const sqlComment = strongReviewComments("duplicate")[0];
    if (!sqlComment) {
      throw new Error("The duplicate-comment fixture was not created.");
    }
    const duplicateEvaluation = await mockCodeReviewService.evaluateSubmission(
      makeSubmission(
        [
          sqlComment,
          { ...sqlComment, id: "duplicate-sql-2" },
          { ...sqlComment, id: "duplicate-sql-3" },
        ],
        [],
      ),
    );
    const foundIds = getVulnerabilityIds(duplicateEvaluation);

    console.log("=== DUPLICATE COMMENTS TEST ===");
    printEvaluation(duplicateEvaluation);
    assertTest(
      foundIds.length === 1 &&
        new Set(foundIds).size === foundIds.length &&
        duplicateEvaluation.vulnerabilitiesMissed.length === 3,
      "Duplicate comments changed the result beyond one unique expected vulnerability.",
    );
  });

  await runAdditionalTest("Test 10 — Empty/minimal explanations", async () => {
    const minimalEvaluation = await mockCodeReviewService.evaluateSubmission(
      makeSubmission(
        [
          { id: "minimal-sql", filePath: "userService.js", line: 4, comment: "sql" },
          { id: "minimal-eval", filePath: "userService.js", line: 10, comment: "eval" },
          { id: "minimal-secret", filePath: "config.js", line: 2, comment: "secret" },
          {
            id: "minimal-authorization",
            filePath: "server.js",
            line: 9,
            comment: "authorization",
          },
        ],
        [],
      ),
    );
    const strongExplanationEvaluation = await mockCodeReviewService.evaluateSubmission(
      makeSubmission(strongReviewComments("quality"), []),
    );
    const strongExplanationQuality = strongExplanationEvaluation.vulnerabilitiesFound
      .map((vulnerability) => vulnerability.explanationQualityScore ?? 0);

    console.log("=== EMPTY/MINIMAL EXPLANATIONS TEST ===");
    printEvaluation(minimalEvaluation);
    assertTest(
      minimalEvaluation.vulnerabilitiesFound.length === 4 &&
        minimalEvaluation.reasoningScore <
          strongExplanationQuality.reduce((total, score) => total + score, 0) /
            strongExplanationQuality.length,
      "Minimal explanations received the same reasoning quality as strong explanations.",
    );
  });

  await runAdditionalTest("Test 11 — Partial refactoring", async () => {
    const partialRefactoringEvaluation =
      await mockCodeReviewService.evaluateSubmission(
        makeSubmission(strongReviewComments("partial-refactoring"), [
          {
            path: "userService.js",
            content:
              "return db.query(\"SELECT * FROM users WHERE id = ?\", [userId]);\nreturn eval(filter);",
          },
          {
            path: "config.js",
            content:
              "module.exports = { databaseUrl: process.env.DATABASE_URL, apiKey: process.env.API_KEY };",
          },
          {
            path: "server.js",
            content: "const userId = req.query.id;\nreturn getUser(userId);",
          },
        ]),
      );

    console.log("=== PARTIAL REFACTORING TEST ===");
    printEvaluation(partialRefactoringEvaluation);
    assertTest(
      partialRefactoringEvaluation.vulnerabilitiesFound.length === 4 &&
        partialRefactoringEvaluation.vulnerabilitiesMissed.length === 0 &&
        partialRefactoringEvaluation.refactoringQualityScore > badRefactoringScore &&
        partialRefactoringEvaluation.refactoringQualityScore <
          perfectEvaluation.refactoringQualityScore,
      "Partial refactoring did not score between bad and strong refactoring.",
    );
  });

  await runAdditionalTest("Test 12 — Repeated evaluations", async () => {
    const beforeChallenge = JSON.stringify(challenge);
    const beforeSubmission = JSON.stringify(perfectReviewSubmission);
    const repeatedEvaluations = await Promise.all([
      mockCodeReviewService.evaluateSubmission(perfectReviewSubmission),
      mockCodeReviewService.evaluateSubmission(perfectReviewSubmission),
      mockCodeReviewService.evaluateSubmission(perfectReviewSubmission),
    ]);
    const first = repeatedEvaluations[0];
    const consistent = repeatedEvaluations.every(
      (evaluation) =>
        JSON.stringify(getVulnerabilityIds(evaluation)) ===
          JSON.stringify(getVulnerabilityIds(first)) &&
        JSON.stringify(evaluation.vulnerabilitiesMissed) ===
          JSON.stringify(first.vulnerabilitiesMissed) &&
        evaluation.overallScore === first.overallScore &&
        evaluation.securityAwarenessScore === first.securityAwarenessScore &&
        evaluation.refactoringQualityScore === first.refactoringQualityScore,
    );

    console.log("=== REPEATED EVALUATIONS TEST ===");
    printEvaluation(first);
    assertTest(
      consistent &&
        JSON.stringify(challenge) === beforeChallenge &&
        JSON.stringify(perfectReviewSubmission) === beforeSubmission,
      "Repeated evaluations were inconsistent or mutated the challenge/submission.",
    );
  });

  console.log("==================================================");
  console.log("CODE REVIEW ROLEPLAY TEST SUMMARY");
  console.log("==================================================");
  for (const result of testResults) {
    console.log(
      `${result.name}: ${result.passed ? "PASS" : "FAIL"}${
        result.reason ? ` — ${result.reason}` : ""
      }`,
    );
  }
  console.log("total tests:", testResults.length);
  console.log("passed tests:", testResults.filter((result) => result.passed).length);
  console.log("failed tests:", testResults.filter((result) => !result.passed).length);
}

void run();
