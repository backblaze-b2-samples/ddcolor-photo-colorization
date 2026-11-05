"""Batch lifecycle: create, read, edit, delete, cancel and (re-)run.

The configuration (model, input size, output format, comparisons) is immutable
after creation because it defines what the outputs and the manifest mean. Only
name and description are editable; to change the model, create a new batch.
"""

from datetime import UTC, datetime

from app.config import settings
from app.repo import batch_store, ddcolor, get_presigned_url
from app.repo.b2_io import list_prefix
from app.service import batch_records, colorize_runner, keys
from app.types import (
    Batch,
    BatchDetail,
    BatchItem,
    BatchItemRecord,
    BatchRecord,
    BatchStatus,
    CreateBatchRequest,
    DeleteBatchResponse,
    ItemStatus,
    UpdateBatchRequest,
)

ACTIVE_STATUSES = (BatchStatus.queued, BatchStatus.running)


class BatchError(Exception):
    """A request the batch service refuses. `status_code` maps it to HTTP."""

    status_code = 400

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class BatchNotFoundError(BatchError):
    status_code = 404


class BatchConflictError(BatchError):
    status_code = 409


class EngineMissingError(BatchError):
    status_code = 503


def to_batch(record: BatchRecord) -> Batch:
    return Batch.model_validate(record.model_dump(exclude={"items", "model_version"}))


def _require(batch_id: str) -> BatchRecord:
    if not keys.is_valid_batch_id(batch_id):
        raise BatchNotFoundError("Batch not found")
    record = batch_store.load(batch_id)
    if record is None:
        raise BatchNotFoundError("Batch not found")
    return record


def _require_engine() -> None:
    if not ddcolor.ml_available():
        raise EngineMissingError(ddcolor.INSTALL_HINT)


def colorized_originals(records: list[BatchRecord]) -> set[str]:
    """Originals that at least one batch colorized successfully."""
    return {i.original_key for r in records for i in r.items if i.status == ItemStatus.done}


def _resolve_sources(req: CreateBatchRequest) -> list[tuple[str, int]]:
    """Return (original_key, size) for the batch, validated against the bucket."""
    listing = {
        obj["Key"]: obj["Size"]
        for obj in list_prefix(keys.grayscale_prefix())
        if keys.is_original_key(obj["Key"])
    }
    if req.all_unprocessed:
        done = colorized_originals(batch_store.list_records())
        chosen = sorted(k for k in listing if k not in done)
        if not chosen:
            raise BatchError("Every ingested photo has already been colorized.")
    else:
        chosen = list(dict.fromkeys(req.source_keys))
        if not chosen:
            raise BatchError("Choose at least one photo, or select all not yet colorized.")
        missing = [k for k in chosen if k not in listing]
        if missing:
            raise BatchError(f"Not an ingested original: {missing[0]}")
    return [(k, listing[k]) for k in chosen]


def create_batch(req: CreateBatchRequest) -> Batch:
    if req.run_now:
        _require_engine()
    sources = _resolve_sources(req)
    now = datetime.now(UTC)
    record = BatchRecord(
        batch_id=keys.new_batch_id(now),
        name=req.name.strip(),
        description=(req.description or "").strip() or None,
        model_id=req.model_id,
        input_size=req.input_size,
        output_format=req.output_format,
        make_comparisons=req.make_comparisons,
        status=BatchStatus.queued if req.run_now else BatchStatus.draft,
        photo_count=len(sources),
        done_count=0,
        failed_count=0,
        original_bytes=sum(size for _, size in sources),
        derived_bytes=0,
        created_at=now,
        updated_at=now,
        items=[BatchItemRecord(original_key=k, original_bytes=size) for k, size in sources],
    )
    batch_store.save(record)
    if req.run_now:
        colorize_runner.enqueue(record.batch_id)
    return to_batch(record)


def list_batches(limit: int = 50) -> list[Batch]:
    if limit < 1 or limit > 500:
        raise BatchError("Limit must be between 1 and 500")
    return [to_batch(r) for r in batch_store.list_records()[:limit]]


def _view_url(key: str | None) -> str | None:
    if not key:
        return None
    return get_presigned_url(
        key, disposition="inline", expires_in=settings.presign_view_expiry_seconds
    )


