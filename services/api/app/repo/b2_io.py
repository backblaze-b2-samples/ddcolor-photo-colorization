"""Prefix-scoped object I/O for the colorization pipeline.

Kept apart from `b2_client` (at its size ceiling) but reusing its cached,
user-agent-tagged S3 client, so every call here carries the custom user agent.
Every write and delete invalidates the shared full-bucket listing cache so the
Bucket Explorer never shows a stale view of what the pipeline produced.
"""

from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings
from app.repo.b2_client import get_s3_client
from app.repo.list_cache import invalidate as _invalidate_list_cache

# S3 DeleteObjects accepts at most 1000 keys per request.
_DELETE_CHUNK = 1000


def put_object_bytes(key: str, data: bytes, content_type: str) -> int:
    """Write `data` to `key`. Returns the byte count. Raises RuntimeError on failure."""
    client = get_s3_client()
    try:
        client.put_object(
            Bucket=settings.b2_bucket_name, Key=key, Body=data, ContentType=content_type
        )
    except (ClientError, BotoCoreError) as e:
        raise RuntimeError(f"B2 put_object failed for '{key}': {e}") from e
    _invalidate_list_cache()
    return len(data)


def list_prefix(prefix: str) -> list[dict]:
    """Every object under `prefix` (`Key`, `Size`, `LastModified`, `ETag`).

    Paginates with list_objects_v2. Not cached: the app prefix is small next to
    the whole bucket, and the pipeline needs to see its own writes immediately.
    Raises RuntimeError on failure.
    """
    client = get_s3_client()
    kwargs: dict = {"Bucket": settings.b2_bucket_name, "Prefix": prefix, "MaxKeys": 1000}
    contents: list[dict] = []
    try:
        while True:
            response = client.list_objects_v2(**kwargs)
            contents.extend(response.get("Contents", []))
            if not response.get("IsTruncated"):
                return contents
            kwargs["ContinuationToken"] = response["NextContinuationToken"]
    except (ClientError, BotoCoreError) as e:
        raise RuntimeError(f"B2 list failed for prefix '{prefix}': {e}") from e


def delete_keys(keys: list[str]) -> int:
    """Delete `keys` with batched DeleteObjects. Returns how many were deleted."""
    if not keys:
        return 0
    client = get_s3_client()
    deleted = 0
    try:
        for start in range(0, len(keys), _DELETE_CHUNK):
            chunk = keys[start : start + _DELETE_CHUNK]
            response = client.delete_objects(
                Bucket=settings.b2_bucket_name,
                Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": False},
            )
            errors = response.get("Errors", [])
            if errors:
                first = errors[0]
                raise RuntimeError(
                    f"B2 delete_objects failed for '{first.get('Key')}': {first.get('Message')}"
                )
            deleted += len(response.get("Deleted", []))
    except (ClientError, BotoCoreError) as e:
        raise RuntimeError(f"B2 delete_objects failed: {e}") from e
    finally:
        _invalidate_list_cache()
    return deleted
