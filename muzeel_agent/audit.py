"""Independent structural and safety audit for a Muzeel agent trace."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from .models import AgentAction, BrowserObservation
from .planner import canonical_json, sha256_text
from .policy import AgentPolicy
from .trace import row_sha256


@dataclass(frozen=True)
class TraceAudit:
    passed: bool
    row_count: int
    executed_action_count: int
    policy_rejection_count: int
    action_failure_count: int
    navigation_violation_count: int
    errors: tuple[str, ...]

    def to_dict(self) -> dict:
        value = asdict(self)
        value["errors"] = list(self.errors)
        return value


def audit_trace(path: Path) -> TraceAudit:
    errors: list[str] = []
    rows = []
    if not path.is_file():
        return TraceAudit(False, 0, 0, 0, 0, 0, ("trace_missing",))
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return TraceAudit(False, 0, 0, 0, 0, 0, ("trace_unreadable",))
    for line_number, line in enumerate(lines, 1):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            errors.append(f"invalid_json_line:{line_number}")
    previous = None
    executed = 0
    rejected = 0
    failures = 0
    navigation_violations = 0
    base_url = None
    required_fields = {
        "schema_version",
        "step_index",
        "previous_sha256",
        "action",
        "planner",
        "policy",
        "before",
        "executed",
        "outcome",
        "after",
        "new_function_marker_count",
        "navigation_violation",
        "error",
        "row_sha256",
    }
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            errors.append(f"trace_row_not_object:{index}")
            continue
        if set(row) != required_fields:
            errors.append(f"trace_fields_mismatch:{index}")
        if row.get("schema_version") != 1:
            errors.append(f"unsupported_schema_version:{index}")
        if row.get("step_index") != index:
            errors.append(f"non_contiguous_step:{index}")
        if row.get("previous_sha256") != previous:
            errors.append(f"broken_hash_chain:{index}")
        if row.get("row_sha256") != row_sha256(row):
            errors.append(f"row_hash_mismatch:{index}")
        previous = row.get("row_sha256")
        action = None
        observation = None
        try:
            action = AgentAction.from_dict(row["action"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"invalid_action:{index}")
        policy = row.get("policy")
        planner = row.get("planner")
        if not isinstance(policy, dict):
            policy = {}
        if not isinstance(planner, dict):
            planner = {}
        metadata = planner.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        if (
            set(planner) != {"request_sha256", "response_sha256", "metadata"}
            or set(metadata) != {"agent", "provider", "model"}
            or metadata.get("agent") is not True
            or not isinstance(metadata.get("provider"), str)
            or not metadata.get("provider")
            or not isinstance(metadata.get("model"), str)
            or not metadata.get("model")
        ):
            errors.append(f"invalid_planner_evidence:{index}")
        elif not isinstance(planner["request_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", planner["request_sha256"]
        ):
            errors.append(f"invalid_planner_request_hash:{index}")
        elif planner["response_sha256"] != sha256_text(
            canonical_json({"action": row.get("action"), "metadata": metadata})
        ):
            errors.append(f"planner_response_hash_mismatch:{index}")
        if set(policy) != {"allowed", "reason"} or not isinstance(
            policy.get("allowed"), bool
        ):
            errors.append(f"invalid_policy_evidence:{index}")
        before = row.get("before") or {}
        try:
            observation = BrowserObservation.from_dict(before)
        except (TypeError, ValueError):
            errors.append(f"invalid_before_evidence:{index}")
        if observation is not None:
            base_url = base_url or observation.url
        if action is not None and observation is not None and base_url is not None:
            reproduced = AgentPolicy(base_url).evaluate(action, observation)
            if reproduced.allowed != policy.get("allowed"):
                errors.append(f"policy_decision_mismatch:{index}")
            if reproduced.reason != policy.get("reason"):
                errors.append(f"policy_reason_mismatch:{index}")
        if policy.get("allowed") is not True:
            rejected += 1
        if row.get("executed") is True:
            executed += 1
            if policy.get("allowed") is not True:
                errors.append(f"executed_without_policy_approval:{index}")
        if row.get("error") is not None:
            failures += 1
        if row.get("navigation_violation") is True:
            navigation_violations += 1
        if policy.get("allowed") is False and (
            row.get("executed") is not False
            or row.get("outcome") != "policy_rejected"
        ):
            errors.append(f"policy_rejection_outcome_mismatch:{index}")
        if action is not None and action.action == "stop" and (
            row.get("executed") is not False or row.get("outcome") != "agent_stop"
        ):
            errors.append(f"stop_outcome_mismatch:{index}")
        if (
            action is not None
            and action.action not in {"stop"}
            and policy.get("allowed") is True
            and row.get("executed") is not True
        ):
            errors.append(f"approved_action_not_executed:{index}")
        if row.get("executed") is True and not isinstance(row.get("after"), dict):
            errors.append(f"executed_action_missing_after_state:{index}")
        after = row.get("after")
        if isinstance(after, dict):
            if set(after) != {"url", "state_sha256"}:
                errors.append(f"invalid_after_evidence:{index}")
            elif observation is not None and base_url is not None:
                navigation_safe = AgentPolicy(base_url).navigation_is_safe(
                    observation.url, after.get("url", "")
                )
                if navigation_safe == bool(row.get("navigation_violation")):
                    errors.append(f"navigation_evidence_mismatch:{index}")
        if row.get("outcome") not in {
            "policy_rejected",
            "agent_stop",
            "action_failed",
            "navigation_violation",
            "action_effect",
            "action_no_effect",
        }:
            errors.append(f"invalid_outcome:{index}")
    passed = (
        bool(rows)
        and not errors
        and failures == 0
        and navigation_violations == 0
    )
    return TraceAudit(
        passed=passed,
        row_count=len(rows),
        executed_action_count=executed,
        policy_rejection_count=rejected,
        action_failure_count=failures,
        navigation_violation_count=navigation_violations,
        errors=tuple(errors),
    )
