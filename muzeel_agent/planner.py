"""Adapter for an external AI planner with a strict one-action JSON contract."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
from typing import Any

from .models import AgentAction, BrowserObservation


DEFAULT_INSTRUCTIONS = Path(__file__).with_name("instructions") / "agent-system-ko.md"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PlannerDecision:
    action: AgentAction
    request_sha256: str
    response_sha256: str
    metadata: dict[str, Any]


class CommandPlanner:
    """Call one external process for each action without granting it browser access."""

    def __init__(
        self,
        command: str,
        *,
        instructions_path: Path = DEFAULT_INSTRUCTIONS,
        timeout_seconds: float = 60,
    ) -> None:
        self.command = shlex.split(command)
        if not self.command:
            raise ValueError("planner command cannot be empty")
        self.instructions = instructions_path.read_text(encoding="utf-8")
        self.timeout_seconds = timeout_seconds

    def next_action(
        self,
        observation: BrowserObservation,
        history: list[dict[str, Any]],
        budget: dict[str, Any],
    ) -> PlannerDecision:
        request = {
            "schema_version": 1,
            "role": "muzeel_safe_interaction_planner",
            "instructions": self.instructions,
            "observation": observation.to_dict(),
            "recent_history": history[-12:],
            "budget": budget,
        }
        request_text = canonical_json(request)
        process = subprocess.run(
            self.command,
            input=request_text + "\n",
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(
                f"planner exited {process.returncode}: {process.stderr.strip()[:500]}"
            )
        if len(process.stdout.encode("utf-8")) > 65536:
            raise ValueError("planner response exceeds 64 KiB")
        try:
            response = json.loads(process.stdout)
        except json.JSONDecodeError as error:
            raise ValueError("planner must return exactly one JSON object") from error
        if not isinstance(response, dict) or set(response) != {"action", "metadata"}:
            raise ValueError("planner response requires action and metadata only")
        metadata = response["metadata"]
        if (
            not isinstance(metadata, dict)
            or set(metadata) != {"agent", "provider", "model"}
            or metadata.get("agent") is not True
            or not isinstance(metadata.get("provider"), str)
            or not metadata.get("provider")
            or not isinstance(metadata.get("model"), str)
            or not metadata.get("model")
        ):
            raise ValueError("planner metadata must identify an actual AI agent")
        action = AgentAction.from_dict(response["action"])
        return PlannerDecision(
            action=action,
            request_sha256=sha256_text(request_text),
            response_sha256=sha256_text(canonical_json(response)),
            metadata=metadata,
        )
