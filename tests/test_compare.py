import unittest
from datetime import datetime, timezone

from loglens.compare import compare_windows, format_comparison
from loglens.parse import LogRecord

SPLIT = datetime(2026, 10, 31, 22, 5, 0, tzinfo=timezone.utc)


def rec(ts, path, status=200):
    return LogRecord(timestamp=ts, method="GET", path=path, status=status)


class TestCompareWindows(unittest.TestCase):
    def setUp(self):
        self.records = [
            rec("2026-10-31T22:00:00Z", "/a", 200),
            rec("2026-10-31T22:01:00Z", "/old-err", 500),
            rec("2026-10-31T22:06:00Z", "/b", 200),
            rec("2026-10-31T22:07:00Z", "/new-err", 503),
            rec("2026-10-31T22:08:00Z", "/new-err", 503),
        ]

    def test_split_counts(self):
        comp = compare_windows(self.records, SPLIT)
        self.assertEqual(comp.before_requests, 2)
        self.assertEqual(comp.after_requests, 3)

    def test_split_boundary_goes_to_after(self):
        comp = compare_windows([rec("2026-10-31T22:05:00Z", "/x")], SPLIT)
        self.assertEqual(comp.before_requests, 0)
        self.assertEqual(comp.after_requests, 1)

    def test_error_rates_and_delta(self):
        comp = compare_windows(self.records, SPLIT)
        self.assertAlmostEqual(comp.before_error_rate, 0.5)
        self.assertAlmostEqual(comp.after_error_rate, 2 / 3)
        self.assertAlmostEqual(comp.error_rate_delta, 2 / 3 - 0.5)

    def test_new_and_resolved_paths(self):
        comp = compare_windows(self.records, SPLIT)
        self.assertEqual(comp.new_error_paths, ("/new-err",))
        self.assertEqual(comp.resolved_error_paths, ("/old-err",))

    def test_unparseable_timestamps_excluded(self):
        records = self.records + [rec("garbage", "/bad", 500)]
        comp = compare_windows(records, SPLIT)
        self.assertEqual(comp.before_requests + comp.after_requests, 5)

    def test_no_change_message(self):
        records = [rec("2026-10-31T22:00:00Z", "/a"), rec("2026-10-31T22:06:00Z", "/b")]
        text = format_comparison(compare_windows(records, SPLIT))
        self.assertIn("No change in error paths.", text)

    def test_format_includes_delta_sign(self):
        text = format_comparison(compare_windows(self.records, SPLIT))
        self.assertIn("(+16.7%)", text)


if __name__ == "__main__":
    unittest.main()
