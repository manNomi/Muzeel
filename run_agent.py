#!/usr/bin/env python3
"""Run Muzeel with a policy-constrained external AI interaction planner."""

from __future__ import annotations

import argparse
import json

from AgentMainExecution import execute_agent
from config import db_details


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True)
    parser.add_argument("--proxy", required=True, help="read proxy host and port")
    parser.add_argument("--planner-command", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--action-budget", type=int, default=20)
    parser.add_argument("--time-budget", type=float, default=180)
    parser.add_argument("--planner-timeout", type=float, default=60)
    args = parser.parse_args()
    result = execute_agent(
        args.site,
        db_details,
        args.proxy,
        args.planner_command,
        args.output,
        action_budget=args.action_budget,
        time_budget_seconds=args.time_budget,
        planner_timeout_seconds=args.planner_timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not result["original_preserved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
