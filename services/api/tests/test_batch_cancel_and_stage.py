"""Cancel, the model-preparation stage, and the stalled-download watchdog.

The bucket is the in-memory fake; DDColor itself is replaced, and the watchdog
is exercised with a fake `snapshot_download` that never returns.
"""

import io
import threading

import pytest
from PIL import Image

from app.repo import batch_store, ddcolor
from app.service import colorize_runner
from app.types import BatchStage, BatchStatus, ItemStatus

GRAY = "colorization/grayscale/"


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("L", (16, 16), 128).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def library(fake_s3, monkeypatch):
    fake_s3.add(f"{GRAY}a.png", _png(), "image/png")
    fake_s3.add(f"{GRAY}b.png", _png(), "image/png")
    monkeypatch.setattr(ddcolor, "ml_available", lambda: True)
    return fake_s3


async def _create(client):
    body = {"name": "box", "all_unprocessed": True, "run_now": True}
    return (await client.post("/batches", json=body)).json()["batch_id"]


@pytest.mark.asyncio
async def test_queued_batch_can_be_cancelled_then_rerun_or_deleted(client, library, monkeypatch):
    monkeypatch.setattr(colorize_runner, "enqueue", lambda batch_id: None)  # stays queued
    batch_id = await _create(client)
    resp = await client.post(f"/batches/{batch_id}/cancel")
    assert resp.status_code == 200 and resp.json()["status"] == "cancelled"
    # Settled now: cancelling again conflicts; re-run is allowed.
    assert (await client.post(f"/batches/{batch_id}/cancel")).status_code == 409
    assert (await client.post(f"/batches/{batch_id}/run")).json()["status"] == "queued"
    await client.post(f"/batches/{batch_id}/cancel")
    assert (await client.delete(f"/batches/{batch_id}")).status_code == 200


@pytest.mark.asyncio
async def test_worker_skips_a_batch_cancelled_while_queued(client, library, monkeypatch):
    monkeypatch.setattr(colorize_runner, "enqueue", lambda batch_id: None)
    batch_id = await _create(client)
    await client.post(f"/batches/{batch_id}/cancel")
    colorize_runner.run_batch_now(batch_id)
    record = batch_store.load(batch_id)
    assert record.status == BatchStatus.cancelled
    assert all(i.status == ItemStatus.pending for i in record.items)


def test_stage_is_published_and_cancel_stops_the_model_load(library, monkeypatch):
    from app.service import batches as svc
    from app.types import CreateBatchRequest

    seen: list[tuple[BatchStage | None, int | None]] = []

    def load_model(model_id, device, on_progress=None, stall_seconds=0):
        assert on_progress("downloading_model", 1_000) is True
        rec = batch_store.load(batch_id)
        seen.append((rec.stage, rec.model_download_bytes))
        svc.cancel_batch(batch_id)  # the user clicks Cancel mid-download
        if on_progress("downloading_model", 2_000) is False:
            raise ddcolor.LoadCancelled()
        raise AssertionError("cancel was not reported to the loader")

    monkeypatch.setattr(colorize_runner, "enqueue", lambda b: None)
    monkeypatch.setattr(ddcolor, "load_model", load_model)
    batch_id = svc.create_batch(CreateBatchRequest(name="x", all_unprocessed=True)).batch_id
    colorize_runner.run_batch_now(batch_id)
    assert seen == [(BatchStage.downloading_model, 1_000)]
    record = batch_store.load(batch_id)
    assert record.status == BatchStatus.cancelled and record.stage is None


def test_stalled_download_raises_instead_of_hanging(monkeypatch):
    monkeypatch.setattr(ddcolor, "_POLL_SECONDS", 0.01)
    monkeypatch.setattr(ddcolor, "_cache_bytes", lambda repo_id: 42)  # never grows
    never = threading.Event()

    def hung_download(repo_id):
        never.wait()

    try:
        with pytest.raises(ddcolor.EngineUnavailableError, match="stalled"):
            ddcolor._watched_download(hung_download, "piddnad/x", None, stall_seconds=0.05)
    finally:
        never.set()


def test_watched_download_returns_the_snapshot_and_reports_progress(monkeypatch):
    monkeypatch.setattr(ddcolor, "_POLL_SECONDS", 0.01)
    monkeypatch.setattr(ddcolor, "_cache_bytes", lambda repo_id: 7)
    calls = []
    path = ddcolor._watched_download(
        lambda repo_id: f"/cache/{repo_id}/snap", "piddnad/x",
        lambda stage, n: calls.append((stage, n)) or True, stall_seconds=5,
    )
    assert path == "/cache/piddnad/x/snap"
    assert calls[0] == ("downloading_model", 7)


def test_cached_snapshot_skips_the_download_only_when_weights_are_complete(tmp_path):
    snap = tmp_path / "snap"
    snap.mkdir()
    offline = lambda repo_id, local_files_only: str(snap)  # noqa: E731
    assert ddcolor._cached_snapshot(offline, "piddnad/x") is None  # empty snapshot
    (snap / "config.json").write_text("{}")
    assert ddcolor._cached_snapshot(offline, "piddnad/x") is None  # config only
    (snap / "pytorch_model.bin").write_bytes(b"w")
    assert ddcolor._cached_snapshot(offline, "piddnad/x") == str(snap)


def test_cached_snapshot_is_none_when_nothing_is_cached():
    def missing(repo_id, local_files_only):
        raise FileNotFoundError(repo_id)

    assert ddcolor._cached_snapshot(missing, "piddnad/x") is None
