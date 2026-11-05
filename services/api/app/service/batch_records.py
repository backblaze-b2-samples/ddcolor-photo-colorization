"""Batch-record writes for the colorization runner: counters and best-effort persistence.

Split out of `colorize_runner` (file-size ceiling). Every write goes through
`batch_store.mutate`, which is cache-first: the change is visible to readers at
once and the B2 upload follows. Here a failed upload is logged (and optionally
retried) instead of raised, so B2 latency spikes never fail a batch.
"""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from app.repo import batch_store
from app.types import BatchItemRecord, BatchRecord, BatchStage, BatchStatus, ItemStatus

logger = logging.getLogger(__name__)

_RETRY_BACKOFF_SECONDS = 2.0


def recount(record: BatchRecord, manifest_bytes: int = 0) -> None:
    """Recompute the batch's counters from its items."""
    record.photo_count = len(record.items)
    record.done_count = sum(1 for i in record.items if i.status == ItemStatus.done)
    record.failed_count = sum(1 for i in record.items if i.status == ItemStatus.failed)
    record.derived_bytes = manifest_bytes + sum(
        (i.colorized_bytes or 0) + (i.comparison_bytes or 0) for i in record.items
    )
    record.updated_at = datetime.now(UTC)


def final_status(record: BatchRecord) -> BatchStatus:
    if record.done_count and record.failed_count:
        return BatchStatus.partial
    return BatchStatus.done if record.done_count else BatchStatus.failed


def write(
    batch_id: str, change: Callable[[BatchRecord], None], *, persist: bool = True, attempts: int = 1
) -> BatchRecord | None:
    """Apply `change` to the batch record; B2 trouble never aborts the batch.

    The change always lands in the in-process record (what the UI polls and the
    cancel check reads). A failed upload is logged and retried up to `attempts`
    times; if it still fails, the next successful write of this record carries
    it to B2, so one slow PUT cannot fail or freeze the batch.
    """
    applied = False

    def once(rec: BatchRecord) -> None:
        nonlocal applied
        if not applied:  # a retry after a failed upload only re-flushes the cache
            change(rec)
            applied = True

    for attempt in range(1, attempts + 1):
        try:
            return batch_store.mutate(batch_id, once, persist=persist)
        except RuntimeError as e:
            logger.warning("Batch %s: record write %d/%d failed: %s", batch_id, attempt, attempts, e)
            if attempt < attempts:
                time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
    return batch_store.load(batch_id)


def mark(batch_id: str, status: BatchStatus) -> None:
    def change(rec: BatchRecord) -> None:
        rec.status = status
        rec.stage = None
        rec.finished_at = datetime.now(UTC)
        recount(rec)

    write(batch_id, change, attempts=3)


def set_item(batch_id: str, index: int, item: BatchItemRecord, *, persist: bool = True) -> None:
    def change(rec: BatchRecord) -> None:
        rec.items[index] = item
        recount(rec)

    write(batch_id, change, persist=persist)


def set_stage(batch_id: str, stage: BatchStage | None) -> None:
    """Live step for the UI; cache-only, the next persisted write carries it."""

    def change(rec: BatchRecord) -> None:
        if rec.status in (BatchStatus.queued, BatchStatus.running):
            rec.stage = stage

    write(batch_id, change, persist=False)
