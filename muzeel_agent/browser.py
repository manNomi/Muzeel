"""Selenium observer and policy-enforced exploration loop for Muzeel."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any, Protocol

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .models import AgentAction, BrowserObservation, InteractiveElement
from .planner import PlannerDecision
from .policy import AgentPolicy
from .trace import TraceWriter


FUNCTION_MARKER = re.compile(r'(https?://[^"\\]+? \| \d+ \| \d+)')


class Planner(Protocol):
    def next_action(
        self,
        observation: BrowserObservation,
        history: list[dict[str, Any]],
        budget: dict[str, Any],
    ) -> PlannerDecision: ...


OBSERVE_INTERACTIVE_SCRIPT = r"""
const query = 'a,button,input,select,textarea,[role],[tabindex]';
function selectorFor(element) {
  if (element.id) return '#' + CSS.escape(element.id);
  if (element.getAttribute('data-testid')) {
    return '[data-testid="' + CSS.escape(element.getAttribute('data-testid')) + '"]';
  }
  const parts = [];
  let node = element;
  while (node && node.nodeType === Node.ELEMENT_NODE && node !== document.body) {
    let part = node.tagName.toLowerCase();
    const parent = node.parentElement;
    if (parent) {
      const siblings = Array.from(parent.children).filter(
        sibling => sibling.tagName === node.tagName
      );
      if (siblings.length > 1) {
        part += ':nth-of-type(' + (siblings.indexOf(node) + 1) + ')';
      }
    }
    parts.unshift(part);
    node = parent;
  }
  return 'body > ' + parts.join(' > ');
}
function visible(element) {
  const style = getComputedStyle(element);
  const rect = element.getBoundingClientRect();
  return style.display !== 'none' && style.visibility !== 'hidden' &&
    rect.width > 0 && rect.height > 0 && rect.bottom >= 0 && rect.top <= innerHeight;
}
return Array.from(document.querySelectorAll(query))
  .filter(visible)
  .slice(0, 200)
  .map(element => ({
    selector: selectorFor(element),
    tag: element.tagName.toLowerCase(),
    role: element.getAttribute('role'),
    name: (element.getAttribute('aria-label') || element.innerText || element.value || '')
      .trim().replace(/\s+/g, ' ').slice(0, 240),
    disabled: Boolean(element.disabled || element.getAttribute('aria-disabled') === 'true'),
    href: element.getAttribute('href'),
    input_type: element.getAttribute('type')
  }));
