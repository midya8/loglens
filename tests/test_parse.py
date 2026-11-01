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


class TestParseCombinedAgents(unittest.TestCase):
    WITH_AGENT = ('10.0.0.1 - - [30/Oct/2026:14:05:01 +0000] "GET /api/orders HTTP/1.1" 200 1234 '
                  '"https://shop.example/orders" "Mozilla/5.0 Chrome/130.0" 0.012')
    WITHOUT_AGENT = COMBINED + " 0.012"

    def test_agent_captured_with_referer(self):
        record = parse_combined(self.WITH_AGENT)
        self.assertEqual(record.user_agent, "Mozilla/5.0 Chrome/130.0")
        self.assertEqual(record.duration_ms, 12.0)  # trailing request_time still wins

    def test_agent_empty_when_absent(self):
        record = parse_combined(self.WITHOUT_AGENT)
        self.assertEqual(record.user_agent, "")
        self.assertEqual(record.duration_ms, 12.0)

    def test_bare_line_still_parses(self):
        record = parse_combined(COMBINED)
        self.assertEqual(record.user_agent, "")

    def test_referer_captured(self):
        record = parse_combined(self.WITH_AGENT)
        self.assertEqual(record.referer, "https://shop.example/orders")

    def test_dash_referer_normalized_to_empty(self):
        line = ('10.0.0.1 - - [30/Oct/2026:14:05:01 +0000] "GET /a HTTP/1.1" 200 100 '
                '"-" "kube-probe/1.30"')
        record = parse_combined(line)
        self.assertEqual(record.referer, "")
        self.assertEqual(record.user_agent, "kube-probe/1.30")


class TestParseJsonLine(unittest.TestCase):
    def test_parses_fields(self):
        record = parse_json_line('{"time": "t1", "method": "POST", "path": "/pay", "status": 502, "ip": "1.2.3.4"}')
        self.assertEqual(record.status, 502)
        self.assertEqual(record.source_ip, "1.2.3.4")

    def test_timestamp_alias(self):
        record = parse_json_line('{"timestamp": "t1", "method": "GET", "path": "/x", "status": 200}')
        self.assertEqual(record.timestamp, "t1")

    def test_referer_keys(self):
        record = parse_json_line('{"time":"t","method":"GET","path":"/x","status":200,"referer":"https://a/b"}')
        self.assertEqual(record.referer, "https://a/b")
        record = parse_json_line('{"time":"t","method":"GET","path":"/x","status":200,"referrer":"https://a/b"}')
        self.assertEqual(record.referer, "https://a/b")
        record = parse_json_line('{"time":"t","method":"GET","path":"/x","status":200}')
        self.assertEqual(record.referer, "")

    def test_user_agent_keys(self):
        record = parse_json_line('{"time":"t","method":"GET","path":"/x","status":200,"user_agent":"curl/8.1"}')
        self.assertEqual(record.user_agent, "curl/8.1")
        record = parse_json_line('{"time":"t","method":"GET","path":"/x","status":200,"agent":"curl/8.1"}')
        self.assertEqual(record.user_agent, "curl/8.1")
        record = parse_json_line('{"time":"t","method":"GET","path":"/x","status":200}')
        self.assertEqual(record.user_agent, "")

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
