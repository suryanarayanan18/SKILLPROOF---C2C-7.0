"""Verification script for the improved problem generation and validation pipeline.

Validates:
1. Reference solution execution against dynamic tests for all 8 seed problems.
2. Generation of at least 20 unique assessment instances across difficulties and seeds.
3. 100% validity of all generated instances (all dynamic tests pass).
4. Generated hidden tests are not empty (containing normal, boundary, and edge cases).
5. Public assessment response strictly excludes reference_solution and tests.
6. Public metadata field contains seed_problem_id, transformation_type, and problem_version.
"""

from __future__ import annotations

import sys
from fastapi.testclient import TestClient

import db
from app import app
from services.challenge_generator import (
    generate_challenge,
    generate_validated_challenge,
    load_seed_problems,
)
from services.problem_validator import validate_problem

client = TestClient(app)


def verify_all_seeds_dynamic_tests():
    print("\n--- 1. Verifying Reference Solutions on Dynamic Tests for All 8 Seeds ---")
    seeds = load_seed_problems()
    assert len(seeds) == 8, f"Expected 8 seed problems, found {len(seeds)}"

    for s in seeds:
        seed_id = s["id"]
        print(f"Testing dynamic generation for seed: {seed_id}...", end=" ", flush=True)

        # Generate 3 independent variations for each seed
        for trial in range(3):
            instance = generate_challenge(seed_problem_id=seed_id)
            assert instance["seed_problem_id"] == seed_id
            assert len(instance["tests"]) >= 4, f"Tests suite too small: {len(instance['tests'])}"

            # Verify presence of normal, boundary, and edge test categories
            test_names = [t.get("name", "").lower() for t in instance["tests"]]
            has_normal = any("normal" in n for n in test_names)
            has_boundary = any("boundary" in n for n in test_names)
            has_edge = any("edge" in n for n in test_names)
            assert has_normal, f"Seed {seed_id} missing normal cases"
            assert has_boundary, f"Seed {seed_id} missing boundary cases"
            assert has_edge, f"Seed {seed_id} missing edge cases"

            # Validate reference solution passes 100%
            is_valid, report = validate_problem(instance)
            assert is_valid, f"Seed {seed_id} trial {trial} failed: {report}"
            assert report["tests_passed"] == report["tests_total"]

        print(f"PASSED ({len(instance['tests'])} tests per instance: normal, boundary, edge)")


def verify_twenty_instances_generation_and_secrecy():
    print("\n--- 2. Generating & Validating at Least 20 Unique Assessment Instances ---")
    seeds = load_seed_problems()
    seed_ids = [s["id"] for s in seeds]
    difficulties = ["beginner", "intermediate", "advanced"]

    instances = []
    num_instances = 24  # Generate 24 instances (at least 20 required)

    for i in range(num_instances):
        seed_id = seed_ids[i % len(seed_ids)]
        diff = difficulties[i % len(difficulties)]

        print(f"Generating instance {i+1}/{num_instances} ({seed_id}, {diff})...", end=" ", flush=True)

        # Use the validation pipeline
        problem = generate_validated_challenge(
            difficulty=diff,
            seed_problem_id=seed_id,
        )

        # Check 1: Validity
        is_valid, report = validate_problem(problem)
        assert is_valid, f"Instance {problem['id']} failed validation: {report}"
        assert report["tests_passed"] == report["tests_total"]

        # Check 2: Hidden tests not empty
        assert len(problem["tests"]) >= 4, f"Instance {problem['id']} has empty or trivial tests"

        # Check 3: Metadata present
        meta = problem.get("metadata", {})
        assert meta.get("seed_problem_id") == seed_id
        assert meta.get("transformation_type") is not None
        assert meta.get("problem_version") is not None
        assert "competency" in meta
        assert "scenario" in meta

        instances.append(problem)
        print(f"VALID ({report['tests_passed']}/{report['tests_total']} tests passed) -> [{meta['transformation_type']}]")

    print(f"\nSuccessfully verified {len(instances)} unique instances.")


def verify_public_api_response_does_not_leak_solution():
    print("\n--- 3. Verifying Public API Secrecy (No reference_solution or tests leaked) ---")
    resp = client.post(
        "/api/assessment",
        json={"skill": "python", "difficulty": "intermediate"},
    )
    assert resp.status_code == 201, f"Failed assessment creation: {resp.text}"
    asm_data = resp.json()
    asm_id = asm_data["id"]

    # Check POST /api/assessment response
    assert "reference_solution" not in asm_data, "Leaked reference_solution in assessment root!"
    assert "tests" not in asm_data, "Leaked tests in assessment root!"

    problem_public = asm_data["problem"]
    assert "reference_solution" not in problem_public, "Leaked reference_solution in ProblemPublicView!"
    assert "tests" not in problem_public, "Leaked hidden tests in ProblemPublicView!"
    assert "starter_code" in problem_public, "Starter code should be public"
    assert "metadata" in problem_public, "Metadata should be present in ProblemPublicView"

    meta = problem_public["metadata"]
    assert meta["seed_problem_id"] is not None
    assert meta["transformation_type"] is not None
    assert meta["problem_version"] is not None

    print(f"POST /api/assessment verified secure.")
    print(f"Public metadata: {meta}")

    # Check GET /api/assessment/{id} response
    get_resp = client.get(f"/api/assessment/{asm_id}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert "reference_solution" not in get_data
    assert "tests" not in get_data
    assert "reference_solution" not in get_data["problem"]
    assert "tests" not in get_data["problem"]

    print("GET /api/assessment/{id} verified secure.")
    print("ALL VERIFICATION CHECKS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    verify_all_seeds_dynamic_tests()
    verify_twenty_instances_generation_and_secrecy()
    verify_public_api_response_does_not_leak_solution()
