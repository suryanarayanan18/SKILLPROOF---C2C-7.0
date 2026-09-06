/**
 * SkillProof Mock Data Module
 * 
 * NOTE FOR PERSON 3 (AI/Gemini Backend):
 * When you are ready to connect the Python Gemini backend, replace these mock objects
 * or update the API service callers in `flow.js` with calls to:
 * - POST /api/generate_challenge
 * - POST /api/evaluate_solution
 */

const MOCK_CHALLENGES = {
  python: {
    name: "Python",
    version: "Python 3.12",
    intermediate: {
      id: "PY-MED-8821",
      protocolNode: "#PY-8821",
      title: "Resilient Stream Aggregator",
      difficulty: "Intermediate",
      duration: "20 min",
      overview: "You've been asked to improve a data-processing function used by an asynchronous production microservice handling multi-tenant telemetry bursts.",
      task: "Implement `aggregate_payload_stream(events)` to group records into 60-second temporal buckets based on unix timestamps, discard malformed payloads, and return partitions with an execution memory bound.",
      inputOutput: {
        input: "events: List[Dict[str, Any]] - An array of incoming telemetry packets",
        output: "Dict[str, Any] - Partitioned buckets and dropped counts"
      },
      constraints: [
        "Bounded memory footprint: O(N log K) worst-case",
        "Deterministic 60s temporal buckets: ts - (ts % 60)",
        "Malformed payloads missing required envelope keys ('timestamp', 'payload') must be gracefully filtered",
        "Safe error isolation without unhandled exceptions"
      ],
      example: {
        input: `[
  {"timestamp": 1718000010, "payload": "METRIC_CPU_IDLE"},
  {"timestamp": 1718000045, "payload": "METRIC_MEM_USED"},
  {"raw": "corrupt_data"}
]`,
        output: `{
  "status": "success",
  "partitions": {
    "1718000000": [
      {"timestamp": 1718000010, "payload": "METRIC_CPU_IDLE"},
      {"timestamp": 1718000045, "payload": "METRIC_MEM_USED"}
    ]
  },
  "malformed_dropped": 1
}`
      },
      starterCode: `from typing import List, Dict, Any
from collections import defaultdict

def aggregate_payload_stream(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Groups events into 60s temporal buckets with schema integrity check.
    O(N log K) bounded memory footprint.
    """
    valid_buckets = defaultdict(list)
    malformed_count = 0
    
    for record in events:
        # Schema validation
        if not isinstance(record, dict) or "timestamp" not in record or "payload" not in record:
            malformed_count += 1
            continue
            
        ts = record["timestamp"]
        bucket_key = str(ts - (ts % 60))
        valid_buckets[bucket_key].append(record)
        
    return {
        "status": "success",
        "partitions": dict(valid_buckets),
        "malformed_dropped": malformed_count
    }
`,
      hint: "Consider using Python's standard collections.defaultdict(list) keyed by ts - (ts % 60). Instead of doing repeated sorting on the full array, collect items into their deterministic temporal bucket and sort each partition individually.",
      tests: [
        { name: "test_temporal_60s_binning", time: "8ms", status: "PASS" },
        { name: "test_malformed_envelope_sanitization", time: "11ms", status: "PASS" },
        { name: "test_memory_bounded_10k_burst", time: "9ms", status: "PASS" }
      ]
    },
    beginner: {
      id: "PY-BEG-1012",
      protocolNode: "#PY-1012",
      title: "Payload Sanitizer & Deduplicator",
      difficulty: "Beginner",
      duration: "10 min",
      overview: "Clean and validate an incoming event array by stripping empty payloads and duplicate IDs.",
      task: "Implement `sanitize_records(records)` to filter invalid records and eliminate duplicate IDs preserving the earliest entry.",
      inputOutput: {
        input: "records: List[Dict[str, Any]]",
        output: "List[Dict[str, Any]]"
      },
      constraints: [
        "Unique record IDs only",
        "O(N) time complexity",
        "Preserve original order"
      ],
      example: {
        input: `[{"id": 1, "val": "ok"}, {"id": 1, "val": "dup"}]`,
        output: `[{"id": 1, "val": "ok"}]`
      },
      starterCode: `from typing import List, Dict, Any

def sanitize_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen_ids = set()
    sanitized = []
    for r in records:
        if r.get("id") and r["id"] not in seen_ids:
            seen_ids.add(r["id"])
            sanitized.append(r)
    return sanitized
`,
      hint: "Use a set() to track unique IDs encountered while iterating through records once.",
      tests: [
        { name: "test_deduplication", time: "4ms", status: "PASS" },
        { name: "test_empty_removal", time: "5ms", status: "PASS" }
      ]
    },
    advanced: {
      id: "PY-ADV-9904",
      protocolNode: "#PY-9904",
      title: "Concurrent Token-Bucket Rate Limiter",
      difficulty: "Advanced",
      duration: "45 min",
      overview: "Design a thread-safe token bucket rate limiter supporting microsecond sliding windows.",
      task: "Implement `TokenBucketLimiter` with acquire() and refill() methods supporting burst capacities.",
      inputOutput: {
        input: "rate: float, capacity: int",
        output: "bool on acquire()"
      },
      constraints: [
        "Thread-safe synchronization",
        "Zero drift on clock drift",
        "Sub-millisecond latency"
      ],
      example: {
        input: "limiter.acquire('client_1', tokens=2)",
        output: "True (or False if depleted)"
      },
      starterCode: `import time
from threading import Lock

class TokenBucketLimiter:
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.monotonic()
        self.lock = Lock()

    def acquire(self, tokens: int = 1) -> bool:
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
`,
      hint: "Use `time.monotonic()` for robust interval calculations resistant to NTP time shifts.",
      tests: [
        { name: "test_burst_allowance", time: "12ms", status: "PASS" },
        { name: "test_concurrency_lock", time: "24ms", status: "PASS" }
      ]
    }
  },
  javascript: {
    name: "JavaScript",
    version: "ES2024 Node.js",
    intermediate: {
      id: "JS-MED-4412",
      protocolNode: "#JS-4412",
      title: "Asynchronous Batch Event Dispatcher",
      difficulty: "Intermediate",
      duration: "20 min",
      overview: "Process high-frequency browser telemetry with automatic debouncing and retry resilience.",
      task: "Implement `createBatchDispatcher(flushFn, { maxBatchSize, flushIntervalMs })`.",
      inputOutput: {
        input: "flushFn: Function, options: Object",
        output: "dispatcher: { push(item), flush() }"
      },
      constraints: [
        "No dropped events on abrupt flush",
        "Timer resets after full batch threshold",
        "Safe error isolation"
      ],
      example: {
        input: "dispatcher.push({ type: 'click' })",
        output: "Dispatched in batches"
      },
      starterCode: `export function createBatchDispatcher(flushFn, { maxBatchSize = 10, flushIntervalMs = 500 } = {}) {
  let queue = [];
  let timer = null;

  async function flush() {
    if (timer) clearTimeout(timer);
    timer = null;
    if (queue.length === 0) return;
    const batch = [...queue];
    queue = [];
    await flushFn(batch);
  }

  function push(item) {
    queue.push(item);
    if (queue.length >= maxBatchSize) {
      flush();
    } else if (!timer) {
      timer = setTimeout(flush, flushIntervalMs);
    }
  }

  return { push, flush };
}
`,
      hint: "Ensure `clearTimeout` is invoked prior to executing batch dispatch to prevent double-flushing.",
      tests: [
        { name: "test_batch_threshold_trigger", time: "6ms", status: "PASS" },
        { name: "test_debounce_timer_flush", time: "14ms", status: "PASS" }
      ]
    }
  }
};

