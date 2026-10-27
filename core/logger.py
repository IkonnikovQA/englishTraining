"""Logger setup for English Trainer."""

import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime


def setup_logger(
    name: str = "EnglishTrainer",
    log_dir: str = None,
    log_file: str = "english_trainer.log",
    console: bool = True,
) -> logging.Logger:
    """Configure and return application logger with file + console handlers."""
    if log_dir is None:
        log_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_file)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid adding duplicate handlers
    if logger.handlers:
        return logger

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler (5 MB max, 5 backups)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
