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

                if "," in line:
                    # Split by comma but be careful about tags
                    parts = line.split(",")
                    model_id = parts[0].strip()

                    # Check if there are tags (enclosed in brackets)
                    if len(parts) >= 3 and "[" in parts[-1] and "]" in parts[-1]:
                        # Last part contains tags
                        tag_part = parts[-1].strip()
                        if tag_part.startswith("[") and tag_part.endswith("]"):
                            # Parse tags from [tag1,tag2,...]
                            tag_content = tag_part[1:-1]  # Remove brackets
                            if tag_content:
                                tags = [tag.strip() for tag in tag_content.split(",")]

                        # Everything between first and last comma is display name
                        if len(parts) >= 3:
                            display_name = ",".join(parts[1:-1]).strip()
                        else:
                            display_name = parts[1].strip()
                    else:
                        # No tags, just display name
                        display_name = ",".join(parts[1:]).strip()
                else:
                    model_id = line

                models.append({"id": model_id, "name": display_name, "tags": tags})
    return models
