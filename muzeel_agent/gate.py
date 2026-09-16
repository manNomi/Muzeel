"""Fail-closed elimination and release decisions from auditable evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math


def _require_nonnegative_counts(values: tuple[tuple[str, object], ...]) -> None:
    for name, value in values:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True)
class EliminationEvidence:
    parser_failure_count: int
    protected_file_count: int
    trace_audit_passed: bool
    exploration_completed: bool
    executed_action_count: int
    policy_rejection_count: int
    action_failure_count: int
    navigation_violation_count: int

    def __post_init__(self) -> None:
        _require_nonnegative_counts(
            (
                ("parser_failure_count", self.parser_failure_count),
                ("protected_file_count", self.protected_file_count),
                ("executed_action_count", self.executed_action_count),
                ("policy_rejection_count", self.policy_rejection_count),
                ("action_failure_count", self.action_failure_count),
                ("navigation_violation_count", self.navigation_violation_count),
            )
        )
        if not isinstance(self.trace_audit_passed, bool) or not isinstance(
            self.exploration_completed, bool
        ):
            raise ValueError("gate booleans must be actual boolean values")


@dataclass(frozen=True)
class GateDecision:
    approved: bool
    reasons: tuple[str, ...]
    evidence: EliminationEvidence

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "reasons": list(self.reasons),
            "evidence": asdict(self.evidence),
        }


def evaluate_elimination_gate(evidence: EliminationEvidence) -> GateDecision:
    reasons = []
    if evidence.parser_failure_count:
        reasons.append("parser_failures_present")
    if not evidence.trace_audit_passed:
        reasons.append("trace_audit_failed")
    if not evidence.exploration_completed:
        reasons.append("exploration_incomplete")
    if evidence.executed_action_count < 1:
        reasons.append("no_interaction_executed")
    if evidence.action_failure_count:
        reasons.append("action_failures_present")
    if evidence.navigation_violation_count:
        reasons.append("navigation_violations_present")
    if evidence.policy_rejection_count > 2:
        reasons.append("planner_policy_rejections_exceeded")
    return GateDecision(not reasons, tuple(reasons), evidence)


@dataclass(frozen=True)
class ReleaseEvidence:
    """Evidence produced after comparing original and processed JavaScript."""

    processed_syntax_failure_count: int
    evaluable_scenario_count: int
    functional_damage_count: int
    new_console_error_category_count: int
    minimum_visual_similarity: float

    def __post_init__(self) -> None:
        _require_nonnegative_counts(
            (
                ("processed_syntax_failure_count", self.processed_syntax_failure_count),
                ("evaluable_scenario_count", self.evaluable_scenario_count),
                ("functional_damage_count", self.functional_damage_count),
                (
                    "new_console_error_category_count",
                    self.new_console_error_category_count,
                ),
            )
        )
        if (
            not isinstance(self.minimum_visual_similarity, (int, float))
            or isinstance(self.minimum_visual_similarity, bool)
            or not math.isfinite(self.minimum_visual_similarity)
            or not 0 <= self.minimum_visual_similarity <= 1
        ):
            raise ValueError("minimum_visual_similarity must be between 0 and 1")


@dataclass(frozen=True)
class ReleaseDecision:
    approved: bool
    reasons: tuple[str, ...]
    evidence: ReleaseEvidence

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "reasons": list(self.reasons),
            "evidence": asdict(self.evidence),
        }


def evaluate_release_gate(
    evidence: ReleaseEvidence,
    *,
    minimum_visual_similarity: float = 0.99,
) -> ReleaseDecision:
    """Approve a processed artifact only after independent regression evidence."""

    if not 0 <= minimum_visual_similarity <= 1:
        raise ValueError("minimum visual similarity threshold must be between 0 and 1")
    reasons = []
    if evidence.processed_syntax_failure_count:
        reasons.append("processed_syntax_failures_present")
    if evidence.evaluable_scenario_count < 1:
        reasons.append("no_evaluable_holdout_scenario")
    if evidence.functional_damage_count:
        reasons.append("functional_damage_present")
    if evidence.new_console_error_category_count:
        reasons.append("new_console_error_categories_present")
    if evidence.minimum_visual_similarity < minimum_visual_similarity:
        reasons.append("visual_similarity_below_threshold")
    return ReleaseDecision(not reasons, tuple(reasons), evidence)
