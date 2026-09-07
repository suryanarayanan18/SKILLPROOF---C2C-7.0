import type { CodeReviewChallenge } from "./types";

/**
 * Demo challenge for the Interactive "Code Review" Roleplay.
 *
 * This is intentionally vulnerable.
 * The expected vulnerabilities are evaluator-only data and
 * should never be displayed directly to the candidate.
 */
const demoCodeReviewChallenge: CodeReviewChallenge = {
  id: "code-review-demo-001",
  title: "Secure the User Profile Service",
  description:
    "Review this small JavaScript service, identify security vulnerabilities, " +
    "leave review comments, and refactor the code to make it safer.",
  language: "javascript",
  difficulty: "intermediate",
  instructions: [
    "Inspect every file before making changes.",
    "Identify security vulnerabilities and explain why they are dangerous.",
    "Leave review comments on the relevant lines.",
    "Refactor the code to address the vulnerabilities.",
    "Submit your review and updated files for evaluation.",
  ],
  files: [
    {
      path: "server.js",
      language: "javascript",
      content: `const express = require("express");
const { getUser } = require("./userService");

const app = express();

app.get("/user", async (req, res) => {
  const userId = req.query.id;

  const user = await getUser(userId);

  if (!user) {
    return res.status(404).json({ error: "User not found" });
  }

  res.json(user);
});

app.listen(3000, () => {
  console.log("Server running on port 3000");
});`,
    },
    {
      path: "userService.js",
      language: "javascript",
      content: `const db = require("./db");

async function getUser(userId) {
  const query = "SELECT * FROM users WHERE id = " + userId;

  return db.query(query);
}

function runUserFilter(filter) {
  return eval(filter);
}

module.exports = {
  getUser,
  runUserFilter,
};`,
    },
    {
      path: "config.js",
      language: "javascript",
      content: `module.exports = {
  databaseUrl: "postgres://admin:password123@localhost:5432/users",
  apiKey: "sk_demo_123456789",
};`,
    },
  ],
  expectedVulnerabilities: [
    {
      id: "vuln-sql-injection",
      title: "SQL Injection",
      description:
        "User-controlled input is directly concatenated into a SQL query.",
      category: "injection",
      severity: "critical",
      filePath: "userService.js",
      startLine: 4,
      endLine: 4,
    },
    {
      id: "vuln-eval",
      title: "Unsafe eval",
      description:
        "eval executes arbitrary JavaScript supplied through the filter input.",
      category: "unsafe-api",
      severity: "critical",
      filePath: "userService.js",
      startLine: 10,
      endLine: 10,
    },
    {
      id: "vuln-secret",
      title: "Hardcoded credentials",
      description:
        "Database credentials and an API key are stored directly in source code.",
      category: "secrets",
      severity: "high",
      filePath: "config.js",
      startLine: 2,
      endLine: 3,
    },
    {
      id: "vuln-authorization",
      title: "Missing authorization check",
      description:
        "The user endpoint retrieves a user based only on a supplied ID without checking whether the requester is authorized to access that user's data.",
      category: "authorization",
      severity: "high",
      filePath: "server.js",
      startLine: 6,
      endLine: 13,
    },
  ],
};

export = demoCodeReviewChallenge;
