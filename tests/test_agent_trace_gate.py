import json
from pathlib import Path
import tempfile
import unittest

from muzeel_agent.audit import audit_trace
from muzeel_agent.gate import (
    EliminationEvidence,
    ReleaseEvidence,
    evaluate_elimination_gate,
    evaluate_release_gate,
)
from muzeel_agent.planner import canonical_json, sha256_text
from muzeel_agent.trace import TraceWriter


def trace_payload(**overrides):
    action = {"action": "click", "target": "#safe"}
    metadata = {"agent": True, "provider": "test", "model": "test"}
    value = {
        "action": action,
        "planner": {
            "request_sha256": "a" * 64,
            "response_sha256": sha256_text(
                canonical_json({"action": action, "metadata": metadata})
            ),
            "metadata": metadata,
        },
        "policy": {"allowed": True, "reason": "safe_observed_control"},
        "before": {
            "url": "https://example.test/",
            "title": "Example",
            "state_sha256": "c" * 64,
            "interactive_elements": [
                {
                    "selector": "#safe",
                    "tag": "button",
                    "role": None,
                    "name": "메뉴 열기",
                    "disabled": False,
                    "href": None,
                    "input_type": None,
                }
            ],
        },
        "executed": True,
        "outcome": "action_effect",
        "after": {
            "url": "https://example.test/",
            "state_sha256": "d" * 64,
        },
        "new_function_marker_count": 2,
        "navigation_violation": False,
        "error": None,
    }
    value.update(overrides)
    return value


class AgentTraceGateTest(unittest.TestCase):
    def test_valid_trace_passes_and_tampering_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            TraceWriter(path).append(trace_payload())
            audit = audit_trace(path)
            self.assertTrue(audit.passed, audit.errors)
            row = json.loads(path.read_text(encoding="utf-8"))
            row["outcome"] = "action_no_effect"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            tampered = audit_trace(path)
            self.assertFalse(tampered.passed)
            self.assertIn("row_hash_mismatch:1", tampered.errors)

    def test_trace_writer_refuses_existing_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            TraceWriter(path).append(trace_payload())
            with self.assertRaises(FileExistsError):
                TraceWriter(path)

    def test_trace_writer_rejects_reserved_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            writer = TraceWriter(Path(directory) / "trace.jsonl")
            with self.assertRaises(ValueError):
                writer.append({"step_index": 99})

    def test_audit_fails_closed_for_non_object_trace_row(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            path.write_text("[]\n", encoding="utf-8")
            audit = audit_trace(path)
            self.assertFalse(audit.passed)
            self.assertIn("trace_row_not_object:1", audit.errors)

    def test_elimination_gate_is_fail_closed(self):
        valid = EliminationEvidence(0, 1, True, True, 1, 0, 0, 0)
        self.assertTrue(evaluate_elimination_gate(valid).approved)
        invalid = EliminationEvidence(1, 1, True, True, 1, 0, 0, 0)
        decision = evaluate_elimination_gate(invalid)
        self.assertFalse(decision.approved)
        self.assertIn("parser_failures_present", decision.reasons)

    def test_release_gate_requires_independent_regression_evidence(self):
        valid = ReleaseEvidence(0, 5, 0, 0, 0.995)
        self.assertTrue(evaluate_release_gate(valid).approved)
        invalid = ReleaseEvidence(0, 0, 1, 1, 0.98)
        decision = evaluate_release_gate(invalid)
        self.assertFalse(decision.approved)
        self.assertEqual(4, len(decision.reasons))

    def test_gate_evidence_rejects_impossible_values(self):
        with self.assertRaises(ValueError):
            EliminationEvidence(-1, 0, True, True, 1, 0, 0, 0)
        with self.assertRaises(ValueError):
            ReleaseEvidence(0, 1, 0, 0, 1.1)


if __name__ == "__main__":
    unittest.main()
