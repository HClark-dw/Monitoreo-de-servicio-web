"""
Pruebas de integración para la API REST HTTP y endpoints de monitoreo.
"""

import json
import logging
import unittest
import urllib.request
import urllib.error

from monitor.api import MonitorApiServer
from monitor.models import TargetConfig, TargetType
from monitor.store import MetricsStore


class TestApiServer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.logger = logging.getLogger("TestApiLogger")
        cls.logger.addHandler(logging.NullHandler())
        cls.store = MetricsStore()

        # Registrar un target de prueba
        cls.test_target = TargetConfig(
            id="test-api-srv",
            name="API Microservice",
            type=TargetType.HTTP,
            url="https://api.github.com"
        )
        cls.store.register_target(cls.test_target)

        # Usar un puerto no estándar para pruebas
        cls.port = 8999
        cls.host = "127.0.0.1"
        cls.server = MonitorApiServer(
            host=cls.host,
            port=cls.port,
            store=cls.store,
            logger=cls.logger
        )
        cls.server.start(daemon=True)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_get_health(self):
        url = f"http://{self.host}:{self.port}/health"
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "healthy")

    def test_get_status(self):
        url = f"http://{self.host}:{self.port}/status"
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("system", data)
            self.assertIn("services", data)
            self.assertEqual(data["system"]["total_monitored_services"], 1)

    def test_get_targets(self):
        url = f"http://{self.host}:{self.port}/targets"
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["count"], 1)
            self.assertEqual(data["targets"][0]["id"], "test-api-srv")

    def test_post_targets(self):
        url = f"http://{self.host}:{self.port}/targets"
        new_target_payload = {
            "name": "Dynamic DNS",
            "type": "tcp",
            "host": "8.8.8.8",
            "port": 53
        }
        body = json.dumps(new_target_payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 201)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("registrado exitosamente", data["message"])

        # Verificar que ahora hay 2 targets en el store
        self.assertEqual(len(self.store.get_all_targets()), 2)


if __name__ == "__main__":
    unittest.main()
