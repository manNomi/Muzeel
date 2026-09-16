"""End-to-end Muzeel execution with an audited AI interaction agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from DataStore import DataStore
from LogParser import LogParser
from browser_interaction_bot.AgentExecution import AgentExecution
from muzeel_agent.audit import audit_trace
from muzeel_agent.gate import EliminationEvidence, evaluate_elimination_gate


def execute_agent(
    site: str,
    db_details: dict,
    proxy_url: str,
    planner_command: str,
    output_file_directory: str,
    *,
    action_budget: int = 20,
    time_budget_seconds: float = 180,
    planner_timeout_seconds: float = 60,
) -> dict[str, Any]:
    output = Path(output_file_directory).resolve()
    output.mkdir(parents=True, exist_ok=True)
    data_store = DataStore(site, db_details)
    data_store.persist_updated_files()
    execution = None
    exploration = None
    run_error = None
    try:
        execution = AgentExecution(
            site,
            planner_command,
            proxy_url=proxy_url,
            output_file_directory=str(output / "browser"),
            action_budget=action_budget,
            time_budget_seconds=time_budget_seconds,
            planner_timeout_seconds=planner_timeout_seconds,
        )
        exploration = execution.execute()
    except Exception as error:
        run_error = f"{type(error).__name__}: {str(error)[:1000]}"
        if execution is not None:
            try:
                execution.close_tools()
            except Exception:
                pass

    trace_path = output / "browser" / "agent-trace.jsonl"
    trace_audit = audit_trace(trace_path)
    exploration_completed = bool(
        exploration is not None and exploration.completed and exploration.run_error is None
    )
    evidence = EliminationEvidence(
        parser_failure_count=len(data_store.instrumentation_errors),
        protected_file_count=len(data_store.excluded_request_urls),
        trace_audit_passed=trace_audit.passed,
        exploration_completed=exploration_completed,
        executed_action_count=trace_audit.executed_action_count,
        policy_rejection_count=trace_audit.policy_rejection_count,
        action_failure_count=trace_audit.action_failure_count,
        navigation_violation_count=trace_audit.navigation_violation_count,
    )
    gate = evaluate_elimination_gate(evidence)
    used_function_ids = {}
    transformation_syntax_errors = {}
    transformation_run_error = None
    if gate.approved and execution is not None:
        try:
            used_function_ids = LogParser.parse_logs(
                execution.logs, data_store.request_url_content_file_map
            )
            data_store.remove_unused_functions(used_function_ids)
            transformation_syntax_errors = data_store.validate_updated_files()
        except Exception as error:
            transformation_run_error = f"{type(error).__name__}: {str(error)[:1000]}"
        if transformation_syntax_errors or transformation_run_error:
            data_store.preserve_original_files()
    else:
        data_store.preserve_original_files()
    data_store.persist_updated_files()

    function_count = sum(len(items) for items in data_store.function_id_map.values())
    used_count = sum(
        len(data_store.function_id_map[url] & used_function_ids.get(url, set()))
        for url in data_store.function_id_map
    )
    elimination_applied = (
        gate.approved
        and not transformation_syntax_errors
        and transformation_run_error is None
    )
    result = {
        "schema_version": 1,
        "site": site,
        "run_error": run_error,
        "exploration": exploration.to_dict() if exploration is not None else None,
        "trace_audit": trace_audit.to_dict(),
        "elimination_gate": gate.to_dict(),
        "transformation_syntax_gate": {
            "evaluated": gate.approved,
            "approved": elimination_applied,
            "errors": transformation_syntax_errors,
            "run_error": transformation_run_error,
        },
        "parser_failure_count": len(data_store.instrumentation_errors),
        "parser_failures": data_store.instrumentation_errors,
        "protected_file_count": len(data_store.excluded_request_urls),
        "protected_files": data_store.excluded_request_urls,
        "function_count": function_count,
        "used_function_count": used_count,
        "removed_function_count": function_count - used_count if elimination_applied else 0,
        "original_preserved": not elimination_applied,
        "release_status": {
            "approved": False,
            "reason": "independent_holdout_evidence_required",
        },
        "output_directory": str(output),
    }
    (output / "agent-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result