def get_batch(batch_id: str) -> BatchDetail:
    record = _require(batch_id)
    items = [
        BatchItem(
            **item.model_dump(
                include={
                    "original_key", "colorized_key", "comparison_key", "status",
                    "error", "width", "height", "duration_ms",
                }
            ),
            original_url=_view_url(item.original_key) or "",
            colorized_url=_view_url(item.colorized_key) if item.status == ItemStatus.done else None,
            comparison_url=(
                _view_url(item.comparison_key) if item.status == ItemStatus.done else None
            ),
        )
        for item in record.items
    ]
    return BatchDetail(
        **to_batch(record).model_dump(), model_version=record.model_version, items=items
    )


def update_batch(batch_id: str, req: UpdateBatchRequest) -> Batch:
    _require(batch_id)

    def change(record: BatchRecord) -> None:
        if req.name is not None:
            record.name = req.name.strip()
        if "description" in req.model_fields_set:
            record.description = (req.description or "").strip() or None
        record.updated_at = datetime.now(UTC)

    updated = batch_store.mutate(batch_id, change)
    if updated is None:
        raise BatchNotFoundError("Batch not found")
    return to_batch(updated)


def delete_batch(batch_id: str) -> DeleteBatchResponse:
    """Delete the batch's derived objects and record. Originals are never touched."""
    record = _require(batch_id)
    if record.status in ACTIVE_STATUSES:
        raise BatchConflictError("This batch is queued or running; wait for it to finish.")
    deleted = batch_store.delete_with_prefixes(
        batch_id,
        [keys.colorized_prefix(batch_id), keys.comparisons_prefix(batch_id)],
        [keys.manifest_key(batch_id)],
    )
    return DeleteBatchResponse(batch_id=batch_id, deleted_objects=deleted)


def run_batch(batch_id: str) -> Batch:
    """Queue a draft, or re-run a finished/partial/failed/interrupted/cancelled batch.

    A `done` batch re-runs every photo. Any other settled batch keeps the photos
    it already colorized and re-runs only the failed or unfinished ones. A re-run
    overwrites this batch's own outputs and rewrites its manifest.
    """
    record = _require(batch_id)
    if record.status in ACTIVE_STATUSES:
        raise BatchConflictError("This batch is already queued or running.")
    _require_engine()
    keep_done = record.status != BatchStatus.done

    def reset(rec: BatchRecord) -> None:
        rec.items = [
            i
            if keep_done and i.status == ItemStatus.done
            else BatchItemRecord(original_key=i.original_key, original_bytes=i.original_bytes)
            for i in rec.items
        ]
        rec.status = BatchStatus.queued
        rec.started_at = rec.finished_at = None
        rec.stage, rec.model_download_bytes = None, None
        batch_records.recount(rec)

    updated = batch_store.mutate(batch_id, reset)
    if updated is None:
        raise BatchNotFoundError("Batch not found")
    colorize_runner.enqueue(batch_id)
    return to_batch(updated)


def cancel_batch(batch_id: str) -> Batch:
    """Stop a queued or running batch; the worker moves on at its next check.

    Photos already colorized keep their outputs; the rest stay `pending`, and
    the batch can be re-run or deleted like any settled batch.
    """
    record = _require(batch_id)
    if record.status not in ACTIVE_STATUSES:
        raise BatchConflictError("Only a queued or running batch can be cancelled.")

    def cancel(rec: BatchRecord) -> None:
        if rec.status not in ACTIVE_STATUSES:
            return
        rec.status = BatchStatus.cancelled
        rec.stage = None
        rec.finished_at = datetime.now(UTC)
        batch_records.recount(rec)

    updated = batch_store.mutate(batch_id, cancel)
    if updated is None:
        raise BatchNotFoundError("Batch not found")
    return to_batch(updated)


def manifest_download_url(batch_id: str) -> str:
    record = _require(batch_id)
    if not record.manifest_key:
        raise BatchNotFoundError("This batch has no manifest yet; run it first.")
    return get_presigned_url(record.manifest_key, filename=f"{batch_id}.csv")
