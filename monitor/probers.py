"""
Módulo de Sondeadores de Red (Probers).
Implementa estrategias de prueba para HTTP/HTTPS y TCP Sockets (Ping de nivel de transporte),
con medición precisa de latencia y control granular de excepciones de red.
"""

from abc import ABC, abstractmethod
import datetime
import socket
import ssl
import time
import urllib.error
import urllib.request
from typing import Dict, Any

from monitor.models import TargetConfig, TargetType, TargetState, CheckResult


class BaseProber(ABC):
    """Clase base abstracta para cualquier estrategia de sondeo de red."""

    @abstractmethod
    def probe(self, target: TargetConfig) -> CheckResult:
        """Ejecuta la prueba de conectividad y retorna el resultado estructurado."""
        pass


class HttpProber(BaseProber):
    """
    Sondeador para servicios web HTTP y HTTPS.
    Maneja códigos de respuesta, tiempos de conexión, errores SSL y timeouts.
    """

    def __init__(self, user_agent: str = "ServerMonitor/1.0 (+https://github.com/monitor)"):
        self.user_agent = user_agent

    def probe(self, target: TargetConfig) -> CheckResult:
        now = time.time()
        iso_now = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).isoformat()
        
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "*/*",
            "Connection": "close"
        }

        req = urllib.request.Request(
            url=target.url,  # type: ignore
            headers=headers,
            method=target.method.upper()
        )

        start_time = time.perf_counter()
        
        try:
            if target.verify_ssl:
                ssl_context = ssl.create_default_context()
            else:
                ssl_context = ssl._create_unverified_context()
            
            with urllib.request.urlopen(req, timeout=target.timeout_seconds, context=ssl_context) as response:
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                status_code = response.status
                
                # Evaluación del estado según el código esperado
                expected = target.expected_status or 200
                if status_code == expected:
                    state = TargetState.UP
                    is_up = True
                    error_msg = None
                elif 200 <= status_code < 400:
                    state = TargetState.UP
                    is_up = True
                    error_msg = f"Respuesta HTTP {status_code} (esperado {expected})"
                else:
                    state = TargetState.DEGRADED
                    is_up = False
                    error_msg = f"Código HTTP inesperado: {status_code} (esperado {expected})"

                return CheckResult(
                    target_id=target.id,
                    target_name=target.name,
                    target_type="http",
                    timestamp=now,
                    iso_timestamp=iso_now,
                    state=state,
                    is_up=is_up,
                    response_time_ms=latency_ms,
                    status_code=status_code,
                    error_message=error_msg,
                    details={
                        "url": target.url,
                        "method": target.method,
                        "content_type": response.headers.get("Content-Type", "desconocido"),
                        "server": response.headers.get("Server", "desconocido")
                    }
                )

        except urllib.error.HTTPError as err:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            status_code = err.code
            
            # Si el target esperaba explícitamente este código (p. ej. pruebas de 404 o 401)
            if target.expected_status and status_code == target.expected_status:
                return CheckResult(
                    target_id=target.id,
                    target_name=target.name,
                    target_type="http",
                    timestamp=now,
                    iso_timestamp=iso_now,
                    state=TargetState.UP,
                    is_up=True,
                    response_time_ms=latency_ms,
                    status_code=status_code,
                    error_message=None,
                    details={"url": target.url, "expected_error_code": status_code}
                )
            
            state = TargetState.DOWN if status_code >= 500 else TargetState.DEGRADED
            return CheckResult(
                target_id=target.id,
                target_name=target.name,
                target_type="http",
                timestamp=now,
                iso_timestamp=iso_now,
                state=state,
                is_up=False,
                response_time_ms=latency_ms,
                status_code=status_code,
                error_message=f"HTTP Error {status_code}: {err.reason}",
                details={"url": target.url, "reason": str(err.reason)}
            )

        except urllib.error.URLError as err:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            reason = err.reason
            error_description = self._classify_url_error(reason)

            return CheckResult(
                target_id=target.id,
                target_name=target.name,
                target_type="http",
                timestamp=now,
                iso_timestamp=iso_now,
                state=TargetState.DOWN,
                is_up=False,
                response_time_ms=latency_ms,
                status_code=None,
                error_message=error_description,
                details={"url": target.url, "raw_reason": str(reason)}
            )

        except (TimeoutError, socket.timeout):
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return CheckResult(
                target_id=target.id,
                target_name=target.name,
                target_type="http",
                timestamp=now,
                iso_timestamp=iso_now,
                state=TargetState.DOWN,
                is_up=False,
                response_time_ms=latency_ms,
                status_code=None,
                error_message=f"Timeout de conexión excedido tras {target.timeout_seconds}s",
                details={"url": target.url, "timeout_seconds": target.timeout_seconds}
            )

        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return CheckResult(
                target_id=target.id,
                target_name=target.name,
                target_type="http",
                timestamp=now,
                iso_timestamp=iso_now,
                state=TargetState.DOWN,
                is_up=False,
                response_time_ms=latency_ms,
                status_code=None,
                error_message=f"Fallo inesperado: {type(exc).__name__} ({str(exc)})",
                details={"url": target.url, "exception_type": type(exc).__name__}
            )

    @staticmethod
    def _classify_url_error(reason: Any) -> str:
        """Clasificación técnica de fallos de nivel de socket/red."""
        if isinstance(reason, socket.gaierror):
            return "Fallo DNS: No se pudo resolver el nombre de host (GetAddressInfo failed)"
        if isinstance(reason, ConnectionRefusedError):
            return "Conexión rechazada: El servidor destino denegó la conexión o el servicio no corre"
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return "Timeout de red: El servidor tardó demasiado en responder"
        if isinstance(reason, ssl.SSLCertVerificationError):
            return "Fallo SSL/TLS: Certificado digital no confiable o expirado"
        if isinstance(reason, ssl.SSLError):
            return f"Fallo SSL/TLS: Error en el handshake seguro ({reason})"
        return f"Error de red: {str(reason)}"