const MOCK_EVALUATION = {
  overallScore: 82,
  maxScore: 100,
  previousScore: 61,
  scoreDelta: "+21 points from previous attempt",
  percentile: "92nd Percentile (Runtime/Mem)",
  verdictTitle: "Strong practical performance",
  verdictCertified: true,
  summary: "Execution demonstrated production-grade determinism with an exceptional O(N log K) algorithmic baseline. Candidate exhibits mastery over structured Python generator constructs, memory isolation, and safe type casting under constrained buffer allocations.",
  quote: "“You demonstrated strong problem-solving ability and a clear understanding of the underlying logic. Your solution was correct and well structured, but there is room to improve efficiency and edge-case handling.”",
  radar: {
    problemSolving: 91,
    correctness: 88,
    codeQuality: 76,
    efficiency: 84,
    understanding: 90,
    practicalApplication: 87
  },
  telemetry: {
    runtime: "28 ms",
    runtimeBracket: "Top 4% bracket",
    heapAllocation: "18.4 MB",
    heapCap: "Cap: 64.0 MB",
    suitePass: "100% Pass",
    suiteVectors: "24/24 Test vectors",
    linter: "9.8 / 10",
    linterStandard: "PEP 8 Strict"
  },
  strengths: [
    {
      title: "Clear problem decomposition",
      desc: "Isolated helper routines systematically, ensuring single-responsibility handlers across data parsers."
    },
    {
      title: "Correct implementation",
      desc: "Achieved flawless deterministic equivalence over all nominal fixtures and boundary permutations."
    },
    {
      title: "Strong understanding of edge cases",
      desc: "Preempted buffer overflow scenarios when simulated stream throttled at dynamic chunk intervals."
    }
  ],
  weaknesses: [
    {
      title: "String allocation in bucket keys",
      desc: "Repeated string parsing in timestamp bucketing creates micro-allocations under extreme burst loads."
    },
    {
      title: "Intermediate list materialization",
      desc: "Consider using generator pipelines to reduce peak RSS memory footprint when partitioning."
    }
  ],
  nextAdaptiveStep: {
    title: "Your next challenge: O(N) Streaming Window Buffer",
    desc: "Designed around the areas you can improve: iteration constraints, dynamic sliding registers, and defensive null guards.",
    estimatedDuration: "25 mins",
    testCases: "3 Calibration Test Cases",
    targetScore: "90+ Score"
  },
  passport: {
    id: "SKP-9082-PY",
    nodeVersion: "PROD-v4.1",
    issueDate: "OCT 24, 2024",
    title: "SkillProof Hermetic Passport",
    credential: "Python · Intermediate Level 2",
    proofHash: "ed25519::729a4c89110037",
    assessor: "Dr. A. Vance (Neural Assessor Node-07)",
    verifiedSkills: [
      { name: "Algorithmic Efficiency", level: "Tier 1 Advanced", score: "88%" },
      { name: "Asynchronous Pipelines", level: "Tier 2 Proficient", score: "84%" },
      { name: "Data Ingestion & Filtering", level: "Tier 1 Advanced", score: "91%" },
      { name: "Defensive Error Isolation", level: "Tier 1 Advanced", score: "87%" }
    ]
  }
};

// Export to window object for pure client-side consumption
if (typeof window !== "undefined") {
  window.SkillProofData = {
    challenges: MOCK_CHALLENGES,
    evaluation: MOCK_EVALUATION
  };
}
