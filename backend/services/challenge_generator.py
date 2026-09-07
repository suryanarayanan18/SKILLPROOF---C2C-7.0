"""Template variation and transformation engine for SkillProof.

Performs structured, explainable transformations on local seed problems:
  seeded competency
  → structured transformation (domain adaptation + parameter scaling)
  → unique assessment instance
  → generated hidden tests (normal, boundary, edge)
  → reference-solution validation
  → candidate receives only the public problem view (reference solution and hidden tests are never exposed).

Zero runtime generative-AI or external API dependencies.
"""

from __future__ import annotations

import copy
import json
import logging
from collections import Counter, OrderedDict, defaultdict
import heapq
from pathlib import Path
import random
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from services.problem_validator import validate_problem

logger = logging.getLogger("skillproof.generator")

PROBLEMS_DIR = Path(__file__).resolve().parent.parent / "data" / "problems"


def load_seed_problems() -> List[Dict[str, Any]]:
    """Load all hand-authored seed problem JSON files from data/problems."""
    problems = []
    if not PROBLEMS_DIR.exists():
        return problems
    for p in sorted(PROBLEMS_DIR.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                problems.append(json.load(f))
        except Exception:
            continue
    return problems


# ---------------------------------------------------------------------------
# Verified Reference Oracles for Dynamic Test Case Generation
# ---------------------------------------------------------------------------

def oracle_array_frequency_k(items: List[int], k: int) -> int:
    counts = Counter(items)
    candidates = [val for val, count in counts.items() if count >= k]
    return min(candidates) if candidates else -1


def oracle_sliding_window_anomaly(stream: List[float], window_size: int) -> float:
    if not stream or window_size <= 0 or len(stream) < window_size:
        return 0.0
    w_sum = sum(stream[:window_size])
    max_sum = w_sum
    for i in range(window_size, len(stream)):
        w_sum += stream[i] - stream[i - window_size]
        if w_sum > max_sum:
            max_sum = w_sum
    return round(float(max_sum) / window_size, 2)


def oracle_interval_consolidation(intervals: List[List[int]]) -> List[List[int]]:
    if not intervals:
        return []
    sorted_int = sorted(intervals, key=lambda x: x[0])
    merged = [list(sorted_int[0])]
    for cur in sorted_int[1:]:
        prev = merged[-1]
        if cur[0] <= prev[1]:
            prev[1] = max(prev[1], cur[1])
        else:
            merged.append(list(cur))
    return merged


def oracle_lru_cache_expiry(operations: List[List[Any]], capacity: int) -> List[Any]:
    cache: OrderedDict[Any, Any] = OrderedDict()
    results = []
    for op in operations:
        action = op[0]
        key = op[1]
        if action == "PUT":
            val = op[2]
            if key in cache:
                cache.move_to_end(key)
            elif len(cache) >= capacity:
                cache.popitem(last=False)
            cache[key] = val
        elif action == "GET":
            if key in cache:
                cache.move_to_end(key)
                results.append(cache[key])
            else:
                results.append(None)
    return results


def oracle_graph_dependency_resolver(tasks: List[str], dependencies: List[List[str]]) -> List[str]:
    adj = defaultdict(list)
    in_degree = {t: 0 for t in tasks}
    for task, prereq in dependencies:
        if task in in_degree and prereq in in_degree:
            adj[prereq].append(task)
            in_degree[task] += 1
    heap = [t for t, deg in in_degree.items() if deg == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        curr = heapq.heappop(heap)
        order.append(curr)
        for neighbor in adj[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                heapq.heappush(heap, neighbor)
    return order if len(order) == len(tasks) else []


def oracle_prefix_sum_anomaly(readings: List[int], target: int) -> int:
    prefix_counts = {0: 1}
    csum = 0
    cnt = 0
    for r in readings:
        csum += r
        diff = csum - target
        if diff in prefix_counts:
            cnt += prefix_counts[diff]
        prefix_counts[csum] = prefix_counts.get(csum, 0) + 1
    return cnt


def oracle_stack_syntax_validator(expression: str) -> bool:
    stack = []
    matching = {")": "(", "]": "[", "}": "{"}
    for ch in str(expression):
        if ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            if not stack or stack[-1] != matching[ch]:
                return False
            stack.pop()
    return len(stack) == 0


def oracle_binary_search_threshold(workloads: List[int], k: int) -> int:
    if not workloads:
        return 0
    if k >= len(workloads):
        return max(workloads)
    def feasible(max_load: int) -> bool:
        workers = 1
        cur = 0
        for w in workloads:
            if cur + w > max_load:
                workers += 1
                cur = w
                if workers > k:
                    return False
            else:
                cur += w
        return True
    low, high = max(workloads), sum(workloads)
    ans = high
    while low <= high:
        mid = (low + high) // 2
        if feasible(mid):
            ans = mid
            high = mid - 1
        else:
            low = mid + 1
    return ans


# ---------------------------------------------------------------------------
# Explainable Domain Scenario Definitions
# ---------------------------------------------------------------------------

EXPANDED_SCENARIOS: Dict[str, List[Dict[str, str]]] = {
    "array_frequency_k": [
        {
            "domain_title": "IoT Sensor Telemetry",
            "domain_context": "high-frequency industrial sensor telemetry stream",
            "metric_name": "sensor reading",
            "competency": "Frequency counting and min-heap/threshold candidate selection",
        },
        {
            "domain_title": "FinTech Audit Risk",
            "domain_context": "payment settlement transaction batch",
            "metric_name": "transaction amount ($)",
            "competency": "Frequency counting and min-heap/threshold candidate selection",
        },
        {
            "domain_title": "Warehouse Logistics",
            "domain_context": "e-commerce warehouse SKU fulfillment batch",
            "metric_name": "item barcode ID",
            "competency": "Frequency counting and min-heap/threshold candidate selection",
        },
        {
            "domain_title": "Network Security Monitor",
            "domain_context": "firewall ingress packet log",
            "metric_name": "destination port recurrence",
            "competency": "Frequency counting and min-heap/threshold candidate selection",
        },
    ],
    "sliding_window_anomaly": [
        {
            "domain_title": "Cloud Service Latency",
            "domain_context": "cloud microservice API response latency stream",
            "metric_name": "response latency (ms)",
            "competency": "Fixed-window cumulative aggregation and two-pointer tracking",
        },
        {
            "domain_title": "Network Ingress Throughput",
            "domain_context": "datacenter core router throughput monitor",
            "metric_name": "packet bandwidth (Mbps)",
            "competency": "Fixed-window cumulative aggregation and two-pointer tracking",
        },
        {
            "domain_title": "Server Thermal Controller",
            "domain_context": "server rack processor core temperature log",
            "metric_name": "core temperature (°C)",
            "competency": "Fixed-window cumulative aggregation and two-pointer tracking",
        },
        {
            "domain_title": "High-Frequency Market Flow",
            "domain_context": "algorithmic trading tick feed",
            "metric_name": "microsecond trade price delta ($)",
            "competency": "Fixed-window cumulative aggregation and two-pointer tracking",
        },
    ],
    "interval_consolidation": [
        {
            "domain_title": "Room Booking Calendar",
            "domain_context": "enterprise conference room reservation schedule",
            "metric_name": "occupancy booking block",
            "competency": "Interval sorting, continuous segment compaction, and greedy merging",
        },
        {
            "domain_title": "Disk Sector Allocation",
            "domain_context": "storage volume block allocation manager",
            "metric_name": "sector address block",
            "competency": "Interval sorting, continuous segment compaction, and greedy merging",
        },
        {
            "domain_title": "Infrastructure Maintenance",
            "domain_context": "cloud host downtime schedule",
            "metric_name": "maintenance window",
            "competency": "Interval sorting, continuous segment compaction, and greedy merging",
        },
        {
            "domain_title": "Broadcast Transmission Schedule",
            "domain_context": "media broadcast transmission manager",
            "metric_name": "airtime programming block",
            "competency": "Interval sorting, continuous segment compaction, and greedy merging",
        },
    ],
    "lru_cache_expiry": [
        {
            "domain_title": "Session Token Store",
            "domain_context": "OAuth token validation cache",
            "metric_name": "session token claim",
            "competency": "O(1) dictionary and doubly-linked eviction policy simulation",
        },
        {
            "domain_title": "Edge CDN Buffer",
            "domain_context": "edge CDN static media buffer",
            "metric_name": "cached web asset",
            "competency": "O(1) dictionary and doubly-linked eviction policy simulation",
        },
        {
            "domain_title": "Database Query Cache",
            "domain_context": "prepared SQL statement execution buffer",
            "metric_name": "query result set",
            "competency": "O(1) dictionary and doubly-linked eviction policy simulation",
        },
        {
            "domain_title": "Service Discovery DNS",
            "domain_context": "microservice hostname resolution cache",
            "metric_name": "resolved IP address",
            "competency": "O(1) dictionary and doubly-linked eviction policy simulation",
        },
    ],
    "graph_dependency_resolver": [
        {
            "domain_title": "Software Build System",
            "domain_context": "multi-module compilation artifact pipeline",
            "metric_name": "build target artifact",
            "competency": "Directed acyclic graph topological sorting and cycle detection",
        },
        {
            "domain_title": "Database Migration Engine",
            "domain_context": "relational database schema migration runner",
            "metric_name": "migration revision script",
            "competency": "Directed acyclic graph topological sorting and cycle detection",
        },
        {
            "domain_title": "Cluster Boot Orchestrator",
            "domain_context": "distributed container cluster boot manager",
            "metric_name": "service daemon",
            "competency": "Directed acyclic graph topological sorting and cycle detection",
        },
        {
            "domain_title": "Data Pipeline ETL",
            "domain_context": "data warehouse workflow transformation DAG",
            "metric_name": "transformation stage",
            "competency": "Directed acyclic graph topological sorting and cycle detection",
        },
    ],
    "prefix_sum_anomaly": [
        {
            "domain_title": "Smart Grid Load Telemetry",
            "domain_context": "power grid load telemetry monitoring system",
            "metric_name": "load variance (kW)",
            "competency": "Prefix sum caching and linear hash-map target counting",
        },
        {
            "domain_title": "General Ledger Audit",
            "domain_context": "double-entry accounting audit trail",
            "metric_name": "credit/debit delta ($)",
            "competency": "Prefix sum caching and linear hash-map target counting",
        },
        {
            "domain_title": "Network Error Diagnostics",
            "domain_context": "datacenter packet switch interface monitor",
            "metric_name": "frame drop rate delta",
            "competency": "Prefix sum caching and linear hash-map target counting",
        },
        {
            "domain_title": "Inventory Delta Balance",
            "domain_context": "warehouse stock movement activity log",
            "metric_name": "unit quantity delta",
            "competency": "Prefix sum caching and linear hash-map target counting",
        },
    ],
    "stack_syntax_validator": [
        {
            "domain_title": "JSON/YAML Syntax Parser",
            "domain_context": "hierarchical configuration syntax analyzer",
            "metric_name": "config delimiter",
            "competency": "LIFO stack bracket pairing and nested grammar integrity",
        },
        {
            "domain_title": "SQL Query Filter Engine",
            "domain_context": "database SQL WHERE-clause predicate validator",
            "metric_name": "predicate subclause",
            "competency": "LIFO stack bracket pairing and nested grammar integrity",
        },
        {
            "domain_title": "Compiler Lexer Tokenizer",
            "domain_context": "compiler front-end lexer token stream",
            "metric_name": "syntax token",
            "competency": "LIFO stack bracket pairing and nested grammar integrity",
        },
        {
            "domain_title": "Formula Calculator Engine",
            "domain_context": "financial calculation formula engine",
            "metric_name": "formula expression",
            "competency": "LIFO stack bracket pairing and nested grammar integrity",
        },
    ],
    "binary_search_threshold": [
        {
            "domain_title": "Distributed Compute Scheduler",
            "domain_context": "distributed container batch processing cluster",
            "metric_name": "job compute cost",
            "competency": "Binary search over monotonic solution space and minimax partitioning",
        },
        {
            "domain_title": "Database Shard Manager",
            "domain_context": "table segment row partition controller",
            "metric_name": "shard row allocation",
            "competency": "Binary search over monotonic solution space and minimax partitioning",
        },
        {
            "domain_title": "Cloud Archive Compressor",
            "domain_context": "cloud archive storage compressor",
            "metric_name": "uncompressed batch chunk",
            "competency": "Binary search over monotonic solution space and minimax partitioning",
        },
        {
            "domain_title": "Video Transcoding Farm",
            "domain_context": "media chunk transcoding node cluster",
            "metric_name": "video chunk duration",
            "competency": "Binary search over monotonic solution space and minimax partitioning",
        },
    ],
}


# ---------------------------------------------------------------------------
# Dynamic Test Suite Generator Covering Normal, Boundary, and Edge Cases
# ---------------------------------------------------------------------------

def generate_dynamic_tests(seed_id: str, rng: Optional[random.Random] = None) -> List[Dict[str, Any]]:
    """
    Generates a fresh hidden test suite covering:
      - Normal cases (randomized realistic inputs)
      - Boundary cases (minimal size, maximal threshold, uniform values)
      - Edge cases (negatives, zeroes, cycles, empty inputs, order sensitivity)
    """
    if rng is None:
        rng = random.Random(uuid4().hex)

    tests: List[Dict[str, Any]] = []

    if seed_id == "array_frequency_k":
        # Normal 1: typical mixed array with guaranteed winner
        target1 = rng.randint(2, 8)
        k1 = rng.randint(2, 3)
        items1 = [rng.randint(1, 15) for _ in range(15)] + [target1] * k1
        rng.shuffle(items1)
        tests.append({
            "name": "Normal: Mixed positive telemetry batch",
            "input": {"items": items1, "k": k1},
            "expected": oracle_array_frequency_k(items1, k1),
        })

        # Normal 2: larger stream with multiple frequent values
        k2 = rng.randint(3, 4)
        items2 = [rng.randint(10, 30) for _ in range(25)] + [12] * k2 + [18] * k2
        rng.shuffle(items2)
        tests.append({
            "name": "Normal: High-volume observations with multiple thresholds",
            "input": {"items": items2, "k": k2},
            "expected": oracle_array_frequency_k(items2, k2),
        })

        # Boundary 1: k equals 1 (global minimum of all items)
        b_items1 = [rng.randint(10, 99) for _ in range(6)]
        tests.append({
            "name": "Boundary: K equals 1 returns global minimum",
            "input": {"items": b_items1, "k": 1},
            "expected": oracle_array_frequency_k(b_items1, 1),
        })

        # Boundary 2: k equals length of items, all identical
        val_unif = rng.randint(5, 25)
        tests.append({
            "name": "Boundary: Uniform sequence where K equals length",
            "input": {"items": [val_unif] * 7, "k": 7},
            "expected": val_unif,
        })

        # Edge 1: No element meets frequency threshold (must return -1)
        unique_items = list(range(1, 8))
        tests.append({
            "name": "Edge: No value reaches threshold frequency (returns -1)",
            "input": {"items": unique_items, "k": 2},
            "expected": -1,
        })

        # Edge 2: Negative values (minimum candidate amongst negative integers)
        neg_items = [-20, -5, -20, -5, -20, 10, 10]
        tests.append({
            "name": "Edge: Negative observations with tie-break",
            "input": {"items": neg_items, "k": 2},
            "expected": -20,
        })

    elif seed_id == "sliding_window_anomaly":
        # Normal 1: mixed positive stream
        stream1 = [round(rng.uniform(10.0, 100.0), 2) for _ in range(12)]
        w1 = rng.randint(3, 4)
        tests.append({
            "name": "Normal: Standard positive time-series",
            "input": {"stream": stream1, "window_size": w1},
            "expected": oracle_sliding_window_anomaly(stream1, w1),
        })

        # Normal 2: longer stream
        stream2 = [round(rng.uniform(-20.0, 80.0), 2) for _ in range(20)]
        w2 = rng.randint(4, 5)
        tests.append({
            "name": "Normal: Extended operational telemetry window",
            "input": {"stream": stream2, "window_size": w2},
            "expected": oracle_sliding_window_anomaly(stream2, w2),
        })

        # Boundary 1: Stream shorter than window size (must return 0.0)
        tests.append({
            "name": "Boundary: Stream length shorter than window size (returns 0.0)",
            "input": {"stream": [12.5, 24.0], "window_size": 4},
            "expected": 0.0,
        })

        # Boundary 2: Stream length exactly equals window size
        exact_stream = [10.0, 20.0, 30.0, 40.0]
        tests.append({
            "name": "Boundary: Window size equals entire stream length",
            "input": {"stream": exact_stream, "window_size": 4},
            "expected": 25.0,
        })

        # Boundary 3: Window size equals 1
        tests.append({
            "name": "Boundary: Window size equals 1 (peak single observation)",
            "input": {"stream": [4.5, 99.2, 12.0], "window_size": 1},
            "expected": 99.2,
        })

        # Edge 1: All negative numbers (max window average must be negative, not 0.0)
        all_neg = [-50.0, -20.0, -10.0, -40.0, -15.0]
        tests.append({
            "name": "Edge: Strictly negative values (verifies negative mean)",
            "input": {"stream": all_neg, "window_size": 2},
            "expected": oracle_sliding_window_anomaly(all_neg, 2),
        })

    elif seed_id == "interval_consolidation":
        # Normal 1: randomized intervals with partial overlaps
        intervals1 = []
        for _ in range(6):
            s = rng.randint(1, 40)
            e = s + rng.randint(2, 15)
            intervals1.append([s, e])
        tests.append({
            "name": "Normal: Randomized overlapping scheduling blocks",
            "input": {"intervals": intervals1},
            "expected": oracle_interval_consolidation(intervals1),
        })

        # Normal 2: multiple discrete clusters
        intervals2 = [[1, 5], [2, 6], [10, 15], [12, 18], [25, 30]]
        tests.append({
            "name": "Normal: Clustered overlapping intervals",
            "input": {"intervals": intervals2},
            "expected": [[1, 6], [10, 18], [25, 30]],
        })

        # Boundary 1: Empty interval list
        tests.append({
            "name": "Boundary: Empty intervals list (returns [])",
            "input": {"intervals": []},
            "expected": [],
        })

        # Boundary 2: Single interval
        tests.append({
            "name": "Boundary: Single isolated interval",
            "input": {"intervals": [[42, 99]]},
            "expected": [[42, 99]],
        })

        # Edge 1: Touching endpoints (e.g. [2, 6] and [6, 10] must merge into [2, 10])
        tests.append({
            "name": "Edge: Touching boundaries at exact endpoint",
            "input": {"intervals": [[2, 6], [6, 10], [10, 14]]},
            "expected": [[2, 14]],
        })

        # Edge 2: Fully nested intervals (one large interval swallows inner ones)
        tests.append({
            "name": "Edge: Fully enclosed nested intervals",
            "input": {"intervals": [[1, 50], [10, 20], [25, 35], [5, 45]]},
            "expected": [[1, 50]],
        })

        # Edge 3: Out-of-order reverse sorted disjoint intervals
        tests.append({
            "name": "Edge: Reverse sorted disjoint intervals",
            "input": {"intervals": [[50, 60], [30, 40], [10, 20]]},
            "expected": [[10, 20], [30, 40], [50, 60]],
        })

    elif seed_id == "lru_cache_expiry":
        # Normal 1: capacity 3 with mixed PUT and GET
        cap1 = 3
        ops1 = [
            ["PUT", "user:1", 100],
            ["PUT", "user:2", 200],
            ["PUT", "user:3", 300],
            ["GET", "user:1"],
            ["PUT", "user:4", 400], # user:2 evicted
            ["GET", "user:2"],       # None
            ["GET", "user:3"],       # 300
            ["GET", "user:4"],       # 400
        ]
        tests.append({
            "name": "Normal: Capacity 3 cache lifecycle",
            "input": {"operations": ops1, "capacity": cap1},
            "expected": oracle_lru_cache_expiry(ops1, cap1),
        })

        # Normal 2: randomized operations
        keys_pool = ["A", "B", "C", "D", "E"]
        ops2 = []
        for _ in range(10):
            if rng.random() < 0.6:
                ops2.append(["PUT", rng.choice(keys_pool), rng.randint(1, 99)])
            else:
                ops2.append(["GET", rng.choice(keys_pool)])
        tests.append({
            "name": "Normal: Dynamic randomized operational stream",
            "input": {"operations": ops2, "capacity": 3},
            "expected": oracle_lru_cache_expiry(ops2, 3),
        })

        # Boundary 1: Capacity 1 (eviction on every new key)
        ops_cap1 = [
            ["PUT", "k1", 1],
            ["PUT", "k2", 2],
            ["GET", "k1"], # None
            ["GET", "k2"], # 2
        ]
        tests.append({
            "name": "Boundary: Minimal capacity 1 eviction",
            "input": {"operations": ops_cap1, "capacity": 1},
            "expected": [None, 2],
        })

        # Edge 1: Update existing key updates value AND recency
        ops_update = [
            ["PUT", "k1", 10],
            ["PUT", "k2", 20],
            ["PUT", "k1", 100], # k1 updated to 100 and moved to MRU
            ["PUT", "k3", 30],  # k2 evicted because k1 was refreshed
            ["GET", "k2"],      # None
            ["GET", "k1"],      # 100
        ]
        tests.append({
            "name": "Edge: Updating existing key refreshes recency preventing eviction",
            "input": {"operations": ops_update, "capacity": 2},
            "expected": [None, 100],
        })

        # Edge 2: GET non-existent key returns None without affecting state
        ops_get_miss = [
            ["PUT", "a", 1],
            ["GET", "missing"],
            ["GET", "a"],
        ]
        tests.append({
            "name": "Edge: Cache misses return None without modifying recency",
            "input": {"operations": ops_get_miss, "capacity": 2},
            "expected": [None, 1],
        })

    elif seed_id == "graph_dependency_resolver":
        # Normal 1: 5-step DAG
        tasks1 = ["parse", "validate", "compile", "optimize", "link"]
        deps1 = [
            ["validate", "parse"],
            ["compile", "validate"],
            ["optimize", "compile"],
            ["link", "optimize"],
        ]
        tests.append({
            "name": "Normal: Linear multi-stage pipeline dependency",
            "input": {"tasks": tasks1, "dependencies": deps1},
            "expected": oracle_graph_dependency_resolver(tasks1, deps1),
        })

        # Normal 2: Diamond branching DAG with tie-breaking
        tasks2 = ["init", "auth", "billing", "dashboard"]
        deps2 = [
            ["auth", "init"],
            ["billing", "init"],
            ["dashboard", "auth"],
            ["dashboard", "billing"],
        ]
        tests.append({
            "name": "Normal: Branching diamond pipeline with alphabetical order",
            "input": {"tasks": tasks2, "dependencies": deps2},
            "expected": oracle_graph_dependency_resolver(tasks2, deps2),
        })

        # Boundary 1: Independent tasks (no dependencies -> alphabetical sort)
        indep_tasks = ["zebra", "apple", "mango", "banana"]
        tests.append({
            "name": "Boundary: Independent tasks ordered lexicographically",
            "input": {"tasks": indep_tasks, "dependencies": []},
            "expected": ["apple", "banana", "mango", "zebra"],
        })

        # Boundary 2: Single task
        tests.append({
            "name": "Boundary: Single isolated task",
            "input": {"tasks": ["standalone"], "dependencies": []},
            "expected": ["standalone"],
        })

        # Edge 1: Direct 2-node circular dependency (returns [])
        tests.append({
            "name": "Edge: Immediate circular deadlock returns []",
            "input": {"tasks": ["service_A", "service_B"], "dependencies": [["service_A", "service_B"], ["service_B", "service_A"]]},
            "expected": [],
        })

        # Edge 2: 3-node cycle embedded in larger graph (returns [])
        cycle_tasks = ["T1", "T2", "T3", "T4"]
        cycle_deps = [["T2", "T1"], ["T3", "T2"], ["T1", "T3"], ["T4", "T1"]]
        tests.append({
            "name": "Edge: Embedded cycle in DAG returns []",
            "input": {"tasks": cycle_tasks, "dependencies": cycle_deps},
            "expected": [],
        })

    elif seed_id == "prefix_sum_anomaly":
        # Normal 1: typical mixed array with matches
        arr1 = [rng.randint(-5, 10) for _ in range(12)]
        target1 = rng.randint(2, 10)
        tests.append({
            "name": "Normal: Subarrays matching target sum",
            "input": {"readings": arr1, "target": target1},
            "expected": oracle_prefix_sum_anomaly(arr1, target1),
        })

        # Normal 2: larger array
        arr2 = [rng.randint(-15, 20) for _ in range(16)]
        target2 = rng.randint(0, 12)
        tests.append({
            "name": "Normal: High-entropy telemetry variations",
            "input": {"readings": arr2, "target": target2},
            "expected": oracle_prefix_sum_anomaly(arr2, target2),
        })

        # Boundary 1: Single element matching target
        tests.append({
            "name": "Boundary: Single-element matching exact target",
            "input": {"readings": [7], "target": 7},
            "expected": 1,
        })

        # Boundary 2: Single element not matching target
        tests.append({
            "name": "Boundary: Single-element not matching target",
            "input": {"readings": [3], "target": 5},
            "expected": 0,
        })

        # Edge 1: All zeroes matching target 0
        tests.append({
            "name": "Edge: All zero elements with target 0 (combinatorial count)",
            "input": {"readings": [0, 0, 0, 0], "target": 0},
            "expected": 10, # 4*(4+1)//2 = 10
        })

        # Edge 2: Fluctuating values cancelling out (zero-sum subsegments)
        fluctuating = [5, -5, 5, -5, 5, -5]
        tests.append({
            "name": "Edge: Alternating positive and negative cancellations",
            "input": {"readings": fluctuating, "target": 0},
            "expected": oracle_prefix_sum_anomaly(fluctuating, 0),
        })

        # Edge 3: Impossible target
        tests.append({
            "name": "Edge: Target outside achievable sums (returns 0)",
            "input": {"readings": [1, 2, 3, 4], "target": 100},
            "expected": 0,
        })

    elif seed_id == "stack_syntax_validator":
        # Normal 1: realistic structured expression with balanced brackets
        tests.append({
            "name": "Normal: Balanced function invocation syntax",
            "input": {"expression": "result = compute_cost(matrix[i], options={'mode': 'fast'})"},
            "expected": True,
        })

        # Normal 2: complex nested SQL where-clause
        tests.append({
            "name": "Normal: Nested SQL query filter predicate",
            "input": {"expression": "WHERE (user_id IN (SELECT id FROM users WHERE (active = 1 AND role = 'admin')))"},
            "expected": True,
        })

        # Boundary 1: Empty string
        tests.append({
            "name": "Boundary: Empty string is valid",
            "input": {"expression": ""},
            "expected": True,
        })

        # Boundary 2: No brackets at all
        tests.append({
            "name": "Boundary: Pure alphanumeric text without brackets",
            "input": {"expression": "x = 42 * y + 10"},
            "expected": True,
        })

        # Edge 1: Cross-over brackets in wrong hierarchical order (e.g. `([)]`)
        tests.append({
            "name": "Edge: Cross-over invalid bracket closure order",
            "input": {"expression": "array[(index])"},
            "expected": False,
        })

        # Edge 2: Only opening brackets (unclosed)
        tests.append({
            "name": "Edge: Unclosed trailing opening brackets",
            "input": {"expression": "def foo(): { [ ("},
            "expected": False,
        })

        # Edge 3: Unmatched closing bracket at start
        tests.append({
            "name": "Edge: Premature closing bracket",
            "input": {"expression": ")}"},
            "expected": False,
        })

        # Edge 4: Deeply nested valid brackets
        tests.append({
            "name": "Edge: Deeply nested valid bracket hierarchy",
            "input": {"expression": "{[({[()]})]}"},
            "expected": True,
        })

    elif seed_id == "binary_search_threshold":
        # Normal 1: standard workloads
        w1 = [rng.randint(5, 40) for _ in range(10)]
        k1 = rng.randint(2, 4)
        tests.append({
            "name": "Normal: Distributed workload partitioning",
            "input": {"workloads": w1, "k": k1},
            "expected": oracle_binary_search_threshold(w1, k1),
        })

        # Normal 2: longer workload array
        w2 = [rng.randint(10, 60) for _ in range(14)]
        k2 = rng.randint(3, 5)
        tests.append({
            "name": "Normal: Multi-node cluster job allocation",
            "input": {"workloads": w2, "k": k2},
            "expected": oracle_binary_search_threshold(w2, k2),
        })

        # Boundary 1: k equals 1 (single worker takes total sum)
        b_w1 = [10, 20, 30, 40]
        tests.append({
            "name": "Boundary: Single worker handles entire workload sum",
            "input": {"workloads": b_w1, "k": 1},
            "expected": sum(b_w1),
        })

        # Boundary 2: k >= len(workloads) (each worker takes at most 1 item)
        b_w2 = [15, 95, 30]
        tests.append({
            "name": "Boundary: Workers count exceeds jobs (answer is max job)",
            "input": {"workloads": b_w2, "k": 5},
            "expected": 95,
        })

        # Edge 1: Uniform workload elements
        tests.append({
            "name": "Edge: Uniform workload chunks",
            "input": {"workloads": [10, 10, 10, 10, 10, 10], "k": 2},
            "expected": 30,
        })

        # Edge 2: Heavily skewed workloads (one giant workload dominates)
        tests.append({
            "name": "Edge: Skewed partition where single dominant job sets floor",
            "input": {"workloads": [2, 3, 200, 4, 5], "k": 3},
            "expected": 200,
        })

    return tests


# ---------------------------------------------------------------------------
# Structured Transformation & Validation Pipeline
# ---------------------------------------------------------------------------

def generate_challenge(
    skill: str = "python",
    difficulty: str = "intermediate",
    seed_problem_id: Optional[str] = None,
    previous_performance: Optional[Any] = None,
    target_weakness: Optional[Any] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Produces a transformed, unique challenge instance from the seed problem corpus:
      - Preserves underlying algorithmic competency
      - Applies explainable domain adaptation and parameter scaling
      - Generates a fresh dynamic hidden test suite (normal, boundary, edge cases)
      - Attaches transformation metadata
    """
    all_problems = load_seed_problems()
    if not all_problems:
        raise RuntimeError("No seed problems available in backend/data/problems/")

    matched = [p for p in all_problems if p.get("difficulty", "").lower() == difficulty.lower()]
    if not matched:
        matched = all_problems

    if seed_problem_id:
        chosen = next((p for p in all_problems if p["id"] == seed_problem_id), None)
        if not chosen:
            chosen = random.choice(matched)
    else:
        chosen = random.choice(matched)

    problem_data = copy.deepcopy(chosen)
    seed_id = problem_data["id"]

    # Select explainable scenario from expanded domain pool
    scenario_pool = EXPANDED_SCENARIOS.get(seed_id, problem_data.get("scenarios", []))
    rng = random.Random(uuid4().hex)
    scenario = rng.choice(scenario_pool)

    title_tmpl = problem_data.get("template_title", "{domain_title}: Technical Assessment")
    desc_tmpl = problem_data.get("template_description", "Implement the solution for {domain_context}.")

    try:
        formatted_title = title_tmpl.format(**scenario)
    except Exception:
        formatted_title = f"{scenario.get('domain_title', 'Technical Assessment')}: Practical Challenge"

    try:
        formatted_description = desc_tmpl.format(**scenario)
    except Exception:
        safe_desc = desc_tmpl.replace("'{', '}'", "'{{', '}}'")
        try:
            formatted_description = safe_desc.format(**scenario)
        except Exception:
            formatted_description = problem_data.get("description", "Implement the algorithmic solution.")

    # Generate fresh hidden test suite covering normal, boundary, and edge cases
    dynamic_tests = generate_dynamic_tests(seed_id, rng=rng)

    instance_id = f"SP-{seed_id[:4].upper()}-{uuid4().hex[:8]}"
    transformation_type = "domain_adaptation+parameter_scaling"

    metadata = {
        "seed_problem_id": seed_id,
        "transformation_type": transformation_type,
        "problem_version": problem_data.get("version", "1.0"),
        "competency": scenario.get("competency", problem_data.get("algorithm_family", "Algorithmic Problem Solving")),
        "scenario": scenario.get("domain_title", "Technical Assessment"),
    }

    return {
        "id": instance_id,
        "seed_problem_id": seed_id,
        "transformation_type": transformation_type,
        "title": formatted_title,
        "description": formatted_description,
        "difficulty": problem_data.get("difficulty", difficulty),
        "concepts": problem_data.get("concepts", []),
        "algorithm_family": problem_data.get("algorithm_family", "General"),
        "constraints": problem_data.get("constraints", []),
        "reference_solution": problem_data["reference_solution"],
        "starter_code": problem_data.get("starter_code", "def solve(*args):\n    pass\n"),
        "tests": dynamic_tests,
        "version": problem_data.get("version", "1.0"),
        "scenario_domain": scenario.get("domain_title", "General"),
        "metadata": metadata,
    }


def generate_validated_challenge(
    skill: str = "python",
    difficulty: str = "intermediate",
    seed_problem_id: Optional[str] = None,
    max_retries: int = 5,
) -> Dict[str, Any]:
    """
    Generates a novel problem instance and validates it against the reference solution.
    If validation fails, the candidate instance is discarded and regenerated.
    Guarantees 100% test pass against the reference solution before serving.
    """
    for attempt in range(max_retries):
        candidate = generate_challenge(
            skill=skill,
            difficulty=difficulty,
            seed_problem_id=seed_problem_id,
        )
        is_valid, report = validate_problem(candidate)
        if is_valid and report.get("tests_total", 0) > 0:
            logger.info(
                "Assessment variation %s (%s) passed self-validation (%d/%d tests).",
                candidate["id"],
                candidate["seed_problem_id"],
                report["tests_passed"],
                report["tests_total"],
            )
            return candidate

        logger.warning(
            "Attempt %d/%d: Variation %s failed self-validation (%s). Discarding and regenerating.",
            attempt + 1,
            max_retries,
            candidate.get("id"),
            report.get("error"),
        )

    # Safe fallback to pre-validated canonical seed problem if all generation attempts fail
    fallback = get_canonical_fallback_problem(difficulty=difficulty, seed_problem_id=seed_problem_id)
    is_valid, report = validate_problem(fallback)
    if not is_valid:
        raise RuntimeError("Canonical fallback problem failed self-validation!")
    return fallback


def get_canonical_fallback_problem(
    difficulty: str = "intermediate",
    seed_problem_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returns a deterministic, validated canonical problem directly from the seed corpus.
    Used as an emergency safety fallback if dynamic variation generation or validation fails.
    """
    all_problems = load_seed_problems()
    if not all_problems:
        raise RuntimeError("No seed problems available in backend/data/problems/")

    matched = [p for p in all_problems if p.get("difficulty", "").lower() == difficulty.lower()]
    if not matched:
        matched = all_problems

    if seed_problem_id:
        chosen = next((p for p in all_problems if p["id"] == seed_problem_id), None)
        if not chosen:
            chosen = matched[0]
    else:
        chosen = matched[0]

    problem_data = copy.deepcopy(chosen)
    seed_id = problem_data["id"]
    instance_id = f"SP-{seed_id[:4].upper()}-{uuid4().hex[:8]}"

    tests = list(problem_data.get("fixed_tests", problem_data.get("tests", [])))

    metadata = {
        "seed_problem_id": seed_id,
        "transformation_type": "canonical_baseline",
        "problem_version": problem_data.get("version", "1.0"),
        "competency": problem_data.get("algorithm_family", "Algorithmic Problem Solving"),
        "scenario": "Canonical Baseline",
    }

    return {
        "id": instance_id,
        "seed_problem_id": seed_id,
        "transformation_type": "canonical_baseline",
        "title": problem_data.get("title", f"{seed_id.replace('_', ' ').title()} Challenge"),
        "description": problem_data.get("description", "Solve the algorithmic challenge."),
        "difficulty": problem_data.get("difficulty", difficulty),
        "concepts": problem_data.get("concepts", []),
        "algorithm_family": problem_data.get("algorithm_family", "General"),
        "constraints": problem_data.get("constraints", []),
        "reference_solution": problem_data["reference_solution"],
        "starter_code": problem_data.get("starter_code", "def solve(*args):\n    pass\n"),
        "tests": tests,
        "version": problem_data.get("version", "1.0"),
        "scenario_domain": "Canonical Benchmark",
        "metadata": metadata,
    }
