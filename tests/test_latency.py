import unittest

from loglens.parse import LogRecord, parse_json_line
from loglens.stats import latency_summary, slowest_requests


def rec(duration, path="/a", status=200):
    return LogRecord(timestamp="t", method="GET", path=path, status=status,
                     duration_ms=duration)


class TestParseDuration(unittest.TestCase):
    def test_duration_ms_key(self):
        r = parse_json_line('{"time":"t","method":"GET","path":"/a","status":200,"duration_ms":42.5}')
        self.assertEqual(r.duration_ms, 42.5)

    def test_request_time_seconds_converted(self):
        r = parse_json_line('{"time":"t","method":"GET","path":"/a","status":200,"request_time":0.25}')
        self.assertEqual(r.duration_ms, 250.0)

    def test_missing_duration_is_none(self):
        r = parse_json_line('{"time":"t","method":"GET","path":"/a","status":200}')
        self.assertIsNone(r.duration_ms)

    def test_non_numeric_duration_ignored(self):
        r = parse_json_line('{"time":"t","method":"GET","path":"/a","status":200,"duration_ms":"fast"}')
        self.assertIsNone(r.duration_ms)


class TestLatencySummary(unittest.TestCase):
    def test_none_without_durations(self):
        self.assertIsNone(latency_summary([rec(None)]))

    def test_percentiles_over_known_durations(self):
        records = [rec(float(ms)) for ms in range(1, 101)] + [rec(None)]
        summary = latency_summary(records)
        self.assertEqual(summary["count"], 100.0)
        self.assertEqual(summary["p50"], 50.0)
        self.assertEqual(summary["p95"], 95.0)
        self.assertEqual(summary["p99"], 99.0)


class TestSlowestRequests(unittest.TestCase):
    def test_sorted_desc_and_limited(self):
        records = [rec(10), rec(500, "/slow", 200), rec(None), rec(100, "/mid")]
        slow = slowest_requests(records, 2)
        self.assertEqual([r.path for r in slow], ["/slow", "/mid"])

    def test_skips_missing_durations(self):
        self.assertEqual(slowest_requests([rec(None)]), [])


if __name__ == "__main__":
    unittest.main()
