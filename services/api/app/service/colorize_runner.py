"""Background colorization worker: one thread, a FIFO queue, one batch at a time.

DDColor is memory-heavy, so batches never run concurrently. Per photo:
get_object original -> DDColor -> put_object colorized -> optional comparison
put_object -> update the batch record. A failing photo marks only its own item
`failed` (with the error) and the batch continues; the batch ends `done`,
`partial` or `failed`, and the manifest CSV is written after the last item.

Status lives in the batch record in B2, so a restart cannot leave a batch
stuck in `running`: `recover_interrupted()` (called at startup) marks anything
left queued or running as `interrupted`, which the UI offers to re-run.

While the model downloads or loads (first use of a checkpoint), the batch stays
`queued` with `stage` set and `model_download_bytes` updated every second; while
it runs, `stage` names the current photo's step (reading, colorizing, saving).
These live updates are cache-only: B2 writes of the record are best-effort, so a
slow or failing record PUT never aborts a download, a photo or the batch.
A batch the user cancels (status `cancelled`) stops at the next poll during the
download or before its next photo; remaining items stay `pending`.
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
from app.service import batch_records, keys
from app.service.batch_records import final_status, recount
from app.types import BatchItemRecord, BatchRecord, BatchStage, BatchStatus, ItemStatus

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
            batch_records.mark(batch_id, BatchStatus.failed)
        finally:
            _queue.task_done()


def _process(record: BatchRecord, item: BatchItemRecord, targets: tuple[str, str]) -> None:
    """Colorize one photo and write its outputs. Mutates `item`; raises on failure."""
    batch_id = record.batch_id
    started = time.perf_counter()
    batch_records.set_stage(batch_id, BatchStage.reading_photo)
    original = imaging.open_image(
        get_object_bytes(item.original_key), max_pixels=settings.max_photo_pixels
    )
    grayscale = imaging.to_grayscale_rgb(original)
    batch_records.set_stage(batch_id, BatchStage.colorizing_photo)
    colorized = ddcolor.colorize(
        grayscale, record.model_id.value, int(record.input_size), settings.ddcolor_device
    )
    data, content_type = imaging.encode(colorized, record.output_format.value)
    colorized_key, comparison_key = targets
    batch_records.set_stage(batch_id, BatchStage.saving_result)
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


def _cancelled(batch_id: str) -> bool:
    current = batch_store.load(batch_id)
    return current is None or current.status == BatchStatus.cancelled


def _prepare_engine(record: BatchRecord) -> tuple[str | None, str | None] | None:
    """Load the model, publishing its stage. Returns (version, engine_error); None if cancelled."""
    batch_id = record.batch_id

    def progress(stage: str, downloaded: int | None) -> bool:
        """Publish the model stage (cache-only); False (stop) once the batch is cancelled."""

        def change(rec: BatchRecord) -> None:
            if rec.status == BatchStatus.queued:
                rec.stage = BatchStage(stage)
                if downloaded is not None:
                    rec.model_download_bytes = downloaded
                rec.updated_at = datetime.now(UTC)

        current = batch_records.write(batch_id, change, persist=False)
        return current is not None and current.status == BatchStatus.queued

    progress(BatchStage.preparing_model.value, None)
    try:
        model_version, device = ddcolor.load_model(
            record.model_id.value,
            settings.ddcolor_device,
            on_progress=progress,
            stall_seconds=settings.model_download_stall_seconds,
        )
        logger.info("Batch %s: %s on %s", batch_id, model_version, device)
        return model_version, None
    except ddcolor.LoadCancelled:
        logger.info("Batch %s cancelled while its model was loading", batch_id)
        return None
    except ddcolor.EngineUnavailableError as e:
        return None, str(e)


def run_batch_now(batch_id: str) -> None:
    """Run one queued batch to completion on the calling thread."""
    record = batch_store.load(batch_id)
    if record is None or record.status != BatchStatus.queued:
        return
    prepared = _prepare_engine(record)
    if prepared is None:
        return
    model_version, engine_error = prepared

    def start(rec: BatchRecord) -> None:
        if rec.status != BatchStatus.queued:  # cancelled meanwhile
            return
        rec.status = BatchStatus.running
        rec.stage = None
        rec.started_at = datetime.now(UTC)
        rec.finished_at = None
        rec.model_version = model_version
        recount(rec)

    record = batch_records.write(batch_id, start, attempts=3)
    if record is None or record.status != BatchStatus.running:
        return
    ext = imaging.extension_for(record.output_format.value)
    targets = keys.output_keys(batch_id, [i.original_key for i in record.items], ext)

    for index, stored in enumerate(record.items):
        if _cancelled(batch_id):
            logger.info("Batch %s cancelled; %d photo(s) left pending", batch_id, len(record.items) - index)
            return
        if stored.status == ItemStatus.done:  # kept by a re-run of unfinished photos
            continue
        item = stored.model_copy(update={"status": ItemStatus.running, "error": None})
        if engine_error is None:
            batch_records.set_item(batch_id, index, item, persist=False)
            try:
                _process(record, item, targets[item.original_key])
                item.status = ItemStatus.done
            except Exception as e:
                logger.warning("Batch %s: %s failed: %s", batch_id, item.original_key, e)
                item.status, item.error = ItemStatus.failed, str(e)[:500]
        else:
            item.status, item.error = ItemStatus.failed, engine_error[:500]
        item.processed_at = datetime.now(UTC)
        batch_records.set_item(batch_id, index, item)

    batch_records.set_stage(batch_id, BatchStage.saving_manifest)
    record = batch_store.load(batch_id) or record
    body = manifest.build_manifest(_manifest_rows(record))
    manifest_key: str | None = keys.manifest_key(batch_id)
    try:
        size = put_object_bytes(manifest_key, body, "text/csv")
    except RuntimeError as e:  # outputs are safe in B2; only the CSV is missing
        logger.warning("Batch %s: manifest write failed: %s", batch_id, e)
        manifest_key, size = None, 0

    def finish(rec: BatchRecord) -> None:
        rec.manifest_key = manifest_key
        rec.stage = None
        recount(rec, manifest_bytes=size)
        if rec.status != BatchStatus.cancelled:
            rec.status = final_status(rec)
        rec.finished_at = datetime.now(UTC)

    batch_records.write(batch_id, finish, attempts=3)


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
            rec.stage = None
            for item in rec.items:
                if item.status == ItemStatus.running:
                    item.status = ItemStatus.pending
            recount(rec)

        batch_store.mutate(record.batch_id, change)
        recovered += 1
    if recovered:
        logger.info("Marked %d batch(es) interrupted after restart", recovered)
    return recovered
