"""Bridge Babel's modern JavaScript parser into Muzeel's Python pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess


class ModernFunctionParser:
    def __init__(self, parser_script: Path | None = None) -> None:
        self.node = shutil.which("node")
        if not self.node:
            raise RuntimeError("Node.js is required for modern JavaScript parsing")
        self.parser_script = parser_script or Path(__file__).with_name(
            "modern_js_functions.mjs"
        )

    def parse_file(self, source_path: Path) -> list[dict]:
        process = subprocess.run(
            [self.node, str(self.parser_script), str(source_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            detail = process.stderr.strip().splitlines()
            message = detail[0] if detail else "unknown parser error"
            raise RuntimeError(f"modern JavaScript parse failed: {message}")
        payload = json.loads(process.stdout)
        functions = payload.get("functions")
        if not isinstance(functions, list):
            raise RuntimeError("modern JavaScript parser returned an invalid payload")
        return functions
