"""
Módulo de Registro Estructurado (Structured Logging).
Provee registro dual:
1. Log tradicional rotativo de texto para depuración humana (RotatingFileHandler).
2. Log estructurado en formato JSON Lines (.jsonl) ideal para agregadores (Datadog, Elastic, Loki).
"""

import json
import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional
from monitor.models import CheckResult


class JsonFormatter(logging.Formatter):
    """Formatea cada registro de log como un objeto JSON individual."""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        if hasattr(record, "check_data") and isinstance(record.check_data, dict):
            data["check"] = record.check_data
        return json.dumps(data, ensure_ascii=False)


def setup_logger(
    name: str = "ServerMonitor",
    log_file: str = "logs/monitor.log",
    json_log_file: Optional[str] = "logs/monitor.jsonl",
    level: str = "INFO",
    max_bytes: int = 5 * 1024 * 1024,  # 5 MB
    backup_count: int = 3
) -> logging.Logger:
    """Configura e inicializa los handlers de logging de manera idempotente."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Evitar duplicación de handlers si se llama varias veces
    if logger.handlers:
        return logger

    # Asegurar que el directorio de logs exista
    os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
    if json_log_file:
        os.makedirs(os.path.dirname(json_log_file) or ".", exist_ok=True)

    # 1. Handler para archivo de texto rotativo
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    file_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # 2. Handler opcional para JSON Lines
    if json_log_file:
        json_handler = RotatingFileHandler(
            json_log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        json_handler.setFormatter(JsonFormatter())
        logger.addHandler(json_handler)

    # 3. Handler para Consola (formato compacto con colores visuales)
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger


def log_check_result(logger: logging.Logger, result: CheckResult) -> None:
    """Registra el resultado de una prueba con nivel y metadatos acordes a su estado."""
    summary = (
        f"[{result.state.value}] {result.target_name} ({result.target_type.upper()}) - "
        f"Latencia: {result.response_time_ms:.1f}ms"
    )
    if result.status_code is not None:
        summary += f" | Código: {result.status_code}"
    if result.error_message:
        summary += f" | Error: {result.error_message}"

    extra = {"check_data": result.to_dict()}

    if result.is_up:
        logger.info(summary, extra=extra)
    elif result.state.value == "DEGRADED":
        logger.warning(summary, extra=extra)
    else:
        logger.error(summary, extra=extra)
