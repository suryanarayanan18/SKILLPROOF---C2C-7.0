"""Template variation engine for SkillProof.

Generates novel, validated challenge instances from local seed problem templates
without runtime LLM or external API dependencies.
"""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

PROBLEMS_DIR = Path(__file__).resolve().parent.parent / "data" / "problems"


def load_seed_problems() -> List[Dict[str, Any]]:
    """Load all hand-authored seed problem JSON files."""
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


def generate_dynamic_tests(seed_id: str, count: int = 5) -> List[Dict[str, Any]]:
    """Generate dynamic hidden test cases for a problem instance."""
    random_gen = random.Random(uuid4().hex)
    tests = []

    if seed_id == "array_frequency_k":
        for i in range(count):
            length = random_gen.randint(10, 30)
            target_val = random_gen.randint(1, 10)
            items = [random_gen.randint(1, 20) for _ in range(length)]
            k = random_gen.randint(2, 4)
            # Guarantee at least some meet k
            items.extend([target_val] * k)
            random_gen.shuffle(items)
            # Compute expected with reference logic
            from collections import Counter
            c = Counter(items)
            cand = [v for v, cnt in c.items() if cnt >= k]
            expected = min(cand) if cand else -1
            tests.append({
                "name": f"Dynamic hidden test #{i+1}",
                "input": {"items": items, "k": k},
                "expected": expected,
            })

    elif seed_id == "sliding_window_anomaly":
        for i in range(count):
            length = random_gen.randint(10, 25)
            w = random_gen.randint(2, 5)
            stream = [round(random_gen.uniform(-50.0, 150.0), 2) for _ in range(length)]
            max_sum = sum(stream[:w])
            curr_sum = max_sum
            for j in range(w, len(stream)):
                curr_sum += stream[j] - stream[j - w]
                if curr_sum > max_sum:
                    max_sum = curr_sum
            expected = round(float(max_sum) / w, 2)
            tests.append({
                "name": f"Dynamic stream window test #{i+1}",
                "input": {"stream": stream, "window_size": w},
                "expected": expected,
            })

    elif seed_id == "interval_consolidation":
        for i in range(count):
            num_intervals = random_gen.randint(4, 10)
            intervals = []
            for _ in range(num_intervals):
                st = random_gen.randint(1, 50)
                ed = st + random_gen.randint(0, 15)
                intervals.append([st, ed])
            # Compute expected
            sorted_intervals = sorted(intervals, key=lambda x: x[0])
            merged = [list(sorted_intervals[0])]
            for cur in sorted_intervals[1:]:
                prev = merged[-1]
                if cur[0] <= prev[1]:
                    prev[1] = max(prev[1], cur[1])
                else:
                    merged.append(list(cur))
            tests.append({
                "name": f"Dynamic interval batch #{i+1}",
                "input": {"intervals": intervals},
                "expected": merged,
            })

    elif seed_id == "lru_cache_expiry":
        for i in range(count):
            cap = random_gen.randint(2, 4)
            num_ops = random_gen.randint(6, 12)
            ops = []
            keys = ["alpha", "beta", "gamma", "delta", "epsilon"]
            for _ in range(num_ops):
                if random_gen.random() < 0.6:
                    ops.append(["PUT", random_gen.choice(keys), random_gen.randint(1, 99)])
                else:
                    ops.append(["GET", random_gen.choice(keys)])
            from collections import OrderedDict
            c = OrderedDict()
            res = []
            for op in ops:
                act, k_ = op[0], op[1]
                if act == "PUT":
                    v = op[2]
                    if k_ in c:
                        c.move_to_end(k_)
                    elif len(c) >= cap:
                        c.popitem(last=False)
                    c[k_] = v
                else:
                    if k_ in c:
                        c.move_to_end(k_)
                        res.append(c[k_])
                    else:
                        res.append(None)
            tests.append({
                "name": f"Dynamic cache operations #{i+1}",
                "input": {"operations": ops, "capacity": cap},
                "expected": res,
            })

    elif seed_id == "graph_dependency_resolver":
        # Additional topological sort tests
        tasks_pool = ["parse", "validate", "compile", "optimize", "link", "package"]
        deps_options = [
            [["validate", "parse"], ["compile", "validate"], ["optimize", "compile"], ["link", "optimize"], ["package", "link"]],
            [["compile", "parse"], ["optimize", "parse"], ["link", "compile"], ["link", "optimize"]],
            [["link", "compile"], ["compile", "link"]], # Cycle test
        ]
        from collections import defaultdict
        import heapq
        for i, deps in enumerate(deps_options):
            active_tasks = sorted(list(set(tasks_pool[:len(deps)+2])))
            adj = defaultdict(list)
            in_degree = {t: 0 for t in active_tasks}
            for task, prereq in deps:
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
            expected = order if len(order) == len(active_tasks) else []
            tests.append({
                "name": f"Topological variation #{i+1}",
                "input": {"tasks": active_tasks, "dependencies": deps},
                "expected": expected,
            })

    elif seed_id == "prefix_sum_anomaly":
        for i in range(count):
            length = random_gen.randint(8, 20)
            readings = [random_gen.randint(-10, 20) for _ in range(length)]
            tgt = random_gen.randint(0, 15)
            # Compute expected
            pcounts = {0: 1}
            csum = 0
            cnt = 0
            for r in readings:
                csum += r
                diff = csum - tgt
                if diff in pcounts:
                    cnt += pcounts[diff]
                pcounts[csum] = pcounts.get(csum, 0) + 1
            tests.append({
                "name": f"Prefix sum dynamic test #{i+1}",
                "input": {"readings": readings, "target": tgt},
                "expected": cnt,
            })

    elif seed_id == "stack_syntax_validator":
        samples = [
            ("config.set('rules', [{'id': 1}, {'id': 2}])", True),
            ("if (a > 0) { return [x, y; }", False),
            ("SELECT * FROM table WHERE (id IN (1, 2, (3)))", True),
            ("([{", False),
            ("((( )))", True),
        ]
        for i, (expr, exp_bool) in enumerate(samples):
            tests.append({
                "name": f"Syntax validation test #{i+1}",
                "input": {"expression": expr},
                "expected": exp_bool,
            })

    elif seed_id == "binary_search_threshold":
        workloads_list = [
            ([12, 34, 67, 90], 2),
            ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 5),
            ([100, 200, 300, 400], 3),
        ]
        def solve_ref(wloads, k):
            if not wloads:
                return 0
            if k >= len(wloads):
                return max(wloads)
            def feasible(max_load):
                w = 1
                cur = 0
                for item in wloads:
                    if cur + item > max_load:
                        w += 1
                        cur = item
                        if w > k:
                            return False
                    else:
                        cur += item
                return True
            low, high = max(wloads), sum(wloads)
            ans = high
            while low <= high:
                mid = (low + high) // 2
                if feasible(mid):
                    ans = mid
                    high = mid - 1
                else:
                    low = mid + 1
            return ans

        for i, (wl, k) in enumerate(workloads_list):
            tests.append({
                "name": f"Binary partition dynamic test #{i+1}",
                "input": {"workloads": wl, "k": k},
                "expected": solve_ref(wl, k),
            })

    return tests


