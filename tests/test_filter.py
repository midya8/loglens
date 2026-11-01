import unittest
from datetime import datetime, timezone

from loglens.filter import (filter_by_path_prefix, filter_by_status, filter_records,
                            parse_bound, parse_prefix_spec, parse_status_spec)
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


class TestParseStatusSpec(unittest.TestCase):
    def test_exact_codes_and_classes(self):
        codes, classes = parse_status_spec("5xx,404")
        self.assertEqual(codes, frozenset({404}))
        self.assertEqual(classes, frozenset({5}))

    def test_multiple_classes_case_insensitive(self):
        codes, classes = parse_status_spec("4XX, 5xx")
        self.assertEqual(codes, frozenset())
        self.assertEqual(classes, frozenset({4, 5}))

    def test_invalid_spec_raises(self):
        for bad in ("bogus", "5x", "5000", "xx", ""):
            with self.assertRaises(ValueError):
                parse_status_spec(bad)


class TestFilterByStatus(unittest.TestCase):
    def rec(self, status):
        return LogRecord(timestamp="t", method="GET", path="/x", status=status)

    def test_class_filter(self):
        records = [self.rec(200), self.rec(404), self.rec(500), self.rec(503)]
        kept = filter_by_status(records, *parse_status_spec("5xx"))
        self.assertEqual([r.status for r in kept], [500, 503])

    def test_exact_code_plus_class(self):
        records = [self.rec(200), self.rec(404), self.rec(500)]
        kept = filter_by_status(records, *parse_status_spec("404,5xx"))
        self.assertEqual([r.status for r in kept], [404, 500])

    def test_no_match_returns_empty(self):
        kept = filter_by_status([self.rec(200)], *parse_status_spec("5xx"))
        self.assertEqual(kept, [])


class TestParsePrefixSpec(unittest.TestCase):
    def test_single_and_multiple(self):
        self.assertEqual(parse_prefix_spec("/api"), ("/api",))
        self.assertEqual(parse_prefix_spec("/api, /health"), ("/api", "/health"))

    def test_empty_segments_rejected(self):
        for bad in ("", ",", "/api,", ",/api"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                parse_prefix_spec(bad)


class TestFilterByPathPrefix(unittest.TestCase):
    def rec(self, path):
        return LogRecord(timestamp="t", method="GET", path=path, status=200)

    def test_keeps_matching_prefixes(self):
        records = [self.rec("/api/a"), self.rec("/health"), self.rec("/web")]
        kept = filter_by_path_prefix(records, ("/api", "/health"))
        self.assertEqual([r.path for r in kept], ["/api/a", "/health"])

    def test_no_match_returns_empty(self):
        self.assertEqual(filter_by_path_prefix([self.rec("/web")], ("/api",)), [])


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
