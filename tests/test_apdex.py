import unittest

from loglens.apdex import apdex_by_path, apdex_score
from loglens.parse import LogRecord


def rec(path="/x", duration_ms=100.0):
    return LogRecord(
        source_ip="1.2.3.4", timestamp="01/Jan/2026:00:00:00 +0000",
        method="GET", path=path, status=200, duration_ms=duration_ms,
    )


class TestApdexScore(unittest.TestCase):
    def test_bucket_boundaries(self):
        records = [
            rec(duration_ms=500.0),    # exactly T: satisfied
            rec(duration_ms=400.0),    # under T: satisfied
            rec(duration_ms=600.0),    # T < d <= 4T: tolerating
            rec(duration_ms=2000.0),   # exactly 4T: tolerating
            rec(duration_ms=2001.0),   # over 4T: frustrated
        ]
        result = apdex_score(records, 0.5)
        self.assertEqual(result["samples"], 5)
        self.assertEqual(result["satisfied"], 2)
        self.assertEqual(result["tolerating"], 2)
        self.assertEqual(result["frustrated"], 1)
        self.assertAlmostEqual(result["score"], (2 + 2 / 2) / 5)
        self.assertEqual(result["threshold_s"], 0.5)

    def test_all_satisfied_scores_one(self):
        self.assertEqual(apdex_score([rec(), rec()], 0.5)["score"], 1.0)

    def test_all_frustrated_scores_zero(self):
        records = [rec(duration_ms=9999.0), rec(duration_ms=9999.0)]
        self.assertEqual(apdex_score(records, 0.5)["score"], 0.0)

    def test_records_without_durations_ignored(self):
        records = [rec(), rec(duration_ms=None)]
        result = apdex_score(records, 0.5)
        self.assertEqual(result["samples"], 1)

    def test_no_durations_returns_none(self):
        self.assertIsNone(apdex_score([rec(duration_ms=None)], 0.5))
        self.assertIsNone(apdex_score([], 0.5))

    def test_non_positive_threshold_rejected(self):
        with self.assertRaises(ValueError):
            apdex_score([rec()], 0.0)
        with self.assertRaises(ValueError):
            apdex_score([rec()], -1.0)


class TestApdexByPath(unittest.TestCase):
    def test_worst_score_first(self):
        records = [
            rec(path="/fast", duration_ms=100.0),
            rec(path="/slow", duration_ms=9000.0),
            rec(path="/mid", duration_ms=1000.0),
        ]
        rows = apdex_by_path(records, 0.5)
        self.assertEqual([r["path"] for r in rows], ["/slow", "/mid", "/fast"])
        self.assertEqual(rows[0]["score"], 0.0)
        self.assertEqual(rows[1]["score"], 0.5)
        self.assertEqual(rows[2]["score"], 1.0)

    def test_tie_breaks_by_sample_count(self):
        records = [
            rec(path="/one", duration_ms=100.0),
            rec(path="/two", duration_ms=100.0),
            rec(path="/two", duration_ms=100.0),
        ]
        rows = apdex_by_path(records, 0.5)
        self.assertEqual(rows[0]["path"], "/two")
        self.assertEqual(rows[0]["samples"], 2)

    def test_paths_without_durations_skipped(self):
        records = [rec(path="/timed"), rec(path="/untimed", duration_ms=None)]
        rows = apdex_by_path(records, 0.5)
        self.assertEqual([r["path"] for r in rows], ["/timed"])

    def test_limit(self):
        records = [rec(path=f"/p{i}", duration_ms=float(i)) for i in range(20)]
        self.assertEqual(len(apdex_by_path(records, 0.5, limit=5)), 5)


if __name__ == "__main__":
    unittest.main()
