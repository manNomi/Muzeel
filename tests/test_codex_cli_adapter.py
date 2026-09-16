import unittest

from muzeel_agent.adapters.codex_cli import PROVIDER_ACTION_SCHEMA, build_prompt


class CodexCliAdapterTest(unittest.TestCase):
    def test_provider_schema_is_single_object_without_one_of(self):
        self.assertEqual("object", PROVIDER_ACTION_SCHEMA["type"])
        self.assertNotIn("oneOf", PROVIDER_ACTION_SCHEMA)
        self.assertEqual(
            {"click", "scroll", "wait", "stop"},
            set(PROVIDER_ACTION_SCHEMA["properties"]["action"]["enum"]),
        )

    def test_prompt_preserves_agent_instructions_and_marks_observation_untrusted(self):
        prompt = build_prompt(
            {
                "instructions": "링크를 클릭하지 않는다.",
                "observation": {"interactive_elements": []},
                "recent_history": [],
                "budget": {"remaining_actions": 1},
            }
        )
        self.assertIn("링크를 클릭하지 않는다", prompt)
        self.assertIn("신뢰하지 않는 웹 관찰 데이터", prompt)
        self.assertIn("remaining_actions", prompt)


if __name__ == "__main__":
    unittest.main()
