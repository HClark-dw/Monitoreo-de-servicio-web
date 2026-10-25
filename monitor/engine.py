"""
Módulo de Motor Concurrente de Monitoreo (Monitoring Engine).
Gestiona el ciclo de sondeo periódico multi-hilo con ThreadPoolExecutor,
controlando intervalos independientes por servicio y apagado limpio (Graceful Shutdown).
"""

from __future__ import annotations
import concurrent.futures
import logging
import threading
import time
from typing import Dict, List, Optional

from monitor.config import MonitorSettings
from monitor.models import TargetConfig, CheckResult, TargetState
from monitor.probers import ProberFactory
from monitor.store import MetricsStore
from monitor.logger import log_check_result


class MonitoringEngine:
    """Motor que orquesta las sondas periódicas concurrentes sobre los servicios."""

    def __init__(
        self,
        settings: MonitorSettings,
        store: MetricsStore,
        logger: logging.Logger
    ):
        self.settings = settings
        self.store = store
        self.logger = logger
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._next_check: Dict[str, float] = {}  # target_id -> timestamp del próximo sondeo
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=settings.max_concurrent_workers,
            thread_name_prefix="ProberWorker"
        )

    def start(self, daemon: bool = True) -> None:
        """Inicia el ciclo de monitoreo en un hilo de fondo."""
        if self._thread and self._thread.is_alive():
            self.logger.warning("El motor de monitoreo ya se encuentra en ejecución.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="MonitoringLoop",
            daemon=daemon
        )
        self._thread.start()
        self.logger.info("Motor de monitoreo iniciado exitosamente.")

    def stop(self) -> None:
        """Detiene de manera limpia el motor y su piscina de hilos de trabajo."""
        self.logger.info("Solicitud de detención recibida. Finalizando tareas en curso...")
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        self._executor.shutdown(wait=True, cancel_futures=True)
        self.logger.info("Motor de monitoreo detenido de forma segura.")

    def run_single_sweep(self) -> List[CheckResult]:
        """Ejecuta una ronda de sondeo inmediata sobre todos los targets registrados."""
        targets = self.store.get_all_targets()
        if not targets:
            return []

        futures = {self._executor.submit(self._execute_probe, target): target for target in targets}
        results: List[CheckResult] = []

        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result()
                results.append(res)
            except Exception as e:
                self.logger.error(f"Error crítico en hilo de sondeo: {e}")

        return results

    def _execute_probe(self, target: TargetConfig) -> CheckResult:
        """Invoca la sonda especializada y registra métricas y logs."""
        try:
            prober = ProberFactory.get_prober(target.type)
            result = prober.probe(target)
        except Exception as exc:
            # Salvaguarda final para garantizar que ningún error desborde el hilo
            now = time.time()
            result = CheckResult(
                target_id=target.id,
                target_name=target.name,
                target_type=target.type.value,
                timestamp=now,
                iso_timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                state=TargetState.DOWN,
                is_up=False,
                response_time_ms=0.0,
                error_message=f"Fallo en prober: {str(exc)}"
            )

        # Actualizar almacén de métricas
        self.store.record_check_result(result)
        # Escribir a los logs configurados
        log_check_result(self.logger, result)

        return result

    def _run_loop(self) -> None:
        """Bucle principal de temporización y despacho de tareas concurrentes."""
        while not self._stop_event.is_set():
            now = time.time()
            targets_to_probe: List[TargetConfig] = []

            for target in self.store.get_all_targets():
                scheduled_time = self._next_check.get(target.id, 0.0)
                if now >= scheduled_time:
                    targets_to_probe.append(target)
                    self._next_check[target.id] = now + target.interval_seconds

            # Despachar sondas en paralelo
            if targets_to_probe:
                for target in targets_to_probe:
                    if self._stop_event.is_set():
                        break
                    self._executor.submit(self._execute_probe, target)

            # Pausa breve para evitar consumo excesivo de CPU (espera reactiva)
            self._stop_event.wait(timeout=1.0)
