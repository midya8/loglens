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


MIXED = """10.0.0.1 - - [30/Oct/2026:14:05:01 +0000] "GET /a HTTP/1.1" 200 100
{"time":"2026-10-31T22:00:01Z","method":"GET","path":"/b","status":500}
"""


class TestFormatDetection(unittest.TestCase):
    def run_file(self, argv, content):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.log"
            path.write_text(content)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(argv + [str(path)])
            return code, buf.getvalue()

    def test_auto_parses_mixed_file_by_default(self):
        code, out = self.run_file([], MIXED)
        self.assertEqual(code, 0)
        self.assertIn("Parsed records: 2", out)
        self.assertIn("Error rate (5xx): 50.0%", out)

    def test_forced_json_skips_combined_lines(self):
        code, out = self.run_file(["--format", "json"], MIXED)
        self.assertEqual(code, 0)
        self.assertIn("Parsed records: 1", out)

    def test_forced_combined_skips_json_lines(self):
        code, out = self.run_file(["--format", "combined"], MIXED)
        self.assertEqual(code, 0)
        self.assertIn("Parsed records: 1", out)
        self.assertIn("200: 1", out)


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

    def test_agents_text_and_json(self):
        log = LOG + '{"time":"2026-10-31T22:06:00Z","method":"GET","path":"/c","status":503,"user_agent":"Go-http-client/1.1"}\n'
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.log"
            path.write_text(log)
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["--format", "json", "--agents", str(path)])
            out = buf.getvalue()
        self.assertIn("Top 5 user agents: [('Go-http-client/1.1', 1)]", out)
        self.assertIn("Top 5 error user agents: [('Go-http-client/1.1', 1)]", out)

    def test_agents_in_json_summary(self):
        log = LOG + '{"time":"2026-10-31T22:06:00Z","method":"GET","path":"/c","status":503,"user_agent":"Go-http-client/1.1"}\n'
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.log"
            path.write_text(log)
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["--format", "json", "--agents", "--json", str(path)])
            data = json.loads(buf.getvalue())
        self.assertEqual(data["top_error_user_agents"], [{"user_agent": "Go-http-client/1.1", "count": 1}])

    def test_agents_omitted_from_json_without_flag(self):
        _, out = run(["--format", "json", "--json"])
        self.assertNotIn("top_user_agents", json.loads(out))

    def test_by_path_sort_p95_json(self):
        _, out = run(["--format", "json", "--by-path", "--sort", "p95", "--json"])
        rows = json.loads(out)["path_breakdown"]
        p95s = [r["p95_ms"] for r in rows]
        self.assertEqual(p95s, sorted(p95s, reverse=True))

    def test_by_path_sort_invalid_exits_2(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.log"
            path.write_text(LOG)
            with self.assertRaises(SystemExit) as ctx:
                main(["--by-path", "--sort", "bogus", str(path)])
        self.assertEqual(ctx.exception.code, 2)

    def test_status_filter_scopes_summary(self):
        _, out = run(["--format", "json", "--status", "5xx", "--json"])
        data = json.loads(out)
        self.assertEqual(data["parsed_records"], 1)
        self.assertEqual(data["status_distribution"], {"500": 1})
        self.assertEqual(data["status_classes"]["5xx"], 1)

    def test_status_filter_exact_code(self):
        _, out = run(["--format", "json", "--status", "200", "--json"])
        self.assertEqual(json.loads(out)["parsed_records"], 2)

    def test_status_filter_invalid_exits_2(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.log"
            path.write_text(LOG)
            with self.assertRaises(SystemExit) as ctx:
                main(["--status", "bogus", str(path)])
        self.assertEqual(ctx.exception.code, 2)

    def test_status_classes_in_text_and_json(self):
        _, out = run([])
        self.assertIn("Status classes:", out)
        _, out = run(["--format", "json", "--json"])
        data = json.loads(out)
        self.assertEqual(data["status_classes"],
                         {"2xx": 2, "3xx": 0, "4xx": 0, "5xx": 1, "other": 0})

    def test_referers_text_and_json(self):
        log = LOG + '{"time":"2026-10-31T22:06:00Z","method":"GET","path":"/c","status":503,"referer":"https://shop.example/cart"}\n'
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.log"
            path.write_text(log)
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["--format", "json", "--referers", "--json", str(path)])
            data = json.loads(buf.getvalue())
        self.assertEqual(data["top_referers"], [{"referer": "https://shop.example/cart", "count": 1}])
        self.assertEqual(data["top_error_referers"], [{"referer": "https://shop.example/cart", "count": 1}])

    def test_referers_omitted_from_json_without_flag(self):
        _, out = run(["--format", "json", "--json"])
        self.assertNotIn("top_referers", json.loads(out))

    def test_report_without_split_at_has_no_comparison(self):
        _, out = run(["--format", "json", "--report", "T"])
        self.assertNotIn("## Before/after", out)

    def test_text_mode_unchanged(self):
        _, out = run(["--format", "json"])
        self.assertTrue(out.startswith("Parsed records: 3"))


if __name__ == "__main__":
    unittest.main()
