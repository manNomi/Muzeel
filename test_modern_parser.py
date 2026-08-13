import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from ModernFunctionParser import ModernFunctionParser


class ModernFunctionParserTest(unittest.TestCase):
    def parse(self, source):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", encoding="utf-8", delete=False
        ) as stream:
            stream.write(source)
            path = Path(stream.name)
        try:
            return ModernFunctionParser().parse_file(path)
        finally:
            path.unlink(missing_ok=True)

    def test_parses_modern_functions_and_unicode_offsets(self):
        source = "const label='한글'; const read=(value)=>value?.name ?? label; class A { method(){ return read(this); } }"
        functions = self.parse(source)
        self.assertEqual(2, len(functions))
        for function in functions:
            body = source[function["start"]:function["end"] + 1]
            self.assertTrue(body.startswith(("value", "{")))

    def test_parser_rejects_invalid_source_without_partial_output(self):
        with self.assertRaises(RuntimeError):
            self.parse("function broken( {")


if __name__ == "__main__":
    unittest.main()
