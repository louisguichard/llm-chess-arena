"""Centralized logging configuration."""

import os
import logging
import google.cloud.logging
from dotenv import load_dotenv

load_dotenv()


def setup_logger():
    """Set up the logger."""
    logger = logging.getLogger("llm-chess-arena")
    if os.getenv("ENV") == "locala":
        logging.basicConfig(level=logging.DEBUG)
    else:
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
