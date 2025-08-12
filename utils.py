"""Utility functions."""

import os


def read_models_from_file(path):
    """Read one model id per non-empty, non-comment line.
    A line can be 'model_id' or 'model_id, Display Name'.

    Returns a list of dicts: {"id": model_id, "name": display_name}.
    'name' is the display name if provided, otherwise it's None.
    If the file doesn't exist, returns [].
    """
    if not os.path.exists(path):
        return []
    models = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "," in line:
                    parts = line.split(",", 1)
                    model_id = parts[0].strip()
                    display_name = parts[1].strip()
                    models.append({"id": model_id, "name": display_name})
                else:
                    models.append({"id": line, "name": None})
    return models
