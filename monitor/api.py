"""
Módulo de Servidor de API REST y Panel Web (API & Web Dashboard).
Implementado con ThreadingHTTPServer de la biblioteca estándar de Python (cero dependencias externas).
Endpoints:
- GET /         : Panel de control web visual (HTML5 + CSS moderno + JavaScript en tiempo real).
- GET /status   : Estado actual de todos los servicios ("UP" / "DOWN"), latencias y SLAs.
- GET /health   : Health check del propio monitor.
- GET /metrics  : Métricas agregadas del sistema.
- GET /targets  : Lista de URLs/hosts configurados.
- POST /targets : Registro dinámico en caliente de nuevos objetivos a monitorear.
"""

from __future__ import annotations
import http.server
import json
import logging
import threading
from urllib.parse import urlparse
from typing import Optional

from monitor.models import TargetConfig, TargetType
from monitor.store import MetricsStore


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panel de Monitoreo de Estado de Servidores</title>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --border-color: #334155;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --up-color: #10b981;
            --down-color: #ef4444;
            --degraded-color: #f59e0b;
            --accent: #3b82f6;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
        body { background-color: var(--bg-color); color: var(--text-primary); padding: 2rem 1rem; }
        .container { max-width: 1100px; margin: 0 auto; }
        header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; border-bottom: 1px solid var(--border-color); padding-bottom: 1.5rem; }
        h1 { font-size: 1.75rem; font-weight: 700; color: #fff; }
        .subtitle { color: var(--text-secondary); font-size: 0.9rem; margin-top: 0.3rem; }
        .badge-live { display: inline-flex; align-items: center; gap: 6px; background: rgba(16, 185, 129, 0.15); color: #34d399; padding: 4px 12px; border-radius: 9999px; font-size: 0.8rem; font-weight: 600; }
        .pulse-dot { width: 8px; height: 8px; border-radius: 50%; background: #10b981; animation: pulse 1.5s infinite; }
        @keyframes pulse { 0% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(1.3); } 100% { opacity: 1; transform: scale(1); } }
        
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
        .stat-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 1.25rem; }
        .stat-label { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); }
        .stat-value { font-size: 1.8rem; font-weight: 700; margin-top: 0.4rem; }
        
        .services-table-wrapper { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; overflow: hidden; }
        table { width: 100%; border-collapse: collapse; text-align: left; }
        th { background: #131d2e; padding: 12px 16px; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); border-bottom: 1px solid var(--border-color); }
        td { padding: 14px 16px; border-bottom: 1px solid var(--border-color); font-size: 0.9rem; }
        tr:last-child td { border-bottom: none; }
        tr:hover { background: rgba(255, 255, 255, 0.02); }
        
        .status-pill { display: inline-block; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.75rem; text-align: center; }
        .status-up { background: rgba(16, 185, 129, 0.2); color: var(--up-color); }
        .status-down { background: rgba(239, 68, 68, 0.2); color: var(--down-color); }
        .status-degraded { background: rgba(245, 158, 11, 0.2); color: var(--degraded-color); }
        .status-unknown { background: rgba(148, 163, 184, 0.2); color: var(--text-secondary); }
        
        .endpoint-col { font-family: monospace; font-size: 0.82rem; color: #cbd5e1; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .latency-badge { font-weight: 600; color: #60a5fa; }
        .sla-col { font-weight: 600; }
        .refresh-info { margin-top: 1rem; text-align: right; font-size: 0.75rem; color: var(--text-secondary); }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>Monitor de Estado de Servidores</h1>
                <div class="subtitle">API de Sondeo Concurrente, Disponibilidad y Resiliencia de Red</div>
            </div>
            <div class="badge-live">
                <span class="pulse-dot"></span>
                <span>En Vivo (Auto-refresh 5s)</span>
            </div>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Servicios Monitoreados</div>
                <div class="stat-value" id="stat-total">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Operacionales (UP)</div>
                <div class="stat-value" id="stat-up" style="color: var(--up-color);">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Caídos (DOWN)</div>
                <div class="stat-value" id="stat-down" style="color: var(--down-color);">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Disponibilidad Global</div>
                <div class="stat-value" id="stat-sla" style="color: #60a5fa;">-%</div>
            </div>
        </div>

        <div class="services-table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>Estado</th>
                        <th>Servicio</th>
                        <th>Tipo</th>
                        <th>Endpoint / Host</th>
                        <th>Latencia</th>
                        <th>SLA Uptime</th>
                        <th>Último Error</th>
                    </tr>
                </thead>
                <tbody id="services-tbody">
                    <tr><td colspan="7" style="text-align: center; color: var(--text-secondary);">Cargando telemetría...</td></tr>
                </tbody>
            </table>
        </div>

        <div class="refresh-info" id="refresh-time">Actualizado: Cargando...</div>
    </div>

    <script>
        async function fetchStatus() {
            try {
                const res = await fetch('/status');
                if (!res.ok) throw new Error('Error al consultar estado');
                const data = await res.json();
                
                // Actualizar contadores
                const sys = data.system;
                document.getElementById('stat-total').textContent = sys.total_monitored_services;
                document.getElementById('stat-up').textContent = sys.services_up;
                document.getElementById('stat-down').textContent = sys.services_down;
                document.getElementById('stat-sla').textContent = sys.global_uptime_percentage + '%';

                // Renderizar tabla
                const tbody = document.getElementById('services-tbody');
                if (!data.services || data.services.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;">No hay servicios configurados</td></tr>';
                    return;
                }

                tbody.innerHTML = data.services.map(s => {
                    const stateClass = s.current_state === 'UP' ? 'status-up' : (s.current_state === 'DOWN' ? 'status-down' : 'status-degraded');
                    const error = s.last_error ? `<span style="color:#f87171;">${s.last_error}</span>` : '<span style="color:#475569;">Ninguno</span>';
                    const latency = s.last_response_time_ms > 0 ? `${s.last_response_time_ms.toFixed(1)} ms` : '-';
                    return `
                        <tr>
                            <td><span class="status-pill ${stateClass}">${s.current_state}</span></td>
                            <td style="font-weight: 600;">${s.target_name}</td>
                            <td><span style="font-size: 0.75rem; text-transform: uppercase; background:#334155; padding: 2px 6px; border-radius: 4px;">${s.target_type}</span></td>
                            <td class="endpoint-col" title="${s.target_endpoint}">${s.target_endpoint}</td>
                            <td class="latency-badge">${latency}</td>
                            <td class="sla-col">${s.uptime_percentage}%</td>
                            <td style="font-size: 0.75rem; max-width: 250px; overflow:hidden; text-overflow:ellipsis;">${error}</td>
                        </tr>
                    `;
                }).join('');

                document.getElementById('refresh-time').textContent = 'Última actualización: ' + new Date().toLocaleTimeString();
            } catch (err) {
                console.error(err);
            }
        }

        fetchStatus();
        setInterval(fetchStatus, 5000);
    </script>
</body>
</html>
"""


class MonitorApiHandler(http.server.BaseHTTPRequestHandler):
    """Manejador HTTP para los endpoints REST y la UI del panel de control."""

    store: MetricsStore  # Inyectado por el servidor
    logger: logging.Logger

    def log_message(self, format: str, *args):
        # Desactivar el logging ruidoso por defecto en consola de BaseHTTPRequestHandler
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/dashboard"):
            self._send_html(DASHBOARD_HTML)
        elif path == "/status":
            data = self.store.get_metrics_snapshot()
            self._send_json(200, data)
        elif path == "/health":
            data = {
                "status": "healthy",
                "monitor_service": "active",
                "version": "1.0.0"
            }
            self._send_json(200, data)
        elif path == "/metrics":
            snapshot = self.store.get_metrics_snapshot()
            self._send_json(200, snapshot["system"])
        elif path == "/targets":
            targets = [t.to_dict() for t in self.store.get_all_targets()]
            self._send_json(200, {"targets": targets, "count": len(targets)})
        else:
            self._send_json(404, {"error": "Ruta no encontrada", "path": path})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/targets":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                payload = json.loads(body)

                target = TargetConfig(
                    name=payload["name"],
                    type=TargetType(payload.get("type", "http").lower()),
                    url=payload.get("url"),
                    host=payload.get("host"),
                    port=int(payload["port"]) if payload.get("port") is not None else None,
                    method=payload.get("method", "GET"),
                    interval_seconds=float(payload.get("interval_seconds", 10.0)),
                    timeout_seconds=float(payload.get("timeout_seconds", 3.0)),
                    expected_status=int(payload.get("expected_status", 200))
                )
                self.store.register_target(target)
                self._send_json(201, {
                    "message": f"Target '{target.name}' registrado exitosamente.",
                    "target": target.to_dict()
                })
            except Exception as e:
                self._send_json(400, {
                    "error": "Error al procesar el target enviado.",
                    "details": str(e)
                })
        else:
            self._send_json(404, {"error": "Endpoint de modificación no encontrado."})

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_content: str):
        body = html_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class MonitorApiServer:
    """Servidor web multihilo para exponer la API REST y el Dashboard."""

    def __init__(self, host: str, port: int, store: MetricsStore, logger: logging.Logger):
        self.host = host
        self.port = port
        self.store = store
        self.logger = logger
        self._server: Optional[http.server.ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self, daemon: bool = True) -> None:
        handler_class = MonitorApiHandler
        handler_class.store = self.store
        handler_class.logger = self.logger

        self._server = http.server.ThreadingHTTPServer((self.host, self.port), handler_class)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="ApiServerThread",
            daemon=daemon
        )
        self._thread.start()
        self.logger.info(f"API REST y Dashboard web disponibles en: http://{self.host}:{self.port}/")

    def stop(self) -> None:
        if self._server:
            self.logger.info("Deteniendo servidor de API HTTP...")
            self._server.shutdown()
            self._server.server_close()
            if self._thread:
                self._thread.join(timeout=3.0)
            self.logger.info("Servidor de API HTTP cerrado.")
