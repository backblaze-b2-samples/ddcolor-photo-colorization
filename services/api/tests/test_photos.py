"""Photo Library listing, was_color flags, and the ingest colour check."""

import io

import pytest
from PIL import Image

from app.service import upload as upload_service

GRAY = "colorization/grayscale/"


def _png(mode="L", color=128) -> bytes:
    buf = io.BytesIO()
    Image.new(mode, (40, 30), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_photos_page_lists_originals_only_and_paginates(client, fake_s3):
    for i in range(3):
        fake_s3.add(f"{GRAY}p{i}.png", _png(), "image/png")
    fake_s3.add("colorization/colorized/b-1/p0.jpg", b"x")  # not an original
    fake_s3.add("elsewhere/p9.png", _png())  # outside the app prefix

    first = (await client.get("/photos", params={"limit": 2})).json()
    assert len(first["items"]) == 2 and first["next_cursor"] == "2"
    second = (await client.get("/photos", params={"limit": 2, "cursor": "2"})).json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    keys = {p["key"] for p in first["items"] + second["items"]}
    assert keys == {f"{GRAY}p0.png", f"{GRAY}p1.png", f"{GRAY}p2.png"}
    assert all(p["colorized_versions"] == 0 for p in first["items"])


@pytest.mark.asyncio
async def test_bad_cursor_is_400(client, fake_s3):
    assert (await client.get("/photos", params={"cursor": "abc"})).status_code == 400


def test_check_color_flags_colour_images_only(fake_s3):
    fake_s3.add(f"{GRAY}gray.png", _png(), "image/png")
    fake_s3.add(f"{GRAY}color.png", _png("RGB", (200, 30, 30)), "image/png")
    assert upload_service.check_color(f"{GRAY}gray.png") is False
    assert upload_service.check_color(f"{GRAY}color.png") is True
    assert "colorization/flags/was-color/color.png" in fake_s3.objects
    assert "colorization/flags/was-color/gray.png" not in fake_s3.objects


@pytest.mark.asyncio
async def test_was_color_surfaces_in_the_library(client, fake_s3):
    fake_s3.add(f"{GRAY}color.png", _png("RGB", (200, 30, 30)), "image/png")
    upload_service.check_color(f"{GRAY}color.png")
    detail = (await client.get("/photos-by-key/detail", params={"key": f"{GRAY}color.png"})).json()
    assert detail["was_color"] is True and detail["versions"] == []


@pytest.mark.asyncio
async def test_photo_detail_rejects_keys_outside_the_library(client, fake_s3):
    resp = await client.get("/photos-by-key/detail", params={"key": "elsewhere/a.png"})
    assert resp.status_code == 400
    resp = await client.get("/photos-by-key/detail", params={"key": f"{GRAY}missing.png"})
    assert resp.status_code == 404
