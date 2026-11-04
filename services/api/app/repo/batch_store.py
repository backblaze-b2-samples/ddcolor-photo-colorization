"""Batch records persisted as JSON objects in B2 (B2 is the only store).

One object per batch at `<prefix>batches/<batch_id>.json`. Reads go through a
small in-process cache keyed by the object's ETag, so the batch list, the Photo
Library and the dashboard re-read a record from B2 only when it changed.

`mutate()` is the single write path: a read-modify-write under one lock, used by
both the API (rename) and the background runner (progress), so a rename made
while a batch runs is never overwritten by the runner's next progress write.
"""

import json
from collections.abc import Callable
from threading import RLock

from app.config import settings
from app.repo.b2_io import delete_keys, list_prefix, put_object_bytes
from app.repo.b2_object import get_object_bytes
from app.types import BatchRecord

_lock = RLock()
# batch key -> (etag or "local", record). "local" marks a record this process
# just wrote; it stays authoritative until a listing shows a different ETag.
_cache: dict[str, tuple[str, BatchRecord]] = {}


def records_prefix() -> str:
    return f"{settings.colorization_prefix}batches/"


def record_key(batch_id: str) -> str:
    return f"{records_prefix()}{batch_id}.json"


def _decode(data: bytes) -> BatchRecord:
    return BatchRecord.model_validate(json.loads(data.decode("utf-8")))


def save(record: BatchRecord) -> BatchRecord:
    """Write `record` to B2 and the local cache. Raises RuntimeError on failure."""
    key = record_key(record.batch_id)
    body = record.model_dump_json(indent=2).encode("utf-8")
    with _lock:
        put_object_bytes(key, body, "application/json")
        _cache[key] = ("local", record)
    return record


def load(batch_id: str) -> BatchRecord | None:
    """Return the record for `batch_id`, or None if it does not exist."""
    key = record_key(batch_id)
    with _lock:
        cached = _cache.get(key)
        if cached is not None:
            return cached[1]
    try:
        record = _decode(get_object_bytes(key))
    except RuntimeError as e:
        if "NoSuchKey" in str(e) or "404" in str(e):
            return None
        raise
    with _lock:
        _cache.setdefault(key, ("loaded", record))
    return record


def list_records() -> list[BatchRecord]:
    """Every batch record, newest first. Fetches only records whose ETag changed."""
    objects = list_prefix(records_prefix())
    live = {obj["Key"] for obj in objects}
    records: list[BatchRecord] = []
    for obj in objects:
        key, etag = obj["Key"], obj.get("ETag", "")
        if not key.endswith(".json"):
            continue
        with _lock:
            cached = _cache.get(key)
        if cached is not None and cached[0] in (etag, "local"):
            records.append(cached[1])
            continue
        record = _decode(get_object_bytes(key))
        with _lock:
            _cache[key] = (etag, record)
        records.append(record)
    with _lock:
        for stale in [k for k, (tag, _) in _cache.items() if k not in live and tag != "local"]:
            del _cache[stale]
    records.sort(key=lambda r: r.created_at, reverse=True)
    return records


def mutate(batch_id: str, change: Callable[[BatchRecord], None]) -> BatchRecord | None:
    """Atomically load, apply `change` in place, and save. None if missing."""
    with _lock:
        record = load(batch_id)
        if record is None:
            return None
        updated = record.model_copy(deep=True)
        change(updated)
        return save(updated)


def delete_with_prefixes(batch_id: str, extra_prefixes: list[str], extra_keys: list[str]) -> int:
    """Delete the record plus every object under `extra_prefixes` and `extra_keys`."""
    keys: list[str] = []
    for prefix in extra_prefixes:
        keys.extend(obj["Key"] for obj in list_prefix(prefix))
    existing = {obj["Key"] for key in extra_keys for obj in list_prefix(key) if obj["Key"] == key}
    keys.extend(sorted(existing))
    keys.append(record_key(batch_id))
    with _lock:
        deleted = delete_keys(keys)
        _cache.pop(record_key(batch_id), None)
    return deleted


def _reset_cache() -> None:
    """Test helper."""
    with _lock:
        _cache.clear()
