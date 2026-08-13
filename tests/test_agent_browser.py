from pathlib import Path
import tempfile
import unittest

from muzeel_agent.audit import audit_trace
from muzeel_agent.browser import AgentExplorer, OBSERVE_INTERACTIVE_SCRIPT
from muzeel_agent.models import AgentAction
from muzeel_agent.planner import PlannerDecision, canonical_json, sha256_text
from muzeel_agent.policy import AgentPolicy


class FakeElement:
    def __init__(self, driver):
        self.driver = driver

    def click(self):
        self.driver.page_source = "<html><button id='safe'>열림</button></html>"


class FakeSwitchTo:
    def window(self, _handle):
        return None


class FakeDriver:
    def __init__(self):
        self.current_url = "https://example.test/"
        self.title = "Example"
        self.page_source = "<html><button id='safe'>메뉴 열기</button></html>"
        self.current_window_handle = "main"
        self.window_handles = ["main"]
        self.switch_to = FakeSwitchTo()
        self._logs = [
            {
                "message": (
                    'console-api 1:1 "https://example.test/app.js | 10 | 20"'
                )
            }
        ]

    def execute_script(self, script, *_args):
        if script == OBSERVE_INTERACTIVE_SCRIPT:
            return [
                {
                    "selector": "#safe",
                    "tag": "button",
                    "role": None,
                    "name": "메뉴 열기",
                    "disabled": False,
                    "href": None,
                    "input_type": None,
                }
            ]
        return None

    def find_element(self, _by, selector):
        if selector != "#safe":
            raise LookupError(selector)
        return FakeElement(self)

    def get_log(self, _kind):
        logs, self._logs = self._logs, []
        return logs

    def close(self):
        return None

    def back(self):
        self.current_url = "https://example.test/"


class SequencePlanner:
    def __init__(self):
        self.actions = [
            AgentAction("click", target="#safe", rationale="메뉴 상태 확인"),
            AgentAction("stop", rationale="안전한 새 행동 없음"),
        ]

    def next_action(self, _observation, _history, _budget):
        action = self.actions.pop(0)
        metadata = {"agent": True, "provider": "test", "model": "test"}
        return PlannerDecision(
            action=action,
            request_sha256="a" * 64,
            response_sha256=sha256_text(
                canonical_json({"action": action.to_dict(), "metadata": metadata})
            ),
            metadata=metadata,
        )


class AgentBrowserTest(unittest.TestCase):
    def test_executes_only_policy_approved_action_and_writes_auditable_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_path = Path(directory) / "trace.jsonl"
            explorer = AgentExplorer(
                FakeDriver(),
                SequencePlanner(),
                AgentPolicy("https://example.test/"),
                trace_path,
                settle_seconds=0,
            )
            result = explorer.run()
            self.assertTrue(result.completed)
            self.assertEqual("agent_stop", result.stop_reason)
            self.assertEqual(1, result.executed_action_count)
            self.assertEqual(1, result.unique_function_marker_count)
            audit = audit_trace(trace_path)
            self.assertTrue(audit.passed, audit.errors)
            self.assertEqual(1, audit.executed_action_count)


if __name__ == "__main__":
    unittest.main()
