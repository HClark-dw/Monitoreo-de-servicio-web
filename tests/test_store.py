"""
Pruebas unitarias para el almacén de métricas y cálculo de SLAs de disponibilidad.
"""

import unittest
from monitor.models import TargetConfig, TargetType, TargetState, CheckResult
from monitor.store import MetricsStore


class TestStore(unittest.TestCase):

    def setUp(self):
        self.store = MetricsStore()
        self.target = TargetConfig(
            id="srv-web",
            name="Servidor Web Principal",
            type=TargetType.HTTP,
            url="https://ejemplo.com"
        )
        self.store.register_target(self.target)

    def test_record_successful_checks(self):
        result = CheckResult(
            target_id="srv-web",
            target_name="Servidor Web Principal",
            target_type="http",
            timestamp=1000.0,
            iso_timestamp="2026-10-25T12:00:00Z",
            state=TargetState.UP,
            is_up=True,
            response_time_ms=50.0,
            status_code=200
        )
        self.store.record_check_result(result)

        metrics = self.store.get_target_metrics("srv-web")
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics["total_checks"], 1)
        self.assertEqual(metrics["successful_checks"], 1)
        self.assertEqual(metrics["failed_checks"], 0)
        self.assertEqual(metrics["uptime_percentage"], 100.0)
        self.assertEqual(metrics["avg_response_time_ms"], 50.0)
        self.assertEqual(metrics["current_state"], "UP")

    def test_record_failed_checks_and_sla(self):
        # 1er chequeo exitoso (100ms)
        r1 = CheckResult(
            target_id="srv-web",
            target_name="Servidor Web Principal",
            target_type="http",
            timestamp=1000.0,
            iso_timestamp="2026-10-25T12:00:00Z",
            state=TargetState.UP,
            is_up=True,
            response_time_ms=100.0,
            status_code=200
        )
        self.store.record_check_result(r1)

        # 2do chequeo fallido
        r2 = CheckResult(
            target_id="srv-web",
            target_name="Servidor Web Principal",
            target_type="http",
            timestamp=1010.0,
            iso_timestamp="2026-10-25T12:00:10Z",
            state=TargetState.DOWN,
            is_up=False,
            response_time_ms=0.0,
            error_message="Conexión rechazada"
        )
        self.store.record_check_result(r2)

        metrics = self.store.get_target_metrics("srv-web")
        self.assertEqual(metrics["total_checks"], 2)
        self.assertEqual(metrics["successful_checks"], 1)
        self.assertEqual(metrics["failed_checks"], 1)
        self.assertEqual(metrics["uptime_percentage"], 50.0)
        self.assertEqual(metrics["consecutive_failures"], 1)
        self.assertEqual(metrics["current_state"], "DOWN")

    def test_system_snapshot(self):
        snapshot = self.store.get_metrics_snapshot()
        self.assertIn("system", snapshot)
        self.assertIn("services", snapshot)
        self.assertEqual(snapshot["system"]["total_monitored_services"], 1)


if __name__ == "__main__":
    unittest.main()
