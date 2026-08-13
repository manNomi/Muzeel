from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from DataStore import DataStore


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _sql):
        return None

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows

    def cursor(self):
        return FakeCursor(self.rows)


class ModernDataStoreTest(unittest.TestCase):
    def make_store(self, source, request_url="https://example.test/app.js"):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        (root / "data" / "muzeel").mkdir(parents=True)
        (root / "data" / "script.c").write_text(source, encoding="utf-8")
        with patch(
            "DataStore.pymysql.connect",
            return_value=FakeConnection([(request_url, "script.c")]),
        ):
            store = DataStore(
                "https://example.test",
                {"cache_directory": str(root), "database": "test"},
            )
        return temporary, root, request_url, store

    def assert_node_syntax(self, source, root):
        path = root / "syntax-check.js"
        path.write_text(source, encoding="utf-8")
        result = subprocess.run(
            ["node", "--check", str(path)], capture_output=True, text=True
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_instruments_and_eliminates_modern_function_bodies(self):
        source = (
            "const label='한글';"
            "const unused=(value)=>value?.name ?? label;"
            "function used(){'use strict'\nreturn 1}used();"
        )
        temporary, root, request_url, store = self.make_store(source)
        self.addCleanup(temporary.cleanup)
        self.assertEqual({}, store.instrumentation_errors)
        self.assertEqual(2, len(store.function_id_map[request_url]))
        self.assert_node_syntax(store.data_map[request_url]["updated"], root)

        used_id = next(
            function_id
            for function_id, metadata in store.function_metadata_map[request_url].items()
            if metadata["function_type"] == "FunctionDeclaration"
        )
        store.remove_unused_functions({request_url: {used_id}})
        processed = store.data_map[request_url]["updated"]
        self.assertIn("const unused=(value)=>void 0", processed)
        self.assertIn("function used(){'use strict'\nreturn 1}", processed)
        self.assert_node_syntax(processed, root)

    def test_invalid_javascript_is_preserved_fail_closed(self):
        source = "const broken = ( => 1"
        temporary, _root, request_url, store = self.make_store(source)
        self.addCleanup(temporary.cleanup)
        self.assertIn(request_url, store.instrumentation_errors)
        self.assertEqual(source, store.data_map[request_url]["updated"])
        store.remove_unused_functions({})
        self.assertEqual(source, store.data_map[request_url]["updated"])

    def test_cross_origin_javascript_is_preserved_by_default(self):
        source = "function analytics(){return 'external'}"
        temporary, _root, request_url, store = self.make_store(
            source, request_url="https://cdn.example.net/analytics.js"
        )
        self.addCleanup(temporary.cleanup)
        self.assertEqual(
            "cross_origin_preserved", store.excluded_request_urls[request_url]
        )
        self.assertEqual(set(), store.function_id_map[request_url])
        self.assertEqual(source, store.data_map[request_url]["updated"])
        store.remove_unused_functions({})
        self.assertEqual(source, store.data_map[request_url]["updated"])

    def test_protected_monitoring_runtime_is_preserved(self):
        source = "const Sentry={init(){return true}};Sentry.init()"
        temporary, _root, request_url, store = self.make_store(source)
        self.addCleanup(temporary.cleanup)
        self.assertEqual(
            "protected_runtime_marker:sentry",
            store.excluded_request_urls[request_url],
        )
        self.assertEqual(source, store.data_map[request_url]["updated"])


if __name__ == "__main__":
    unittest.main()
