#!/usr/bin/env python3
"""Validate the public Solid Connection experiment summary."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main() -> int:
    actions = load("actions.json")
    results = load("results.json")
    holdout = load("holdout.json")
    environment = load("environment.json")

    assert len(actions["actions"]) == 13
    assert [row["index"] for row in actions["actions"]] == list(range(1, 14))
    assert {row["action"] for row in actions["actions"]} <= {"click", "scroll"}
    assert all(
        row.get("target") or row.get("delta_y") for row in actions["actions"]
    )

    original_bytes = results["original_javascript_bytes"]
    for stage in results["stages"]:
        assert stage["function_count"] == (
            stage["used_function_count"] + stage["removed_function_count"]
        )
        assert stage["saved_javascript_bytes"] == (
            original_bytes - stage["processed_javascript_bytes"]
        )
        calculated = 100 * stage["saved_javascript_bytes"] / original_bytes
        assert abs(calculated - stage["reduction_percent"]) < 0.001

    final = next(stage for stage in results["stages"] if stage["id"] == "modern_safe")
    assert final["accepted"] is True
    assert final["parse_failure_count"] == 0
    assert final["browser_action_failure_count"] == 0
    assert final["syntax_invalid_file_count"] == 0
    assert sum(row["count"] for row in results["protected_files"]) == final[
        "excluded_file_count"
    ]

    assert holdout["scenario_count"] == len(holdout["scenarios"]) == 5
    assert holdout["evaluable_scenario_count"] == 5
    assert holdout["damaged_scenario_count"] == 0
    assert holdout["functional_success_rate"] == 1.0
    assert all(
        row["original_passed"] and row["processed_passed"]
        for row in holdout["scenarios"]
    )
    assert all(
        row["original_console_error_count"] == row["processed_console_error_count"]
        for row in holdout["scenarios"]
    )
    assert holdout["new_processed_console_error_categories"] == []
    assert environment["live_passthrough_request_count"] == 0
    print("solid-connection dataset: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
