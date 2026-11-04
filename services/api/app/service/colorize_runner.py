"""Background colorization worker: one thread, a FIFO queue, one batch at a time.

DDColor is memory-heavy, so batches never run concurrently. Per photo:
get_object original -> DDColor -> put_object colorized -> optional comparison
put_object -> update the batch record. A failing photo marks only its own item
`failed` (with the error) and the batch continues; the batch ends `done`,
`partial` or `failed`, and the manifest CSV is written after the last item.

Status lives in the batch record in B2, so a restart cannot leave a batch
stuck in `running`: `recover_interrupted()` (called at startup) marks anything
left queued or running as `interrupted`, which the UI offers to re-run.
"""

import logging
import time
from datetime import UTC, datetime
from queue import Queue
from threading import Lock, Thread

from app.config import settings
from app.repo import batch_store, comparison, ddcolor, imaging, manifest
from app.repo.b2_io import put_object_bytes
from app.repo.b2_object import get_object_bytes
from app.service import keys
from app.types import BatchItemRecord, BatchRecord, BatchStatus, ItemStatus

logger = logging.getLogger(__name__)

_queue: Queue[str] = Queue()
_thread: Thread | None = None
_thread_lock = Lock()
# Recovery only touches records last written before this process started, so a
# batch queued by this process while recovery runs is never mislabelled.
_PROCESS_STARTED = datetime.now(UTC)


def enqueue(batch_id: str) -> None:
    """Queue `batch_id` and make sure the single worker thread is running."""
    global _thread
    with _thread_lock:
        if _thread is None or not _thread.is_alive():
            _thread = Thread(target=_worker, name="colorize-runner", daemon=True)
            _thread.start()
    _queue.put(batch_id)


def _worker() -> None:
    while True:
        batch_id = _queue.get()
        try:
            run_batch_now(batch_id)
        except Exception:
            logger.exception("Colorization batch %s crashed", batch_id)
            _mark(batch_id, BatchStatus.failed)
        finally:
            _queue.task_done()


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


def _mark(batch_id: str, status: BatchStatus) -> None:
    def change(rec: BatchRecord) -> None:
        rec.status = status
        rec.finished_at = datetime.now(UTC)
        recount(rec)

    try:
        batch_store.mutate(batch_id, change)
    except RuntimeError:
        logger.exception("Could not persist status %s for batch %s", status, batch_id)


def _set_item(batch_id: str, index: int, item: BatchItemRecord) -> None:
    def change(rec: BatchRecord) -> None:
        rec.items[index] = item
        recount(rec)

    batch_store.mutate(batch_id, change)


def _process(record: BatchRecord, item: BatchItemRecord, targets: tuple[str, str]) -> None:
    """Colorize one photo and write its outputs. Mutates `item`; raises on failure."""
    started = time.perf_counter()
    original = imaging.open_image(
        get_object_bytes(item.original_key), max_pixels=settings.max_photo_pixels
    )
    grayscale = imaging.to_grayscale_rgb(original)
    colorized = ddcolor.colorize(
        grayscale, record.model_id.value, int(record.input_size), settings.ddcolor_device
    )
    data, content_type = imaging.encode(colorized, record.output_format.value)
    colorized_key, comparison_key = targets
    item.colorized_bytes = put_object_bytes(colorized_key, data, content_type)
    item.colorized_key = colorized_key
    if record.make_comparisons:
        caption = f"DDColor {record.model_id.value} @ {int(record.input_size)}"
        composite = comparison.build_comparison(grayscale, colorized, caption)
        item.comparison_bytes = put_object_bytes(comparison_key, composite, "image/jpeg")
        item.comparison_key = comparison_key
    item.width, item.height = colorized.size
    item.duration_ms = round((time.perf_counter() - started) * 1000)


def _manifest_rows(record: BatchRecord) -> list[dict]:
    return [
        {
            "original_key": i.original_key,
            "colorized_key": i.colorized_key,
            "comparison_key": i.comparison_key,
            "model_id": record.model_id.value,
            "model_version": record.model_version,
            "input_size": int(record.input_size),
            "output_format": record.output_format.value,
            "width": i.width,
            "height": i.height,
            "original_bytes": i.original_bytes,
            "colorized_bytes": i.colorized_bytes,
            "duration_ms": i.duration_ms,
            "status": i.status.value,
            "error": i.error,
            "processed_at": i.processed_at,
        }
        for i in record.items
    ]


def run_batch_now(batch_id: str) -> None:
    """Run one queued batch to completion on the calling thread."""
    record = batch_store.load(batch_id)
    if record is None or record.status != BatchStatus.queued:
        return

    engine_error: str | None = None
    try:
        model_version, device = ddcolor.load_model(record.model_id.value, settings.ddcolor_device)
        logger.info("Batch %s: %s on %s", batch_id, model_version, device)
    except ddcolor.EngineUnavailableError as e:
        model_version, engine_error = None, str(e)

    def start(rec: BatchRecord) -> None:
        rec.status = BatchStatus.running
        rec.started_at = datetime.now(UTC)
        rec.finished_at = None
        rec.model_version = model_version
        recount(rec)

    record = batch_store.mutate(batch_id, start)
    if record is None:
        return
    ext = imaging.extension_for(record.output_format.value)
    targets = keys.output_keys(batch_id, [i.original_key for i in record.items], ext)

    for index, stored in enumerate(record.items):
        item = stored.model_copy(update={"status": ItemStatus.running, "error": None})
        if engine_error is None:
            _set_item(batch_id, index, item)
            try:
                _process(record, item, targets[item.original_key])
                item.status = ItemStatus.done
            except Exception as e:
                logger.warning("Batch %s: %s failed: %s", batch_id, item.original_key, e)
                item.status, item.error = ItemStatus.failed, str(e)[:500]
        else:
            item.status, item.error = ItemStatus.failed, engine_error[:500]
        item.processed_at = datetime.now(UTC)
        _set_item(batch_id, index, item)

    record = batch_store.load(batch_id) or record
    body = manifest.build_manifest(_manifest_rows(record))
    manifest_key = keys.manifest_key(batch_id)
    size = put_object_bytes(manifest_key, body, "text/csv")

    def finish(rec: BatchRecord) -> None:
        rec.manifest_key = manifest_key
        recount(rec, manifest_bytes=size)
        rec.status = final_status(rec)
        rec.finished_at = datetime.now(UTC)

    batch_store.mutate(batch_id, finish)


def recover_interrupted() -> int:
    """Mark batches a previous process left queued/running as `interrupted`."""
    recovered = 0
    for record in batch_store.list_records():
        if record.status not in (BatchStatus.queued, BatchStatus.running):
            continue
        if record.updated_at >= _PROCESS_STARTED:
            continue

        def change(rec: BatchRecord) -> None:
            rec.status = BatchStatus.interrupted
            for item in rec.items:
                if item.status == ItemStatus.running:
                    item.status = ItemStatus.pending
            recount(rec)

        batch_store.mutate(record.batch_id, change)
        recovered += 1
    if recovered:
        logger.info("Marked %d batch(es) interrupted after restart", recovered)
    return recovered
