"""Centralized logging configuration."""

import logging
import sys


def setup_logger():
    """Set up the logger."""
    logger = logging.getLogger("llm-chess-arena")
    logger.setLevel(logging.INFO)

    # Prevent duplicate logs if already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


# Initialize the logger
log = setup_logger()
