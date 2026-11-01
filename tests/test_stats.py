import unittest

from loglens.parse import LogRecord
from loglens.stats import status_classes, top_methods, top_referers, top_user_agents
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

    def test_sort_by_requests(self):
        records = [self.rec("/bad", 500), self.rec("/busy", 200),
                   self.rec("/busy", 200), self.rec("/busy", 200)]
        rows = path_breakdown(records, sort="requests")
        self.assertEqual([r["path"] for r in rows], ["/busy", "/bad"])

    def test_sort_by_p95_untimed_last(self):
        records = [self.rec("/slow", 200, 900.0), self.rec("/fast", 200, 10.0),
                   self.rec("/untimed", 500)]
        rows = path_breakdown(records, sort="p95")
        self.assertEqual([r["path"] for r in rows], ["/slow", "/fast", "/untimed"])

    def test_unknown_sort_rejected(self):
        with self.assertRaises(ValueError):
            path_breakdown([self.rec("/a", 200)], sort="bogus")


class TestStatusClasses(unittest.TestCase):
    def rec(self, status):
        return LogRecord(timestamp="t", method="GET", path="/x", status=status)

    def test_rolls_up_by_class(self):
        records = [self.rec(200), self.rec(204), self.rec(301), self.rec(404),
                   self.rec(500), self.rec(503)]
        self.assertEqual(status_classes(records),
                         {"2xx": 2, "3xx": 1, "4xx": 1, "5xx": 2, "other": 0})

    def test_out_of_range_statuses_count_as_other(self):
        records = [self.rec(100), self.rec(999)]
        self.assertEqual(status_classes(records)["other"], 2)

    def test_empty_input_returns_zeroed_classes(self):
        self.assertEqual(status_classes([]),
                         {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0, "other": 0})


class TestTopMethods(unittest.TestCase):
    def rec(self, method, status):
        return LogRecord(timestamp="t", method=method, path="/x", status=status)

    def test_counts_and_ranking(self):
        records = [self.rec("GET", 200), self.rec("POST", 500),
                   self.rec("POST", 200), self.rec("", 200)]
        self.assertEqual(top_methods(records), [("POST", 2), ("GET", 1)])

    def test_errors_only(self):
        records = [self.rec("GET", 200), self.rec("POST", 500), self.rec("GET", 503)]
        self.assertEqual(top_methods(records, errors_only=True),
                         [("POST", 1), ("GET", 1)])  # ties keep first-seen order

    def test_empty_methods_skipped(self):
        self.assertEqual(top_methods([self.rec("", 500)], errors_only=True), [])


class TestTopReferers(unittest.TestCase):
    def rec(self, status, referer):
        return LogRecord(timestamp="t", method="GET", path="/x", status=status, referer=referer)

    def test_counts_and_ranking(self):
        records = [self.rec(200, "https://a/x"), self.rec(500, "https://a/cart"),
                   self.rec(503, "https://a/cart"), self.rec(200, "")]
        self.assertEqual(top_referers(records), [("https://a/cart", 2), ("https://a/x", 1)])

    def test_errors_only(self):
        records = [self.rec(200, "https://a/x"), self.rec(500, "https://a/cart")]
        self.assertEqual(top_referers(records, errors_only=True), [("https://a/cart", 1)])

    def test_empty_and_refererless(self):
        self.assertEqual(top_referers([]), [])
        self.assertEqual(top_referers([self.rec(500, "")]), [])


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
