"""Centralized logging configuration."""

import os
import logging
import google.cloud.logging
from dotenv import load_dotenv

load_dotenv()


class ExcludeStaticFilter(logging.Filter):
    """Filter out noisy access logs for static assets and favicon."""

    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(getattr(record, "msg", ""))
        if not msg:
            return True
        return "/static/" not in msg and "favicon.ico" not in msg


def setup_logger():
    """Set up the logger."""
    logger = logging.getLogger("llm-chess-arena")
    if os.getenv("ENV") == "local":
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

    # Suppress common access logs for static files
    static_filter = ExcludeStaticFilter()
    for name in ("werkzeug", "gunicorn.access"):
        logging.getLogger(name).addFilter(static_filter)
    return logger


# Initialize the logger
log = setup_logger()
