import unittest

from run_snapshot_agent import cache_key, content_type, is_javascript, make_fake_connection


class SnapshotAgentTest(unittest.TestCase):
    def test_cache_key_preserves_or_strips_query_and_always_strips_fragment(self):
        url = "https://example.test/app.js?v=2#part"
        self.assertEqual(url.split("#")[0], cache_key(url, "preserve"))
        self.assertEqual("https://example.test/app.js", cache_key(url, "strip"))

    def test_detects_javascript_from_header_or_extension(self):
        header_entry = {
            "key": "https://example.test/chunk",
            "headers": [["Content-Type", "application/javascript; charset=utf-8"]],
        }
        extension_entry = {
            "key": "https://example.test/chunk.mjs?v=1",
            "headers": [["Content-Type", "text/plain"]],
        }
        self.assertEqual("application/javascript", content_type(header_entry))
        self.assertTrue(is_javascript(header_entry))
        self.assertTrue(is_javascript(extension_entry))

    def test_fake_connection_returns_snapshot_rows(self):
        rows = [("https://example.test/app.js", "script-001.c")]
        connection = make_fake_connection(rows)
        with connection.cursor() as cursor:
            cursor.execute("ignored")
            self.assertEqual(rows, cursor.fetchall())


if __name__ == "__main__":
    unittest.main()
