import unittest

from muzeel_agent.models import AgentAction, BrowserObservation
from muzeel_agent.policy import AgentPolicy


def observation(*elements):
    return BrowserObservation.from_dict(
        {
            "url": "https://example.test/",
            "title": "Example",
            "state_sha256": "a" * 64,
            "interactive_elements": list(elements),
        }
    )


def element(**overrides):
    value = {
        "selector": "#safe",
        "tag": "button",
        "role": None,
        "name": "메뉴 열기",
        "disabled": False,
        "href": None,
        "input_type": None,
    }
    value.update(overrides)
    return value


class AgentModelPolicyTest(unittest.TestCase):
    def setUp(self):
        self.policy = AgentPolicy("https://example.test/")

    def test_accepts_observed_safe_button(self):
        action = AgentAction.from_dict({"action": "click", "target": "#safe"})
        decision = self.policy.evaluate(action, observation(element()))
        self.assertTrue(decision.allowed)
        self.assertEqual("safe_observed_control", decision.reason)

    def test_rejects_unobserved_or_dangerous_target(self):
        unknown = AgentAction.from_dict({"action": "click", "target": "#unknown"})
        self.assertFalse(self.policy.evaluate(unknown, observation(element())).allowed)
        dangerous = observation(element(name="회원가입"))
        decision = self.policy.evaluate(
            AgentAction.from_dict({"action": "click", "target": "#safe"}),
            dangerous,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual("dangerous_intent_name", decision.reason)

    def test_rejects_links_and_form_controls(self):
        link_observation = observation(element(tag="a", href="/about"))
        decision = self.policy.evaluate(
            AgentAction.from_dict({"action": "click", "target": "#safe"}),
            link_observation,
        )
        self.assertEqual("navigation_denied_by_default", decision.reason)
        input_observation = observation(element(tag="input", input_type="text"))
        decision = self.policy.evaluate(
            AgentAction.from_dict({"action": "click", "target": "#safe"}),
            input_observation,
        )
        self.assertEqual("form_control_denied", decision.reason)

    def test_enforces_scroll_and_wait_budgets(self):
        current = observation(element())
        self.assertTrue(
            self.policy.evaluate(
                AgentAction.from_dict({"action": "scroll", "delta_y": 800}), current
            ).allowed
        )
        self.assertFalse(
            self.policy.evaluate(
                AgentAction.from_dict({"action": "scroll", "delta_y": 801}), current
            ).allowed
        )
        self.assertFalse(
            self.policy.evaluate(
                AgentAction.from_dict({"action": "wait", "seconds": 3.1}), current
            ).allowed
        )

    def test_rejects_invalid_action_shapes_and_hashes(self):
        invalid_actions = [
            {"action": "click"},
            {"action": "scroll", "delta_y": 0},
            {"action": "wait", "seconds": True},
            {"action": "stop", "target": "#safe"},
            {"action": "stop", "unknown": 1},
        ]
        for raw in invalid_actions:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                AgentAction.from_dict(raw)
        raw_observation = observation(element()).to_dict()
        raw_observation["state_sha256"] = "z" * 64
        with self.assertRaises(ValueError):
            BrowserObservation.from_dict(raw_observation)

    def test_allows_only_same_path_navigation(self):
        self.assertTrue(
            self.policy.navigation_is_safe(
                "https://example.test/?one=1", "https://example.test/?two=2"
            )
        )
        self.assertFalse(
            self.policy.navigation_is_safe(
                "https://example.test/", "https://example.test/account"
            )
        )


if __name__ == "__main__":
    unittest.main()
