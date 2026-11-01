import unittest

from loglens.parse import LogRecord, parse_combined, parse_json_line
from loglens.stats import human_bytes, size_summary, top_paths_by_bytes

COMBINED = ('10.0.0.1 - - [30/Oct/2026:14:05:01 +0000] '
            '"GET /app.js HTTP/1.1" 200 84210 "-" "agent"')


def rec(path="/a", size=100):
    return LogRecord(timestamp="t", method="GET", path=path, status=200,
                     size_bytes=size)


class TestParseSizes(unittest.TestCase):
    def test_combined_captures_size(self):
        record = parse_combined(COMBINED)
        self.assertEqual(record.size_bytes, 84210)

    def test_combined_dash_size_is_none(self):
        line = COMBINED.replace("200 84210", "200 -")
        self.assertIsNone(parse_combined(line).size_bytes)

    def test_combined_with_trailing_request_time_still_captures_size(self):
        record = parse_combined(COMBINED + " 0.042")
        self.assertEqual(record.size_bytes, 84210)
        self.assertAlmostEqual(record.duration_ms, 42.0)

    def test_json_size_key_variants(self):
        for key in ("size_bytes", "body_bytes_sent", "bytes", "size"):
            line = ('{"time": "t", "method": "GET", "path": "/a", "status": 200,'
                    f' "{key}": 512}}')
            self.assertEqual(parse_json_line(line).size_bytes, 512, key)

    def test_json_without_size_is_none(self):
        line = '{"time": "t", "method": "GET", "path": "/a", "status": 200}'
        self.assertIsNone(parse_json_line(line).size_bytes)

    def test_json_non_numeric_size_ignored(self):
        line = ('{"time": "t", "method": "GET", "path": "/a", "status": 200,'
                ' "bytes": "big"}')
        self.assertIsNone(parse_json_line(line).size_bytes)


class TestSizeSummary(unittest.TestCase):
    def test_aggregates(self):
        summary = size_summary([rec(size=100), rec(size=300)])
        self.assertEqual(summary["total_bytes"], 400)
        self.assertEqual(summary["count"], 2)
        self.assertAlmostEqual(summary["mean_bytes"], 200.0)
        self.assertEqual(summary["max_bytes"], 300)

    def test_none_when_no_sizes(self):
        bare = LogRecord(timestamp="t", method="GET", path="/a", status=200)
        self.assertIsNone(size_summary([bare]))

    def test_skips_records_without_size(self):
        bare = LogRecord(timestamp="t", method="GET", path="/a", status=200)
        summary = size_summary([bare, rec(size=50)])
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["total_bytes"], 50)


class TestTopPathsByBytes(unittest.TestCase):
    def test_ranked_by_bytes_not_requests(self):
        records = [rec("/chatty", 10), rec("/chatty", 10), rec("/chatty", 10),
                   rec("/heavy", 1000)]
        ranked = top_paths_by_bytes(records)
        self.assertEqual(ranked[0]["path"], "/heavy")
        self.assertAlmostEqual(ranked[0]["share"], 1000 / 1030)
        self.assertEqual(ranked[1]["requests"], 3)

    def test_limit_and_empty(self):
        self.assertEqual(top_paths_by_bytes([]), [])
        records = [rec(f"/p{i}", 10 * (i + 1)) for i in range(5)]
        self.assertEqual(len(top_paths_by_bytes(records, limit=2)), 2)


class TestHumanBytes(unittest.TestCase):
    def test_units(self):
        self.assertEqual(human_bytes(950), "950 B")
        self.assertEqual(human_bytes(12697), "12.4 KB")
        self.assertEqual(human_bytes(3 * 1024 * 1024 + 100000), "3.1 MB")


if __name__ == "__main__":
    unittest.main()
