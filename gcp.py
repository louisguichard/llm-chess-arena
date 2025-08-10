"""Google Cloud Storage utilities."""

import json
from google.cloud import storage

GCS_BUCKET_NAME = "llm-chess-arena"


def get_gcs_bucket():
    """Get the GCS bucket."""
    try:
        client = storage.Client()
        return client.get_bucket(GCS_BUCKET_NAME)
    except Exception as e:
        print(f"Error connecting to GCS: {e}")
        return None


def read_json_from_gcs(blob_name):
    """Read a JSON file from GCS."""
    bucket = get_gcs_bucket()
    if not bucket:
        return {}
    blob = bucket.blob(blob_name)
    if not blob.exists():
        return {}
    try:
        json_data = blob.download_as_string()
        return json.loads(json_data)
    except Exception as e:
        print(f"Error reading {blob_name} from GCS: {e}")
        return {}


def write_json_to_gcs(blob_name, data):
    """Write a JSON file to GCS."""
    bucket = get_gcs_bucket()
    if not bucket:
        return
    blob = bucket.blob(blob_name)
    try:
        blob.upload_from_string(
            json.dumps(data, indent=2, ensure_ascii=False),
            content_type="application/json",
        )
        print(f"Successfully wrote to {blob_name} in GCS bucket {GCS_BUCKET_NAME}.")
    except Exception as e:
        print(f"Error writing {blob_name} to GCS: {e}")


def write_file_to_gcs(blob_name, data, content_type="text/plain"):
    """Write a file to GCS."""
    bucket = get_gcs_bucket()
    if not bucket:
        return
    blob = bucket.blob(blob_name)
    try:
        blob.upload_from_string(data, content_type=content_type)
        print(
            f"Successfully wrote file to {blob_name} in GCS bucket {GCS_BUCKET_NAME}."
        )
    except Exception as e:
        print(f"Error writing file {blob_name} to GCS: {e}")
