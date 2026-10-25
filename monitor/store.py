"""
Módulo de Almacén de Estado y Métricas (State & Metrics Store).
Almacena en memoria el estado actual, métricas acumuladas y SLAs de disponibilidad.
Thread-safe mediante reentrant locks (RLock) para soportar accesos concurrentes de workers y API HTTP.
"""

from __future__ import annotations
import threading
import time
from typing import Dict, List, Optional, Any
from monitor.models import TargetConfig, TargetMetrics, CheckResult, TargetState


class MetricsStore:
    """Almacén central y seguro en entornos multi-hilo para estados y métricas."""

    def __init__(self):
        self._lock = threading.RLock()
        self._targets: Dict[str, TargetConfig] = {}
        self._metrics: Dict[str, TargetMetrics] = {}
        self._start_time: float = time.time()

    def register_target(self, target: TargetConfig) -> None:
        """Registra o actualiza la configuración de un target en el almacén."""
        with self._lock:
            self._targets[target.id] = target
            if target.id not in self._metrics:
                endpoint = target.url if target.url else f"{target.host}:{target.port}"
                self._metrics[target.id] = TargetMetrics(
                    target_id=target.id,
                    target_name=target.name,
                    target_type=target.type.value,
                    target_endpoint=endpoint
                )

    def get_all_targets(self) -> List[TargetConfig]:
        with self._lock:
            return list(self._targets.values())

    def get_target(self, target_id: str) -> Optional[TargetConfig]:
        with self._lock:
            return self._targets.get(target_id)

    def record_check_result(self, result: CheckResult) -> None:
        """Actualiza las métricas del target de forma atómica y segura."""
        with self._lock:
            metrics = self._metrics.get(result.target_id)
            if metrics:
                metrics.update(result)

    def get_metrics_snapshot(self) -> Dict[str, Any]:
        """Obtiene una instantánea completa del estado del sistema y servicios monitoreados."""
        with self._lock:
            uptime_seconds = round(time.time() - self._start_time, 1)
            targets_data = [m.to_dict() for m in self._metrics.values()]
            
            total_targets = len(targets_data)
            up_count = sum(1 for t in targets_data if t["current_state"] == TargetState.UP.value)
            down_count = sum(1 for t in targets_data if t["current_state"] == TargetState.DOWN.value)
            degraded_count = sum(1 for t in targets_data if t["current_state"] == TargetState.DEGRADED.value)

            overall_availability = 0.0
            if targets_data:
                valid_uptimes = [t["uptime_percentage"] for t in targets_data if t["total_checks"] > 0]
                if valid_uptimes:
                    overall_availability = round(sum(valid_uptimes) / len(valid_uptimes), 2)

            return {
                "system": {
                    "monitor_uptime_seconds": uptime_seconds,
                    "total_monitored_services": total_targets,
                    "services_up": up_count,
                    "services_down": down_count,
                    "services_degraded": degraded_count,
                    "global_uptime_percentage": overall_availability,
                    "healthy": down_count == 0
                },
                "services": targets_data
            }

    def get_target_metrics(self, target_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            metrics = self._metrics.get(target_id)
            return metrics.to_dict() if metrics else None
