import unittest

from loglens.compare import compare_windows
from loglens.parse import LogRecord
from loglens.report import render_incident_report
from loglens.timeline import parse_timestamp


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

    def test_user_agents_section(self):
        records = [
            rec("2026-10-31T22:00:01Z", "/a", 500, ip="10.0.0.1"),
            rec("2026-10-31T22:00:02Z", "/b", 503, ip="10.0.0.2"),
        ]
        records[0] = LogRecord(timestamp=records[0].timestamp, method="GET", path="/a",
                               status=500, source_ip="10.0.0.1", user_agent="Go-http-client/1.1")
        out = render_incident_report(records)
        self.assertIn("## User agents behind 5xxs", out)
        self.assertIn("`Go-http-client/1.1` - 1 error", out)

    def test_user_agents_section_omitted_without_agents(self):
        out = render_incident_report(self.records)
        self.assertNotIn("## User agents behind 5xxs", out)

    def test_comparison_section_included(self):
        records = [
            rec("2026-10-31T21:59:00Z", "/a", 200),
            rec("2026-10-31T22:01:00Z", "/b", 500),
            rec("2026-10-31T22:01:30Z", "/c", 502),
            rec("2026-10-31T22:02:00Z", "/a", 200),
        ]
        comparison = compare_windows(records, parse_timestamp("2026-10-31T22:00:00Z"))
        out = render_incident_report(records, comparison=comparison)
        self.assertIn("## Before/after 2026-10-31T22:00:00+00:00", out)
        self.assertIn("- **Requests:** 1 before, 3 after", out)
        self.assertIn("- **Error rate:** 0.0% before, 66.7% after (+66.7%)", out)
        self.assertIn("- **New failing paths:** `/b`, `/c`", out)
        self.assertNotIn("Recovered paths", out)

    def test_comparison_section_omitted_by_default(self):
        out = render_incident_report(self.records)
        self.assertNotIn("## Before/after", out)

    def test_comparison_no_change_note(self):
        records = [
            rec("2026-10-31T21:59:00Z", "/a", 500),
            rec("2026-10-31T22:01:00Z", "/a", 500),
        ]
        comparison = compare_windows(records, parse_timestamp("2026-10-31T22:00:00Z"))
        out = render_incident_report(records, comparison=comparison)
        self.assertIn("- **Error paths:** no change", out)

    def test_no_sections_without_errors(self):
        records = [rec("2026-10-31T22:00:01Z", "/a", 200, 5.0)]
        out = render_incident_report(records)
        self.assertNotIn("Hottest failing paths", out)
        self.assertNotIn("Source IPs", out)


if __name__ == "__main__":
    unittest.main()
