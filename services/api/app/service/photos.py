"""Photo Library and dashboard aggregates, scoped to the app's colorization prefix.

The library lists ingested originals (newest first) and joins each one with the
colorized versions recorded in batch records. It is the sample-specific view;
the kit's Bucket Explorer remains the full-bucket view.
"""

from datetime import UTC, datetime

from app.config import settings
from app.repo import batch_store, get_presigned_url
from app.repo.b2_io import list_prefix
from app.service import keys
from app.service.batches import colorized_originals, to_batch
from app.service.files import FileKeyError, FileNotFoundServiceError, validate_key
from app.types import (
    BatchRecord,
    ColorizationStats,
    ItemStatus,
    Photo,
    PhotoDetail,
    PhotoPage,
    PhotoVersion,
)

MAX_PAGE = 200


def _view_url(key: str) -> str:
    return get_presigned_url(
        key, disposition="inline", expires_in=settings.presign_view_expiry_seconds
    )


def _versions_by_original(records: list[BatchRecord]) -> dict[str, list[PhotoVersion]]:
    """Every successful colorized output, grouped by original, newest first."""
    grouped: dict[str, list[PhotoVersion]] = {}
    for record in records:
        for item in record.items:
            if item.status != ItemStatus.done or not item.colorized_key:
                continue
            grouped.setdefault(item.original_key, []).append(
                PhotoVersion(
                    batch_id=record.batch_id,
                    batch_name=record.name,
                    model_id=record.model_id,
                    input_size=record.input_size,
                    colorized_key=item.colorized_key,
                    comparison_key=item.comparison_key,
                    size=item.colorized_bytes or 0,
                    processed_at=item.processed_at,
                    colorized_url="",
                    comparison_url=None,
                    download_url="",
                )
            )
    floor = datetime.min.replace(tzinfo=UTC)
    for versions in grouped.values():
        versions.sort(key=lambda v: v.processed_at or floor, reverse=True)
    return grouped


def _was_color_names() -> set[str]:
    return {keys.filename_of(obj["Key"]) for obj in list_prefix(keys.was_color_prefix())}


def _photo(obj: dict, versions: list[PhotoVersion], flagged: set[str]) -> Photo:
    key = obj["Key"]
    return Photo(
        key=key,
        filename=keys.filename_of(key),
        size=obj["Size"],
        last_modified=obj["LastModified"],
        was_color=keys.filename_of(key) in flagged,
        colorized_versions=len(versions),
        original_url=_view_url(key),
        colorized_url=_view_url(versions[0].colorized_key) if versions else None,
        colorized_model_id=versions[0].model_id if versions else None,
    )


def _originals() -> list[dict]:
    objects = [o for o in list_prefix(keys.grayscale_prefix()) if keys.is_original_key(o["Key"])]
    objects.sort(key=lambda o: (o["LastModified"], o["Key"]), reverse=True)
    return objects


def list_photos(limit: int = 48, cursor: str | None = None) -> PhotoPage:
    """One page of originals. `cursor` is the opaque offset from `next_cursor`."""
    if limit < 1 or limit > MAX_PAGE:
        raise ValueError(f"Limit must be between 1 and {MAX_PAGE}")
    try:
        offset = int(cursor) if cursor else 0
    except ValueError:
        raise ValueError("Invalid cursor") from None
    if offset < 0:
        raise ValueError("Invalid cursor")
    originals = _originals()
    page = originals[offset : offset + limit]
    versions = _versions_by_original(batch_store.list_records())
    flagged = _was_color_names()
    items = [_photo(obj, versions.get(obj["Key"], []), flagged) for obj in page]
    more = offset + limit < len(originals)
    return PhotoPage(items=items, next_cursor=str(offset + limit) if more else None)


def get_photo_detail(key: str) -> PhotoDetail:
    """One original with every colorized version and its presigned URLs."""
    validate_key(key)
    if not keys.is_original_key(key):
        raise FileKeyError("Not a photo in the grayscale library")
    obj = next((o for o in list_prefix(key) if o["Key"] == key), None)
    if obj is None:
        raise FileNotFoundServiceError("Photo not found")
    versions = _versions_by_original(batch_store.list_records()).get(key, [])
    signed = [
        v.model_copy(
            update={
                "colorized_url": _view_url(v.colorized_key),
                "comparison_url": _view_url(v.comparison_key) if v.comparison_key else None,
                "download_url": get_presigned_url(
                    v.colorized_key,
                    filename=f"{keys.stem_of(key)}-{v.model_id.value}{_ext(v.colorized_key)}",
                ),
            }
        )
        for v in versions
    ]
    photo = _photo(obj, versions, _was_color_names())
    return PhotoDetail(**photo.model_dump(), versions=signed)


def _ext(key: str) -> str:
    name = keys.filename_of(key)
    return name[name.rfind(".") :] if "." in name else ""


def amplification_ratio(grayscale_bytes: int, derived_bytes: int) -> float:
    """Stored bytes per ingested byte; 0 before anything is ingested."""
    if grayscale_bytes <= 0:
        return 0.0
    return round((grayscale_bytes + derived_bytes) / grayscale_bytes, 3)


def get_stats(recent: int = 5) -> ColorizationStats:
    """Dashboard aggregates from one listing of the app prefix plus batch records."""
    root = keys.prefix()
    derived_roots = tuple(f"{root}{p}" for p in ("colorized/", "comparisons/", "manifests/"))
    grayscale_count = grayscale_bytes = derived_bytes = 0
    for obj in list_prefix(root):
        if keys.is_original_key(obj["Key"]):
            grayscale_count += 1
            grayscale_bytes += obj["Size"]
        elif obj["Key"].startswith(derived_roots):
            derived_bytes += obj["Size"]
    records = batch_store.list_records()
    return ColorizationStats(
        photos_ingested=grayscale_count,
        photos_colorized=len(colorized_originals(records)),
        batches_total=len(records),
        grayscale_bytes=grayscale_bytes,
        derived_bytes=derived_bytes,
        amplification_ratio=amplification_ratio(grayscale_bytes, derived_bytes),
        recent_batches=[to_batch(r) for r in records[:recent]],
    )
