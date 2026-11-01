import unittest

from loglens.parse import parse_combined, parse_json_line, parse_lines

COMBINED = '10.0.0.1 - - [30/Oct/2026:14:05:01 +0000] "GET /api/orders HTTP/1.1" 200 1234'


class TestParseCombined(unittest.TestCase):
    def test_parses_fields(self):
        record = parse_combined(COMBINED)
        self.assertEqual(record.source_ip, "10.0.0.1")
        self.assertEqual(record.method, "GET")
        self.assertEqual(record.path, "/api/orders")
        self.assertEqual(record.status, 200)

    def test_rejects_garbage(self):
        self.assertIsNone(parse_combined("not a log line"))
        self.assertIsNone(parse_combined(""))


class TestParseJsonLine(unittest.TestCase):
    def test_parses_fields(self):
        record = parse_json_line('{"time": "t1", "method": "POST", "path": "/pay", "status": 502, "ip": "1.2.3.4"}')
        self.assertEqual(record.status, 502)
        self.assertEqual(record.source_ip, "1.2.3.4")

    def test_timestamp_alias(self):
        record = parse_json_line('{"timestamp": "t1", "method": "GET", "path": "/x", "status": 200}')
        self.assertEqual(record.timestamp, "t1")

    def test_rejects_missing_and_invalid(self):
        self.assertIsNone(parse_json_line('{"method": "GET"}'))
        self.assertIsNone(parse_json_line("{not json"))
        self.assertIsNone(parse_json_line('[1, 2]'))
        self.assertIsNone(parse_json_line('{"time":"t","method":"GET","path":"/x","status":"200"}'))


class TestParseLines(unittest.TestCase):
    def test_mixed_formats_and_blanks(self):
        lines = [COMBINED, "", "garbage", '{"time":"t","method":"GET","path":"/j","status":404}']
        records = parse_lines(lines)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[1].status, 404)

    def test_single_format_skips_others(self):
        records = parse_lines([COMBINED], formats=("json",))
        self.assertEqual(records, [])


class TestCombinedRequestTime(unittest.TestCase):
    def test_trailing_request_time_becomes_duration(self):
        line = '10.0.0.1 - - [30/Oct/2026:14:05:01 +0000] "GET /a HTTP/1.1" 200 1234 0.042'
        record = parse_combined(line)
        self.assertEqual(record.duration_ms, 42.0)
        self.assertEqual(record.status, 200)

    def test_integer_size_is_not_a_duration(self):
        line = '10.0.0.1 - - [30/Oct/2026:14:05:01 +0000] "GET /a HTTP/1.1" 200 1234'
        record = parse_combined(line)
        self.assertIsNone(record.duration_ms)

    def test_quoted_user_agent_ending_not_a_duration(self):
        line = ('10.0.0.1 - - [30/Oct/2026:14:05:01 +0000] "GET /a HTTP/1.1" 200 1234 '
                '"-" "Mozilla/5.0"')
        record = parse_combined(line)
        self.assertIsNone(record.duration_ms)


if __name__ == "__main__":
    unittest.main()
