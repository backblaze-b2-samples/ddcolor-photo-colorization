"""Manifest writer, comparison composite, imaging helpers and the key layout."""

import csv
import io
from datetime import UTC, datetime

import pytest
from PIL import Image

from app.repo import comparison, imaging, manifest
from app.service import keys

# --- manifest -----------------------------------------------------------------


def test_manifest_header_matches_the_documented_columns():
    body = manifest.build_manifest([])
    header = body.decode().splitlines()[0].split(",")
    assert header == [
        "original_key", "colorized_key", "comparison_key", "model_id", "model_version",
        "input_size", "output_format", "width", "height", "original_bytes",
        "colorized_bytes", "duration_ms", "status", "error", "processed_at",
    ]


def test_manifest_row_renders_iso_utc_and_blanks():
    row = {
        "original_key": "colorization/grayscale/a, b.jpg",  # comma must be quoted
        "colorized_key": None,
        "status": "failed",
        "error": "boom",
        "processed_at": datetime(2026, 11, 4, 12, 30, tzinfo=UTC),
    }
    parsed = list(csv.DictReader(io.StringIO(manifest.build_manifest([row]).decode())))
    assert parsed[0]["original_key"] == "colorization/grayscale/a, b.jpg"
    assert parsed[0]["colorized_key"] == ""
    assert parsed[0]["processed_at"] == "2026-11-04T12:30:00Z"


def test_manifest_rejects_unknown_columns():
    with pytest.raises(ValueError):
        manifest.build_manifest([{"not_a_column": 1}])


# --- comparison -----------------------------------------------------------------


def test_comparison_places_panels_side_by_side_with_caption():
    original = Image.new("RGB", (400, 300), (120, 120, 120))
    colorized = Image.new("RGB", (400, 300), (200, 80, 40))
    data = comparison.build_comparison(original, colorized, "DDColor ddcolor_paper_tiny @ 512")
    out = Image.open(io.BytesIO(data))
    assert out.format == "JPEG"
    assert out.size == (400 + comparison.GUTTER + 400, 300 + comparison.CAPTION_HEIGHT)
    left = out.getpixel((50, 50))
    right = out.getpixel((400 + comparison.GUTTER + 50, 50))
    assert abs(left[0] - left[2]) < 10  # grey panel on the left
    assert right[0] - right[2] > 100  # colour panel on the right


def test_comparison_scales_large_panels_down():
    big = Image.new("RGB", (4000, 3000))
    out = Image.open(io.BytesIO(comparison.build_comparison(big, big, "x")))
    assert out.height == comparison.PANEL_MAX_HEIGHT + comparison.CAPTION_HEIGHT


# --- imaging --------------------------------------------------------------------


def _encode(img: Image.Image, fmt: str) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def test_grayscale_scan_is_not_color_and_color_photo_is():
    gray = imaging.open_image(_encode(Image.new("L", (64, 64), 128), "PNG"))
    color = imaging.open_image(_encode(Image.new("RGB", (64, 64), (220, 40, 40)), "PNG"))
    assert imaging.is_color(gray) is False
    assert imaging.is_color(color) is True


def test_sixteen_bit_tiff_decodes_to_rgb():
    img = Image.new("I;16", (32, 16), 40000)
    out = imaging.open_image(_encode(img, "TIFF"))
    assert out.mode == "RGB"
    assert out.size == (32, 16)
    assert 140 < out.getpixel((0, 0))[0] < 170  # 40000/256 ~ 156


def test_pixel_ceiling_and_garbage_raise_decode_error():
    data = _encode(Image.new("L", (100, 100)), "PNG")
    with pytest.raises(imaging.ImageDecodeError):
        imaging.open_image(data, max_pixels=1000)
    with pytest.raises(imaging.ImageDecodeError):
        imaging.open_image(b"not an image")


@pytest.mark.parametrize(("fmt", "ctype"), [("jpeg", "image/jpeg"), ("png", "image/png"), ("webp", "image/webp")])
def test_encode_keeps_dimensions(fmt, ctype):
    data, content_type = imaging.encode(Image.new("RGB", (37, 21), (1, 2, 3)), fmt)
    assert content_type == ctype
    assert Image.open(io.BytesIO(data)).size == (37, 21)


# --- key layout -----------------------------------------------------------------


def test_key_layout_lives_under_the_app_prefix():
    bid = "b-20261104-120000-abcdef"
    assert keys.grayscale_prefix() == "colorization/grayscale/"
    assert keys.colorized_prefix(bid) == f"colorization/colorized/{bid}/"
    assert keys.comparisons_prefix(bid) == f"colorization/comparisons/{bid}/"
    assert keys.manifest_key(bid) == f"colorization/manifests/{bid}.csv"
    assert keys.was_color_key("colorization/grayscale/a.jpg") == "colorization/flags/was-color/a.jpg"


def test_output_keys_are_unique_per_batch_even_for_shared_stems():
    bid = "b-20261104-120000-abcdef"
    out = keys.output_keys(
        bid, ["colorization/grayscale/a.png", "colorization/grayscale/a.tif"], "jpg"
    )
    assert out["colorization/grayscale/a.png"][0] == f"colorization/colorized/{bid}/a.jpg"
    assert out["colorization/grayscale/a.tif"][0] == f"colorization/colorized/{bid}/a-2.jpg"
    assert out["colorization/grayscale/a.tif"][1] == f"colorization/comparisons/{bid}/a-2.jpg"


def test_batch_ids_are_validated():
    assert keys.is_valid_batch_id(keys.new_batch_id())
    assert not keys.is_valid_batch_id("../../etc")
    assert not keys.is_original_key("colorization/grayscale/sub/a.jpg")
    assert keys.is_original_key("colorization/grayscale/a.jpg")
