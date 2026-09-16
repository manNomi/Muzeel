"""Fail-closed policy for actions proposed by an external AI planner."""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urljoin, urlsplit

from .models import AgentAction, BrowserObservation, InteractiveElement


DENIED_NAME_PATTERN = re.compile(
    r"(?:로그인|로그아웃|회원가입|탈퇴|삭제|결제|구매|주문|신청|제출|전송|"
    r"업로드|다운로드|저장|login|log[ -]?out|sign[ -]?(?:in|up|out)|delete|"
    r"remove|purchase|checkout|pay|order|submit|send|apply|upload|download|save)",
    re.IGNORECASE,
)
DENIED_PATH_PATTERN = re.compile(
    r"/(?:login|logout|signup|register|checkout|payment|purchase|delete|account|my)(?:/|$)",
    re.IGNORECASE,
)
SAFE_ROLES = {"button", "tab", "option", "menuitem", "switch", "combobox"}
SAFE_TAGS = {"button"}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    element: InteractiveElement | None = None


class AgentPolicy:
    def __init__(
        self,
        base_url: str,
        *,
        max_scroll_pixels: int = 800,
        max_wait_seconds: float = 3,
    ) -> None:
        self.base_url = base_url
        self.base_origin = self._origin(base_url)
        self.max_scroll_pixels = max_scroll_pixels
        self.max_wait_seconds = max_wait_seconds

    @staticmethod
    def _origin(url: str) -> tuple[str, str]:
        split = urlsplit(url)
        return split.scheme, split.netloc

    def evaluate(
        self, action: AgentAction, observation: BrowserObservation
    ) -> PolicyDecision:
        if self._origin(observation.url) != self.base_origin:
            return PolicyDecision(False, "observation_origin_changed")
        if action.action == "stop":
            return PolicyDecision(True, "safe_stop")
        if action.action == "scroll":
            if abs(action.delta_y or 0) > self.max_scroll_pixels:
                return PolicyDecision(False, "scroll_budget_exceeded")
            return PolicyDecision(True, "safe_scroll")
        if action.action == "wait":
            if (action.seconds or 0) > self.max_wait_seconds:
                return PolicyDecision(False, "wait_budget_exceeded")
            return PolicyDecision(True, "safe_wait")

        matching = [
            element
            for element in observation.interactive_elements
            if element.selector == action.target
        ]
        if len(matching) != 1:
            return PolicyDecision(False, "target_not_uniquely_observed")
        element = matching[0]
        if element.disabled:
            return PolicyDecision(False, "target_disabled", element)
        if element.tag in {"input", "textarea", "select", "form"}:
            return PolicyDecision(False, "form_control_denied", element)
        if element.input_type in {"file", "submit", "password", "email", "tel"}:
            return PolicyDecision(False, "sensitive_input_denied", element)
        if DENIED_NAME_PATTERN.search(element.name or ""):
            return PolicyDecision(False, "dangerous_intent_name", element)
        if element.href:
            destination = urljoin(observation.url, element.href)
            if self._origin(destination) != self.base_origin:
                return PolicyDecision(False, "cross_origin_navigation_denied", element)
            if DENIED_PATH_PATTERN.search(urlsplit(destination).path):
                return PolicyDecision(False, "sensitive_path_denied", element)
            return PolicyDecision(False, "navigation_denied_by_default", element)
        if element.tag not in SAFE_TAGS and (element.role or "") not in SAFE_ROLES:
            return PolicyDecision(False, "unsupported_control_type", element)
        return PolicyDecision(True, "safe_observed_control", element)

    def navigation_is_safe(self, before_url: str, after_url: str) -> bool:
        before = urlsplit(before_url)
        after = urlsplit(after_url)
        return (
            (before.scheme, before.netloc) == (after.scheme, after.netloc)
            and before.path == after.path
        )
