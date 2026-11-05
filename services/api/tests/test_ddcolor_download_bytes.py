"""Download progress counts partial (`*.incomplete`) Hub blobs, not only finished files."""

from pathlib import Path

from app.repo import ddcolor


def test_blob_bytes_missing_dir_is_zero(tmp_path: Path):
    assert ddcolor.blob_bytes(tmp_path / "blobs") == 0


def test_blob_bytes_counts_incomplete_and_finished_blobs(tmp_path: Path):
    blobs = tmp_path / "blobs"
    blobs.mkdir()
    (blobs / "abc").write_bytes(b"x" * 100)
    (blobs / "def.incomplete").write_bytes(b"y" * 250)
    (blobs / "subdir").mkdir()
    assert ddcolor.blob_bytes(blobs) == 350
