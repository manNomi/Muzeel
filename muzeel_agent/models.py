"""Validated data contracts shared by the planner and browser executor."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


ALLOWED_ACTIONS = {"click", "scroll", "wait", "stop"}


@dataclass(frozen=True)
class InteractiveElement:
    selector: str
    tag: str
    role: str | None
    name: str
    disabled: bool
    href: str | None = None
    input_type: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "InteractiveElement":
        if not isinstance(raw, dict):
            raise ValueError("interactive element must be an object")
        allowed = set(cls.__dataclass_fields__)
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError(f"unknown interactive element fields: {sorted(unknown)}")
        element = cls(**raw)
        if not isinstance(element.selector, str) or not element.selector:
            raise ValueError("interactive element requires selector and tag")
        if not isinstance(element.tag, str) or not element.tag:
            raise ValueError("interactive element requires selector and tag")
        if element.role is not None and not isinstance(element.role, str):
            raise ValueError("interactive element role must be a string or null")
        if not isinstance(element.name, str) or not isinstance(element.disabled, bool):
            raise ValueError("interactive element name and disabled have invalid types")
        if element.href is not None and not isinstance(element.href, str):
            raise ValueError("interactive element href must be a string or null")
        if element.input_type is not None and not isinstance(element.input_type, str):
            raise ValueError("interactive element input_type must be a string or null")
        return element

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BrowserObservation:
    url: str
    title: str
    state_sha256: str
    interactive_elements: tuple[InteractiveElement, ...]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "BrowserObservation":
        if not isinstance(raw, dict):
            raise ValueError("observation must be an object")
        required = {"url", "title", "state_sha256", "interactive_elements"}
        if set(raw) != required:
            raise ValueError("observation fields do not match the contract")
        elements = tuple(
            InteractiveElement.from_dict(item) for item in raw["interactive_elements"]
        )
        if not isinstance(raw["url"], str) or not isinstance(raw["title"], str):
            raise ValueError("observation url and title must be strings")
        if not isinstance(raw["interactive_elements"], list):
            raise ValueError("interactive_elements must be an array")
        if not isinstance(raw["state_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", raw["state_sha256"]
        ):
            raise ValueError("state_sha256 must be a SHA-256 hex digest")
        return cls(
            url=raw["url"],
            title=raw["title"],
            state_sha256=raw["state_sha256"],
            interactive_elements=elements,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "state_sha256": self.state_sha256,
            "interactive_elements": [item.to_dict() for item in self.interactive_elements],
        }


@dataclass(frozen=True)
class AgentAction:
    action: str
    target: str | None = None
    delta_y: int | None = None
    seconds: float | None = None
    rationale: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AgentAction":
        if not isinstance(raw, dict):
            raise ValueError("action must be an object")
        unknown = set(raw) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"unknown action fields: {sorted(unknown)}")
        action = cls(**raw)
        action.validate_shape()
        return action

    def validate_shape(self) -> None:
        if self.action not in ALLOWED_ACTIONS:
            raise ValueError(f"unsupported action: {self.action}")
        if self.rationale is not None and (
            not isinstance(self.rationale, str) or len(self.rationale) > 300
        ):
            raise ValueError("rationale must be a string with at most 300 characters")
        if self.action == "click" and not self.target:
            raise ValueError("click requires target")
        if self.target is not None and not isinstance(self.target, str):
            raise ValueError("target must be a string")
        if self.action != "click" and self.target is not None:
            raise ValueError(f"{self.action} cannot have target")
        if self.action == "scroll":
            if (
                not isinstance(self.delta_y, int)
                or isinstance(self.delta_y, bool)
                or self.delta_y == 0
            ):
                raise ValueError("scroll requires a non-zero delta_y")
        elif self.delta_y is not None:
            raise ValueError(f"{self.action} cannot have delta_y")
        if self.action == "wait":
            if (
                not isinstance(self.seconds, (int, float))
                or isinstance(self.seconds, bool)
                or self.seconds <= 0
            ):
                raise ValueError("wait requires positive seconds")
        elif self.seconds is not None:
            raise ValueError(f"{self.action} cannot have seconds")

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}
