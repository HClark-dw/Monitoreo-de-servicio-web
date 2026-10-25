"""
Módulo de Configuración.
Carga y valida el archivo de configuración JSON con valores por defecto seguros.
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass
from typing import List, Tuple
from monitor.models import TargetConfig, TargetType


@dataclass
class MonitorSettings:
    default_check_interval_seconds: float = 10.0
    default_timeout_seconds: float = 3.0
    max_concurrent_workers: int = 5
    api_host: str = "127.0.0.1"
    api_port: int = 8080
    enable_api: bool = True
    enable_console_dashboard: bool = True
    log_level: str = "INFO"
    log_file: str = "logs/monitor.log"
    json_log_file: str = "logs/monitor.jsonl"


def load_config(file_path: str = "config.json") -> Tuple[MonitorSettings, List[TargetConfig]]:
    """
    Carga el archivo de configuración. Si no existe, genera una configuración por defecto.
    Retorna una tupla (MonitorSettings, List[TargetConfig]).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No se encontró el archivo de configuración en '{file_path}'.")

    with open(file_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # Cargar Settings
    raw_settings = raw_data.get("settings", {})
    settings = MonitorSettings(
        default_check_interval_seconds=float(raw_settings.get("default_check_interval_seconds", 10.0)),
        default_timeout_seconds=float(raw_settings.get("default_timeout_seconds", 3.0)),
        max_concurrent_workers=int(raw_settings.get("max_concurrent_workers", 5)),
        api_host=str(raw_settings.get("api_host", "127.0.0.1")),
        api_port=int(raw_settings.get("api_port", 8080)),
        enable_api=bool(raw_settings.get("enable_api", True)),
        enable_console_dashboard=bool(raw_settings.get("enable_console_dashboard", True)),
        log_level=str(raw_settings.get("log_level", "INFO")),
        log_file=str(raw_settings.get("log_file", "logs/monitor.log")),
        json_log_file=str(raw_settings.get("json_log_file", "logs/monitor.jsonl"))
    )

    # Cargar Targets
    raw_targets = raw_data.get("targets", [])
    targets: List[TargetConfig] = []
    
    for idx, t in enumerate(raw_targets):
        target_name = t.get("name", f"Target_{idx + 1}")
        target_type_str = t.get("type", "http").lower()
        
        target = TargetConfig(
            name=target_name,
            type=TargetType(target_type_str),
            id=t.get("id", ""),
            url=t.get("url"),
            host=t.get("host"),
            port=int(t["port"]) if t.get("port") is not None else None,
            method=t.get("method", "GET"),
            interval_seconds=float(t.get("interval_seconds", settings.default_check_interval_seconds)),
            timeout_seconds=float(t.get("timeout_seconds", settings.default_timeout_seconds)),
            expected_status=int(t["expected_status"]) if t.get("expected_status") is not None else 200,
            verify_ssl=bool(t.get("verify_ssl", True))
        )
        targets.append(target)

    return settings, targets
