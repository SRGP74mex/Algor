"""
Configuración centralizada del sistema de logging para Algor.
"""
import logging
import sys
from typing import Optional


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configura el registrador raíz y los formateadores para la aplicación."""
    level = logging.DEBUG if verbose else logging.INFO
    log_format = "[%(asctime)s] [%(levelname)-7s] [%(name)s]: %(message)s"
    date_format = "%H:%M:%S"

    # Evitar duplicar manejadores si ya se llamó antes
    root_logger = logging.getLogger("algor")
    root_logger.setLevel(level)

    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(log_format, datefmt=date_format)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    return root_logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Devuelve un registrador hijo con el prefijo algor.<name>."""
    if name:
        return logging.getLogger(f"algor.{name}")
    return logging.getLogger("algor")

