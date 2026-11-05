"""Batch lifecycle: API CRUD, the runner's state transitions, restart recovery,
and the 503 the run endpoint returns when the optional ML stack is missing.

The bucket is the in-memory fake; only the DDColor call itself is replaced (its
real inference is exercised at run time with `pnpm setup:ml`, not in verify).
"""

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image

from app.repo import batch_store, ddcolor
from app.service import colorize_runner
from app.types import BatchStatus, ItemStatus

GRAY = "colorization/grayscale/"


def _png(color=128, size=(48, 32)) -> bytes:
    buf = io.BytesIO()
    Image.new("L", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _fake_colorize(img, model_id, input_size, device):
    """Stand-in for DDColor: same size, warm tint (so outputs are real images)."""
    return Image.merge("RGB", (img.getchannel(0), img.getchannel(0).point(lambda v: v // 2), Image.new("L", img.size, 20)))


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr(ddcolor, "ml_available", lambda: True)
    monkeypatch.setattr(ddcolor, "load_model", lambda m, d, **kw: (f"{m}@abc123", "cpu"))
    monkeypatch.setattr(ddcolor, "colorize", _fake_colorize)
    # Run synchronously so the test observes the finished batch.
    monkeypatch.setattr(colorize_runner, "enqueue", colorize_runner.run_batch_now)


@pytest.fixture
def library(fake_s3):
    fake_s3.add(f"{GRAY}street.png", _png(), "image/png")
    fake_s3.add(f"{GRAY}harbour.png", _png(90, (64, 40)), "image/png")
    return fake_s3


async def _create(client, **overrides):
    body = {"name": "Archive box 1", "all_unprocessed": True, "run_now": True, **overrides}
    return await client.post("/batches", json=body)


@pytest.mark.asyncio
async def test_create_and_run_writes_outputs_comparisons_and_manifest(client, library, engine):
    resp = await _create(client)
    assert resp.status_code == 201
    batch_id = resp.json()["batch_id"]

    detail = (await client.get(f"/batches/{batch_id}")).json()
    assert detail["status"] == "done"
    assert detail["done_count"] == 2 and detail["failed_count"] == 0
    assert detail["model_version"] == "ddcolor_artistic@abc123"
    by_key = {i["original_key"]: i for i in detail["items"]}
    item = by_key[f"{GRAY}harbour.png"]
    assert (item["width"], item["height"]) == (64, 40)  # original resolution kept
    assert item["colorized_key"] == f"colorization/colorized/{batch_id}/harbour.jpg"
    assert item["colorized_url"].startswith("https://signed.example/")
    assert item["comparison_key"] in library.objects

    manifest_key = f"colorization/manifests/{batch_id}.csv"
    rows = list(csv.DictReader(io.StringIO(library.objects[manifest_key]["Body"].decode())))
    assert {r["status"] for r in rows} == {"done"}
    assert rows[0]["model_version"] == "ddcolor_artistic@abc123"
    assert detail["derived_bytes"] > 0
    # Originals are untouched.
    assert library.objects[f"{GRAY}street.png"]["Body"] == _png()


@pytest.mark.asyncio
async def test_one_failing_photo_makes_the_batch_partial(client, library, engine):
    library.add(f"{GRAY}broken.png", b"not an image", "image/png")
    batch_id = (await _create(client)).json()["batch_id"]
    detail = (await client.get(f"/batches/{batch_id}")).json()
    assert detail["status"] == "partial"
    failed = [i for i in detail["items"] if i["status"] == "failed"]
    assert len(failed) == 1 and "cannot decode" in failed[0]["error"]


@pytest.mark.asyncio
async def test_run_returns_503_with_install_command_without_ml(client, library, monkeypatch):
    monkeypatch.setattr(ddcolor, "ml_available", lambda: False)
    draft = await _create(client, run_now=False)
    assert draft.status_code == 201 and draft.json()["status"] == "draft"
    resp = await client.post(f"/batches/{draft.json()['batch_id']}/run")
    assert resp.status_code == 503
    assert "pnpm setup:ml" in resp.json()["detail"]
    # Creating with run_now refuses up front instead of saving a dead batch.
    assert (await _create(client)).status_code == 503


def test_ml_available_is_false_in_the_core_venv_or_true_with_the_stack():
    # Answers without importing torch either way; must never raise.
    assert ddcolor.ml_available() in (True, False)


@pytest.mark.asyncio
async def test_edit_changes_only_name_and_description(client, library, engine):
    batch_id = (await _create(client, run_now=False)).json()["batch_id"]
    resp = await client.patch(
        f"/batches/{batch_id}", json={"name": "Box 2", "description": "harbour set"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert (body["name"], body["description"], body["model_id"]) == (
        "Box 2", "harbour set", "ddcolor_artistic",
    )


@pytest.mark.asyncio
async def test_delete_removes_derived_objects_but_keeps_originals(client, library, engine):
    batch_id = (await _create(client)).json()["batch_id"]
    resp = await client.delete(f"/batches/{batch_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted_objects"] == 2 + 2 + 1 + 1  # outputs, comparisons, manifest, record
    assert sorted(library.objects) == [f"{GRAY}harbour.png", f"{GRAY}street.png"]
    assert (await client.get(f"/batches/{batch_id}")).status_code == 404


@pytest.mark.asyncio
async def test_rerun_with_another_model_keeps_both_versions(client, library, engine):
    first = (await _create(client)).json()["batch_id"]
    nothing_left = await _create(client)
    assert nothing_left.status_code == 400  # all already colorized
    second = (
        await _create(
            client, all_unprocessed=False, model_id="ddcolor_paper_tiny",
            source_keys=[f"{GRAY}street.png"],
        )
    ).json()["batch_id"]
    detail = (await client.get("/photos-by-key/detail", params={"key": f"{GRAY}street.png"})).json()
    assert {v["batch_id"] for v in detail["versions"]} == {first, second}
    # The library card names the checkpoint behind the version it shows (the latest).
    cards = {p["key"]: p for p in (await client.get("/photos")).json()["items"]}
    assert cards[f"{GRAY}street.png"]["colorized_model_id"] == "ddcolor_paper_tiny"
    assert cards[f"{GRAY}harbour.png"]["colorized_model_id"] == "ddcolor_artistic"
    stats = (await client.get("/batches/stats")).json()
    assert stats["photos_colorized"] == 2 and stats["batches_total"] == 2
    assert stats["amplification_ratio"] > 1


@pytest.mark.asyncio
async def test_unknown_or_malformed_batch_is_404(client, fake_s3):
    assert (await client.get("/batches/b-20261104-120000-abcdef")).status_code == 404
    assert (await client.get("/batches/..%2F..%2Fsecret")).status_code == 404


@pytest.mark.asyncio
async def test_running_batch_cannot_be_deleted_or_rerun(client, library, monkeypatch):
    monkeypatch.setattr(ddcolor, "ml_available", lambda: True)
    monkeypatch.setattr(colorize_runner, "enqueue", lambda batch_id: None)  # stays queued
    batch_id = (await _create(client)).json()["batch_id"]
    assert (await client.delete(f"/batches/{batch_id}")).status_code == 409
    assert (await client.post(f"/batches/{batch_id}/run")).status_code == 409


def test_restart_marks_stale_running_batches_interrupted(library, monkeypatch):
    from app.service import batches as svc
    from app.types import CreateBatchRequest

    monkeypatch.setattr(colorize_runner, "enqueue", lambda batch_id: None)
    monkeypatch.setattr(ddcolor, "ml_available", lambda: True)
    batch = svc.create_batch(CreateBatchRequest(name="x", all_unprocessed=True))

    def as_if_previous_process(rec):
        rec.status = BatchStatus.running
        rec.items[0].status = ItemStatus.running
        rec.updated_at = datetime.now(UTC) - timedelta(days=1)

    batch_store.mutate(batch.batch_id, as_if_previous_process)
    monkeypatch.setattr(colorize_runner, "_PROCESS_STARTED", datetime.now(UTC))
    assert colorize_runner.recover_interrupted() == 1
    record = batch_store.load(batch.batch_id)
    assert record.status == BatchStatus.interrupted
    assert record.items[0].status == ItemStatus.pending
    # An interrupted batch is re-runnable.
    assert svc.run_batch(batch.batch_id).status == BatchStatus.queued


def test_engine_failure_fails_every_item_and_still_writes_a_manifest(library, monkeypatch):
    from app.service import batches as svc
    from app.types import CreateBatchRequest

    def no_engine(model_id, device, **kw):
        raise ddcolor.EngineUnavailableError("weights unreachable")

    monkeypatch.setattr(ddcolor, "ml_available", lambda: True)
    monkeypatch.setattr(ddcolor, "load_model", no_engine)
    monkeypatch.setattr(colorize_runner, "enqueue", colorize_runner.run_batch_now)
    batch = svc.create_batch(CreateBatchRequest(name="x", all_unprocessed=True))
    record = batch_store.load(batch.batch_id)
    assert record.status == BatchStatus.failed
    assert all(i.error == "weights unreachable" for i in record.items)
    assert record.manifest_key in library.objects


@pytest.mark.parametrize(
    ("pref", "cuda", "mps", "expected"),
    [
        ("auto", True, True, "cuda"),
        ("auto", False, True, "mps"),
        ("auto", False, False, "cpu"),
        ("mps", False, False, "cpu"),  # unavailable choice falls back, never raises
        ("cuda", True, False, "cuda"),
        ("cpu", True, True, "cpu"),
        ("bogus", True, True, "cpu"),
    ],
)
def test_device_selection(pref, cuda, mps, expected):
    assert ddcolor.resolve_device(pref, cuda=cuda, mps=mps) == expected
