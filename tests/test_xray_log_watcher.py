import json
import unittest

from watchdog.collectors.xray_log_watcher import XrayLogWatcher


class DummySource:
    def __init__(self):
        self.access_log = ""
        self.follow = False
        self.is_json = False


class XrayLogWatcherTextParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.watcher = XrayLogWatcher(DummySource())

    def test_parse_regular_access_log_line(self):
        line = (
            "2025/11/14 22:47:23.462702 from 58.152.53.88:52986 accepted "
            "ping0.cc:443 [inbound-19798 >> direct] email: dacog96g"
        )
        event = self.watcher._parse_text_line(line)  # pylint: disable=protected-access
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.email, "dacog96g")
        self.assertEqual(event.ip, "58.152.53.88")
        self.assertEqual(event.target, "ping0.cc:443")
        self.assertEqual(event.metadata["host"], "ping0.cc")
        self.assertEqual(event.metadata["port"], 443)
        self.assertNotIn("protocol", event.metadata)

    def test_filters_internal_api_loopback(self):
        line = (
            "2025/11/14 22:44:45.001961 from 127.0.0.1:33122 accepted "
            "tcp:127.0.0.1:62789 [api -> api]"
        )
        event = self.watcher._parse_text_line(line)  # pylint: disable=protected-access
        self.assertIsNone(event)

    def test_parse_udp_over_tcp_hostname(self):
        line = (
            "2025/11/14 22:46:55.673099 from 223.122.177.73:59188 accepted "
            "sp.v2.udp-over-tcp.arpa:0 [inbound-19798 >> direct] email: u7lkrk2d"
        )
        event = self.watcher._parse_text_line(line)  # pylint: disable=protected-access
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.metadata["host"], "sp.v2.udp-over-tcp.arpa")
        self.assertEqual(event.metadata["port"], 0)

    def test_parse_transport_prefixed_target(self):
        line = (
            "2025/11/14 22:46:49.857434 from 223.122.177.73:59588 accepted "
            "tcp:ipv6.ping0.cc:443 [inbound-19798 >> direct] email: u7lkrk2d"
        )
        event = self.watcher._parse_text_line(line)  # pylint: disable=protected-access
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.metadata["transport"], "tcp")
        self.assertEqual(event.metadata["host"], "ipv6.ping0.cc")
        self.assertEqual(event.metadata["port"], 443)


class XrayLogWatcherJsonParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = DummySource()
        self.source.is_json = True
        self.watcher = XrayLogWatcher(self.source)

    def test_filters_internal_api_loopback_json(self):
        record = {
            "detour": "api -> api",
            "target": "tcp:127.0.0.1:62789",
            "from": "127.0.0.1:33122",
        }
        event = self.watcher._parse_line(json.dumps(record))  # pylint: disable=protected-access
        self.assertIsNone(event)

    def test_keeps_regular_json_records(self):
        record = {
            "email": "dacog96g",
            "ip": "58.152.53.88",
            "target": "www.gstatic.com:80",
            "uplink": 123,
            "downlink": 456,
        }
        event = self.watcher._parse_line(json.dumps(record))  # pylint: disable=protected-access
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.email, "dacog96g")
        self.assertEqual(event.ip, "58.152.53.88")
        self.assertEqual(event.target, "www.gstatic.com:80")
        self.assertEqual(event.bytes_read, 123)
        self.assertEqual(event.bytes_written, 456)


if __name__ == "__main__":
    unittest.main()
