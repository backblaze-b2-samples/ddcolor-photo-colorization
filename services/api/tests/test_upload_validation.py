"""Unit + integration tests for upload validation and content sniffing."""

from datetime import UTC, datetime

import pytest

from app.service import upload as upload_service
from app.service.upload import (
    ALLOWED_TYPES,
    UploadError,
    _validate_declared,
    content_type_has_signature,
    create_presigned_upload,
    matches_content_signature,
    sanitize_filename,
    validate_extension_matches_type,
    verify_upload,
)
from app.types import FileMetadata


def _meta(key: str, *, size_bytes: int, content_type: str) -> FileMetadata:
    filename = key.rsplit("/", 1)[-1]
    return FileMetadata(
        key=key,
        filename=filename,
        folder="colorization/grayscale/",
        size_bytes=size_bytes,
        size_human=f"{size_bytes} B",
        content_type=content_type,
        uploaded_at=datetime(2026, 2, 14, tzinfo=UTC),
        url=None,
    )

# --- sanitize_filename ------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),  # path components stripped
        ("a\x00b.txt", "ab.txt"),  # null byte removed
        ("my file.txt", "my_file.txt"),  # unsafe char substituted
        ("...hidden", "_hidden"),  # dot run collapses to _ before dot-strip
        ("", "unnamed"),  # empty → placeholder
        ("/", "unnamed"),  # only a path separator → placeholder
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "a" * 300 + ".txt",  # long name with extension
        "a" * 300,  # long name, NO extension (regression: was 301 chars + ".")
        "a" * 300 + "." + "b" * 250,  # absurdly long extension
    ],
)
def test_sanitize_filename_truncates_long_names(raw):
    result = sanitize_filename(raw)
    assert len(result) <= 200
    assert not result.startswith(".")


# --- validate_extension_matches_type ----------------------------------------


@pytest.mark.parametrize(
    ("filename", "content_type", "expected"),
    [
        ("photo.jpg", "image/jpeg", True),
        ("photo.jpeg", "image/jpeg", True),
        ("photo.png", "image/jpeg", False),  # extension/type mismatch
        ("noext", "image/jpeg", True),  # no extension → not enforced
        ("x.exe", "image/jpeg", False),
        ("x.pdf", "application/octet-stream", False),  # type not in map
        ("scan.tif", "image/tiff", True),
        ("scan.tiff", "image/tiff", True),
        ("scan.bmp", "image/bmp", True),
        ("scan.webp", "image/webp", True),
        ("scan.tif", "image/png", False),  # extension/type mismatch
    ],
)
def test_validate_extension_matches_type(filename, content_type, expected):
    assert validate_extension_matches_type(filename, content_type) is expected


# --- matches_content_signature ----------------------------------------------

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 8
_TIFF_LE = b"II*\x00" + b"\x00" * 8
_TIFF_BE = b"MM\x00*" + b"\x00" * 8
_BMP = b"BM" + b"\x00" * 8


@pytest.mark.parametrize(
    ("data", "content_type", "expected"),
    [
        (_PNG, "image/png", True),
        (b"<html>not a png", "image/png", False),  # spoofed image
        (_JPEG, "image/jpeg", True),
        (_TIFF_LE, "image/tiff", True),
        (_TIFF_BE, "image/tiff", True),
        (b"nope", "image/tiff", False),
        (_BMP, "image/bmp", True),
        (_PNG, "image/bmp", False),
        (b"{}", "application/json", True),  # not an allowed type: nothing to verify
    ],
)
def test_matches_content_signature(data, content_type, expected):
    assert matches_content_signature(data, content_type) is expected


def test_signature_predicate_agrees_with_checker():
    """`content_type_has_signature` and `matches_content_signature` share one
    source, so every allowed type is classified consistently — this guards the
    verify fast-path that skips the Range-GET for signature-less types."""
    for ct in ALLOWED_TYPES:
        if content_type_has_signature(ct):
            # a real signature rejects an all-zero header
            assert matches_content_signature(b"\x00" * 16, ct) is False
        else:
            # a signature-less type accepts anything
            assert matches_content_signature(b"\x00" * 16, ct) is True


# --- presign-time declared-upload validation --------------------------------


def test_presign_rejects_oversized(monkeypatch):
    monkeypatch.setattr(upload_service.settings, "max_file_size", 10)
    with pytest.raises(UploadError) as exc:
        _validate_declared("a.jpg", "image/jpeg", 999)
    assert exc.value.status_code == 413


def test_presign_rejects_disallowed_type():
    with pytest.raises(UploadError) as exc:
        _validate_declared("a.exe", "application/x-msdownload", 4)
    assert exc.value.status_code == 415


def test_presign_rejects_extension_mismatch():
    with pytest.raises(UploadError) as exc:
        _validate_declared("a.png", "image/jpeg", 4)
    assert exc.value.status_code == 415


def test_presign_rejects_empty_file():
    with pytest.raises(UploadError):
        _validate_declared("a.jpg", "image/jpeg", 0)


