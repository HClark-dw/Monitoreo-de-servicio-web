"""
Modelos de datos fuertemente tipados para el sistema de monitoreo.
Diseñados con dataclasses para inmutabilidad, serialización JSON limpia y portabilidad sin dependencias.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Dict, Any
import datetime
import uuid


class TargetType(str, Enum):
    HTTP = "http"
    TCP = "tcp"


class TargetState(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


@dataclass
class TargetConfig:
    name: str
    type: TargetType
    id: str = field(default="")
    url: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    method: str = "GET"
    interval_seconds: float = 10.0
    timeout_seconds: float = 3.0
    expected_status: Optional[int] = 200
    verify_ssl: bool = True

    def __post_init__(self):
        # Normalizar tipo
        if isinstance(self.type, str):
            self.type = TargetType(self.type.lower())
        
        # Generar ID determinista o único si no se provee
        if not self.id:
            safe_name = "".join(c if c.isalnum() else "_" for c in self.name.lower()).strip("_")
            self.id = safe_name or str(uuid.uuid4())[:8]

        # Validaciones de integridad según tipo
        if self.type == TargetType.HTTP:
            if not self.url:
                raise ValueError(f"Target '{self.name}' de tipo HTTP requiere el campo 'url'.")
            if not (self.url.startswith("http://") or self.url.startswith("https://")):
                raise ValueError(f"La URL '{self.url}' en '{self.name}' debe comenzar con http:// o https://")
        elif self.type == TargetType.TCP:
            if not self.host or self.port is None:
                raise ValueError(f"Target '{self.name}' de tipo TCP requiere 'host' y 'port'.")
            if not (1 <= self.port <= 65535):
                raise ValueError(f"El puerto {self.port} en '{self.name}' está fuera del rango válido (1-65535).")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "url": self.url,
            "host": self.host,
            "port": self.port,
            "method": self.method,
            "interval_seconds": self.interval_seconds,
            "timeout_seconds": self.timeout_seconds,
            "expected_status": self.expected_status,
            "verify_ssl": self.verify_ssl
        }


@dataclass
class CheckResult:
    target_id: str
    target_name: str
    target_type: str
    timestamp: float
    iso_timestamp: str
    state: TargetState
    is_up: bool
    response_time_ms: float
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_name": self.target_name,
            "target_type": self.target_type,
            "timestamp": self.timestamp,
            "iso_timestamp": self.iso_timestamp,
            "state": self.state.value,
            "is_up": self.is_up,
            "response_time_ms": round(self.response_time_ms, 2),
            "status_code": self.status_code,
            "error_message": self.error_message,
            "details": self.details
        }


@dataclass
class TargetMetrics:
    target_id: str
    target_name: str
    target_type: str
    target_endpoint: str
    current_state: TargetState = TargetState.UNKNOWN
    total_checks: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    uptime_percentage: float = 100.0
    last_response_time_ms: float = 0.0
    min_response_time_ms: float = 0.0
    max_response_time_ms: float = 0.0
    avg_response_time_ms: float = 0.0
    last_check_iso: Optional[str] = None
    last_error: Optional[str] = None
    consecutive_failures: int = 0
    history: list = field(default_factory=list)  # Últimos 10 resultados

    def update(self, result: CheckResult, history_limit: int = 10) -> None:
        self.total_checks += 1
        self.last_check_iso = result.iso_timestamp
        self.current_state = result.state
        self.last_response_time_ms = result.response_time_ms

        if result.is_up:
            self.successful_checks += 1
            self.consecutive_failures = 0
            self.last_error = None
        else:
            self.failed_checks += 1
            self.consecutive_failures += 1
            self.last_error = result.error_message

        # Cálculo de porcentaje de disponibilidad (Uptime SLA)
        self.uptime_percentage = round((self.successful_checks / self.total_checks) * 100.0, 2)

        # Cálculo de latencias para checks exitosos
        if result.is_up and result.response_time_ms > 0:
            if self.min_response_time_ms == 0.0 or result.response_time_ms < self.min_response_time_ms:
                self.min_response_time_ms = round(result.response_time_ms, 2)
            if result.response_time_ms > self.max_response_time_ms:
                self.max_response_time_ms = round(result.response_time_ms, 2)
            
            # Media móvil acumulada de latencia
            prev_avg = self.avg_response_time_ms
            n = self.successful_checks
            self.avg_response_time_ms = round(((prev_avg * (n - 1)) + result.response_time_ms) / n, 2)

        # Registro en historial circular
        self.history.append({
            "iso_timestamp": result.iso_timestamp,
            "state": result.state.value,
            "response_time_ms": round(result.response_time_ms, 2),
            "status_code": result.status_code,
            "error_message": result.error_message
        })
        if len(self.history) > history_limit:
            self.history.pop(0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_name": self.target_name,
            "target_type": self.target_type,
            "target_endpoint": self.target_endpoint,
            "current_state": self.current_state.value,
            "total_checks": self.total_checks,
            "successful_checks": self.successful_checks,
            "failed_checks": self.failed_checks,
            "uptime_percentage": self.uptime_percentage,
            "last_response_time_ms": round(self.last_response_time_ms, 2),
            "min_response_time_ms": round(self.min_response_time_ms, 2),
            "max_response_time_ms": round(self.max_response_time_ms, 2),
            "avg_response_time_ms": round(self.avg_response_time_ms, 2),
            "last_check_iso": self.last_check_iso,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
            "recent_history": self.history[-5:]
        }
