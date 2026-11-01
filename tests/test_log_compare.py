import unittest

from loglens.compare import compare_logs, format_log_comparison
from loglens.parse import LogRecord


def rec(path="/a", status=200, dur=None):
    return LogRecord(timestamp="t", method="GET", path=path, status=status,
                     duration_ms=dur)


class TestCompareLogs(unittest.TestCase):
    def test_error_rate_delta_and_paths(self):
        baseline = [rec("/a", 500), rec("/b", 200), rec("/gone", 500)]
        current = [rec("/a", 200), rec("/b", 200), rec("/new", 503)]
        comp = compare_logs(baseline, current)
        self.assertLess(comp.error_rate_delta, 0)
        self.assertEqual(comp.new_error_paths, ("/new",))
        self.assertEqual(comp.resolved_error_paths, ("/a", "/gone"))

    def test_regressions_ranked_by_error_increase(self):
        baseline = [rec("/a", 500), rec("/b", 500)]
        current = [rec("/a", 500), rec("/a", 500), rec("/a", 500),
                   rec("/b", 500), rec("/b", 500)]
        comp = compare_logs(baseline, current)
        self.assertEqual(comp.regressions[0]["path"], "/a")
        self.assertEqual(comp.regressions[0]["delta"], 2)
        self.assertEqual(comp.regressions[1]["path"], "/b")

    def test_improving_paths_are_not_regressions(self):
        baseline = [rec("/a", 500), rec("/a", 500)]
        current = [rec("/a", 500)]
        self.assertEqual(compare_logs(baseline, current).regressions, ())

    def test_latency_fields_none_without_durations(self):
        comp = compare_logs([rec()], [rec()])
        self.assertIsNone(comp.baseline_p95_ms)
        self.assertIsNone(comp.current_p50_ms)

    def test_latency_deltas(self):
        baseline = [rec("/a", 200, 10), rec("/a", 200, 20)]
        current = [rec("/a", 200, 100), rec("/a", 200, 200)]
        comp = compare_logs(baseline, current)
        self.assertEqual(comp.baseline_p50_ms, 10.0)   # nearest-rank p50
        self.assertEqual(comp.current_p50_ms, 100.0)

    def test_empty_sides(self):
        comp = compare_logs([], [])
        self.assertEqual(comp.baseline_requests, 0)
        self.assertEqual(comp.error_rate_delta, 0.0)


class TestFormatLogComparison(unittest.TestCase):
    def test_renders_all_sections(self):
        baseline = [rec("/old", 500, 10)]
        current = [rec("/new", 500, 20), rec("/new", 500, 30)]
        text = format_log_comparison(compare_logs(baseline, current))
        self.assertIn("Baseline: 1 requests", text)
        self.assertIn("New error paths: /new", text)
        self.assertIn("Resolved error paths: /old", text)
        self.assertIn("Biggest regressions:", text)
        self.assertIn("Latency p50:", text)

    def test_no_change_note(self):
        text = format_log_comparison(compare_logs([rec("/a", 500)], [rec("/a", 500)]))
        self.assertIn("No change in error paths.", text)


if __name__ == "__main__":
    unittest.main()
