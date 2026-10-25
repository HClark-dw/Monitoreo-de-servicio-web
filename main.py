"""
Punto de Entrada Principal (Main Entry Point)
Aplicación de Monitoreo de Estado de Servidores y Servicios Web.
Ejecuta la orquestación concurrente, logging rotativo y servidor de API/Dashboard.
"""

import argparse
import os
import signal
import sys
import time

from monitor.config import load_config
from monitor.logger import setup_logger
from monitor.store import MetricsStore
from monitor.engine import MonitoringEngine
from monitor.api import MonitorApiServer
from monitor.models import TargetState


if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def print_banner(host: str, port: int, target_count: int, api_enabled: bool) -> None:
    print("=" * 72)
    print(" [>] MONITOR DE ESTADO DE SERVIDORES Y SERVICIOS WEB - V1.0")
    print("     Demostracion de Red, Concurrencia y Resiliencia en Python")
    print("=" * 72)
    print(f"  * Servicios configurados : {target_count}")
    if api_enabled:
        print(f"  * Dashboard y API REST   : http://{host}:{port}/")
        print(f"  * Endpoint JSON Estado   : http://{host}:{port}/status")
        print(f"  * Endpoint JSON Metricas : http://{host}:{port}/metrics")
    print(f"  * Registro de Logs       : logs/monitor.log & logs/monitor.jsonl")
    print("=" * 72)
    print(" Presione [Ctrl + C] para detener el servicio de forma segura.\n")


def print_console_summary(store: MetricsStore) -> None:
    """Imprime en consola un reporte visual tabular con el estado actual."""
    snapshot = store.get_metrics_snapshot()
    sys_data = snapshot["system"]
    services = snapshot["services"]

    print("\n" + "=" * 72)
    print(f" [REPORTE DE ESTADO] ({time.strftime('%Y-%m-%d %H:%M:%S')})")
    print(f" Uptime Monitor: {sys_data['monitor_uptime_seconds']}s | "
          f"Servicios: {sys_data['total_monitored_services']} | "
          f"UP: {sys_data['services_up']} | "
          f"DOWN: {sys_data['services_down']} | "
          f"Disponibilidad: {sys_data['global_uptime_percentage']}%")
    print("-" * 72)
    print(f"{'ESTADO':<8} | {'TIPO':<5} | {'LATENCIA':<10} | {'SLA':<7} | {'SERVICIO'}")
    print("-" * 72)

    for s in services:
        st = s["current_state"]
        tag = f"[{st}]"
        lat = f"{s['last_response_time_ms']:.1f} ms" if s['last_response_time_ms'] > 0 else "-"
        sla = f"{s['uptime_percentage']}%"
        name = s["target_name"]
        print(f"{tag:<8} | {s['target_type'].upper():<5} | {lat:<10} | {sla:<7} | {name}")
    print("=" * 72 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Monitor periódico concurrente de servicios web y servidores."
    )
    parser.add_argument(
        "-c", "--config",
        default="config.json",
        help="Ruta al archivo de configuración JSON (por defecto: config.json)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Ejecuta una única ronda de sondeo, imprime el reporte y termina (Modo CLI/Cron)"
    )
    parser.add_argument(
        "--no-api",
        action="store_true",
        help="Deshabilita el servidor de API HTTP y Dashboard Web"
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        help="Sobrescribe el puerto de la API HTTP (ejemplo: 8080)"
    )

    args = parser.parse_args()

    # Cargar configuración
    try:
        settings, targets = load_config(args.config)
    except Exception as e:
        print(f"Error fatal al cargar la configuración: {e}", file=sys.stderr)
        sys.exit(1)

    if args.port:
        settings.api_port = args.port
    if args.no_api:
        settings.enable_api = False

    # Inicializar logger
    logger = setup_logger(
        name="ServerMonitor",
        log_file=settings.log_file,
        json_log_file=settings.json_log_file,
        level=settings.log_level
    )

    # Inicializar almacén y registrar targets
    store = MetricsStore()
    for target in targets:
        store.register_target(target)

    # Inicializar motor de monitoreo
    engine = MonitoringEngine(settings=settings, store=store, logger=logger)

    # Modo ejecución única (ideal para CI/CD y scripts de inspección rápida)
    if args.once:
        logger.info("Iniciando sondeo único de verificación...")
        engine.run_single_sweep()
        print_console_summary(store)
        engine.stop()
        sys.exit(0)

    # Iniciar servidor web si está habilitado
    api_server = None
    if settings.enable_api:
        api_server = MonitorApiServer(
            host=settings.api_host,
            port=settings.api_port,
            store=store,
            logger=logger
        )
        api_server.start(daemon=True)

    # Imprimir banner informativo
    print_banner(
        host=settings.api_host,
        port=settings.api_port,
        target_count=len(targets),
        api_enabled=settings.enable_api
    )

    # Iniciar motor de monitoreo en segundo plano
    engine.start(daemon=True)

    # Ejecutar una primera ronda inmediata para tener telemetría inicial
    engine.run_single_sweep()
    print_console_summary(store)

    # Manejo de señales para Graceful Shutdown
    running = True

    def handle_signal(sig, frame):
        nonlocal running
        print("\n[!] Señal de interrupción capturada. Apagando monitor...")
        running = False

    try:
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
    except Exception:
        pass

    # Bucle principal de reporte por consola
    last_report_time = time.time()
    try:
        while running:
            time.sleep(0.5)
            # Imprimir reporte periódico en consola cada 20 segundos
            if time.time() - last_report_time >= 20.0:
                print_console_summary(store)
                last_report_time = time.time()
    except KeyboardInterrupt:
        print("\n[!] Interrupción de teclado capturada.")
    finally:
        print("Finalizando componentes...")
        engine.stop()
        if api_server:
            api_server.stop()
        print("Monitor apagado correctamente.")


if __name__ == "__main__":
    main()