"""


class BrowserObserver:
    def __init__(self, driver: Any) -> None:
        self.driver = driver

    def capture(self) -> BrowserObservation:
        elements = self.driver.execute_script(OBSERVE_INTERACTIVE_SCRIPT)
        page_source = self.driver.page_source
        state_payload = json.dumps(
            {
                "url": self.driver.current_url,
                "title": self.driver.title,
                "page_source_sha256": hashlib.sha256(
                    page_source.encode("utf-8")
                ).hexdigest(),
                "elements": elements,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return BrowserObservation(
            url=self.driver.current_url,
            title=self.driver.title,
            state_sha256=hashlib.sha256(state_payload.encode("utf-8")).hexdigest(),
            interactive_elements=tuple(
                InteractiveElement.from_dict(element) for element in elements
            ),
        )


@dataclass(frozen=True)
class ExplorationResult:
    completed: bool
    stop_reason: str
    elapsed_seconds: float
    decision_count: int
    executed_action_count: int
    policy_rejection_count: int
    action_failure_count: int
    navigation_violation_count: int
    unique_function_marker_count: int
    trace_path: str
    run_error: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentExplorer:
    def __init__(
        self,
        driver: Any,
        planner: Planner,
        policy: AgentPolicy,
        trace_path: Path,
        *,
        action_budget: int = 20,
        time_budget_seconds: float = 180,
        plateau_limit: int = 5,
        settle_seconds: float = 0.35,
    ) -> None:
        if min(action_budget, plateau_limit) < 1 or time_budget_seconds <= 0:
            raise ValueError("exploration budgets must be positive")
        self.driver = driver
        self.planner = planner
        self.policy = policy
        self.trace = TraceWriter(trace_path)
        self.action_budget = action_budget
        self.time_budget_seconds = time_budget_seconds
        self.plateau_limit = plateau_limit
        self.settle_seconds = settle_seconds
        self.function_ids: set[str] = set()
        self.console_logs: set[str] = set()

    def _drain_console(self) -> set[str]:
        before = set(self.function_ids)
        for entry in self.driver.get_log("browser"):
            message = entry.get("message", "")
            self.console_logs.add(message)
            self.function_ids.update(FUNCTION_MARKER.findall(message))
        return self.function_ids - before

    def _execute(self, action: AgentAction) -> None:
        if action.action == "scroll":
            self.driver.execute_script("window.scrollBy(0, arguments[0])", action.delta_y)
            return
        if action.action == "wait":
            time.sleep(action.seconds or 0)
            return
        if action.action == "click":
            element = WebDriverWait(self.driver, 10).until(
                lambda current: current.find_element(By.CSS_SELECTOR, action.target)
            )
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'})", element
            )
            element.click()
            return
        raise ValueError(f"cannot execute action: {action.action}")

    def _close_new_windows(self, original_window: str, original_handles: set[str]) -> bool:
        current_handles = set(self.driver.window_handles)
        extra = current_handles - original_handles
        for handle in extra:
            self.driver.switch_to.window(handle)
            self.driver.close()
        self.driver.switch_to.window(original_window)
        return bool(extra)

    def run(self) -> ExplorationResult:
        started = time.monotonic()
        observer = BrowserObserver(self.driver)
        history: list[dict[str, Any]] = []
        executed = 0
        rejected = 0
        failures = 0
        navigation_violations = 0
        plateau = 0
        completed = False
        stop_reason = "unknown"
        run_error = None
        self._drain_console()
        try:
            observation = observer.capture()
            max_decisions = self.action_budget + 3
            while self.trace.count < max_decisions:
                elapsed = time.monotonic() - started
                if elapsed >= self.time_budget_seconds:
                    stop_reason = "time_budget"
                    break
                if executed >= self.action_budget:
                    completed = True
                    stop_reason = "action_budget"
                    break
                decision = self.planner.next_action(
                    observation,
                    history,
                    {
                        "remaining_actions": self.action_budget - executed,
                        "remaining_seconds": round(
                            self.time_budget_seconds - elapsed, 3
                        ),
                        "plateau_actions": plateau,
                    },
                )
                action = decision.action
                policy = self.policy.evaluate(action, observation)
                base_payload = {
                    "action": action.to_dict(),
                    "planner": {
                        "request_sha256": decision.request_sha256,
                        "response_sha256": decision.response_sha256,
                        "metadata": decision.metadata,
                    },
                    "policy": {
                        "allowed": policy.allowed,
                        "reason": policy.reason,
                    },
                    "before": observation.to_dict(),
                }
                if not policy.allowed:
                    rejected += 1
                    row = self.trace.append(
                        {
                            **base_payload,
                            "executed": False,
                            "outcome": "policy_rejected",
                            "after": None,
                            "new_function_marker_count": 0,
                            "navigation_violation": False,
                            "error": None,
                        }
                    )
                    history.append(
                        {
                            "action": row["action"],
                            "outcome": row["outcome"],
                            "policy_reason": policy.reason,
                        }
                    )
                    if rejected > 2:
                        stop_reason = "policy_rejections_exceeded"
                        break
                    continue
                if action.action == "stop":
                    self.trace.append(
                        {
                            **base_payload,
                            "executed": False,
                            "outcome": "agent_stop",
                            "after": None,
                            "new_function_marker_count": 0,
                            "navigation_violation": False,
                            "error": None,
                        }
                    )
                    completed = True
                    stop_reason = "agent_stop"
                    break

                original_window = self.driver.current_window_handle
                original_handles = set(self.driver.window_handles)
                error = None
                try:
                    self._execute(action)
                    time.sleep(self.settle_seconds)
                except Exception as exception:
                    error = f"{type(exception).__name__}: {str(exception)[:500]}"
                    failures += 1
                new_window = self._close_new_windows(original_window, original_handles)
                after = observer.capture()
                navigation_violation = new_window or not self.policy.navigation_is_safe(
                    observation.url, after.url
                )
                if navigation_violation:
                    navigation_violations += 1
                    if after.url != observation.url:
                        self.driver.back()
                        time.sleep(self.settle_seconds)
                        after = observer.capture()
                new_markers = self._drain_console()
                state_changed = observation.state_sha256 != after.state_sha256
                outcome = (
                    "action_failed"
                    if error
                    else (
                        "navigation_violation"
                        if navigation_violation
                        else (
                            "action_effect"
                            if state_changed or new_markers
                            else "action_no_effect"
                        )
                    )
                )
                self.trace.append(
                    {
                        **base_payload,
                        "executed": True,
                        "outcome": outcome,
                        "after": {
                            "url": after.url,
                            "state_sha256": after.state_sha256,
                        },
                        "new_function_marker_count": len(new_markers),
                        "navigation_violation": navigation_violation,
                        "error": error,
                    }
                )
                executed += 1
                history.append(
                    {
                        "action": action.to_dict(),
                        "outcome": outcome,
                        "new_function_marker_count": len(new_markers),
                        "after_state_sha256": after.state_sha256,
                    }
                )
                plateau = plateau + 1 if outcome == "action_no_effect" else 0
                observation = after
                if error:
                    stop_reason = "action_failure"
                    break
                if navigation_violation:
                    stop_reason = "navigation_violation"
                    break
                if plateau >= self.plateau_limit:
                    completed = True
                    stop_reason = "coverage_plateau"
                    break
        except Exception as exception:
            run_error = f"{type(exception).__name__}: {str(exception)[:1000]}"
            stop_reason = "run_error"
        return ExplorationResult(
            completed=completed,
            stop_reason=stop_reason,
            elapsed_seconds=round(time.monotonic() - started, 6),
            decision_count=self.trace.count,
            executed_action_count=executed,
            policy_rejection_count=rejected,
            action_failure_count=failures,
            navigation_violation_count=navigation_violations,
            unique_function_marker_count=len(self.function_ids),
            trace_path=str(self.trace.path.resolve()),
            run_error=run_error,
        )
