import unittest

from loglens.parse import LogRecord
from loglens.report import render_incident_report


def rec(ts, path, status, duration=None, ip="10.0.0.1"):
    return LogRecord(timestamp=ts, method="GET", path=path, status=status,
                     source_ip=ip, duration_ms=duration)


class TestRenderIncidentReport(unittest.TestCase):
    def setUp(self):
        self.records = [
            rec("2026-10-31T22:00:01Z", "/a", 200, 10.0),
            rec("2026-10-31T22:00:02Z", "/b", 500, 900.0),
            rec("2026-10-31T22:05:00Z", "/a", 200),
        ]

    def test_empty_input(self):
        out = render_incident_report([])
        self.assertIn("No parseable records", out)

    def test_header_stats(self):
        out = render_incident_report(self.records, title="Spike")
        self.assertTrue(out.startswith("# Spike"))
        self.assertIn("**Records:** 3", out)
        self.assertIn("**Error rate (5xx):** 33.3%", out)
        self.assertIn("**Window:** 2026-10-31T22:00:01+00:00", out)

    def test_failing_paths_and_ips(self):
        out = render_incident_report(self.records)
        self.assertIn("## Hottest failing paths", out)
        self.assertIn("`/b` - 1 error\n", out)  # singular
        self.assertIn("10.0.0.1 - 1 error\n", out)

    def test_latency_section_present_with_durations(self):
        out = render_incident_report(self.records)
        self.assertIn("## Latency", out)
        self.assertIn("p99 900.0 ms", out)
        self.assertIn("900.0 ms - `GET /b` -> 500", out)

    def test_latency_section_omitted_without_durations(self):
        records = [rec("2026-10-31T22:00:01Z", "/a", 200)]
        out = render_incident_report(records)
        self.assertNotIn("## Latency", out)

    def test_peak_section(self):
        out = render_incident_report(self.records)
        self.assertIn("## Peak", out)
        self.assertIn("1 error in 2 requests", out)

    def test_incident_window_with_spikes(self):
        records = [
            rec("2026-10-31T22:00:01Z", "/a", 200),
            rec("2026-10-31T22:01:01Z", "/b", 500),
            rec("2026-10-31T22:01:02Z", "/b", 500),
            rec("2026-10-31T22:01:03Z", "/a", 200),
            rec("2026-10-31T22:09:01Z", "/b", 500),
            rec("2026-10-31T22:09:02Z", "/b", 502),
            rec("2026-10-31T22:09:03Z", "/a", 200),
        ]
        out = render_incident_report(records)
        self.assertIn("## Incident window", out)
        self.assertIn("**First spike:** 2026-10-31T22:01:00+00:00", out)
        self.assertIn("**Last spike:** 2026-10-31T22:09:00+00:00", out)
        self.assertIn("- **Peak:** 2026-10-31T22:01:00+00:00 - 2 errors in 3 requests", out)
        self.assertNotIn("## Peak", out)

    def test_incident_window_omitted_without_spikes(self):
        # one error in a bucket never reads as a spike, so Peak still shows
        out = render_incident_report(self.records)
        self.assertNotIn("## Incident window", out)
        self.assertIn("## Peak", out)

    def test_no_peak_without_errors(self):
        records = [rec("2026-10-31T22:00:01Z", "/a", 200)]
        self.assertNotIn("## Peak", render_incident_report(records))

    def test_per_path_breakdown_table(self):
        out = render_incident_report(self.records)
        self.assertIn("## Per-path breakdown", out)
        self.assertIn("| `/b` | 1 | 1 | 100% | 900 ms |", out)
        self.assertIn("| `/a` | 2 | 0 | 0% | 10 ms |", out)

    def test_no_sections_without_errors(self):
        records = [rec("2026-10-31T22:00:01Z", "/a", 200, 5.0)]
        out = render_incident_report(records)
        self.assertNotIn("Hottest failing paths", out)
        self.assertNotIn("Source IPs", out)


if __name__ == "__main__":
    unittest.main()
