"""
Pruebas unitarias para los sondeadores de red (HTTP y TCP).
Simula respuestas exitosas y excepciones comunes de red (DNS, Timeout, Connection Refused, HTTP 500).
"""

import socket
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

from monitor.models import TargetConfig, TargetType, TargetState
from monitor.probers import HttpProber, TcpProber, ProberFactory


class TestProbers(unittest.TestCase):

    def setUp(self):
        self.http_target = TargetConfig(
            name="Test HTTP Target",
            type=TargetType.HTTP,
            url="https://example.com/api",
            timeout_seconds=2.0
        )
        self.tcp_target = TargetConfig(
            name="Test TCP Target",
            type=TargetType.TCP,
            host="127.0.0.1",
            port=8080,
            timeout_seconds=1.0
        )

    @patch("urllib.request.urlopen")
    def test_http_probe_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {"Content-Type": "application/json", "Server": "Nginx"}
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        prober = HttpProber()
        result = prober.probe(self.http_target)

        self.assertTrue(result.is_up)
        self.assertEqual(result.state, TargetState.UP)
        self.assertEqual(result.status_code, 200)
        self.assertGreaterEqual(result.response_time_ms, 0.0)
        self.assertIsNone(result.error_message)

    @patch("urllib.request.urlopen")
    def test_http_probe_500_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com/api",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=None
        )

        prober = HttpProber()
        result = prober.probe(self.http_target)

        self.assertFalse(result.is_up)
        self.assertEqual(result.state, TargetState.DOWN)
        self.assertEqual(result.status_code, 500)
        self.assertIn("HTTP Error 500", result.error_message)

    @patch("urllib.request.urlopen")
    def test_http_probe_dns_error(self, mock_urlopen):
        # Simulación de socket.gaierror envuelto en URLError
        dns_error = socket.gaierror(-2, "Name or service not known")
        mock_urlopen.side_effect = urllib.error.URLError(reason=dns_error)

        prober = HttpProber()
        result = prober.probe(self.http_target)

        self.assertFalse(result.is_up)
        self.assertEqual(result.state, TargetState.DOWN)
        self.assertIn("Fallo DNS", result.error_message)

    @patch("urllib.request.urlopen")
    def test_http_probe_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = socket.timeout("timed out")

        prober = HttpProber()
        result = prober.probe(self.http_target)

        self.assertFalse(result.is_up)
        self.assertEqual(result.state, TargetState.DOWN)
        self.assertIn("Timeout", result.error_message)

    @patch("socket.create_connection")
    def test_tcp_probe_success(self, mock_create_connection):
        mock_sock = MagicMock()
        mock_create_connection.return_value = mock_sock

        prober = TcpProber()
        result = prober.probe(self.tcp_target)

        self.assertTrue(result.is_up)
        self.assertEqual(result.state, TargetState.UP)
        self.assertIsNone(result.error_message)
        mock_sock.close.assert_called_once()

    @patch("socket.create_connection")
    def test_tcp_probe_connection_refused(self, mock_create_connection):
        mock_create_connection.side_effect = ConnectionRefusedError(10061, "Connection refused")

        prober = TcpProber()
        result = prober.probe(self.tcp_target)

        self.assertFalse(result.is_up)
        self.assertEqual(result.state, TargetState.DOWN)
        self.assertIn("rechazada", result.error_message)

    @patch("socket.create_connection")
    def test_tcp_probe_timeout(self, mock_create_connection):
        mock_create_connection.side_effect = socket.timeout("timed out")

        prober = TcpProber()
        result = prober.probe(self.tcp_target)

        self.assertFalse(result.is_up)
        self.assertEqual(result.state, TargetState.DOWN)
        self.assertIn("Timeout TCP", result.error_message)

    def test_prober_factory(self):
        p1 = ProberFactory.get_prober(TargetType.HTTP)
        self.assertIsInstance(p1, HttpProber)
        p2 = ProberFactory.get_prober(TargetType.TCP)
        self.assertIsInstance(p2, TcpProber)


if __name__ == "__main__":
    unittest.main()
