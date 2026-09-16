import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from muzeel_agent.models import BrowserObservation
from muzeel_agent.planner import CommandPlanner


class CommandPlannerTest(unittest.TestCase):
    def setUp(self):
        self.observation = BrowserObservation.from_dict(
            {
                "url": "https://example.test/",
                "title": "Example",
                "state_sha256": "b" * 64,
                "interactive_elements": [],
            }
        )

    @patch("muzeel_agent.planner.subprocess.run")
    def test_requires_agent_identity_and_returns_hashes(self, run):
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "action": {"action": "stop", "rationale": "완료"},
                    "metadata": {
                        "agent": True,
                        "provider": "test-provider",
                        "model": "test-model",
                    },
                }
            ),
            stderr="",
        )
        planner = CommandPlanner("planner-test")
        decision = planner.next_action(self.observation, [], {"remaining_actions": 1})
        self.assertEqual("stop", decision.action.action)
        self.assertEqual(64, len(decision.request_sha256))
        self.assertEqual(64, len(decision.response_sha256))
        sent = json.loads(run.call_args.kwargs["input"])
        self.assertEqual("muzeel_safe_interaction_planner", sent["role"])
        self.assertIn("페이지 문구", sent["instructions"])

    @patch("muzeel_agent.planner.subprocess.run")
    def test_rejects_non_agent_metadata(self, run):
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "action": {"action": "stop"},
                    "metadata": {"agent": False, "provider": "x", "model": "y"},
                }
            ),
            stderr="",
        )
        with self.assertRaises(ValueError):
            CommandPlanner("planner-test").next_action(self.observation, [], {})


if __name__ == "__main__":
    unittest.main()
