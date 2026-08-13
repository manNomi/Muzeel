"""Small local utilities for validating Muzeel agent evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import audit_trace
from .gate import (
    EliminationEvidence,
    ReleaseEvidence,
    evaluate_elimination_gate,
    evaluate_release_gate,
)
from .models import AgentAction, BrowserObservation
from .policy import AgentPolicy


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit-trace")
    audit_parser.add_argument("trace", type=Path)

    action_parser = subparsers.add_parser("validate-action")
    action_parser.add_argument("--base-url", required=True)
    action_parser.add_argument("--observation", type=Path, required=True)
    action_parser.add_argument("--action", type=Path, required=True)

    gate_parser = subparsers.add_parser("gate")
    gate_parser.add_argument("evidence", type=Path)

    release_parser = subparsers.add_parser("release-gate")
    release_parser.add_argument("evidence", type=Path)
    release_parser.add_argument("--minimum-visual-similarity", type=float, default=0.99)

    args = parser.parse_args()
    if args.command == "audit-trace":
        audit = audit_trace(args.trace)
        print(json.dumps(audit.to_dict(), indent=2, sort_keys=True))
        return 0 if audit.passed else 1
    if args.command == "validate-action":
        observation = BrowserObservation.from_dict(
            json.loads(args.observation.read_text(encoding="utf-8"))
        )
        action = AgentAction.from_dict(
            json.loads(args.action.read_text(encoding="utf-8"))
        )
        decision = AgentPolicy(args.base_url).evaluate(action, observation)
        output = {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "element": decision.element.to_dict() if decision.element else None,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if decision.allowed else 1
    raw_evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    if args.command == "release-gate":
        evidence = ReleaseEvidence(**raw_evidence)
        decision = evaluate_release_gate(
            evidence,
            minimum_visual_similarity=args.minimum_visual_similarity,
        )
    else:
        evidence = EliminationEvidence(**raw_evidence)
        decision = evaluate_elimination_gate(evidence)
    print(json.dumps(decision.to_dict(), indent=2, sort_keys=True))
    return 0 if decision.approved else 1


if __name__ == "__main__":
    raise SystemExit(main())
