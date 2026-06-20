"""
logger.py
Configures application-wide logging for ClaudeBrakeLEDs.
Call setup_logging() once at startup in brake_leds.py.
"""

import logging
import logging.handlers
import pathlib


def setup_logging() -> logging.Logger:
    """
    Configure logging to write to a rotating log file and console.
    Log file: ~/ClaudeBrakeLEDs/brakeleds.log
    Rotates at 1MB, keeps 3 backups.
    Returns the root logger for use in brake_leds.py.
    """
    log_path = pathlib.Path(__file__).parent / "brakeleds.log"

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Rotating file handler — production logging on Pi
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,   # 1MB per file
        backupCount=3          # keep 3 backups = 4MB max total
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler — useful during development on Windows
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logging.getLogger(__name__)
