"""Centralized logging configuration."""

import logging
import google.cloud.logging


def setup_logger():
    """Set up the logger."""
    client = google.cloud.logging.Client()
    client.setup_logging(log_level=logging.DEBUG)

    logger = logging.getLogger("llm-chess-arena")
    logger.setLevel(logging.DEBUG)

    return logger


# Initialize the logger
log = setup_logger()
