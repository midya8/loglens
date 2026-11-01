import unittest

from loglens.parse import LogRecord
from loglens.stats import top_user_agents
from loglens.stats import (
    error_rate,
    path_breakdown,
    percentile,
    status_distribution,
    top_error_ips,
    top_paths,
)


def rec(path, status, ip="10.0.0.1"):
    return LogRecord(timestamp="t", method="GET", path=path, status=status, source_ip=ip)


class TestStats(unittest.TestCase):
    def setUp(self):
        self.records = [
            rec("/a", 200), rec("/a", 200), rec("/b", 500),
            rec("/a", 503, "10.0.0.2"), rec("/c", 404),
        ]

    def test_status_distribution(self):
        self.assertEqual(status_distribution(self.records), {200: 2, 404: 1, 500: 1, 503: 1})

    def test_error_rate(self):
        self.assertAlmostEqual(error_rate(self.records), 2 / 5)
        self.assertEqual(error_rate([]), 0.0)

    def test_top_paths(self):
        self.assertEqual(top_paths(self.records, 1), [("/a", 3)])
        self.assertEqual(top_paths(self.records, 2, errors_only=True), [("/b", 1), ("/a", 1)])

    def test_top_error_ips(self):
        self.assertEqual(top_error_ips(self.records), [("10.0.0.1", 1), ("10.0.0.2", 1)])

    def test_percentile(self):
        self.assertEqual(percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50), 5)
        self.assertEqual(percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 99), 10)
        self.assertEqual(percentile([42], 95), 42)
        with self.assertRaises(ValueError):
            percentile([], 50)
        with self.assertRaises(ValueError):
            percentile([1], 0)


class TestPathBreakdown(unittest.TestCase):
    def rec(self, path, status, duration=None):
        return LogRecord(timestamp="t", method="GET", path=path, status=status,
                         duration_ms=duration)

    def test_sorted_worst_first(self):
        records = [
            self.rec("/ok", 200, 5.0), self.rec("/ok", 200, 6.0),
            self.rec("/bad", 500, 900.0), self.rec("/bad", 200, 10.0),
        ]
        rows = path_breakdown(records)
        self.assertEqual(rows[0]["path"], "/bad")
        self.assertEqual(rows[0]["error_rate"], 0.5)
        self.assertEqual(rows[0]["p95_ms"], 900.0)
        self.assertEqual(rows[1]["path"], "/ok")

    def test_p95_none_without_durations(self):
        rows = path_breakdown([self.rec("/a", 200)])
        self.assertIsNone(rows[0]["p95_ms"])

    def test_limit_applied(self):
        records = [self.rec(f"/p{i}", 200) for i in range(5)]
        self.assertEqual(len(path_breakdown(records, 2)), 2)

    def test_tiebreak_by_volume_then_name(self):
        records = [self.rec("/b", 200), self.rec("/a", 200), self.rec("/a", 200)]
        rows = path_breakdown(records)
        self.assertEqual([r["path"] for r in rows], ["/a", "/b"])


class TestTopUserAgents(unittest.TestCase):
    def rec(self, status, agent):
        return LogRecord(timestamp="t", method="GET", path="/x", status=status, user_agent=agent)

    def test_counts_and_ranking(self):
        records = [self.rec(200, "curl"), self.rec(500, "bot"), self.rec(503, "bot"), self.rec(200, "")]
        self.assertEqual(top_user_agents(records), [("bot", 2), ("curl", 1)])

    def test_errors_only(self):
        records = [self.rec(200, "curl"), self.rec(500, "bot")]
        self.assertEqual(top_user_agents(records, errors_only=True), [("bot", 1)])

    def test_empty_and_agentless(self):
        self.assertEqual(top_user_agents([]), [])
        self.assertEqual(top_user_agents([self.rec(500, "")]), [])


if __name__ == "__main__":
    unittest.main()
