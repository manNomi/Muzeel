"""ChromeExecution variant driven by a policy-constrained external AI planner."""

from __future__ import annotations

from pathlib import Path
import time

from muzeel_agent.browser import AgentExplorer
from muzeel_agent.planner import CommandPlanner
from muzeel_agent.policy import AgentPolicy

from .ChromeExecution import ChromeExecution
from .event_handling.DefaultEventHandler import DefaultEventHandler


class AgentExecution(ChromeExecution):
    def __init__(
        self,
        url: str,
        planner_command: str,
        *,
        output_file_directory: str,
        proxy_url: str | None = None,
        action_budget: int = 20,
        time_budget_seconds: float = 180,
        planner_timeout_seconds: float = 60,
    ) -> None:
        super().__init__(
            url,
            DefaultEventHandler(),
            proxy_url=proxy_url,
            output_file_directory=output_file_directory,
        )
        self.planner = CommandPlanner(
            planner_command, timeout_seconds=planner_timeout_seconds
        )
        self.action_budget = action_budget
        self.time_budget_seconds = time_budget_seconds
        self.exploration_result = None

    def execute(self):
        self.url = self.open_page(self.url)
        time.sleep(2)
        explorer = AgentExplorer(
            self.browser,
            self.planner,
            AgentPolicy(self.url),
            Path(self.output_file_directory) / "agent-trace.jsonl",
            action_budget=self.action_budget,
            time_budget_seconds=self.time_budget_seconds,
        )
        result = explorer.run()
        function_logs = {f'"{function_id}"' for function_id in explorer.function_ids}
        self.close_tools()
        self.logs.update(function_logs)
        self.exploration_result = result
        return result
