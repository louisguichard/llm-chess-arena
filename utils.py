"""Utility functions."""

import os


def read_models_from_file(path):
    """Read one model id per non-empty, non-comment line.

    Returns a list of strings. If the file doesn't exist, returns [].
    """
    if not os.path.exists(path):
        return []
    models = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                models.append(line)
    return models
