"""
Pruebas unitarias para el módulo de configuración y validación de datos.
"""

import os
import json
import tempfile
import unittest

from monitor.config import load_config, MonitorSettings
from monitor.models import TargetConfig, TargetType


class TestConfig(unittest.TestCase):

    def test_target_validation_http(self):
        # Target HTTP válido
        t = TargetConfig(name="Google", type=TargetType.HTTP, url="https://google.com")
        self.assertEqual(t.type, TargetType.HTTP)
        self.assertEqual(t.name, "Google")
        self.assertTrue(t.id != "")

        # Target HTTP sin URL debe fallar
        with self.assertRaises(ValueError):
            TargetConfig(name="SinURL", type=TargetType.HTTP, url="")

        # Target HTTP con esquema no permitido
        with self.assertRaises(ValueError):
            TargetConfig(name="EsquemaInvalido", type=TargetType.HTTP, url="ftp://google.com")

    def test_target_validation_tcp(self):
        # Target TCP válido
        t = TargetConfig(name="DNS", type=TargetType.TCP, host="8.8.8.8", port=53)
        self.assertEqual(t.type, TargetType.TCP)
        self.assertEqual(t.port, 53)

        # Target TCP sin puerto
        with self.assertRaises(ValueError):
            TargetConfig(name="SinPuerto", type=TargetType.TCP, host="8.8.8.8", port=None)

        # Target TCP con puerto fuera de rango
        with self.assertRaises(ValueError):
            TargetConfig(name="PuertoAlto", type=TargetType.TCP, host="8.8.8.8", port=99999)

    def test_load_config_file(self):
        sample_config = {
            "settings": {
                "default_check_interval_seconds": 5,
                "api_port": 9090
            },
            "targets": [
                {
                    "name": "Test Web",
                    "type": "http",
                    "url": "https://example.com"
                }
            ]
        }

        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json", encoding="utf-8") as tmp:
            json.dump(sample_config, tmp)
            tmp_path = tmp.name

        try:
            settings, targets = load_config(tmp_path)
            self.assertEqual(settings.api_port, 9090)
            self.assertEqual(settings.default_check_interval_seconds, 5.0)
            self.assertEqual(len(targets), 1)
            self.assertEqual(targets[0].name, "Test Web")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