class TcpProber(BaseProber):
    """
    Sondeador a nivel de capa de transporte TCP (Ping / Socket Probe).
    Permite verificar IPs públicas/privadas y puertos específicos (e.g., DNS:53, DB:5432, SSH:22, Web:80).
    Mide la latencia de negociación del handshake SYN/ACK sin requerir privilegios de superusuario ICMP.
    """

    def probe(self, target: TargetConfig) -> CheckResult:
        now = time.time()
        iso_now = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).isoformat()
        host = target.host or "127.0.0.1"
        port = target.port or 80

        start_time = time.perf_counter()
        sock = None
        try:
            sock = socket.create_connection((host, port), timeout=target.timeout_seconds)
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            return CheckResult(
                target_id=target.id,
                target_name=target.name,
                target_type="tcp",
                timestamp=now,
                iso_timestamp=iso_now,
                state=TargetState.UP,
                is_up=True,
                response_time_ms=latency_ms,
                status_code=0,
                error_message=None,
                details={"host": host, "port": port, "protocol": "TCP"}
            )

        except (socket.timeout, TimeoutError):
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return CheckResult(
                target_id=target.id,
                target_name=target.name,
                target_type="tcp",
                timestamp=now,
                iso_timestamp=iso_now,
                state=TargetState.DOWN,
                is_up=False,
                response_time_ms=latency_ms,
                status_code=None,
                error_message=f"Timeout TCP al conectar a {host}:{port} ({target.timeout_seconds}s)",
                details={"host": host, "port": port}
            )

        except ConnectionRefusedError:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return CheckResult(
                target_id=target.id,
                target_name=target.name,
                target_type="tcp",
                timestamp=now,
                iso_timestamp=iso_now,
                state=TargetState.DOWN,
                is_up=False,
                response_time_ms=latency_ms,
                status_code=None,
                error_message=f"Conexión rechazada en {host}:{port} (puerto cerrado o firewall)",
                details={"host": host, "port": port}
            )

        except socket.gaierror:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return CheckResult(
                target_id=target.id,
                target_name=target.name,
                target_type="tcp",
                timestamp=now,
                iso_timestamp=iso_now,
                state=TargetState.DOWN,
                is_up=False,
                response_time_ms=latency_ms,
                status_code=None,
                error_message=f"Error DNS: No se pudo resolver el host '{host}'",
                details={"host": host, "port": port}
            )

        except OSError as oe:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return CheckResult(
                target_id=target.id,
                target_name=target.name,
                target_type="tcp",
                timestamp=now,
                iso_timestamp=iso_now,
                state=TargetState.DOWN,
                is_up=False,
                response_time_ms=latency_ms,
                status_code=None,
                error_message=f"Error de socket ({oe.errno}): {oe.strerror}",
                details={"host": host, "port": port, "errno": oe.errno}
            )

        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return CheckResult(
                target_id=target.id,
                target_name=target.name,
                target_type="tcp",
                timestamp=now,
                iso_timestamp=iso_now,
                state=TargetState.DOWN,
                is_up=False,
                response_time_ms=latency_ms,
                status_code=None,
                error_message=f"Fallo inesperado TCP: {type(exc).__name__} ({str(exc)})",
                details={"host": host, "port": port}
            )

        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass


class ProberFactory:
    """Fábrica para instanciar el sondeador correspondiente."""

    _probers: Dict[TargetType, BaseProber] = {
        TargetType.HTTP: HttpProber(),
        TargetType.TCP: TcpProber()
    }

    @classmethod
    def get_prober(cls, target_type: TargetType) -> BaseProber:
        prober = cls._probers.get(target_type)
        if not prober:
            raise ValueError(f"No existe un prober registrado para el tipo '{target_type}'.")
        return prober
