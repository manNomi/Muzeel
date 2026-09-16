import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = (
    ROOT / "experiments" / "state-aware-exploration" / "validate_transition.py"
)
EXAMPLE = (
    ROOT / "experiments" / "state-aware-exploration" / "transition.example.json"
)


class StateTransitionDatasetTest(unittest.TestCase):
    def run_validator(self, path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), str(path)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_public_example_is_valid(self) -> None:
        result = self.run_validator(EXAMPLE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("transition dataset: valid", result.stdout)

    def test_raw_javascript_is_rejected(self) -> None:
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        data["javascript_source"] = "function privateSiteCode() {}"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsafe.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            result = self.run_validator(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("forbidden public keys", result.stderr)

    def test_script_count_must_match_records(self) -> None:
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        data["discovery"]["new_script_count"] = 2
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mismatch.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            result = self.run_validator(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("new_script_count", result.stderr)


if __name__ == "__main__":
    unittest.main()
