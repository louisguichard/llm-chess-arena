"""Utility functions."""

import os


def read_models_from_file(path):
    """Read one model id per non-empty, non-comment line.
    A line can be:
    - 'model_id'
    - 'model_id, Display Name'
    - 'model_id, Display Name, [tag1,tag2,...]'

    Returns a list of dicts: {"id": model_id, "name": display_name, "tags": [list_of_tags]}.
    'name' is the display name if provided, otherwise it's None.
    'tags' is a list of tag strings if provided, otherwise it's an empty list.
    If the file doesn't exist, returns [].
    """
    if not os.path.exists(path):
        return []
    models = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                model_id = None
                display_name = None
                tags = []

                # Look for tags first (they are enclosed in brackets)
                if "[" in line and "]" in line:
                    # Find the tag section
                    tag_start = line.rfind("[")
                    tag_end = line.rfind("]")
                    if tag_start < tag_end:
                        tag_part = line[tag_start : tag_end + 1]
                        tag_content = tag_part[1:-1]  # Remove brackets
                        if tag_content:
                            tags = [tag.strip() for tag in tag_content.split(",")]
                        # Remove the tag part from the line for further processing
                        line = line[:tag_start].strip().rstrip(",").strip()

                if "," in line:
                    # Split by comma
                    parts = line.split(",", 1)  # Split only on first comma
                    model_id = parts[0].strip()
                    display_name = parts[1].strip() if len(parts) > 1 else None
                else:
                    model_id = line

                models.append({"id": model_id, "name": display_name, "tags": tags})
    return models
