"""Centralized logging configuration."""

import logging
import google.cloud.logging


def setup_logger():
    """Set up the logger."""
    logger = logging.getLogger("llm-chess-arena")
    try:
        client = google.cloud.logging.Client()
        client.setup_logging(log_level=logging.DEBUG)
    except Exception:
        print(
            "Could not set up Google Cloud Logging. Falling back to standard logging."
        )
        logging.basicConfig(level=logging.DEBUG)

    logger.setLevel(logging.DEBUG)
    return logger


# Initialize the logger
log = setup_logger()
