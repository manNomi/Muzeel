"""Tamper-evident JSONL trace writer for agent decisions and outcomes."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def row_sha256(row: dict[str, Any]) -> str:
    payload = {key: value for key, value in row.items() if key != "row_sha256"}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class TraceWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size:
            raise FileExistsError(f"refusing to append to existing trace: {self.path}")
        self.previous_sha256: str | None = None
        self.count = 0

    def append(self, payload: dict[str, Any]) -> dict[str, Any]:
        reserved = {"schema_version", "step_index", "previous_sha256", "row_sha256"}
        if not isinstance(payload, dict) or set(payload) & reserved:
            raise ValueError("trace payload contains invalid or reserved fields")
        self.count += 1
        row = {
            "schema_version": 1,
            "step_index": self.count,
            "previous_sha256": self.previous_sha256,
            **payload,
        }
        row["row_sha256"] = row_sha256(row)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(canonical_json(row) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.previous_sha256 = row["row_sha256"]
        return row
