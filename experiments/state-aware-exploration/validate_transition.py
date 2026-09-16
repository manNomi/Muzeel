#!/usr/bin/env python3
"""Validate public state-transition data without third-party dependencies."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL = {
    "schema_version",
    "run_id",
    "sequence",
    "explorer",
    "state_before",
    "action",
    "state_after",
    "discovery",
    "outcome",
    "timing",
}
FORBIDDEN_PUBLIC_KEYS = {
    "javascript_source",
    "html",
    "dom",
    "cookie",
    "cookies",
    "token",
    "access_token",
    "refresh_token",
    "browser_profile",
}
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key).lower())
            keys.extend(walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(walk_keys(child))
    return keys


def require_non_negative_integer(value: Any, field: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")


def validate_state(state: Any, field: str) -> None:
    if not isinstance(state, dict):
        raise ValueError(f"{field} must be an object")
    for key in ("state_id", "url_hash", "dom_hash", "screenshot_hash"):
        if not HASH_PATTERN.fullmatch(str(state.get(key, ""))):
            raise ValueError(f"{field}.{key} must be a sha256 hash")
    require_non_negative_integer(
        state.get("visible_interaction_count"),
        f"{field}.visible_interaction_count",
    )


def validate_transition(data: Any) -> None:
    if not isinstance(data, dict):
        raise ValueError("transition must be an object")

    missing = REQUIRED_TOP_LEVEL - data.keys()
    if missing:
        raise ValueError(f"missing top-level fields: {sorted(missing)}")
    if data["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    if not isinstance(data["run_id"], str) or not data["run_id"].strip():
        raise ValueError("run_id must be a non-empty string")
    if not isinstance(data["sequence"], int) or data["sequence"] < 1:
        raise ValueError("sequence must be a positive integer")
    if data["explorer"] not in {"original", "rule_rescan", "ai_agent"}:
        raise ValueError("explorer is invalid")

    forbidden = FORBIDDEN_PUBLIC_KEYS.intersection(walk_keys(data))
    if forbidden:
        raise ValueError(f"forbidden public keys: {sorted(forbidden)}")

    validate_state(data["state_before"], "state_before")
    validate_state(data["state_after"], "state_after")

    action = data["action"]
    if not isinstance(action, dict):
        raise ValueError("action must be an object")
    if action.get("type") not in {"click", "scroll", "wait", "input", "submit"}:
        raise ValueError("action.type is invalid")
    if action.get("policy_decision") not in {"allowed", "denied"}:
        raise ValueError("action.policy_decision is invalid")
    if not isinstance(action.get("target_id"), str) or not action["target_id"]:
        raise ValueError("action.target_id must be a non-empty string")

    discovery = data["discovery"]
    if not isinstance(discovery, dict):
        raise ValueError("discovery must be an object")
    for field in (
        "new_interaction_count",
        "network_request_count",
        "new_script_count",
        "function_coverage_delta",
    ):
        require_non_negative_integer(discovery.get(field), f"discovery.{field}")
    scripts = discovery.get("new_scripts")
    if not isinstance(scripts, list):
        raise ValueError("discovery.new_scripts must be an array")
    if discovery["new_script_count"] != len(scripts):
        raise ValueError("new_script_count must equal the new_scripts length")
    for index, script in enumerate(scripts):
        if not isinstance(script, dict):
            raise ValueError(f"new_scripts[{index}] must be an object")
        if not HASH_PATTERN.fullmatch(str(script.get("url_hash", ""))):
            raise ValueError(f"new_scripts[{index}].url_hash must be a sha256 hash")
        require_non_negative_integer(script.get("bytes"), f"new_scripts[{index}].bytes")
        if script.get("status") not in {
            "discovered",
            "instrumented",
            "replayed",
            "protected",
            "failed",
        }:
            raise ValueError(f"new_scripts[{index}].status is invalid")

    if discovery.get("new_state") is True:
        if data["state_before"]["state_id"] == data["state_after"]["state_id"]:
            raise ValueError("new_state cannot reuse the previous state_id")

    outcome = data["outcome"]
    if not isinstance(outcome, dict) or outcome.get("status") not in {
        "succeeded",
        "failed",
        "denied",
    }:
        raise ValueError("outcome.status is invalid")
    if not isinstance(outcome.get("navigation_violation"), bool):
        raise ValueError("outcome.navigation_violation must be boolean")
    if not isinstance(outcome.get("console_error_categories"), list):
        raise ValueError("outcome.console_error_categories must be an array")

    timing = data["timing"]
    if not isinstance(timing, dict):
        raise ValueError("timing must be an object")
    for field in ("started_at", "settled_at"):
        if not isinstance(timing.get(field), str) or not timing[field]:
            raise ValueError(f"timing.{field} must be a non-empty string")
    require_non_negative_integer(timing.get("elapsed_ms"), "timing.elapsed_ms")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_transition.py TRANSITION.json", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        validate_transition(data)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"transition dataset: invalid: {error}", file=sys.stderr)
        return 1
    print("transition dataset: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
