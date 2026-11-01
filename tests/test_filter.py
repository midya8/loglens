import unittest
from datetime import datetime, timezone

from loglens.filter import filter_records, parse_bound
from loglens.parse import LogRecord


def rec(ts, path="/a"):
    return LogRecord(timestamp=ts, method="GET", path=path, status=200)


T1 = "2026-10-31T22:00:01Z"
T2 = "2026-10-31T22:05:00+00:00"
T3 = "31/Oct/2026:22:10:00 +0000"  # combined format, same instant scale
BAD = "not-a-timestamp"


class TestFilterRecords(unittest.TestCase):
    def setUp(self):
        self.records = [rec(T1, "/early"), rec(T2, "/mid"), rec(T3, "/late")]

    def test_no_bounds_returns_input(self):
        self.assertEqual(filter_records(self.records), self.records)

    def test_since_excludes_earlier(self):
        since = parse_bound("2026-10-31T22:01:00Z")
        paths = [r.path for r in filter_records(self.records, since=since)]
        self.assertEqual(paths, ["/mid", "/late"])

    def test_until_excludes_later(self):
        until = parse_bound("2026-10-31T22:05:00Z")
        paths = [r.path for r in filter_records(self.records, until=until)]
        self.assertEqual(paths, ["/early", "/mid"])

    def test_window_inclusive_bounds(self):
        since = parse_bound(T1)
        until = parse_bound("2026-10-31T22:05:00Z")
        paths = [r.path for r in filter_records(self.records, since=since, until=until)]
        self.assertEqual(paths, ["/early", "/mid"])

    def test_unparseable_record_dropped_when_filtering(self):
        records = self.records + [rec(BAD, "/bad")]
        since = parse_bound("2026-10-31T00:00:00Z")
        paths = [r.path for r in filter_records(records, since=since)]
        self.assertNotIn("/bad", paths)

    def test_mixed_timestamp_formats_compare_by_instant(self):
        # T3 (combined) is the latest instant despite the different format.
        until = parse_bound("2026-10-31T22:07:00Z")
        paths = [r.path for r in filter_records(self.records, until=until)]
        self.assertEqual(paths, ["/early", "/mid"])

    def test_empty_result(self):
        since = parse_bound("2027-01-01T00:00:00Z")
        self.assertEqual(filter_records(self.records, since=since), [])


class TestParseBound(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(
            parse_bound("2026-10-31T22:00:01Z"),
            datetime(2026, 10, 31, 22, 0, 1, tzinfo=timezone.utc),
        )

    def test_date_only_midnight_utc(self):
        self.assertEqual(
            parse_bound("2026-10-31"),
            datetime(2026, 10, 31, 0, 0, 0, tzinfo=timezone.utc),
        )

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            parse_bound("tomorrow-ish")


if __name__ == "__main__":
    unittest.main()
