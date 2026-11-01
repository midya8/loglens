import unittest
from datetime import datetime, timezone

from loglens.parse import LogRecord
from loglens.timeline import is_spike, bucket_records, format_timeline, parse_timestamp


def rec(ts, status=200):
    return LogRecord(timestamp=ts, method="GET", path="/x", status=status)


class TestParseTimestamp(unittest.TestCase):
    def test_combined_format(self):
        moment = parse_timestamp("30/Oct/2026:14:05:01 +0000")
        self.assertEqual((moment.year, moment.month, moment.day, moment.hour), (2026, 10, 30, 14))
        self.assertEqual(moment.tzinfo, timezone.utc)

    def test_iso_with_offset_normalizes(self):
        moment = parse_timestamp("2026-10-30T10:05:01-04:00")
        self.assertEqual(moment.utcoffset().total_seconds(), -4 * 3600)

    def test_naive_assumed_utc(self):
        self.assertEqual(parse_timestamp("2026-10-30T14:05:01").tzinfo, timezone.utc)
        self.assertEqual(parse_timestamp("2026-10-30 14:05:01").tzinfo, timezone.utc)

    def test_unparseable_returns_none(self):
        self.assertIsNone(parse_timestamp("not a timestamp"))
        self.assertIsNone(parse_timestamp(""))


class TestBucketRecords(unittest.TestCase):
    def test_groups_into_minute_buckets(self):
        records = [
            rec("30/Oct/2026:14:05:01 +0000"),
            rec("30/Oct/2026:14:05:40 +0000", 500),
            rec("30/Oct/2026:14:06:10 +0000", 503),
            rec("30/Oct/2026:14:06:20 +0000", 503),
        ]
        buckets = bucket_records(records, bucket_seconds=60)
        self.assertEqual(len(buckets), 2)
        self.assertEqual(buckets[0].requests, 2)
        self.assertEqual(buckets[0].errors, 1)
        self.assertEqual(buckets[1].requests, 2)
        self.assertEqual(buckets[1].errors, 2)
        self.assertAlmostEqual(buckets[1].error_rate, 1.0)

    def test_buckets_are_chronological(self):
        records = [
            rec("30/Oct/2026:14:06:00 +0000"),
            rec("30/Oct/2026:14:05:00 +0000"),
        ]
        buckets = bucket_records(records)
        self.assertLess(buckets[0].start, buckets[1].start)

    def test_unparseable_timestamps_skipped(self):
        records = [rec("garbage"), rec("30/Oct/2026:14:05:00 +0000")]
        buckets = bucket_records(records)
        self.assertEqual(len(buckets), 1)
        self.assertEqual(buckets[0].requests, 1)

    def test_empty_input(self):
        self.assertEqual(bucket_records([]), [])

    def test_rejects_non_positive_bucket(self):
        with self.assertRaises(ValueError):
            bucket_records([rec("30/Oct/2026:14:05:00 +0000")], bucket_seconds=0)

    def test_custom_threshold(self):
        records = [rec("30/Oct/2026:14:05:00 +0000", 404)]
        self.assertEqual(bucket_records(records)[0].errors, 0)
        self.assertEqual(bucket_records(records, error_threshold=400)[0].errors, 1)


class TestFormatTimeline(unittest.TestCase):
    def test_rows_show_counts_and_rate(self):
        buckets = bucket_records(
            [rec("30/Oct/2026:14:05:01 +0000"), rec("30/Oct/2026:14:05:40 +0000", 500)]
        )
        text = format_timeline(buckets)
        self.assertIn("14:05", text)
        self.assertIn("2 req", text)
        self.assertIn("50%", text)
        self.assertIn("#", text)

    def test_empty_renders_empty(self):
        self.assertEqual(format_timeline([]), "")


class TestSpikeFlagging(unittest.TestCase):
    def bucket(self, requests, errors):
        from loglens.timeline import Bucket
        return Bucket(start=datetime(2026, 10, 31, 22, 0, tzinfo=timezone.utc),
                      requests=requests, errors=errors)

    def test_spike_requires_both_conditions(self):
        self.assertTrue(is_spike(self.bucket(4, 2)))       # 50% rate, 2 errors
        self.assertFalse(is_spike(self.bucket(1, 1)))      # 100% rate but 1 error
        self.assertFalse(is_spike(self.bucket(100, 10)))   # 10 errors but 10% rate

    def test_custom_thresholds(self):
        self.assertTrue(is_spike(self.bucket(10, 1), min_error_rate=0.05, min_errors=1))

    def test_invalid_thresholds_rejected(self):
        with self.assertRaises(ValueError):
            is_spike(self.bucket(4, 2), min_error_rate=0)
        with self.assertRaises(ValueError):
            is_spike(self.bucket(4, 2), min_errors=0)

    def test_format_marks_spike(self):
        buckets = [self.bucket(4, 2), self.bucket(10, 0)]
        out = format_timeline(buckets)
        lines = out.splitlines()
        self.assertIn("<-- spike", lines[0])
        self.assertNotIn("<-- spike", lines[1])


if __name__ == "__main__":
    unittest.main()