def generate_challenge(
    skill: str = "python",
    difficulty: str = "intermediate",
    seed_problem_id: Optional[str] = None,
    previous_performance: Optional[Any] = None,
    target_weakness: Optional[Any] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Produces a transformed, distinct challenge from the seeded corpus.
    Applies scenario domain swapping, bounds randomization, and generates
    a verified hidden test suite.
    """
    all_problems = load_seed_problems()
    if not all_problems:
        raise RuntimeError("No seed problems available in backend/data/problems/")

    # Select candidates matching difficulty or fall back
    matched = [p for p in all_problems if p.get("difficulty", "").lower() == difficulty.lower()]
    if not matched:
        matched = all_problems

    if seed_problem_id:
        chosen = next((p for p in all_problems if p["id"] == seed_problem_id), None)
        if not chosen:
            chosen = random.choice(matched)
    else:
        chosen = random.choice(matched)

    # Clone so we do not mutate the seed
    problem_data = copy.deepcopy(chosen)
    seed_id = problem_data["id"]

    # Apply scenario variation
    scenarios = problem_data.get("scenarios", [])
    if scenarios:
        scenario = random.choice(scenarios)
    else:
        scenario = {
            "domain_title": "Core Algorithm Assessment",
            "domain_context": "system compute runtime",
            "metric_name": "data element",
        }

    title_tmpl = problem_data.get("template_title", "{domain_title}: Technical Assessment")
    desc_tmpl = problem_data.get("template_description", "Implement the solution for {domain_context}.")

    formatted_title = title_tmpl.format(**scenario)
    formatted_description = desc_tmpl.format(**scenario)

    # Assemble test suite: fixed tests + dynamic tests
    all_tests = list(problem_data.get("fixed_tests", []))
    dynamic_tests = generate_dynamic_tests(seed_id, count=4)
    all_tests.extend(dynamic_tests)

    instance_id = f"SP-{seed_id[:4].upper()}-{uuid4().hex[:8]}"

    return {
        "id": instance_id,
        "seed_problem_id": seed_id,
        "title": formatted_title,
        "description": formatted_description,
        "difficulty": problem_data.get("difficulty", difficulty),
        "concepts": problem_data.get("concepts", []),
        "algorithm_family": problem_data.get("algorithm_family", "General"),
        "constraints": problem_data.get("constraints", []),
        "reference_solution": problem_data["reference_solution"],
        "starter_code": problem_data.get("starter_code", "def solve(*args):\n    pass\n"),
        "tests": all_tests,
        "version": problem_data.get("version", "1.0"),
        "scenario_domain": scenario.get("domain_title", "General"),
    }


def get_canonical_fallback_problem(
    difficulty: str = "intermediate",
    seed_problem_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returns a deterministic, validated canonical problem directly from the seed corpus.
    Used as a safety fallback if dynamic variation generation or validation fails.
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

    # Use fixed tests directly to guarantee 100% test pass against reference solution
    tests = list(problem_data.get("fixed_tests", problem_data.get("tests", [])))

    return {
        "id": instance_id,
        "seed_problem_id": seed_id,
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
    }

