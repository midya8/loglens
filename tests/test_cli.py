import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from loglens.__main__ import main

LOG = """\
{"time":"2026-10-31T22:00:01Z","method":"GET","path":"/a","status":200,"duration_ms":10.0}
{"time":"2026-10-31T22:00:02Z","method":"GET","path":"/b","status":500,"duration_ms":900.0}
{"time":"2026-10-31T22:05:00Z","method":"GET","path":"/a","status":200}
"""


def run(argv):
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "app.log"
        path.write_text(LOG)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv + [str(path)])
        return code, buf.getvalue()


class TestJsonOutput(unittest.TestCase):
    def test_summary_shape(self):
        code, out = run(["--format", "json", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["parsed_records"], 3)
        self.assertAlmostEqual(data["error_rate_5xx"], 1 / 3)
        self.assertEqual(data["status_distribution"], {"200": 2, "500": 1})
        self.assertEqual(data["top_paths"][0], {"path": "/a", "count": 2})
        self.assertEqual(data["top_error_ips"], [])

    def test_latency_included_when_present(self):
        _, out = run(["--format", "json", "--json", "--latency"])
        data = json.loads(out)
        self.assertEqual(data["latency_ms"]["count"], 2)
        self.assertEqual(data["latency_ms"]["p99"], 900.0)
        self.assertEqual(data["slowest_requests"][0]["path"], "/b")

    def test_latency_omitted_without_durations(self):
        _, out = run(["--format", "json", "--json", "--since", "2026-10-31T22:05:00Z"])
        data = json.loads(out)
        self.assertNotIn("latency_ms", data)

    def test_timeline_buckets(self):
        _, out = run(["--format", "json", "--json", "--timeline", "--bucket", "300"])
        data = json.loads(out)
        self.assertEqual(len(data["timeline"]), 2)
        self.assertEqual(data["timeline"][0]["requests"], 2)
        self.assertEqual(data["timeline"][0]["errors"], 1)

    def test_report_with_split_at_includes_comparison(self):
        _, out = run(["--format", "json", "--report", "T", "--split-at", "2026-10-31T22:02:00Z"])
        self.assertTrue(out.startswith("# T"))
        self.assertIn("## Before/after 2026-10-31T22:02:00+00:00", out)
        self.assertIn("50.0% before, 0.0% after (-50.0%)", out)
        self.assertIn("- **Recovered paths:** `/b`", out)

    def test_report_without_split_at_has_no_comparison(self):
        _, out = run(["--format", "json", "--report", "T"])
        self.assertNotIn("## Before/after", out)

    def test_text_mode_unchanged(self):
        _, out = run(["--format", "json"])
        self.assertTrue(out.startswith("Parsed records: 3"))


if __name__ == "__main__":
    unittest.main()
