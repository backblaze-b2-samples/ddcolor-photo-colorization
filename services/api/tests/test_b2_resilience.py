"""Transient B2 errors on the batch record never fail a download, a photo or a batch.

During B2 latency spikes a PUT of `batches/<id>.json` can time out. The record
is cache-first (readers and the cancel check see changes at once), progress
writes are cache-only, and a failed record upload is logged and healed by the
next successful one. Re-running a partial batch retries only unfinished photos,
and presigned view URLs stay stable across polls.
"""

import io

import pytest
from botocore.exceptions import ReadTimeoutError
from PIL import Image

from app.repo import b2_client, batch_store, ddcolor
from app.service import batch_records, colorize_runner
from app.types import BatchStatus, ItemStatus

GRAY = "colorization/grayscale/"
RECORDS = "colorization/batches/"


def _png(color=128) -> bytes:
    buf = io.BytesIO()
    Image.new("L", (24, 16), color).save(buf, format="PNG")
    return buf.getvalue()


def _fake_colorize(img, model_id, input_size, device):
    return img.convert("RGB")


@pytest.fixture
def engine(fake_s3, monkeypatch):
    fake_s3.add(f"{GRAY}a.png", _png(), "image/png")
    fake_s3.add(f"{GRAY}b.png", _png(90), "image/png")
    monkeypatch.setattr(ddcolor, "ml_available", lambda: True)
    monkeypatch.setattr(ddcolor, "colorize", _fake_colorize)
    monkeypatch.setattr(colorize_runner, "enqueue", lambda batch_id: None)
    monkeypatch.setattr(batch_records, "_RETRY_BACKOFF_SECONDS", 0)
    return fake_s3


def _flaky_record_puts(fake, monkeypatch, fail: set[int]):
    """Make the Nth record PUTs (1-based, counted from now) raise a read timeout."""
    real_put = fake.put_object
    count = {"n": 0}

    def put_object(**kw):
        if kw["Key"].startswith(RECORDS):
            count["n"] += 1
            if count["n"] in fail:
                raise ReadTimeoutError(endpoint_url="https://s3.example/" + kw["Key"])
        return real_put(**kw)

    monkeypatch.setattr(fake, "put_object", put_object)
    return count


def _create(**overrides):
    from app.service import batches as svc
    from app.types import CreateBatchRequest

    req = CreateBatchRequest(name="box", all_unprocessed=True, **overrides)
    return svc.create_batch(req).batch_id


def test_progress_write_failure_never_aborts_the_model_load(engine, monkeypatch):
    def load_model(model_id, device, on_progress=None, stall_seconds=0):
        # The progress callback raising (e.g. a B2 timeout) is swallowed by _report.
        ddcolor._report(lambda s, n: (_ for _ in ()).throw(RuntimeError("B2 timeout")), "x", 1)
        assert on_progress("downloading_model", 5) is True
        return f"{model_id}@rev", "cpu"

    monkeypatch.setattr(ddcolor, "load_model", load_model)
    batch_id = _create()
    colorize_runner.run_batch_now(batch_id)
    record = batch_store.load(batch_id)
    assert record.status == BatchStatus.done and record.done_count == 2


def test_record_put_timeouts_do_not_fail_the_batch(engine, monkeypatch):
    monkeypatch.setattr(ddcolor, "load_model", lambda m, d, **kw: (f"{m}@rev", "cpu"))
    batch_id = _create()
    # Fail the start write once and the first photo's result write.
    _flaky_record_puts(engine, monkeypatch, fail={1, 3})
    colorize_runner.run_batch_now(batch_id)
    record = batch_store.load(batch_id)
    assert record.status == BatchStatus.done
    assert [i.status for i in record.items] == [ItemStatus.done, ItemStatus.done]
    # The healed state reached B2, not only the cache.
    batch_store._reset_cache()
    stored = batch_store.load(batch_id)
    assert stored.status == BatchStatus.done and stored.done_count == 2
    assert stored.manifest_key is not None


def test_mutate_is_visible_before_the_upload_and_survives_its_failure(engine, monkeypatch):
    batch_id = _create(run_now=False)
    _flaky_record_puts(engine, monkeypatch, fail={1})

    def rename(rec):
        rec.name = "renamed"

    with pytest.raises(RuntimeError):
        batch_store.mutate(batch_id, rename)
    assert batch_store.load(batch_id).name == "renamed"  # readers see it now
    batch_store.mutate(batch_id, lambda rec: None)  # next flush heals B2
    batch_store._reset_cache()
    assert batch_store.load(batch_id).name == "renamed"


def test_progress_updates_are_cache_only(engine):
    batch_id = _create(run_now=False)
    before = engine.objects[f"{RECORDS}{batch_id}.json"]["Body"]

    def tick(rec):
        rec.model_download_bytes = 123

    batch_store.mutate(batch_id, tick, persist=False)
    assert batch_store.load(batch_id).model_download_bytes == 123
    assert engine.objects[f"{RECORDS}{batch_id}.json"]["Body"] == before


def test_rerun_of_a_partial_batch_retries_only_unfinished_photos(engine, monkeypatch):
    from app.service import batches as svc

    monkeypatch.setattr(ddcolor, "load_model", lambda m, d, **kw: (f"{m}@rev", "cpu"))
    engine.add(f"{GRAY}broken.png", b"not an image", "image/png")
    batch_id = _create()
    colorize_runner.run_batch_now(batch_id)
    assert batch_store.load(batch_id).status == BatchStatus.partial

    calls: list = []
    monkeypatch.setattr(ddcolor, "colorize", lambda img, *a: calls.append(1) or img.convert("RGB"))
    queued = svc.run_batch(batch_id)
    assert queued.done_count == 2 and queued.status == BatchStatus.queued
    colorize_runner.run_batch_now(batch_id)
    assert calls == []  # the two finished photos were not colorized again
    record = batch_store.load(batch_id)
    assert record.status == BatchStatus.partial and record.done_count == 2


def test_presigned_view_urls_are_stable_across_polls(fake_s3, monkeypatch):
    signed = iter(f"https://signed.example/{n}" for n in range(10))

    class Signer:
        def generate_presigned_url(self, *_a, **_kw):
            return next(signed)

    monkeypatch.setattr(b2_client, "get_s3_client", lambda: Signer())
    first = b2_client.get_presigned_url("k.jpg", disposition="inline", expires_in=3600)
    assert b2_client.get_presigned_url("k.jpg", disposition="inline", expires_in=3600) == first
    assert b2_client.get_presigned_url("other.jpg", disposition="inline", expires_in=3600) != first
