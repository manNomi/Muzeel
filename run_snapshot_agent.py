#!/usr/bin/env python3
"""Run the safe Muzeel AI Agent against a frozen HTTP snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urlsplit, urlunsplit

from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from seleniumwire import webdriver

from DataStore import DataStore
from LogParser import LogParser
from muzeel_agent.audit import audit_trace
from muzeel_agent.browser import AgentExplorer
from muzeel_agent.gate import EliminationEvidence, evaluate_elimination_gate
from muzeel_agent.planner import CommandPlanner
from muzeel_agent.policy import AgentPolicy


def cache_key(url: str, query_policy: str) -> str:
    parts = urlsplit(url)
    query = "" if query_policy == "strip" else parts.query
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def content_type(entry: dict) -> str:
    return next(
        (
            value.split(";", 1)[0].strip().lower()
            for name, value in entry["headers"]
            if name.lower() == "content-type"
        ),
        "",
    )


def is_javascript(entry: dict) -> bool:
    path = urlsplit(entry["key"]).path.lower()
    kind = content_type(entry)
    return "javascript" in kind or "ecmascript" in kind or path.endswith((".js", ".mjs"))


def make_fake_connection(rows: list[tuple[str, str]]):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _sql):
            return None

        def fetchall(self):
            return rows

    class Connection:
        def cursor(self):
            return Cursor()

    return Connection()


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def node_syntax(path: Path) -> dict:
    result = subprocess.run(
        ["node", "--check", str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "passed": result.returncode == 0,
        "stderr": result.stderr.strip()[:1000] or None,
    }


def browser_options(profile: Path) -> Options:
    options = Options()
    options.page_load_strategy = "eager"
    options.add_experimental_option("mobileEmulation", {"deviceName": "iPhone X"})
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--no-first-run")
    options.add_argument(f"--user-data-dir={profile}")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    return options


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True)
    parser.add_argument("--site-id")
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--planner-command", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--action-budget", type=int, default=12)
    parser.add_argument("--time-budget", type=float, default=300)
    parser.add_argument("--planner-timeout", type=float, default=90)
    args = parser.parse_args()
    site_id = args.site_id or urlsplit(args.site).netloc.replace(".", "-")
    if args.output.exists():
        parser.error("output directory already exists")
    if not (args.snapshot_dir / "manifest.json").is_file():
        parser.error("snapshot manifest is missing")
    if not args.driver.is_file():
        parser.error("ChromeDriver is missing")

    output = args.output.resolve()
    snapshot_dir = args.snapshot_dir.resolve()
    output.mkdir(parents=True)
    work = output / "work"
    data_dir = work / "data"
    muzeel_data_dir = data_dir / "muzeel"
    processed_dir = output / "processed-js"
    instrumented_dir = output / "instrumented-js"
    for directory in (muzeel_data_dir, processed_dir, instrumented_dir):
        directory.mkdir(parents=True)
    snapshot = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    query_policy = snapshot.get("query_policy", "strip")
    javascript_entries = [
        entry for entry in snapshot["entries"].values() if is_javascript(entry)
    ]
    rows = []
    entry_files = {}
    for index, entry in enumerate(javascript_entries, 1):
        filename = f"script-{index:03d}.c"
        shutil.copy2(snapshot_dir / entry["body_file"], data_dir / filename)
        rows.append((entry["key"], filename))
        entry_files[entry["key"]] = filename

    import pymysql

    pymysql.connect = lambda *_args, **_kwargs: make_fake_connection(rows)
    previous_directory = Path.cwd()
    os.chdir(work)
    driver = None
    try:
        store = DataStore(
            args.site,
            {
                "database": "muzeel",
                "user": "root",
                "password": "",
                "cache_directory": str(work),
                "port": 3306,
            },
        )
        store.persist_updated_files()
        for entry in javascript_entries:
            filename = entry_files[entry["key"]].replace(".c", ".m")
            shutil.copy2(muzeel_data_dir / filename, instrumented_dir / filename.replace(".m", ".js"))

        hits = []
        misses = []
        with tempfile.TemporaryDirectory(prefix="muzeel-agent-profile-") as profile:
            driver = webdriver.Chrome(
                service=Service(str(args.driver.resolve())),
                options=browser_options(Path(profile)),
                seleniumwire_options={
                    "disable_encoding": True,
                    "verify_ssl": False,
                    "suppress_connection_errors": True,
                },
            )

            def replay(request):
                key = cache_key(request.url, query_policy)
                entry = snapshot["entries"].get(key)
                if entry is None:
                    misses.append(key)
                    request.create_response(
                        status_code=404,
                        headers={"Content-Type": "text/plain", "Cache-Control": "no-store"},
                        body=b"snapshot miss",
                    )
                    return
                hits.append(key)
                body_path = snapshot_dir / entry["body_file"]
                if key in entry_files:
                    instrumented = muzeel_data_dir / entry_files[key].replace(".c", ".m")
                    if instrumented.is_file():
                        body_path = instrumented
                request.create_response(
                    status_code=entry["status"],
                    headers=entry["headers"],
                    body=body_path.read_bytes(),
                )

            driver.request_interceptor = replay
            driver.set_page_load_timeout(30)
            driver.get(args.site)
            time.sleep(3)
            explorer = AgentExplorer(
                driver,
                CommandPlanner(
                    args.planner_command,
                    timeout_seconds=args.planner_timeout,
                ),
                AgentPolicy(args.site),
                output / "agent-trace.jsonl",
                action_budget=args.action_budget,
                time_budget_seconds=args.time_budget,
            )
            exploration = explorer.run()
            driver.save_screenshot(str(output / "final-exploration.png"))
            raw_console_logs = sorted(explorer.console_logs)
            function_logs = {f'"{function_id}"' for function_id in explorer.function_ids}

        trace_audit = audit_trace(output / "agent-trace.jsonl")
        elimination_gate = evaluate_elimination_gate(
            EliminationEvidence(
                parser_failure_count=len(store.instrumentation_errors),
                protected_file_count=len(store.excluded_request_urls),
                trace_audit_passed=trace_audit.passed,
                exploration_completed=exploration.completed and exploration.run_error is None,
                executed_action_count=trace_audit.executed_action_count,
                policy_rejection_count=trace_audit.policy_rejection_count,
                action_failure_count=trace_audit.action_failure_count,
                navigation_violation_count=trace_audit.navigation_violation_count,
            )
        )
        used = LogParser.parse_logs(function_logs, store.request_url_content_file_map)
        transformation_errors = {}
        if elimination_gate.approved:
            store.remove_unused_functions(used)
            transformation_errors = store.validate_updated_files()
        if not elimination_gate.approved or transformation_errors:
            store.preserve_original_files()
        store.persist_updated_files()
        elimination_applied = elimination_gate.approved and not transformation_errors

        scripts = []
        for entry in javascript_entries:
            filename = entry_files[entry["key"]]
            original = data_dir / filename
            processed = muzeel_data_dir / filename.replace(".c", ".m")
            exported = processed_dir / filename.replace(".c", ".js")
            shutil.copy2(processed, exported)
            functions = store.function_id_map.get(entry["key"], set())
            used_ids = used.get(entry["key"], set())
            scripts.append(
                {
                    "url": entry["key"],
                    "source_file": str(original),
                    "processed_file": str(exported),
                    "original_bytes": original.stat().st_size,
                    "processed_bytes": exported.stat().st_size,
                    "function_count": len(functions),
                    "used_function_count": len(functions & used_ids),
                    "removed_function_count": len(functions - used_ids) if elimination_applied else 0,
                    "syntax": node_syntax(exported),
                }
            )
        original_bytes = sum(row["original_bytes"] for row in scripts)
        processed_bytes = sum(row["processed_bytes"] for row in scripts)
        repository = Path(__file__).resolve().parent
        result = {
            "schema_version": 1,
            "site_id": site_id,
            "site": args.site,
            "snapshot_dir": str(snapshot_dir),
            "snapshot_tree_sha256": tree_sha256(snapshot_dir),
            "muzeel_repo_commit": subprocess.check_output(
                ["git", "-C", str(Path(__file__).resolve().parent), "rev-parse", "HEAD"],
                text=True,
            ).strip(),
            "provenance": {
                "runner": str(Path(__file__).resolve()),
                "runner_sha256": file_sha256(Path(__file__).resolve()),
                "repository_status": subprocess.check_output(
                    ["git", "-C", str(repository), "status", "--porcelain=v1"],
                    text=True,
                ).splitlines(),
                "repository_diff_sha256": hashlib.sha256(
                    subprocess.check_output(
                        ["git", "-C", str(repository), "diff", "--binary", "HEAD"]
                    )
                ).hexdigest(),
            },
            "exploration": exploration.to_dict(),
            "trace_audit": trace_audit.to_dict(),
            "elimination_gate": elimination_gate.to_dict(),
            "transformation_syntax_gate": {
                "approved": elimination_applied,
                "errors": transformation_errors,
            },
            "parser_failures": store.instrumentation_errors,
            "protected_files": store.excluded_request_urls,
            "snapshot_hit_count": len(hits),
            "snapshot_miss_count": len(misses),
            "snapshot_unique_misses": sorted(set(misses)),
            "javascript_file_count": len(scripts),
            "total_function_count": sum(row["function_count"] for row in scripts),
            "used_function_count": sum(row["used_function_count"] for row in scripts),
            "removed_function_count": sum(row["removed_function_count"] for row in scripts),
            "javascript_bytes": {
                "original": original_bytes,
                "processed": processed_bytes,
                "reduction_pct": round(
                    100 * (original_bytes - processed_bytes) / original_bytes, 3
                ) if original_bytes else None,
            },
            "original_preserved": not elimination_applied,
            "release_status": {
                "approved": False,
                "reason": "independent_holdout_evidence_required",
            },
            "scripts": scripts,
        }
        (output / "raw-console-logs.json").write_text(
            json.dumps(raw_console_logs, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (output / "used-function-ids.json").write_text(
            json.dumps(
                {url: sorted(values) for url, values in used.items()},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        (output / "agent-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if elimination_applied else 2
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        os.chdir(previous_directory)


if __name__ == "__main__":
    raise SystemExit(main())