def test_presign_returns_signed_put(monkeypatch):
    captured = {}

    def fake_sign(key, content_type, content_length, expires_in):
        captured.update(
            key=key,
            content_type=content_type,
            content_length=content_length,
            expires_in=expires_in,
        )
        return "https://b2.example/signed-put"

    monkeypatch.setattr(upload_service, "generate_presigned_upload", fake_sign)
    result = create_presigned_upload("My Photo.png", "image/png", 1234)

    assert result.key == "colorization/grayscale/My_Photo.png"
    assert result.url == "https://b2.example/signed-put"
    assert result.headers["Content-Type"] == "image/png"
    # The exact size + type are signed in, so B2 enforces them.
    assert captured["content_length"] == 1234
    assert captured["content_type"] == "image/png"


# --- Bulk Ingest is image-only -----------------------------------------------


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [("scan.tif", "image/tiff"), ("scan.bmp", "image/bmp"), ("scan.webp", "image/webp")],
)
def test_presign_accepts_scan_formats(filename, content_type):
    expected = f"colorization/grayscale/{filename}"
    assert _validate_declared(filename, content_type, 16) == expected


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [("doc.pdf", "application/pdf"), ("notes.txt", "text/plain"), ("clip.mp4", "video/mp4")],
)
def test_presign_rejects_non_images(filename, content_type):
    with pytest.raises(UploadError) as exc:
        _validate_declared(filename, content_type, 16)
    assert exc.value.status_code == 415


# --- post-upload verification (HEAD + Range-GET sniff) -----------------------

_PNG_HEAD = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


def _wire_verify(monkeypatch, *, metadata, head_bytes):
    deleted: list[str] = []
    invalidated: list[bool] = []
    monkeypatch.setattr(
        upload_service, "get_file_metadata", lambda key: metadata
    )
    monkeypatch.setattr(
        upload_service, "get_object_head_bytes", lambda key, length: head_bytes
    )
    monkeypatch.setattr(
        upload_service, "delete_file", lambda key: deleted.append(key)
    )
    monkeypatch.setattr(
        upload_service, "invalidate_listing", lambda: invalidated.append(True)
    )
    monkeypatch.setattr(upload_service, "check_color", lambda key: False)
    return deleted, invalidated


def test_verify_accepts_valid_object(monkeypatch):
    meta = _meta("colorization/grayscale/a.png", size_bytes=16, content_type="image/png")
    deleted, invalidated = _wire_verify(
        monkeypatch, metadata=meta, head_bytes=_PNG_HEAD
    )
    result = verify_upload("colorization/grayscale/a.png")
    assert result.key == "colorization/grayscale/a.png"
    assert result.metadata is None  # rich extraction stays on-demand
    assert deleted == []
    assert invalidated == [True]  # new object made visible


def test_verify_rejects_and_deletes_signature_mismatch(monkeypatch):
    meta = _meta("colorization/grayscale/a.png", size_bytes=16, content_type="image/png")
    deleted, _ = _wire_verify(
        monkeypatch, metadata=meta, head_bytes=b"<html>not a png"
    )
    with pytest.raises(UploadError) as exc:
        verify_upload("colorization/grayscale/a.png")
    assert exc.value.status_code == 415
    assert deleted == ["colorization/grayscale/a.png"]  # invalid object removed


def test_verify_rejects_oversize(monkeypatch):
    monkeypatch.setattr(upload_service.settings, "max_file_size", 10)
    meta = _meta("colorization/grayscale/big.jpg", size_bytes=999, content_type="image/jpeg")
    deleted, _ = _wire_verify(monkeypatch, metadata=meta, head_bytes=b"x")
    with pytest.raises(UploadError) as exc:
        verify_upload("colorization/grayscale/big.jpg")
    assert exc.value.status_code == 413
    assert deleted == ["colorization/grayscale/big.jpg"]


def test_verify_missing_object_is_404(monkeypatch):
    deleted, _ = _wire_verify(monkeypatch, metadata=None, head_bytes=b"")
    with pytest.raises(UploadError) as exc:
        verify_upload("colorization/grayscale/gone.txt")
    assert exc.value.status_code == 404
    assert deleted == []  # nothing to delete


def test_verify_rejects_key_outside_uploads_prefix():
    with pytest.raises(UploadError):
        verify_upload("other/evil.txt")


def test_verify_reports_was_color(monkeypatch):
    meta = _meta("colorization/grayscale/a.png", size_bytes=16, content_type="image/png")
    _wire_verify(monkeypatch, metadata=meta, head_bytes=_PNG_HEAD)
    monkeypatch.setattr(upload_service, "check_color", lambda key: True)
    assert verify_upload("colorization/grayscale/a.png").was_color is True


# --- uploads_total metric increments on verify ------------------------------


@pytest.mark.asyncio
async def test_successful_verify_increments_uploads_metric(client, monkeypatch):
    from app.runtime import metrics

    monkeypatch.setattr(metrics, "_upload_count", 0)
    meta = _meta("colorization/grayscale/a.png", size_bytes=16, content_type="image/png")
    _wire_verify(monkeypatch, metadata=meta, head_bytes=_PNG_HEAD)

    resp = await client.post("/upload/verify", json={"key": "colorization/grayscale/a.png"})
    assert resp.status_code == 200

    metrics_resp = await client.get("/metrics")
    assert "uploads_total 1" in metrics_resp.text
